from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from models import *
from models import Return  # ensure Return is imported for cash return filtering
from sqlalchemy import func
from datetime import datetime, timedelta
from utils.decorators import role_required

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
@login_required
def index():
    """Route to appropriate dashboard based on user role"""
    role = current_user.role
    
    if role == 'super_admin':
        return redirect(url_for('dashboard.super_admin'))
    elif role == 'general_manager':
        return redirect(url_for('dashboard.general_manager'))
    elif role == 'outlet_admin':
        return redirect(url_for('dashboard.outlet_admin'))
    elif role == 'sales_rep':
        return redirect(url_for('dashboard.sales_rep'))
    elif role == 'accountant':
        return redirect(url_for('dashboard.accountant'))
    else:
        return redirect(url_for('auth.login'))


@dashboard_bp.route('/dashboard/super-admin')
@role_required(['super_admin'])
def super_admin():
    """Super Admin Dashboard with real data"""
    
    # Date range: last 30 days
    today = datetime.now().date()
    thirty_days_ago = today - timedelta(days=30)
    
    # Total Revenue (all outlets, last 30 days)
    total_revenue = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.status == 'completed',
        Sale.sale_date >= thirty_days_ago
    ).scalar() or 0
    
    # Total Transactions
    total_transactions = db.session.query(func.count(Sale.id)).filter(
        Sale.status == 'completed',
        Sale.sale_date >= thirty_days_ago
    ).scalar() or 0
    
    # Total Outstanding Credit
    total_outstanding = db.session.query(func.sum(Customer.current_balance)).filter(
        Customer.is_active == True
    ).scalar() or 0
    
    # Total Inventory Value
    inventory_value = db.session.query(
        func.sum(Inventory.quantity * Product.cost_price)
    ).join(Product, Inventory.product_id == Product.id).scalar() or 0
    
    # Total Active Outlets (excluding warehouse)
    total_outlets = Outlet.query.filter(
        Outlet.is_active == True,
        Outlet.is_warehouse == False
    ).count()
    
    # Total Active Users
    total_users = User.query.filter_by(is_active=True).count()
    
    # Total Products
    total_products = Product.query.filter_by(is_active=True).count()
    
    # Total Customers
    total_customers = Customer.query.filter_by(is_active=True).count()
    
    # Expenses (last 30 days)
    total_expenses = db.session.query(func.sum(Expense.amount)).filter(
        Expense.expense_date >= thirty_days_ago
    ).scalar() or 0
    
    # Outstanding Remittances
    total_collections = db.session.query(func.sum(CashCollection.amount)).scalar() or 0
    total_remittances = db.session.query(func.sum(Remittance.amount)).scalar() or 0
    outstanding_remittances = total_collections - total_remittances
    
    # Recent Sales (last 10)
    recent_sales = Sale.query.filter_by(status='completed').order_by(
        Sale.sale_date.desc()
    ).limit(10).all()
    
    # Low Stock Products (across all outlets)
    low_stock_products = db.session.query(
        Product.name,
        Outlet.name.label('outlet_name'),
        Inventory.quantity
    ).join(Inventory, Product.id == Inventory.product_id)\
     .join(Outlet, Inventory.outlet_id == Outlet.id)\
     .filter(
         Product.is_active == True,
         Inventory.quantity <= Product.reorder_level
     ).limit(10).all()
    
    # Outlet Performance (revenue by outlet)
    outlet_performance = db.session.query(
        Outlet.name,
        func.sum(Sale.total_amount).label('revenue'),
        func.count(Sale.id).label('transactions')
    ).join(Sale, Outlet.id == Sale.outlet_id)\
     .filter(
         Sale.status == 'completed',
         Sale.sale_date >= thirty_days_ago,
         Outlet.is_warehouse == False
     ).group_by(Outlet.id).order_by(func.sum(Sale.total_amount).desc()).all()
    
    return render_template(
        'dashboard/super_admin.html',
        total_revenue=total_revenue,
        total_transactions=total_transactions,
        total_outstanding=total_outstanding,
        inventory_value=inventory_value,
        total_outlets=total_outlets,
        total_users=total_users,
        total_products=total_products,
        total_customers=total_customers,
        total_expenses=total_expenses,
        outstanding_remittances=outstanding_remittances,
        recent_sales=recent_sales,
        low_stock_products=low_stock_products,
        outlet_performance=outlet_performance
    )


@dashboard_bp.route('/dashboard/general-manager')
@role_required(['general_manager'])
def general_manager():
    """General Manager Dashboard with real data"""
    
    today = datetime.now().date()
    thirty_days_ago = today - timedelta(days=30)
    
    # Similar to super admin but may have different focus
    total_revenue = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.status == 'completed',
        Sale.sale_date >= thirty_days_ago
    ).scalar() or 0
    
    total_transactions = db.session.query(func.count(Sale.id)).filter(
        Sale.status == 'completed',
        Sale.sale_date >= thirty_days_ago
    ).scalar() or 0
    
    total_outstanding = db.session.query(func.sum(Customer.current_balance)).filter(
        Customer.is_active == True
    ).scalar() or 0

    # Today's revenue and transactions
    today_revenue = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.status == 'completed',
        func.date(Sale.sale_date) == today
    ).scalar() or 0

    today_transactions = db.session.query(func.count(Sale.id)).filter(
        Sale.status == 'completed',
        func.date(Sale.sale_date) == today
    ).scalar() or 0

    # Low stock items across all outlets
    low_stock_count = db.session.query(func.count(Inventory.id)).join(
        Product, Inventory.product_id == Product.id
    ).filter(
        Product.is_active == True,
        Inventory.quantity <= Product.reorder_level
    ).scalar() or 0

    # Per-outlet performance (last 30 days)
    outlet_performance = db.session.query(
        Outlet.name.label('outlet_name'),
        func.count(Sale.id).label('transactions'),
        func.sum(Sale.total_amount).label('revenue')
    ).join(Sale, Outlet.id == Sale.outlet_id)\
     .filter(
        Sale.status == 'completed',
        Sale.sale_date >= thirty_days_ago,
        Outlet.is_warehouse == False
    ).group_by(Outlet.id).order_by(func.sum(Sale.total_amount).desc()).all()

    # Pending Transfers (for approval)
    pending_transfers = StockTransfer.query.filter_by(status='pending').count()
    
    # Recent activity
    recent_sales = Sale.query.filter_by(status='completed').order_by(
        Sale.sale_date.desc()
    ).limit(10).all()
    
    return render_template(
        'dashboard/general_manager.html',
        total_revenue=total_revenue,
        total_transactions=total_transactions,
        today_revenue=today_revenue,
        today_transactions=today_transactions,
        total_outstanding=total_outstanding,
        low_stock_count=low_stock_count,
        outlet_performance=outlet_performance,
        pending_transfers=pending_transfers,
        recent_sales=recent_sales
    )


@dashboard_bp.route('/dashboard/outlet-admin')
@role_required(['outlet_admin'])
def outlet_admin():
    """Outlet Admin Dashboard with real data for their outlet"""
    
    outlet_id = current_user.outlet_id
    today = datetime.now().date()
    thirty_days_ago = today - timedelta(days=30)
    
    # Outlet Revenue
    outlet_revenue = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.outlet_id == outlet_id,
        Sale.status == 'completed',
        Sale.sale_date >= thirty_days_ago
    ).scalar() or 0
    
    # Outlet Transactions
    outlet_transactions = db.session.query(func.count(Sale.id)).filter(
        Sale.outlet_id == outlet_id,
        Sale.status == 'completed',
        Sale.sale_date >= thirty_days_ago
    ).scalar() or 0
    
    # Today's Sales
    today_sales = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.outlet_id == outlet_id,
        Sale.status == 'completed',
        func.date(Sale.sale_date) == today
    ).scalar() or 0
    
    # Inventory Value at this outlet
    outlet_inventory_value = db.session.query(
        func.sum(Inventory.quantity * Product.cost_price)
    ).join(Product, Inventory.product_id == Product.id).filter(
        Inventory.outlet_id == outlet_id
    ).scalar() or 0
    
    # Low Stock at this outlet
    low_stock_count = db.session.query(func.count(Inventory.id)).join(
        Product, Inventory.product_id == Product.id
    ).filter(
        Inventory.outlet_id == outlet_id,
        Product.is_active == True,
        Inventory.quantity <= Product.reorder_level
    ).scalar() or 0
    
    # Outstanding Credit (customers at this outlet)
    outlet_outstanding = db.session.query(func.sum(Customer.current_balance)).filter(
        Customer.primary_outlet_id == outlet_id,
        Customer.is_active == True
    ).scalar() or 0
    
    # Recent Sales
    recent_sales = Sale.query.filter_by(
        outlet_id=outlet_id,
        status='completed'
    ).order_by(Sale.sale_date.desc()).limit(10).all()
    
    # Pending Stock Transfers (incoming)
    pending_transfers = StockTransfer.query.filter_by(
        to_outlet_id=outlet_id,
        status='approved'
    ).count()
    
    return render_template(
        'dashboard/outlet_admin.html',
        outlet_revenue=outlet_revenue,
        outlet_transactions=outlet_transactions,
        today_sales=today_sales,
        outlet_inventory_value=outlet_inventory_value,
        low_stock_count=low_stock_count,
        outlet_outstanding=outlet_outstanding,
        recent_sales=recent_sales,
        pending_transfers=pending_transfers
    )


@dashboard_bp.route('/dashboard/sales-rep')
@role_required(['sales_rep'])
def sales_rep():
    """Sales Rep Dashboard with their personal metrics"""
    
    user_id = current_user.id
    outlet_id = current_user.outlet_id
    today = datetime.now().date()
    # today = today - timedelta(days=1)
    thirty_days_ago = today - timedelta(days=30)
    
    # My Sales (last 30 days)
    my_sales = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.sales_rep_id == user_id,
        Sale.status == 'completed',
        Sale.sale_date >= thirty_days_ago
    ).scalar() or 0
    
    # My Transactions
    my_transactions = db.session.query(func.count(Sale.id)).filter(
        Sale.sales_rep_id == user_id,
        Sale.status == 'completed',
        Sale.sale_date >= thirty_days_ago
    ).scalar() or 0
    
    # Today's Sales (Total)
    today_sales = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.sales_rep_id == user_id,
        Sale.status == 'completed',
        func.date(Sale.sale_date) == today
    ).scalar() or 0
    
    # Today's Sales Breakdown by Payment Mode (INCLUDING SPLIT PAYMENTS)
    today_sales_breakdown = db.session.query(
        PaymentMode.name,
        PaymentMode.code,
        PaymentMode.is_credit,
        func.sum(Sale.total_amount).label('total'),
        func.count(Sale.id).label('count')
    ).join(Sale.payment_mode).filter(
        Sale.sales_rep_id == user_id,
        Sale.status == 'completed',
        func.date(Sale.sale_date) == today,
        Sale.payment_mode_id.isnot(None)  # Only non-split payments
    ).group_by(PaymentMode.id).all()
    
    # Get split payment sales separately
    split_sales_total = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.sales_rep_id == user_id,
        Sale.status == 'completed',
        func.date(Sale.sale_date) == today,
        Sale.is_split_payment == True
    ).scalar() or 0
    
    split_sales_count = db.session.query(func.count(Sale.id)).filter(
        Sale.sales_rep_id == user_id,
        Sale.status == 'completed',
        func.date(Sale.sale_date) == today,
        Sale.is_split_payment == True
    ).scalar() or 0
    
    # Format breakdown for template
    payment_breakdown = []
    today_credit_sales = 0
    today_cash_sales = 0
    
    for pm_name, pm_code, is_credit, total, count in today_sales_breakdown:
        payment_breakdown.append({
            'name': pm_name,
            'code': pm_code,
            'is_credit': is_credit,
            'total': float(total),
            'count': count
        })
        
        if is_credit:
            today_credit_sales += float(total)
        else:
            today_cash_sales += float(total)
    
    # Add split payment to breakdown if exists
    if split_sales_count > 0:
        payment_breakdown.append({
            'name': 'Split Payment',
            'code': 'SPLIT',
            'is_credit': False,  # Split payments are treated as cash for balance calculation
            'total': float(split_sales_total),
            'count': split_sales_count
        })
        today_cash_sales += float(split_sales_total)
    
    # Today's Returns — split by refund method
    # Cash/physical returns ONLY (reduce actual cash in hand)
    today_cash_returns = db.session.query(func.sum(Return.total_refund_amount)).join(
        Sale, Return.sale_id == Sale.id
    ).filter(
        Sale.sales_rep_id == user_id,
        Return.status == 'completed',
        Return.refund_method != 'credit_adjustment',  # credit adj does NOT affect cash
        func.date(Return.return_date) == today
    ).scalar() or 0

    # Credit-adjustment returns (do NOT reduce cash — only adjust customer balance)
    today_credit_returns = db.session.query(func.sum(Return.total_refund_amount)).join(
        Sale, Return.sale_id == Sale.id
    ).filter(
        Sale.sales_rep_id == user_id,
        Return.status == 'completed',
        Return.refund_method == 'credit_adjustment',
        func.date(Return.return_date) == today
    ).scalar() or 0

    today_returns = today_cash_returns + today_credit_returns  # total for display

    # Real Cash Balance: only deduct cash returns, not credit adjustments
    real_cash_balance = today_cash_sales - float(today_cash_returns)
    
    # My Outstanding Remittances
    my_collections = db.session.query(func.sum(CashCollection.amount)).filter_by(
        sales_rep_id=user_id
    ).scalar() or 0
    
    my_remittances = db.session.query(func.sum(Remittance.amount)).filter_by(
        sales_rep_id=user_id
    ).scalar() or 0
    
    my_outstanding = my_collections - my_remittances
    
    # My Recent Sales (TODAY ONLY - FIXED)
    my_recent_sales = Sale.query.filter(
        Sale.sales_rep_id == user_id,
        Sale.status == 'completed',
        func.date(Sale.sale_date) == today
    ).order_by(Sale.sale_date.desc()).limit(10).all()
    
    # Quick Actions Count
    customers_count = Customer.query.filter_by(
        primary_outlet_id=outlet_id,
        is_active=True
    ).count()
    
    # Get outlet information
    outlet = Outlet.query.get(outlet_id)
    
    return render_template(
        'dashboard/sales_rep.html',
        outlet=outlet,
        my_sales=my_sales,
        my_transactions=my_transactions,
        today_sales=today_sales,
        today_credit_sales=today_credit_sales,
        today_cash_sales=today_cash_sales,
        payment_breakdown=payment_breakdown,
        today_returns=today_returns,
        real_cash_balance=real_cash_balance,
        my_outstanding=my_outstanding,
        my_recent_sales=my_recent_sales,
        customers_count=customers_count
    )

# @dashboard_bp.route('/dashboard/sales-rep')
# @role_required(['sales_rep'])
# def sales_rep():
#     """Sales Rep Dashboard with their personal metrics"""
    
#     user_id = current_user.id
#     outlet_id = current_user.outlet_id
#     today = datetime.now().date()
#     thirty_days_ago = today - timedelta(days=30)
    
#     # My Sales (last 30 days)
#     my_sales = db.session.query(func.sum(Sale.total_amount)).filter(
#         Sale.sales_rep_id == user_id,
#         Sale.status == 'completed',
#         Sale.sale_date >= thirty_days_ago
#     ).scalar() or 0
    
#     # My Transactions
#     my_transactions = db.session.query(func.count(Sale.id)).filter(
#         Sale.sales_rep_id == user_id,
#         Sale.status == 'completed',
#         Sale.sale_date >= thirty_days_ago
#     ).scalar() or 0
    
#     # Today's Sales (Total)
#     today_sales = db.session.query(func.sum(Sale.total_amount)).filter(
#         Sale.sales_rep_id == user_id,
#         Sale.status == 'completed',
#         func.date(Sale.sale_date) == today
#     ).scalar() or 0
    
#     # Today's Sales Breakdown by Payment Mode
#     today_sales_breakdown = db.session.query(
#         PaymentMode.name,
#         PaymentMode.code,
#         PaymentMode.is_credit,
#         func.sum(Sale.total_amount).label('total'),
#         func.count(Sale.id).label('count')
#     ).join(Sale.payment_mode).filter(
#         Sale.sales_rep_id == user_id,
#         Sale.status == 'completed',
#         func.date(Sale.sale_date) == today
#     ).group_by(PaymentMode.id).all()
    
#     # Format breakdown for template
#     payment_breakdown = []
#     today_credit_sales = 0
#     today_cash_sales = 0
    
#     for pm_name, pm_code, is_credit, total, count in today_sales_breakdown:
#         payment_breakdown.append({
#             'name': pm_name,
#             'code': pm_code,
#             'is_credit': is_credit,
#             'total': float(total),
#             'count': count
#         })
        
#         if is_credit:
#             today_credit_sales += float(total)
#         else:
#             today_cash_sales += float(total)
    
#     # Today's Returns (Total)
#     today_returns = db.session.query(func.sum(Return.total_refund_amount)).join(
#         Sale, Return.sale_id == Sale.id
#     ).filter(
#         Sale.sales_rep_id == user_id,
#         Return.status == 'completed',
#         func.date(Return.return_date) == today
#     ).scalar() or 0
    
#     # Real Cash Balance (Cash sales - Returns)
#     # This represents actual cash collected today minus refunds
#     real_cash_balance = today_cash_sales - float(today_returns)
    
#     # My Outstanding Remittances
#     my_collections = db.session.query(func.sum(CashCollection.amount)).filter_by(
#         sales_rep_id=user_id
#     ).scalar() or 0
    
#     my_remittances = db.session.query(func.sum(Remittance.amount)).filter_by(
#         sales_rep_id=user_id
#     ).scalar() or 0
    
#     my_outstanding = my_collections - my_remittances
    
#     # My Recent Sales (for the transactions table)
#     my_recent_sales = Sale.query.filter_by(
#         sales_rep_id=user_id,
#         status='completed'
#     ).order_by(Sale.sale_date.desc()).limit(10).all()
    
#     # Quick Actions Count
#     customers_count = Customer.query.filter_by(
#         primary_outlet_id=outlet_id,
#         is_active=True
#     ).count()
    
#     # Get outlet information
#     outlet = Outlet.query.get(outlet_id)
    
#     return render_template(
#         'dashboard/sales_rep.html',
#         outlet=outlet,
#         my_sales=my_sales,
#         my_transactions=my_transactions,
#         today_sales=today_sales,
#         today_credit_sales=today_credit_sales,
#         today_cash_sales=today_cash_sales,
#         payment_breakdown=payment_breakdown,
#         today_returns=today_returns,
#         real_cash_balance=real_cash_balance,
#         my_outstanding=my_outstanding,
#         my_recent_sales=my_recent_sales,
#         customers_count=customers_count
#     )


@dashboard_bp.route('/dashboard/accountant')
@role_required(['accountant'])
def accountant():
    """Accountant Dashboard with financial overview"""
    
    today = datetime.now().date()
    thirty_days_ago = today - timedelta(days=30)
    
    # Total Revenue
    total_revenue = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.status == 'completed',
        Sale.sale_date >= thirty_days_ago
    ).scalar() or 0
    
    # Total Expenses
    total_expenses = db.session.query(func.sum(Expense.amount)).filter(
        Expense.expense_date >= thirty_days_ago
    ).scalar() or 0
    
    # Outstanding Credit
    total_outstanding = db.session.query(func.sum(Customer.current_balance)).filter(
        Customer.is_active == True
    ).scalar() or 0
    
    # Total Collections
    total_collections = db.session.query(func.sum(CashCollection.amount)).filter(
        CashCollection.collection_date >= thirty_days_ago
    ).scalar() or 0
    
    # Total Remittances
    total_remittances = db.session.query(func.sum(Remittance.amount)).filter(
        Remittance.remittance_date >= thirty_days_ago
    ).scalar() or 0
    
    # Payment Mode Breakdown
    payment_breakdown = db.session.query(
        func.sum(Sale.total_amount).label('total'),
        func.count(Sale.id).label('count')
    ).filter(
        Sale.status == 'completed',
        Sale.sale_date >= thirty_days_ago
    ).first()
    
    return render_template(
        'dashboard/accountant.html',
        total_revenue=total_revenue,
        total_expenses=total_expenses,
        total_outstanding=total_outstanding,
        total_collections=total_collections,
        total_remittances=total_remittances
    )
