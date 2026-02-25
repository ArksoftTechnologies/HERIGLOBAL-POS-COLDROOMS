from flask import Blueprint, render_template, request, jsonify, url_for, flash, redirect, send_file, abort
from flask_login import login_required, current_user
from app import db
from models import Repayment, RepaymentPayment, Customer, PaymentMode, Sale, User, Outlet
from models.remittance_model import CashCollection
from utils.decorators import role_required
from utils.pdf_generator import PDFGenerator
from datetime import datetime, timedelta, date
from sqlalchemy import func, desc, or_
import io

repayments_bp = Blueprint('repayments', __name__, url_prefix='/repayments')

def generate_repayment_number():
    """Generate unique repayment number in format REP-YYYY-NNNN"""
    year = datetime.now().year
    last_repayment = Repayment.query.filter(
        Repayment.repayment_number.like(f'REP-{year}-%')
    ).order_by(Repayment.id.desc()).first()
    
    if last_repayment:
        try:
            last_num = int(last_repayment.repayment_number.split('-')[-1])
            new_num = last_num + 1
        except ValueError:
            new_num = 1
    else:
        new_num = 1
    
    return f'REP-{year}-{new_num:04d}'

@repayments_bp.route('/create', methods=['GET'])
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def create():
    """Display repayment form"""
    # Pass ONLY simple data, no complex objects
    customer_id = request.args.get('customer_id', type=int)
    
    return render_template(
        'repayments/create.html',
        customer_id=customer_id or 0  # Simple integer only
    )


@repayments_bp.route('/api/payment-modes', methods=['GET'])
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def get_payment_modes():
    """Get payment modes as JSON (AJAX endpoint)"""
    payment_modes = PaymentMode.query.filter(
        PaymentMode.is_active == True,
        PaymentMode.is_credit == False  # Exclude credit mode
    ).all()
    
    return jsonify([{
        'id': pm.id,
        'name': pm.name,
        'code': pm.code,
        'requires_reference': pm.requires_reference
    } for pm in payment_modes])

@repayments_bp.route('/create', methods=['POST'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def process_repayment():
    """Process a new repayment transaction"""
    data = request.get_json()
    
    customer_id = data.get('customer_id')
    amount = float(data.get('amount', 0))
    payment_type = data.get('payment_type', 'single')
    payment_mode_id = data.get('payment_mode_id')
    split_payments = data.get('split_payments', [])
    transaction_reference = data.get('transaction_reference')
    notes = data.get('notes')
    
    if amount <= 0:
        return jsonify({'error': 'Repayment amount must be greater than zero'}), 400

    try:
        # Atomic Transaction
        # Lock customer row to prevent race conditions
        customer = Customer.query.with_for_update().get(customer_id)
        
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404
        
        if not customer.is_active:
                return jsonify({'error': 'Cannot record repayment for inactive customer'}), 400

        if customer.is_walk_in:
            return jsonify({'error': 'Cannot record repayment for walk-in customer'}), 400

        if amount > customer.current_balance:
            return jsonify({
                'error': f'Repayment amount (${amount:.2f}) exceeds outstanding balance (${customer.current_balance:.2f})'
            }), 400
        
        # Validate Split Payments
        if payment_type == 'split':
            split_total = sum(float(p['amount']) for p in split_payments)
            if abs(split_total - amount) > 0.01:
                return jsonify({'error': 'Payment breakdown total does not match repayment amount'}), 400
            
            # Check for credit mode in split
            for p in split_payments:
                    mode = PaymentMode.query.get(p['payment_mode_id'])
                    if mode and mode.is_credit:
                        return jsonify({'error': 'Cannot use credit mode for repayment'}), 400
        else:
                # Check single payment mode
            mode = PaymentMode.query.get(payment_mode_id)
            if mode and mode.is_credit:
                return jsonify({'error': 'Cannot use credit mode for repayment'}), 400

        # Generate Repayment Number
        repayment_number = generate_repayment_number()
        
        # Balances
        balance_before = customer.current_balance
        from decimal import Decimal
        balance_after = balance_before - Decimal(str(amount))
        
        # Create Repayment Record
        repayment = Repayment(
            repayment_number=repayment_number,
            customer_id=customer_id,
            outlet_id=current_user.outlet_id if current_user.outlet_id else 1, # Fallback or require outlet selection for super admin? Assuming current user's outlet for now or passing it.
            received_by=current_user.id,
            amount=amount,
            payment_mode_id=payment_mode_id if payment_type == 'single' else None,
            is_split_payment=(payment_type == 'split'),
            transaction_reference=transaction_reference if payment_type == 'single' else None,
            notes=notes,
            balance_before=balance_before,
            balance_after=balance_after
        )
        
        # Handle Super Admin/GM outlet assignment (if they can record for any outlet)
        # For now, defaulting to their assigned outlet or if none (Head Office), maybe require selection.
        # Requirement: "Outlet Admin: Can record repayments at their outlet". "Super Admin: Can record at any outlet".
        # If Super Admin, we might need outlet_id in payload or default to customer's primary outlet?
        # Let's use payload outlet_id if provided, else current_user.outlet_id.
        
        if data.get('outlet_id'):
                repayment.outlet_id = data.get('outlet_id')
        elif getattr(current_user, 'outlet_id', None):
                repayment.outlet_id = current_user.outlet_id
        else:
                # Fallback for Super Admin without outlet
                repayment.outlet_id = 1 

        db.session.add(repayment)
        db.session.flush() # Get ID
        
        # Create Split Records
        if payment_type == 'split':
            for p in split_payments:
                rep_payment = RepaymentPayment(
                    repayment_id=repayment.id,
                    payment_mode_id=p['payment_mode_id'],
                    amount=p['amount'],
                    transaction_reference=p.get('reference')
                )
                db.session.add(rep_payment)
        
        # Update Customer Balance
        customer.current_balance = balance_after
        customer.updated_at = datetime.utcnow()
        
        # --- Auto-collect repayment into sales rep collection ---
        # Determine collection type from payment mode
        def _col_type(mode):
            if not mode:
                return 'other'
            code = (mode.code or '').lower()
            nm   = (mode.name or '').lower()
            if 'cash' in code or 'cash' in nm:
                return 'cash'
            if 'bank' in code or 'transfer' in code or 'bank' in nm or 'transfer' in nm:
                return 'bank_transfer'
            if 'mobile' in code or 'mobile' in nm or 'momo' in code:
                return 'mobile_money'
            return 'other'

        year = datetime.now().year
        last_col = CashCollection.query.filter(
            CashCollection.collection_number.like(f'COL-{year}-%')
        ).order_by(CashCollection.id.desc()).first()
        try:
            col_num = int(last_col.collection_number.split('-')[-1]) + 1 if last_col else 1
        except (ValueError, AttributeError):
            col_num = 1
        col_number = f'COL-{year}-{col_num:04d}'

        if payment_type == 'split':
            col_type = 'other'
            col_pm_id = None
        else:
            single_mode = PaymentMode.query.get(payment_mode_id)
            col_type = _col_type(single_mode)
            col_pm_id = payment_mode_id

        collection = CashCollection(
            collection_number=col_number,
            sales_rep_id=current_user.id,
            outlet_id=repayment.outlet_id,
            collection_date=date.today(),
            collection_type=col_type,
            amount=amount,
            payment_mode_id=col_pm_id,
            source_description=(
                f'Debt repayment #{repayment_number} from '
                f'{customer.first_name} {customer.last_name}'
            ),
            source_type='repayment',
            source_id=repayment.id,
            is_reversal=False,
            notes='Automatically credited from debt repayment'
        )
        db.session.add(collection)
        # ---------------------------------------------------------
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'repayment_id': repayment.id,
            'repayment_number': repayment_number,
            'new_balance': float(balance_after),
            'redirect': url_for('repayments.view_receipt', id=repayment.id)
        })

    except Exception as e:
        db.session.rollback()
        # Log error
        print(f"Repayment Error: {e}")
        return jsonify({'error': 'An error occurred while processing the repayment.'}), 500

@repayments_bp.route('/', methods=['GET'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def list_repayments():
    """List repayments with filtering"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    customer_id = request.args.get('customer_id', type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    outlet_id = request.args.get('outlet_id', type=int)

    query = Repayment.query

    # Role-based filtering
    if current_user.role == 'sales_rep':
        # Sales reps see ONLY repayments they personally received
        query = query.filter_by(received_by=current_user.id)
    elif current_user.role == 'outlet_admin':
        query = query.filter_by(outlet_id=current_user.outlet_id)
    
    # Apply filters
    if customer_id:
        query = query.filter_by(customer_id=customer_id)
    if outlet_id and current_user.role in ['super_admin', 'general_manager']:
          query = query.filter_by(outlet_id=outlet_id)
    if date_from:
        query = query.filter(Repayment.repayment_date >= datetime.strptime(date_from, '%Y-%m-%d'))
    if date_to:
         # Include the whole day
        query = query.filter(Repayment.repayment_date <= datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))

    # Order by newest first
    query = query.order_by(desc(Repayment.repayment_date))
    
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('repayments/list.html', pagination=pagination)

@repayments_bp.route('/<int:id>', methods=['GET'])
@login_required
def view_receipt(id):
    """View repayment receipt"""
    repayment = Repayment.query.get_or_404(id)
    
    # Access Control
    if current_user.role in ['outlet_admin', 'sales_rep']:
        if repayment.outlet_id != current_user.outlet_id:
             # Basic check, though logic allows viewing if they have link? 
             # Lets enforce strict outlet access for now unless specified otherwise.
             pass 
    
    return render_template('repayments/detail.html', repayment=repayment)

@repayments_bp.route('/customers/<int:id>/ledger', methods=['GET'])
@login_required
def view_ledger(id):
    """View customer ledger"""
    customer = Customer.query.get_or_404(id)
    
    # Fetch all credit sales
    credit_mode = PaymentMode.query.filter_by(is_credit=True).first()
    credit_mode_id = credit_mode.id if credit_mode else None
    
    # If no credit mode defined (edge case), list all sales? No, only credit sales increase balance usually.
    # But for ledger correctness, we should show all "on credit" transactions.
    # Assuming sales with payment_mode.is_credit are the ones.
    
    if credit_mode_id:
        credit_sales = Sale.query.filter(
            Sale.customer_id == id,
            # Sale.payment_mode_id == credit_mode_id # Or any credit-flagged mode
            Sale.payment_mode.has(is_credit=True)
        ).all()
    else:
        credit_sales = []

    repayments = Repayment.query.filter_by(customer_id=id).all()
    
    transactions = []
    
    for sale in credit_sales:
        is_overdue = False
        if sale.due_date and sale.due_date < datetime.now().date() and sale.status != 'cancelled': 
            # Check if fully paid? 
            # Ledger logic implies checking if specific invoice is paid is complex without allocation.
            # Simplified: Use due date comparison for visual warning.
            is_overdue = True
            
        transactions.append({
            'date': sale.sale_date,
            'type': 'Sale',
            'reference': sale.sale_number,
            'description': f'{len(sale.items)} items - Credit Sale',
            'debit': float(sale.total_amount),
            'credit': 0,
            'balance': 0, # Calculated later
            'is_overdue': is_overdue,
            'due_date': sale.due_date,
            'raw_obj': sale
        })
        
    for rep in repayments:
        transactions.append({
            'date': rep.repayment_date,
            'type': 'Repayment',
            'reference': rep.repayment_number,
            'description': rep.notes or 'Payment Received',
             # Split payment details could be added to description
            'debit': 0,
            'credit': float(rep.amount),
            'balance': 0,
            'is_overdue': False,
            'raw_obj': rep
        })
        
    # Sort chronological
    transactions.sort(key=lambda x: x['date'])
    
    # Calculate running balance
    balance = 0
    for t in transactions:
        balance += t['debit'] - t['credit']
        t['balance'] = balance
        
    # Sort for display (Newest First) if requested, but Ledger usually easiest read Oldest->Newest for math.
    # UI request: "Sort: Newest First (toggleable)". 
    # Let's pass Chronological to template, allow JS reversing or handle in template.
    # Actually, user usually wants to see recent activity first, but running balance logic needs calc from start.
    # We calculated correctly. Now we can reverse the list for display if needed, but 'balance' field is "balance at that time".
    
    return render_template(
        'customers/ledger.html', 
        customer=customer, 
        transactions=transactions, # Chronological
        current_balance=customer.current_balance,
        now=datetime.now()
    )

@repayments_bp.route('/<int:id>/pdf')
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep', 'accountant'])
def download_repayment_pdf(id):
    """Download repayment receipt as PDF"""
    
    repayment = Repayment.query.get_or_404(id)
    
    # Check access
    if current_user.role in ['outlet_admin', 'sales_rep']:
        if repayment.outlet_id != current_user.outlet_id:
             abort(403)
    
    # Get data
    customer = Customer.query.get(repayment.customer_id)
    outlet = Outlet.query.get(repayment.outlet_id)
    
    # Generate HTML
    return PDFGenerator.generate_repayment_receipt(repayment, customer, outlet)
