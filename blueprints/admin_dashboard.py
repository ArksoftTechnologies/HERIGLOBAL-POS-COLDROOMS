from datetime import datetime, timedelta, date
from flask import Blueprint, render_template, request, jsonify, url_for
from flask_login import login_required, current_user
from sqlalchemy import func, desc, or_
from models import db, User, Outlet, Product, Sale, SaleItem, Customer, Inventory, Expense, CashCollection, Remittance
from utils.decorators import role_required

admin_dashboard_bp = Blueprint('admin_dashboard', __name__, url_prefix='/admin/dashboard')

def get_previous_period_revenue(date_from, date_to):
    """Calculate revenue for equivalent previous period"""
    if not date_from or not date_to:
        return 0
    
    period_length = (date_to - date_from).days
    previous_start = date_from - timedelta(days=period_length)
    previous_end = date_from - timedelta(days=1)
    
    previous_revenue = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.status == 'completed',
        Sale.sale_date >= previous_start,
        Sale.sale_date <= previous_end
    ).scalar() or 0
    
    return previous_revenue

def calculate_growth_rate(current, previous):
    """Calculate percentage growth rate"""
    if previous == 0:
        return 100 if current > 0 else 0
    
    return ((current - previous) / previous) * 100

def get_outlet_previous_revenue(outlet_id, date_from, date_to):
    """Get outlet revenue for previous equivalent period"""
    if not date_from or not date_to:
        return 0
    
    period_length = (date_to - date_from).days
    previous_start = date_from - timedelta(days=period_length)
    previous_end = date_from - timedelta(days=1)
    
    previous_revenue = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.outlet_id == outlet_id,
        Sale.status == 'completed',
        Sale.sale_date >= previous_start,
        Sale.sale_date <= previous_end
    ).scalar() or 0
    
    return previous_revenue

@admin_dashboard_bp.route('/')
@login_required
@role_required(['super_admin', 'general_manager'])
def index():
    """Super Admin Consolidated Dashboard"""
    total_users = User.query.filter_by(is_active=True).count()
    total_outlets = Outlet.query.filter_by(is_active=True, is_warehouse=False).count()
    return render_template(
        'admin/dashboard.html',
        total_users=total_users,
        total_outlets=total_outlets
    )

@admin_dashboard_bp.route('/api/summary')
@login_required
@role_required(['super_admin', 'general_manager'])
def api_summary():
    """API Endpoint for Executive Summary Data"""
    date_from_str = request.args.get('date_from')
    date_to_str = request.args.get('date_to')
    
    today = datetime.now().date()
    # Default to current month if not specified
    if not date_from_str:
        date_from = today.replace(day=1)
    else:
        date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
        
    if not date_to_str:
        date_to = today
    else:
        date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()

    # Total Revenue
    revenue_query = db.session.query(func.sum(Sale.total_amount)).filter(Sale.status == 'completed')
    if date_from: revenue_query = revenue_query.filter(func.date(Sale.sale_date) >= date_from)
    if date_to: revenue_query = revenue_query.filter(func.date(Sale.sale_date) <= date_to)
    total_revenue = revenue_query.scalar() or 0
    
    # Transactions
    transactions_query = db.session.query(func.count(Sale.id)).filter(Sale.status == 'completed')
    if date_from: transactions_query = transactions_query.filter(func.date(Sale.sale_date) >= date_from)
    if date_to: transactions_query = transactions_query.filter(func.date(Sale.sale_date) <= date_to)
    total_transactions = transactions_query.scalar() or 0
    
    # Outstanding Credit (Current snapshot)
    total_outstanding = db.session.query(func.sum(Customer.current_balance)).filter(Customer.is_active == True).scalar() or 0
    
    # Inventory Value (Current snapshot)
    inventory_value = db.session.query(func.sum(Inventory.quantity * Product.cost_price)).join(Product, Inventory.product_id == Product.id).scalar() or 0
    
    # Expenses
    expenses_query = db.session.query(func.sum(Expense.amount))
    if date_from: expenses_query = expenses_query.filter(func.date(Expense.expense_date) >= date_from)
    if date_to: expenses_query = expenses_query.filter(func.date(Expense.expense_date) <= date_to)
    total_expenses = expenses_query.scalar() or 0
    
    # Collections & Remittances
    col_query = db.session.query(func.sum(CashCollection.amount))
    rem_query = db.session.query(func.sum(Remittance.amount))
    
    if date_from:
        col_query = col_query.filter(CashCollection.collection_date >= date_from)
        rem_query = rem_query.filter(Remittance.remittance_date >= date_from)
    if date_to:
        col_query = col_query.filter(CashCollection.collection_date <= date_to)
        rem_query = rem_query.filter(Remittance.remittance_date <= date_to)
        
    total_collections = col_query.scalar() or 0
    total_remittances = rem_query.scalar() or 0
    
    avg_transaction = (total_revenue / total_transactions) if total_transactions > 0 else 0
    
    # Growth
    prev_revenue = get_previous_period_revenue(date_from, date_to)
    revenue_growth = calculate_growth_rate(total_revenue, prev_revenue)
    
    return jsonify({
        'total_revenue': float(total_revenue),
        'total_transactions': total_transactions,
        'avg_transaction_value': float(avg_transaction),
        'total_outstanding_credit': float(total_outstanding),
        'total_inventory_value': float(inventory_value),
        'total_expenses': float(total_expenses),
        'total_collections': float(total_collections),
        'total_remittances': float(total_remittances),
        'net_cash_position': float(total_collections - total_remittances),
        'revenue_growth': revenue_growth,
        'net_profit_estimate': float(total_revenue - total_expenses)
    })

@admin_dashboard_bp.route('/api/outlets')
@login_required
@role_required(['super_admin', 'general_manager'])
def api_outlets():
    """API Endpoint for Outlet Performance"""
    # Simply using last 30 days default for comparison if no dates provided
    today = datetime.now().date()
    date_from = today - timedelta(days=30)
    date_to = today
    
    outlets = Outlet.query.filter(Outlet.is_active == True, Outlet.is_warehouse == False).all()
    performance_data = []
    
    for outlet in outlets:
        revenue = db.session.query(func.sum(Sale.total_amount)).filter(
            Sale.outlet_id == outlet.id,
            Sale.status == 'completed',
            func.date(Sale.sale_date) >= date_from,
            func.date(Sale.sale_date) <= date_to
        ).scalar() or 0
        
        transactions = db.session.query(func.count(Sale.id)).filter(
            Sale.outlet_id == outlet.id,
            Sale.status == 'completed',
            func.date(Sale.sale_date) >= date_from,
            func.date(Sale.sale_date) <= date_to
        ).scalar() or 0
        
        expenses = db.session.query(func.sum(Expense.amount)).filter(
            Expense.outlet_id == outlet.id,
            func.date(Expense.expense_date) >= date_from,
            func.date(Expense.expense_date) <= date_to
        ).scalar() or 0
        
        inventory_val = db.session.query(func.sum(Inventory.quantity * Product.cost_price)).join(Product).filter(
            Inventory.outlet_id == outlet.id
        ).scalar() or 0
        
        outstanding = db.session.query(func.sum(Customer.current_balance)).filter(
            Customer.primary_outlet_id == outlet.id,
            Customer.is_active == True
        ).scalar() or 0
        
        avg_txn = (revenue / transactions) if transactions > 0 else 0
        profit = revenue - expenses
        margin = (profit / revenue * 100) if revenue > 0 else 0
        
        prev_rev = get_outlet_previous_revenue(outlet.id, date_from, date_to)
        growth = calculate_growth_rate(revenue, prev_rev)
        
        performance_data.append({
            'outlet_id': outlet.id,
            'outlet_name': outlet.name,
            'outlet_code': outlet.code,
            'revenue': float(revenue),
            'transactions': transactions,
            'avg_transaction': float(avg_txn),
            'expenses': float(expenses),
            'profit': float(profit),
            'profit_margin': float(margin),
            'inventory_value': float(inventory_val),
            'outstanding_credit': float(outstanding),
            'growth_rate': growth
        })
        
    # Rank by revenue
    performance_data.sort(key=lambda x: x['revenue'], reverse=True)
    for i, data in enumerate(performance_data, 1):
        data['rank'] = i
        
    return jsonify(performance_data)

@admin_dashboard_bp.route('/api/trends')
@login_required
@role_required(['super_admin', 'general_manager'])
def api_trends():
    """API Endpoint for Sales Trends"""
    days = request.args.get('days', 30, type=int)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    daily_sales = db.session.query(
        func.date(Sale.sale_date).label('date'),
        func.sum(Sale.total_amount).label('revenue'),
        func.count(Sale.id).label('transactions')
    ).filter(
        Sale.status == 'completed',
        func.date(Sale.sale_date) >= start_date,
        func.date(Sale.sale_date) <= end_date
    ).group_by(func.date(Sale.sale_date)).all()
    
    sales_map = {str(d.date): d for d in daily_sales}
    trend_data = []
    
    current = start_date
    while current <= end_date:
        key = str(current)
        if key in sales_map:
            trend_data.append({
                'date': key,
                'revenue': float(sales_map[key].revenue),
                'transactions': sales_map[key].transactions
            })
        else:
             trend_data.append({'date': key, 'revenue': 0, 'transactions': 0})
        current += timedelta(days=1)
        
    return jsonify(trend_data)

@admin_dashboard_bp.route('/api/alerts')
@login_required
@role_required(['super_admin', 'general_manager'])
def api_alerts():
    """API Endpoint for Critical Alerts"""
    alerts = []
    
    # 1. Critical Low Stock
    low_stock_count = db.session.query(Inventory).join(Product).filter(
        Product.is_active == True,
        Inventory.quantity <= Product.reorder_level * 0.25
    ).count()
    
    if low_stock_count > 0:
        alerts.append({
            'type': 'critical',
            'category': 'inventory',
            'message': f'{low_stock_count} products critically low in stock',
            'count': low_stock_count,
            'action_url': url_for('reports.inventory_low_stock')
        })
        
    # 2. High Outstanding Remittances (> 100k)
    # Group by sales rep
    reps = User.query.filter_by(role='sales_rep').all()
    high_outstanding_count = 0
    for rep in reps:
        col = db.session.query(func.sum(CashCollection.amount)).filter_by(sales_rep_id=rep.id).scalar() or 0
        rem = db.session.query(func.sum(Remittance.amount)).filter_by(sales_rep_id=rep.id).scalar() or 0
        if (col - rem) > 100000:
            high_outstanding_count += 1
            
    if high_outstanding_count > 0:
        alerts.append({
            'type': 'warning',
            'category': 'remittance',
            'message': f'{high_outstanding_count} sales reps have outstanding > ₦100,000',
            'count': high_outstanding_count,
            'action_url': url_for('remittance.outstanding')
        })
        
    # 3. Customers over limit
    over_limit = Customer.query.filter(
        Customer.is_active == True,
        Customer.current_balance > Customer.credit_limit
    ).count()
    
    if over_limit > 0:
        alerts.append({
            'type': 'critical',
            'category': 'credit',
            'message': f'{over_limit} customers exceeding credit limits',
            'count': over_limit,
            'action_url': url_for('customers.index', filter='over_limit')
        })
    
    # 4. Outlets with no sales today
    today = datetime.now().date()
    # Logic: Outlets that exist but have no sales today
    active_outlets_count = Outlet.query.filter_by(is_active=True, is_warehouse=False).count()
    outlets_with_sales = db.session.query(Sale.outlet_id).filter(
        func.date(Sale.sale_date) == today
    ).distinct().count()
    
    no_sales_count = active_outlets_count - outlets_with_sales
    if no_sales_count > 0:
         alerts.append({
            'type': 'info',
            'category': 'sales',
            'message': f'{no_sales_count} outlets with no sales today',
            'count': no_sales_count,
            'action_url': url_for('reports.sales_summary')
        })

    return jsonify(alerts)


@admin_dashboard_bp.route('/api/stock-receives')
@login_required
@role_required(['super_admin', 'general_manager'])
def api_stock_receives():
    """API: Recent stock additions to warehouse/outlets (InventoryAdjustment with qty > 0)."""
    from models import InventoryAdjustment

    date_from_str = request.args.get('date_from')
    date_to_str   = request.args.get('date_to')
    limit = request.args.get('limit', 20, type=int)

    today = datetime.now().date()
    if not date_from_str:
        # Default: last 30 days
        date_from = today - timedelta(days=30)
    else:
        date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()

    if not date_to_str:
        date_to = today
    else:
        date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()

    # Fetch positive adjustments (stock-ins) within date range
    adjustments = (
        InventoryAdjustment.query
        .filter(
            InventoryAdjustment.quantity_change > 0,
            func.date(InventoryAdjustment.adjusted_at) >= date_from,
            func.date(InventoryAdjustment.adjusted_at) <= date_to
        )
        .order_by(InventoryAdjustment.adjusted_at.desc())
        .limit(limit)
        .all()
    )

    data = []
    for adj in adjustments:
        data.append({
            'id': adj.id,
            'date': adj.adjusted_at.strftime('%d %b %Y'),
            'time': adj.adjusted_at.strftime('%I:%M %p'),
            'product_name': adj.product.name,
            'product_sku':  adj.product.sku,
            'outlet_name':  adj.outlet.name,
            'is_warehouse': adj.outlet.is_warehouse if hasattr(adj.outlet, 'is_warehouse') else False,
            'adjustment_type': adj.adjustment_type.replace('_', ' ').title(),
            'qty_before': adj.quantity_before,
            'qty_added':  adj.quantity_change,
            'qty_after':  adj.quantity_after,
            'reason':     adj.reason or '—',
            'reference':  adj.reference_number or '—',
            'performed_by': adj.user.full_name if adj.user else '—',
        })

    # Summary totals
    total_units = sum(a['qty_added'] for a in data)

    return jsonify({
        'adjustments': data,
        'total_units_received': total_units,
        'count': len(data),
        'date_from': str(date_from),
        'date_to': str(date_to),
    })

