from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from models import *
from sqlalchemy import func
from utils.decorators import role_required
from datetime import datetime, timedelta

outlets = Blueprint('outlets', __name__)

@outlets.route('/outlets')
@login_required
@role_required(['super_admin', 'general_manager'])
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    status = request.args.get('status', 'all')
    
    query = Outlet.query
    
    # Filter by search term
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Outlet.name.ilike(search_term)) |
            (Outlet.code.ilike(search_term)) |
            (Outlet.city.ilike(search_term))
        )
    
    # Filter by status
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_active=False)
        
    # Pagination
    pagination = query.order_by(Outlet.is_warehouse.desc(), Outlet.name.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('outlets/list.html', outlets=pagination.items, pagination=pagination, search=search, status=status)

@outlets.route('/outlets/create', methods=['GET', 'POST'])
@login_required
@role_required(['super_admin'])
def create_outlet():
    """Create new outlet"""
    
    if request.method == 'GET':
        return render_template('outlets/create.html')
    
    # POST - Create outlet
    try:
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip().upper()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        state = request.form.get('state', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        manager_name = request.form.get('manager_name', '').strip()
        
        # Validation
        if not name or len(name) < 3:
            flash('Outlet name must be at least 3 characters', 'error')
            return redirect(url_for('outlets.create_outlet'))
        
        if not code or len(code) < 2:
            flash('Outlet code must be at least 2 characters', 'error')
            return redirect(url_for('outlets.create_outlet'))
        
        # Check uniqueness
        existing_name = Outlet.query.filter(
            func.lower(Outlet.name) == func.lower(name)
        ).first()
        if existing_name:
            flash('Outlet name already exists', 'error')
            return redirect(url_for('outlets.create_outlet'))
        
        existing_code = Outlet.query.filter_by(code=code).first()
        if existing_code:
            flash('Outlet code already exists', 'error')
            return redirect(url_for('outlets.create_outlet'))
        
        # Create outlet
        outlet = Outlet(
            name=name,
            code=code,
            address=address,
            city=city,
            state=state,
            phone=phone,
            email=email if email else None,
            manager_name=manager_name,
            is_warehouse=False,
            is_active=True
        )
        
        db.session.add(outlet)
        db.session.commit()
        
        flash(f'Outlet {name} created successfully', 'success')
        return redirect(url_for('outlets.index'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating outlet: {str(e)}', 'error')
        return redirect(url_for('outlets.create_outlet'))

@outlets.route('/admin/outlets/<int:id>/manage')
@role_required(['super_admin'])
def manage_outlet(id):
    """Comprehensive outlet management page for Super Admin"""
    from datetime import datetime, timedelta
    
    outlet = Outlet.query.get_or_404(id)
    thirty_days_ago = datetime.now().date() - timedelta(days=30)
    
    # Stats
    outlet_stats = {
        'revenue': db.session.query(func.sum(Sale.total_amount)).filter(
            Sale.outlet_id==id,
            Sale.status=='completed',
            Sale.sale_date >= thirty_days_ago
        ).scalar() or 0,
        'transactions': db.session.query(func.count(Sale.id)).filter(
            Sale.outlet_id==id,
            Sale.status=='completed',
            Sale.sale_date >= thirty_days_ago
        ).scalar() or 0,
        'inventory_value': db.session.query(
            func.sum(Inventory.quantity * Product.cost_price)
        ).join(Product).filter(Inventory.outlet_id==id).scalar() or 0,
        'outstanding_credit': db.session.query(func.sum(Customer.current_balance)).filter(
            Customer.primary_outlet_id==id
        ).scalar() or 0
    }
    
    # Users
    outlet_users = User.query.filter_by(outlet_id=id).all()
    
    # Recent Sales
    recent_sales = Sale.query.filter_by(outlet_id=id, status='completed').order_by(
        Sale.sale_date.desc()
    ).limit(20).all()
    
    # Low Stock
    low_stock_items = Inventory.query.join(Product).filter(
        Inventory.outlet_id == id,
        Inventory.quantity <= Product.reorder_level
    ).all()
    
    # Expenses
    recent_expenses = Expense.query.filter(
        Expense.outlet_id == id,
        Expense.expense_date >= thirty_days_ago
    ).order_by(Expense.expense_date.desc()).limit(20).all()
    
    total_expenses = db.session.query(func.sum(Expense.amount)).filter(
        Expense.outlet_id == id,
        Expense.expense_date >= thirty_days_ago
    ).scalar() or 0
    
    # Remittances
    remittance_data = []
    for user in outlet_users:
        if user.role == 'sales_rep':
            collections = db.session.query(func.sum(CashCollection.amount)).filter_by(
                sales_rep_id=user.id
            ).scalar() or 0
            
            remitted = db.session.query(func.sum(Remittance.amount)).filter_by(
                sales_rep_id=user.id
            ).scalar() or 0
            
            remittance_data.append({
                'name': user.full_name,
                'collections': collections,
                'remitted': remitted,
                'outstanding': collections - remitted
            })
    
    return render_template(
        'admin/outlet_management.html',
        outlet=outlet,
        outlet_stats=outlet_stats,
        outlet_users=outlet_users,
        recent_sales=recent_sales,
        low_stock_items=low_stock_items,
        recent_expenses=recent_expenses,
        total_expenses=total_expenses,
        remittance_data=remittance_data
    )

@outlets.route('/outlets/<int:id>')
@login_required
def detail(id):
    """Comprehensive outlet detail page with full activity metrics"""
    
    # Permission check: Outlet Admin/Sales Rep can only view their own outlet
    if current_user.role in ['outlet_admin', 'sales_rep'] and current_user.outlet_id != id:
        flash('You do not have permission to view this outlet.', 'danger')
        return redirect(url_for('dashboard.index'))
        
    # Permission check for Accountant (read-only access allowed)
    if current_user.role == 'accountant':
        # Accountant can view but with limited actions
        pass

    outlet = Outlet.query.get_or_404(id)
    
    # Date ranges for metrics
    today = datetime.now().date()
    thirty_days_ago = today - timedelta(days=30)
    this_month_start = today.replace(day=1)
    
    # ==================== SALES METRICS ====================
    
    # Today's Sales
    today_sales = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.outlet_id == id,
        Sale.status == 'completed',
        func.date(Sale.sale_date) == today
    ).scalar() or 0
    
    # Today's Transactions Count
    today_transactions = db.session.query(func.count(Sale.id)).filter(
        Sale.outlet_id == id,
        Sale.status == 'completed',
        func.date(Sale.sale_date) == today
    ).scalar() or 0
    
    # This Month's Sales
    month_sales = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.outlet_id == id,
        Sale.status == 'completed',
        Sale.sale_date >= this_month_start
    ).scalar() or 0
    
    # Last 30 Days Sales
    thirty_day_sales = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.outlet_id == id,
        Sale.status == 'completed',
        Sale.sale_date >= thirty_days_ago
    ).scalar() or 0
    
    # Sales by Payment Mode (Last 30 Days)
    sales_by_payment = db.session.query(
        PaymentMode.name,
        PaymentMode.code,
        PaymentMode.is_credit,
        func.sum(Sale.total_amount).label('total'),
        func.count(Sale.id).label('count')
    ).join(Sale.payment_mode).filter(
        Sale.outlet_id == id,
        Sale.status == 'completed',
        Sale.sale_date >= thirty_days_ago
    ).group_by(PaymentMode.id).all()
    
    payment_breakdown = []
    total_credit_sales = 0
    total_cash_sales = 0
    
    for pm_name, pm_code, is_credit, total, count in sales_by_payment:
        payment_breakdown.append({
            'name': pm_name,
            'code': pm_code,
            'is_credit': is_credit,
            'total': float(total),
            'count': count
        })
        
        if is_credit:
            total_credit_sales += float(total)
        else:
            total_cash_sales += float(total)
    
    # ==================== INVENTORY METRICS ====================
    
    # Total Inventory Value (at cost)
    inventory_value = db.session.query(
        func.sum(Inventory.quantity * Product.cost_price)
    ).join(Product, Inventory.product_id == Product.id).filter(
        Inventory.outlet_id == id
    ).scalar() or 0
    
    # Total Inventory Value (at selling price)
    inventory_value_selling = db.session.query(
        func.sum(Inventory.quantity * Product.selling_price)
    ).join(Product, Inventory.product_id == Product.id).filter(
        Inventory.outlet_id == id
    ).scalar() or 0
    
    # Total Products in Stock
    total_products = db.session.query(func.count(Inventory.id)).filter(
        Inventory.outlet_id == id,
        Inventory.quantity > 0
    ).scalar() or 0
    
    # Low Stock Items (below reorder level)
    low_stock_count = db.session.query(func.count(Inventory.id)).join(
        Product, Inventory.product_id == Product.id
    ).filter(
        Inventory.outlet_id == id,
        Product.is_active == True,
        Inventory.quantity <= Product.reorder_level,
        Inventory.quantity > 0
    ).scalar() or 0
    
    # Out of Stock Items
    out_of_stock_count = db.session.query(func.count(Inventory.id)).filter(
        Inventory.outlet_id == id,
        Inventory.quantity == 0
    ).scalar() or 0
    
    # Low Stock Items (for display)
    low_stock_items = db.session.query(
        Product.name,
        Product.sku,
        Inventory.quantity,
        Product.reorder_level
    ).join(Inventory, Product.id == Inventory.product_id).filter(
        Inventory.outlet_id == id,
        Product.is_active == True,
        Inventory.quantity <= Product.reorder_level,
        Inventory.quantity > 0
    ).order_by(Inventory.quantity.asc()).limit(10).all()
    
    # ==================== TRANSFER METRICS ====================
    
    # Pending Incoming Transfers
    pending_incoming = StockTransfer.query.filter(
        StockTransfer.to_outlet_id == id,
        StockTransfer.status.in_(['pending', 'approved'])
    ).count()
    
    # Pending Outgoing Transfers
    pending_outgoing = StockTransfer.query.filter(
        StockTransfer.from_outlet_id == id,
        StockTransfer.status == 'pending'
    ).count()
    
    # Recent Transfers (Last 10)
    recent_transfers = StockTransfer.query.filter(
        db.or_(
            StockTransfer.from_outlet_id == id,
            StockTransfer.to_outlet_id == id
        )
    ).order_by(StockTransfer.requested_at.desc()).limit(10).all()
    
    # ==================== CUSTOMER METRICS ====================
    
    # Total Customers
    total_customers = Customer.query.filter_by(
        primary_outlet_id=id,
        is_active=True
    ).count()
    
    # Outstanding Credit
    outstanding_credit = db.session.query(func.sum(Customer.current_balance)).filter(
        Customer.primary_outlet_id == id,
        Customer.is_active == True
    ).scalar() or 0
    
    # Customers with Outstanding Balance
    customers_with_balance = db.session.query(func.count(Customer.id)).filter(
        Customer.primary_outlet_id == id,
        Customer.is_active == True,
        Customer.current_balance > 0
    ).scalar() or 0
    
    # ==================== RETURNS METRICS ====================
    
    # Total Returns (Last 30 Days) - all methods, for display tile
    total_returns = db.session.query(func.sum(Return.total_refund_amount)).filter(
        Return.outlet_id == id,
        Return.status == 'completed',
        Return.return_date >= thirty_days_ago
    ).scalar() or 0

    # Cash Returns ONLY (non-credit-adjustment) - these actually reduce cash at hand
    cash_returns = db.session.query(func.sum(Return.total_refund_amount)).filter(
        Return.outlet_id == id,
        Return.status == 'completed',
        Return.refund_method != 'credit_adjustment',
        Return.return_date >= thirty_days_ago
    ).scalar() or 0

    # Returns Count
    returns_count = db.session.query(func.count(Return.id)).filter(
        Return.outlet_id == id,
        Return.status == 'completed',
        Return.return_date >= thirty_days_ago
    ).scalar() or 0
    
    # ==================== EXPENSE METRICS ====================
    
    # Total Expenses (Last 30 Days)
    total_expenses = db.session.query(func.sum(Expense.amount)).filter(
        Expense.outlet_id == id,
        Expense.expense_date >= thirty_days_ago
    ).scalar() or 0
    
    # Expenses Count
    expenses_count = db.session.query(func.count(Expense.id)).filter(
        Expense.outlet_id == id,
        Expense.expense_date >= thirty_days_ago
    ).scalar() or 0
    
    # ==================== REMITTANCE METRICS ====================
    
    # Total Collections (Last 30 Days)
    total_collections = db.session.query(func.sum(CashCollection.amount)).filter(
        CashCollection.outlet_id == id,
        CashCollection.collection_date >= thirty_days_ago
    ).scalar() or 0
    
    # Total Remittances (Last 30 Days)
    total_remittances = db.session.query(func.sum(Remittance.amount)).filter(
        Remittance.outlet_id == id,
        Remittance.remittance_date >= thirty_days_ago
    ).scalar() or 0
    
    # Outstanding Remittances
    outstanding_remittances = total_collections - total_remittances
    
    # ==================== RECENT ACTIVITY ====================
    
    # Recent Sales (Last 10)
    recent_sales = Sale.query.filter_by(
        outlet_id=id,
        status='completed'
    ).order_by(Sale.sale_date.desc()).limit(10).all()
    
    # Top Sales Reps (Last 30 Days)
    top_sales_reps = db.session.query(
        User.full_name,
        User.username,
        func.sum(Sale.total_amount).label('total_sales'),
        func.count(Sale.id).label('transaction_count')
    ).join(Sale, User.id == Sale.sales_rep_id).filter(
        Sale.outlet_id == id,
        Sale.status == 'completed',
        Sale.sale_date >= thirty_days_ago
    ).group_by(User.id).order_by(func.sum(Sale.total_amount).desc()).limit(5).all()
    
    # ==================== STAFF METRICS ====================
    
    # Active Staff Count
    active_staff = User.query.filter_by(
        outlet_id=id,
        is_active=True
    ).count()
    
    # Staff by Role
    staff_by_role = db.session.query(
        User.role,
        func.count(User.id).label('count')
    ).filter_by(outlet_id=id, is_active=True).group_by(User.role).all()
    
    # ==================== CALCULATE NET PROFIT (SIMPLIFIED) ====================

    # Net Cash Flow = (Cash Sales - Cash Refunds) - Expenses
    # Credit adjustment returns do NOT reduce physical cash
    net_cash_flow = total_cash_sales - float(cash_returns) - float(total_expenses)
    
    return render_template(
        'outlets/detail.html',
        today = datetime.now(),
        outlet=outlet,
        # Sales metrics
        today_sales=today_sales,
        today_transactions=today_transactions,
        month_sales=month_sales,
        thirty_day_sales=thirty_day_sales,
        payment_breakdown=payment_breakdown,
        total_credit_sales=total_credit_sales,
        total_cash_sales=total_cash_sales,
        # Inventory metrics
        inventory_value=inventory_value,
        inventory_value_selling=inventory_value_selling,
        total_products=total_products,
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        low_stock_items=low_stock_items,
        # Transfer metrics
        pending_incoming=pending_incoming,
        pending_outgoing=pending_outgoing,
        recent_transfers=recent_transfers,
        # Customer metrics
        total_customers=total_customers,
        outstanding_credit=outstanding_credit,
        customers_with_balance=customers_with_balance,
        # Returns metrics
        total_returns=total_returns,
        returns_count=returns_count,
        # Expense metrics
        total_expenses=total_expenses,
        expenses_count=expenses_count,
        # Remittance metrics
        total_collections=total_collections,
        total_remittances=total_remittances,
        outstanding_remittances=outstanding_remittances,
        # Activity
        recent_sales=recent_sales,
        top_sales_reps=top_sales_reps,
        # Staff
        active_staff=active_staff,
        staff_by_role=staff_by_role,
        # Financial
        net_cash_flow=net_cash_flow
    )

@outlets.route('/outlets/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(['super_admin'])
def edit(id):
    outlet = Outlet.query.get_or_404(id)
    
    if request.method == 'POST':
        # Warehouse protection: Cannot change name or code of warehouse
        if outlet.is_warehouse:
            # Only allow updating contact info
             outlet.address = request.form.get('address')
             outlet.city = request.form.get('city')
             outlet.phone = request.form.get('phone')
             outlet.email = request.form.get('email')
             outlet.manager_name = request.form.get('manager_name')
             db.session.commit()
             flash('Warehouse details updated successfully (Name/Code are locked).', 'success')
             return redirect(url_for('outlets.detail', id=outlet.id))

        # Standard Outlet Update
        name = request.form.get('name')
        code = request.form.get('code').upper()
        
        # Check for duplicates if name/code changed
        if name != outlet.name and Outlet.query.filter(Outlet.name.ilike(name)).first():
             flash('Outlet name already exists.', 'danger')
             return render_template('outlets/edit.html', outlet=outlet)
             
        if code != outlet.code and Outlet.query.filter_by(code=code).first():
             flash('Outlet code already exists.', 'danger')
             return render_template('outlets/edit.html', outlet=outlet)

        outlet.name = name
        outlet.code = code
        outlet.address = request.form.get('address')
        outlet.city = request.form.get('city')
        outlet.phone = request.form.get('phone')
        outlet.email = request.form.get('email')
        outlet.manager_name = request.form.get('manager_name')
        
        db.session.commit()
        flash('Outlet updated successfully.', 'success')
        return redirect(url_for('outlets.detail', id=outlet.id))
        
    return render_template('outlets/edit.html', outlet=outlet)

@outlets.route('/outlets/<int:id>/deactivate', methods=['POST'])
@login_required
@role_required(['super_admin'])
def deactivate(id):
    outlet = Outlet.query.get_or_404(id)
    
    if outlet.is_warehouse:
        flash('Central Warehouse cannot be deactivated.', 'danger')
        return redirect(url_for('outlets.detail', id=id))
        
    outlet.is_active = False
    db.session.commit()
    flash('Outlet deactivated successfully.', 'success')
    return redirect(url_for('outlets.index'))

@outlets.route('/outlets/<int:id>/activate', methods=['POST'])
@login_required
@role_required(['super_admin'])
def activate(id):
    outlet = Outlet.query.get_or_404(id)
    outlet.is_active = True
    db.session.commit()
    flash('Outlet activated successfully.', 'success')
    return redirect(url_for('outlets.detail', id=id))
