from flask import Blueprint, render_template, request, jsonify, url_for, flash, redirect, current_app, send_file, abort
from flask_login import login_required, current_user
from app import db
from models.remittance_model import CashCollection, Remittance
from models.outlet import Outlet
from models.user import User
from models.payment import PaymentMode
from datetime import datetime, date, timedelta
from sqlalchemy import func, desc
from functools import wraps
from utils.pdf_generator import PDFGenerator
import io

remittance_bp = Blueprint('remittance', __name__, url_prefix='/remittance')

def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                flash('Access denied. You do not have permission to view this page.', 'error')
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def generate_collection_number():
    """Generate unique collection number in format COL-YYYY-NNNN"""
    year = datetime.now().year
    last_collection = CashCollection.query.filter(
        CashCollection.collection_number.like(f'COL-{year}-%')
    ).order_by(CashCollection.id.desc()).first()
    
    if last_collection:
        try:
            last_num = int(last_collection.collection_number.split('-')[-1])
            new_num = last_num + 1
        except ValueError:
            new_num = 1
    else:
        new_num = 1
    
    return f'COL-{year}-{new_num:04d}'

def generate_remittance_number():
    """Generate unique remittance number in format REM-YYYY-NNNN"""
    year = datetime.now().year
    last_remittance = Remittance.query.filter(
        Remittance.remittance_number.like(f'REM-{year}-%')
    ).order_by(Remittance.id.desc()).first()
    
    if last_remittance:
        try:
            last_num = int(last_remittance.remittance_number.split('-')[-1])
            new_num = last_num + 1
        except ValueError:
            new_num = 1
    else:
        new_num = 1
    
    return f'REM-{year}-{new_num:04d}'

@remittance_bp.route('/', methods=['GET'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep', 'accountant'])
def index():
    """Remittance Dashboard"""
    # --- Outlet filter (super_admin / general_manager only) ---
    outlets = []
    selected_outlet_id = None
    if current_user.role in ['super_admin', 'general_manager']:
        outlets = Outlet.query.order_by(Outlet.name).all()
        selected_outlet_id = request.args.get('outlet_id', type=int)  # None = all outlets

    total_collections = 0
    total_remittances = 0
    outstanding_balance = 0
    
    query_col = db.session.query(func.sum(CashCollection.amount))
    query_col_rev = db.session.query(func.sum(CashCollection.amount))
    query_rem = db.session.query(func.sum(Remittance.amount))
    
    if current_user.role == 'sales_rep':
        query_col = query_col.filter(
            CashCollection.sales_rep_id == current_user.id,
            CashCollection.is_reversal == False
        )
        query_col_rev = query_col_rev.filter(
            CashCollection.sales_rep_id == current_user.id,
            CashCollection.is_reversal == True
        )
        query_rem = query_rem.filter(Remittance.sales_rep_id == current_user.id)
    elif current_user.role == 'outlet_admin':
        query_col = query_col.filter(
            CashCollection.outlet_id == current_user.outlet_id,
            CashCollection.is_reversal == False
        )
        query_col_rev = query_col_rev.filter(
            CashCollection.outlet_id == current_user.outlet_id,
            CashCollection.is_reversal == True
        )
        query_rem = query_rem.filter(Remittance.outlet_id == current_user.outlet_id)
    else:
        # super_admin / general_manager: optionally filter by outlet
        query_col = query_col.filter(CashCollection.is_reversal == False)
        query_col_rev = query_col_rev.filter(CashCollection.is_reversal == True)
        if selected_outlet_id:
            query_col = query_col.filter(CashCollection.outlet_id == selected_outlet_id)
            query_col_rev = query_col_rev.filter(CashCollection.outlet_id == selected_outlet_id)
            query_rem = query_rem.filter(Remittance.outlet_id == selected_outlet_id)
        
    total_collections = (query_col.scalar() or 0) - (query_col_rev.scalar() or 0)
    total_remittances = query_rem.scalar() or 0
    outstanding_balance = max(0, total_collections - total_remittances)
    
    # Recent Activity
    recent_collections = CashCollection.query
    recent_remittances = Remittance.query
    
    if current_user.role == 'sales_rep':
        recent_collections = recent_collections.filter_by(sales_rep_id=current_user.id)
        recent_remittances = recent_remittances.filter_by(sales_rep_id=current_user.id)
    elif current_user.role == 'outlet_admin':
        recent_collections = recent_collections.filter_by(outlet_id=current_user.outlet_id)
        recent_remittances = recent_remittances.filter_by(outlet_id=current_user.outlet_id)
    else:
        # super_admin / general_manager outlet filter
        if selected_outlet_id:
            recent_collections = recent_collections.filter_by(outlet_id=selected_outlet_id)
            recent_remittances = recent_remittances.filter_by(outlet_id=selected_outlet_id)
        
    recent_collections = recent_collections.order_by(CashCollection.collection_date.desc()).limit(5).all()
    recent_remittances = recent_remittances.order_by(Remittance.remittance_date.desc()).limit(5).all()

    return render_template('remittance/dashboard.html',
                           total_collections=total_collections,
                           total_remittances=total_remittances,
                           outstanding_balance=outstanding_balance,
                           recent_collections=recent_collections,
                           recent_remittances=recent_remittances,
                           outlets=outlets,
                           selected_outlet_id=selected_outlet_id)

@remittance_bp.route('/collections/declare', methods=['GET', 'POST'])
@login_required
@role_required(['sales_rep', 'outlet_admin', 'super_admin'])
def declare_collection():
    """Declare cash collection"""
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Validation
            amount = float(data.get('amount', 0))
            if amount <= 0:
                raise ValueError("Amount must be greater than zero")
            if amount > 10000000:
                 raise ValueError("Amount exceeds maximum allowed (₦10,000,000)")

            collection_date_str = data.get('collection_date')
            collection_date = datetime.strptime(collection_date_str, '%Y-%m-%d').date()
            if collection_date > date.today():
                raise ValueError("Collection date cannot be in the future")
            if (date.today() - collection_date).days > 30:
                raise ValueError("Collection date cannot be more than 30 days ago")
                
            source_description = data.get('source_description', '').strip()
            if len(source_description) < 10:
                raise ValueError("Source description must be at least 10 characters")
                
            # Determine sales rep and outlet
            if current_user.role == 'sales_rep':
                sales_rep_id = current_user.id
                outlet_id = current_user.outlet_id
            else:
                sales_rep_id = data.get('sales_rep_id') or current_user.id
                outlet_id = data.get('outlet_id') or current_user.outlet_id
                
            collection_number = generate_collection_number()
            
            collection = CashCollection(
                collection_number=collection_number,
                sales_rep_id=sales_rep_id,
                outlet_id=outlet_id,
                collection_date=collection_date,
                collection_type=data.get('collection_type'),
                amount=amount,
                payment_mode_id=data.get('payment_mode_id'),
                transaction_reference=data.get('transaction_reference'),
                source_description=source_description,
                notes=data.get('notes')
            )
            
            db.session.add(collection)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Collection declared successfully. #{collection_number}',
                'redirect': url_for('remittance.collection_detail', id=collection.id)
            })
            
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Collection declaration failed: {e}")
            return jsonify({'error': 'Failed to declare collection'}), 500

    # GET request
    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
    # For admins to select rep
    sales_reps = []
    if current_user.role in ['outlet_admin', 'super_admin']:
        sales_reps = User.query.filter_by(role='sales_rep').all()
        if current_user.role == 'outlet_admin':
            sales_reps = [u for u in sales_reps if u.outlet_id == current_user.outlet_id]
            
    return render_template('remittance/declare_collection.html',
                           payment_modes=payment_modes,
                           sales_reps=sales_reps,
                           today=date.today())

@remittance_bp.route('/remittances/record', methods=['GET', 'POST'])
@login_required
@role_required(['sales_rep', 'outlet_admin', 'super_admin'])
def record_remittance():
    """Record remittance to company"""
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Validation
            amount = float(data.get('amount', 0))
            if amount <= 0:
                raise ValueError("Amount must be greater than zero")
                
            remittance_date_str = data.get('remittance_date')
            remittance_date = datetime.strptime(remittance_date_str, '%Y-%m-%d').date()
            if remittance_date > date.today():
                raise ValueError("Remittance date cannot be in the future")
                
            remittance_method = data.get('remittance_method')
            bank_name = data.get('bank_name')
            transaction_reference = data.get('transaction_reference')
            
            if remittance_method == 'bank_transfer' and (not bank_name or not transaction_reference):
                raise ValueError("Bank name and transaction reference required for bank transfer")
                
             # Determine sales rep and outlet
            if current_user.role == 'sales_rep':
                sales_rep_id = current_user.id
                outlet_id = current_user.outlet_id
            else:
                sales_rep_id = data.get('sales_rep_id') or current_user.id
                outlet_id = data.get('outlet_id') or current_user.outlet_id

            # Validate that they are not remitting more than they collected
            total_col = db.session.query(func.sum(CashCollection.amount)).filter_by(sales_rep_id=sales_rep_id, is_reversal=False).scalar() or 0
            total_col_rev = db.session.query(func.sum(CashCollection.amount)).filter_by(sales_rep_id=sales_rep_id, is_reversal=True).scalar() or 0
            total_rem = db.session.query(func.sum(Remittance.amount)).filter_by(sales_rep_id=sales_rep_id).scalar() or 0
            cur_outstanding = max(0, (total_col - total_col_rev) - total_rem)
            
            if amount > cur_outstanding:
                raise ValueError(f"Cannot remit more than collected amount. Outstanding is ₦{cur_outstanding:,.2f}")

            remittance_number = generate_remittance_number()
            
            remittance = Remittance(
                remittance_number=remittance_number,
                sales_rep_id=sales_rep_id,
                outlet_id=outlet_id,
                remittance_date=remittance_date,
                amount=amount,
                remittance_method=remittance_method,
                payment_mode_id=data.get('payment_mode_id'),
                bank_name=bank_name,
                account_number=data.get('account_number'),
                transaction_reference=transaction_reference,
                notes=data.get('notes'),
                status='recorded'
            )
            
            db.session.add(remittance)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Remittance recorded successfully. #{remittance_number}',
                'redirect': url_for('remittance.remittance_detail', id=remittance.id)
            })
            
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Remittance recording failed: {e}")
            return jsonify({'error': 'Failed to record remittance'}), 500

    # GET request
    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
    
    # Calculate outstanding balance for current user
    outstanding_balance = 0
    if current_user.role == 'sales_rep':
        total_col = db.session.query(func.sum(CashCollection.amount)).filter_by(sales_rep_id=current_user.id, is_reversal=False).scalar() or 0
        total_col_rev = db.session.query(func.sum(CashCollection.amount)).filter_by(sales_rep_id=current_user.id, is_reversal=True).scalar() or 0
        total_rem = db.session.query(func.sum(Remittance.amount)).filter_by(sales_rep_id=current_user.id).scalar() or 0
        outstanding_balance = max(0, (total_col - total_col_rev) - total_rem)

    return render_template('remittance/record_remittance.html',
                           payment_modes=payment_modes,
                           outstanding_balance=outstanding_balance,
                           today=date.today())

@remittance_bp.route('/collections', methods=['GET'])
@login_required
def collections_list():
    """List cash collections"""
    page = request.args.get('page', 1, type=int)
    
    query = CashCollection.query.order_by(CashCollection.collection_date.desc())
    
    # Role scoping (untouched)
    if current_user.role == 'sales_rep':
        query = query.filter_by(sales_rep_id=current_user.id)
    elif current_user.role == 'outlet_admin':
        query = query.filter_by(outlet_id=current_user.outlet_id)
    
    # Outlet filter for super_admin / general_manager
    outlets = []
    selected_outlet_id = None
    if current_user.role in ['super_admin', 'general_manager']:
        outlets = Outlet.query.order_by(Outlet.name).all()
        selected_outlet_id = request.args.get('outlet_id', type=int)
        if selected_outlet_id:
            query = query.filter_by(outlet_id=selected_outlet_id)
        
    collections = query.paginate(page=page, per_page=20, error_out=False)
    
    return render_template(
        'remittance/collections.html',
        collections=collections,
        outlets=outlets,
        selected_outlet_id=selected_outlet_id
    )

@remittance_bp.route('/remittances', methods=['GET'])
@login_required
def remittances_list():
    """List remittances"""
    page = request.args.get('page', 1, type=int)
    
    query = Remittance.query.order_by(Remittance.remittance_date.desc())
    
    # Role scoping (untouched)
    if current_user.role == 'sales_rep':
        query = query.filter_by(sales_rep_id=current_user.id)
    elif current_user.role == 'outlet_admin':
        query = query.filter_by(outlet_id=current_user.outlet_id)
    
    # Outlet filter for super_admin / general_manager
    outlets = []
    selected_outlet_id = None
    if current_user.role in ['super_admin', 'general_manager']:
        outlets = Outlet.query.order_by(Outlet.name).all()
        selected_outlet_id = request.args.get('outlet_id', type=int)
        if selected_outlet_id:
            query = query.filter_by(outlet_id=selected_outlet_id)
        
    remittances = query.paginate(page=page, per_page=20, error_out=False)
    
    return render_template(
        'remittance/remittances.html',
        remittances=remittances,
        outlets=outlets,
        selected_outlet_id=selected_outlet_id
    )

@remittance_bp.route('/collections/<int:id>', methods=['GET'])
@login_required
def collection_detail(id):
    """View collection detail"""
    collection = CashCollection.query.get_or_404(id)
    
    if current_user.role == 'sales_rep' and collection.sales_rep_id != current_user.id:
        flash("Access denied", "error")
        return redirect(url_for('remittance.index'))
    elif current_user.role == 'outlet_admin' and collection.outlet_id != current_user.outlet_id:
        flash("Access denied", "error")
        return redirect(url_for('remittance.index'))
        
    return render_template('remittance/collection_detail.html', collection=collection)

@remittance_bp.route('/remittances/<int:id>', methods=['GET'])
@login_required
def remittance_detail(id):
    """View remittance detail"""
    remittance = Remittance.query.get_or_404(id)
    
    if current_user.role == 'sales_rep' and remittance.sales_rep_id != current_user.id:
        flash("Access denied", "error")
        return redirect(url_for('remittance.index'))
    elif current_user.role == 'outlet_admin' and remittance.outlet_id != current_user.outlet_id:
        flash("Access denied", "error")
        return redirect(url_for('remittance.index'))
        
    return render_template('remittance/remittance_detail.html', remittance=remittance)

@remittance_bp.route('/ledger', methods=['GET'])
@login_required
def ledger():
    """View ledger details"""
    sales_rep_id = request.args.get('sales_rep_id', type=int) or current_user.id
    
    if current_user.role == 'sales_rep':
        sales_rep_id = current_user.id
    
    # Determine date range
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    # Fetch collections
    col_query = CashCollection.query.filter_by(sales_rep_id=sales_rep_id)
    if date_from:
        col_query = col_query.filter(CashCollection.collection_date >= date_from)
    if date_to:
        col_query = col_query.filter(CashCollection.collection_date <= date_to)
    collections = col_query.all()
    
    # Fetch remittances
    rem_query = Remittance.query.filter_by(sales_rep_id=sales_rep_id)
    if date_from:
        rem_query = rem_query.filter(Remittance.remittance_date >= date_from)
    if date_to:
        rem_query = rem_query.filter(Remittance.remittance_date <= date_to)
    remittances = rem_query.all()
    
    # Combine and sort
    transactions = []
    for col in collections:
        if col.is_reversal:
            # Show reversal as a negative / debit entry
            transactions.append({
                'date': col.collection_date,
                'type': 'Return Reversal',
                'reference': col.collection_number,
                'description': col.source_description or 'Return reversal',
                'collection': -float(col.amount),   # negative — debits the balance
                'remittance': 0
            })
        else:
            transactions.append({
                'date': col.collection_date,
                'type': 'Collection',
                'reference': col.collection_number,
                'description': col.source_description,
                'collection': float(col.amount),
                'remittance': 0
            })
        
    for rem in remittances:
        transactions.append({
            'date': rem.remittance_date,
            'type': 'Remittance',
            'reference': rem.remittance_number,
            'description': f"{rem.remittance_method} - {rem.transaction_reference}",
            'collection': 0,
            'remittance': float(rem.amount)
        })
        
    transactions.sort(key=lambda x: x['date'])
    
    # Calculate running balance
    balance = 0
    for txn in transactions:
        balance += txn['collection'] - txn['remittance']
        txn['balance'] = balance
        
    sales_rep = User.query.get(sales_rep_id)
    
    return render_template('remittance/ledger.html', transactions=transactions, sales_rep=sales_rep)

@remittance_bp.route('/outstanding', methods=['GET'])
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'accountant'])
def outstanding():
    """Outstanding balances report"""

    # Outlet filter for super_admin / general_manager
    outlets = []
    selected_outlet_id = None
    if current_user.role in ['super_admin', 'general_manager']:
        outlets = Outlet.query.order_by(Outlet.name).all()
        selected_outlet_id = request.args.get('outlet_id', type=int)

    sales_reps = User.query.filter_by(role='sales_rep').all()
    if current_user.role == 'outlet_admin':
        sales_reps = [u for u in sales_reps if u.outlet_id == current_user.outlet_id]
    elif selected_outlet_id:
        # super_admin filtering by a specific outlet
        sales_reps = [u for u in sales_reps if u.outlet_id == selected_outlet_id]

    report_data = []
    total_outstanding = 0
    
    for rep in sales_reps:
        total_col = (
            db.session.query(func.sum(CashCollection.amount))
            .filter_by(sales_rep_id=rep.id, is_reversal=False).scalar() or 0
        )
        total_col_rev = (
            db.session.query(func.sum(CashCollection.amount))
            .filter_by(sales_rep_id=rep.id, is_reversal=True).scalar() or 0
        )
        net_collections = total_col - total_col_rev
        total_rem = (
            db.session.query(func.sum(Remittance.amount))
            .filter_by(sales_rep_id=rep.id).scalar() or 0
        )
        outstanding = max(0, net_collections - total_rem)
        
        last_remittance = Remittance.query.filter_by(sales_rep_id=rep.id).order_by(Remittance.remittance_date.desc()).first()
        days_overdue = 0
        if last_remittance:
            days_overdue = (date.today() - last_remittance.remittance_date).days
        else:
             first_collection = CashCollection.query.filter_by(sales_rep_id=rep.id, is_reversal=False).order_by(CashCollection.collection_date.asc()).first()
             if first_collection:
                 days_overdue = (date.today() - first_collection.collection_date).days
        
        report_data.append({
            'sales_rep': rep,
            'total_collections': net_collections,
            'total_remittances': total_rem,
            'outstanding': outstanding,
            'last_remittance_date': last_remittance.remittance_date if last_remittance else None,
            'days_overdue': days_overdue
        })
        total_outstanding += outstanding
        
    return render_template(
        'remittance/outstanding.html',
        report_data=report_data,
        total_outstanding=total_outstanding,
        outlets=outlets,
        selected_outlet_id=selected_outlet_id
    )

@remittance_bp.route('/collections/<int:id>/pdf')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep', 'accountant'])
def download_collection_pdf(id):
    """Download collection declaration as PDF"""
    
    collection = CashCollection.query.get_or_404(id)
    
    # Check access
    if current_user.role == 'sales_rep' and collection.sales_rep_id != current_user.id:
        abort(403)
    elif current_user.role == 'outlet_admin' and collection.outlet_id != current_user.outlet_id:
        abort(403)
    
    # Get outlet
    outlet = Outlet.query.get(collection.outlet_id)
    
    # Generate HTML
    return PDFGenerator.generate_collection_receipt(collection, outlet)

@remittance_bp.route('/remittances/<int:id>/pdf')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep', 'accountant'])
def download_remittance_pdf(id):
    """Download remittance record as PDF"""
    
    remittance = Remittance.query.get_or_404(id)
    
    # Check access
    if current_user.role == 'sales_rep' and remittance.sales_rep_id != current_user.id:
        abort(403)
    elif current_user.role == 'outlet_admin' and remittance.outlet_id != current_user.outlet_id:
        abort(403)
    
    # Get outlet
    outlet = Outlet.query.get(remittance.outlet_id)
    
    # Generate HTML
    return PDFGenerator.generate_remittance_receipt_pdf(remittance, outlet)
