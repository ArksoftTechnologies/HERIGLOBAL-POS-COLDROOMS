from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from sqlalchemy import func, case, extract, desc, and_
from models import db, User, Outlet, Product, Category, Sale, SaleItem, PaymentMode, Inventory, InventoryAdjustment, StockTransfer, Return, ReturnItem, Customer
from utils.decorators import role_required

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

def get_date_range():
    """Helper to get date range from request args"""
    today = datetime.now().date()
    date_from_str = request.args.get('date_from')
    date_to_str = request.args.get('date_to')
    
    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
        except ValueError:
            date_from = today - timedelta(days=30)
    else:
        date_from = today - timedelta(days=30)
        
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
        except ValueError:
            date_to = today
    else:
        date_to = today
        
    return date_from, date_to

@reports_bp.route('/')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'accountant'])
def index():
    """Reports Dashboard"""
    return render_template('reports/index.html')

@reports_bp.route('/sales/summary')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'accountant'])
def sales_summary():
    """Sales Summary Report"""
    date_from, date_to = get_date_range()
    outlet_id = request.args.get('outlet_id', type=int)
    sales_rep_id = request.args.get('sales_rep_id', type=int)
    
    # Base query
    query = db.session.query(
        func.count(Sale.id).label('total_transactions'),
        func.sum(Sale.total_amount).label('total_sales'),
        func.avg(Sale.total_amount).label('average_transaction')
    ).filter(Sale.status == 'completed')
    
    # Apply filters
    if date_from:
        query = query.filter(func.date(Sale.sale_date) >= date_from)
    if date_to:
        query = query.filter(func.date(Sale.sale_date) <= date_to)
    
    if current_user.role == 'outlet_admin':
        outlet_id = current_user.outlet_id
    
    if outlet_id:
        query = query.filter(Sale.outlet_id == outlet_id)
        
    if sales_rep_id:
        query = query.filter(Sale.sales_rep_id == sales_rep_id)
        
    summary = query.first()
    
    # Credit vs Cash breakdown
    payment_query = db.session.query(
        PaymentMode.name,
        func.sum(Sale.total_amount).label('total')
    ).join(Sale).filter(Sale.status == 'completed')
    
    if date_from:
        payment_query = payment_query.filter(func.date(Sale.sale_date) >= date_from)
    if date_to:
        payment_query = payment_query.filter(func.date(Sale.sale_date) <= date_to)
    if outlet_id:
        payment_query = payment_query.filter(Sale.outlet_id == outlet_id)
    if sales_rep_id:
        payment_query = payment_query.filter(Sale.sales_rep_id == sales_rep_id)
        
    payment_breakdown = payment_query.group_by(PaymentMode.name).all()
    
    # Sales by Outlet (for admins)
    outlet_breakdown = None
    if current_user.role in ['super_admin', 'general_manager', 'accountant'] and not outlet_id:
        outlet_breakdown = db.session.query(
            Outlet.name,
            func.count(Sale.id).label('transactions'),
            func.sum(Sale.total_amount).label('total')
        ).join(Sale).filter(Sale.status == 'completed')
        
        if date_from:
            outlet_breakdown = outlet_breakdown.filter(func.date(Sale.sale_date) >= date_from)
        if date_to:
            outlet_breakdown = outlet_breakdown.filter(func.date(Sale.sale_date) <= date_to)
            
        outlet_breakdown = outlet_breakdown.group_by(Outlet.name).all()

    # Top Products
    top_products = db.session.query(
        Product.name,
        func.sum(SaleItem.quantity).label('quantity_sold'),
        func.sum(SaleItem.subtotal).label('revenue')
    ).join(SaleItem.sale).join(Product).filter(Sale.status == 'completed')
    
    if date_from:
        top_products = top_products.filter(func.date(Sale.sale_date) >= date_from)
    if date_to:
        top_products = top_products.filter(func.date(Sale.sale_date) <= date_to)
    if outlet_id:
        top_products = top_products.filter(Sale.outlet_id == outlet_id)
        
    top_products = top_products.group_by(Product.id).order_by(desc('revenue')).limit(10).all()

    # Context data
    outlets = Outlet.query.all() if current_user.role in ['super_admin', 'general_manager', 'accountant'] else []
    sales_reps = User.query.filter_by(role='sales_rep').all()
    
    return render_template('reports/sales_summary.html',
                         summary=summary,
                         payment_breakdown=payment_breakdown,
                         outlet_breakdown=outlet_breakdown,
                         top_products=top_products,
                         outlets=outlets,
                         sales_reps=sales_reps,
                         date_from=date_from,
                         date_to=date_to,
                         selected_outlet=outlet_id,
                         selected_rep=sales_rep_id)

@reports_bp.route('/sales/detailed')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'accountant'])
def sales_detailed():
    """Detailed Sales Report with Pagination"""
    date_from, date_to = get_date_range()
    outlet_id = request.args.get('outlet_id', type=int)
    sales_rep_id = request.args.get('sales_rep_id', type=int)
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    query = Sale.query.filter(Sale.status == 'completed').order_by(Sale.sale_date.desc())
    
    if date_from:
        query = query.filter(func.date(Sale.sale_date) >= date_from)
    if date_to:
        query = query.filter(func.date(Sale.sale_date) <= date_to)
        
    if current_user.role == 'outlet_admin':
        outlet_id = current_user.outlet_id
    
    if outlet_id:
        query = query.filter(Sale.outlet_id == outlet_id)
    if sales_rep_id:
        query = query.filter(Sale.sales_rep_id == sales_rep_id)
        
    sales_pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    outlets = Outlet.query.all() if current_user.role in ['super_admin', 'general_manager', 'accountant'] else []
    sales_reps = User.query.filter_by(role='sales_rep').all()
    
    return render_template('reports/sales_detailed.html',
                         sales=sales_pagination,
                         outlets=outlets,
                         sales_reps=sales_reps,
                         date_from=date_from,
                         date_to=date_to,
                         selected_outlet=outlet_id,
                         selected_rep=sales_rep_id)

@reports_bp.route('/inventory/balance-sheet')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'accountant'])
def inventory_balance_sheet():
    """Inventory Balance Sheet"""
    date_from, date_to = get_date_range()
    outlet_id = request.args.get('outlet_id', type=int)
    
    # Default to first outlet if None and admin
    if not outlet_id:
        if current_user.role == 'outlet_admin':
            outlet_id = current_user.outlet_id
        else:
            first_outlet = Outlet.query.first()
            if first_outlet:
                outlet_id = first_outlet.id
    
    if not outlet_id:
        return render_template('reports/inventory_balance_sheet_empty.html', message="Please select an outlet")

    page = request.args.get('page', 1, type=int)
    per_page = 20

    # Get products
    products_query = Product.query.filter_by(is_active=True).order_by(Product.name)
    products_pagination = products_query.paginate(page=page, per_page=per_page, error_out=False)
    
    balance_sheet = []
    
    # Pre-fetch relevant data for the chunk of products to avoid N+1 (basic version here, could be optimized further)
    for product in products_pagination.items:
        # 1. Opening Stock (Complex: Current - movements since date) OR (0 + movements until date)
        # For simplicity in this chunk, assuming we calculate from CURRENT backward if date_to is today,
        # OR calculating forward if we had frozen snapshots (which we don't yet).
        # Strategy: 
        # Closing Stock (at date_to) = Opening (at date_from) + In - Out
        # But we only store CURRENT stock in Inventory table.
        # So: Closing Stock = Current Stock (if date_to is today) 
        # If date_to is past, we'd need to reverse movements from today back to date_to.
        # This is a common complexity.
        # 
        # Simplified Logic for MVP:
        # Show movements WITHIN date range.
        # Opening Stock = Theoretical (not easily tracked without snapshots) -> Label as "Movements" for now
        # OR: Just show activity sheet: Received, Sold, Returned, Damaged in period.
        
        # Current logic:
        # Received: StockTransfers (to_outlet)
        # Sold: SaleItems
        # Returned: ReturnItems (resellable)
        # Damaged: ReturnItems (damaged)
        # Adjustments: InventoryAdjustments
        
        received = db.session.query(func.sum(StockTransfer.quantity)).filter(
            StockTransfer.product_id == product.id,
            StockTransfer.to_outlet_id == outlet_id,
            StockTransfer.status == 'completed',
            func.date(StockTransfer.received_at) >= date_from,
            func.date(StockTransfer.received_at) <= date_to
        ).scalar() or 0
        
        sold = db.session.query(func.sum(SaleItem.quantity)).join(Sale).filter(
            SaleItem.product_id == product.id,
            Sale.outlet_id == outlet_id,
            Sale.status == 'completed',
            func.date(Sale.sale_date) >= date_from,
            func.date(Sale.sale_date) <= date_to
        ).scalar() or 0
        
        returned = db.session.query(func.sum(ReturnItem.quantity_returned)).join(Return).filter(
            ReturnItem.product_id == product.id,
            Return.outlet_id == outlet_id,
            ReturnItem.condition == 'resellable',
            Return.status == 'completed',
            func.date(Return.return_date) >= date_from,
            func.date(Return.return_date) <= date_to
        ).scalar() or 0
        
        damaged = db.session.query(func.sum(ReturnItem.quantity_returned)).join(Return).filter(
            ReturnItem.product_id == product.id,
            Return.outlet_id == outlet_id,
            ReturnItem.condition == 'damaged',
            Return.status == 'completed',
            func.date(Return.return_date) >= date_from,
            func.date(Return.return_date) <= date_to
        ).scalar() or 0
        
        adjusted = db.session.query(func.sum(InventoryAdjustment.quantity_change)).filter(
            InventoryAdjustment.product_id == product.id,
            InventoryAdjustment.outlet_id == outlet_id,
            func.date(InventoryAdjustment.adjusted_at) >= date_from,
            func.date(InventoryAdjustment.adjusted_at) <= date_to
        ).scalar() or 0
        
        # Current stock (Real-time)
        current_inv = Inventory.query.filter_by(product_id=product.id, outlet_id=outlet_id).first()
        current_qty = current_inv.quantity if current_inv else 0
        
        # Estimated Opening (Back calculation from current if date_to is today)
        # This is an approximation
        
        row = {
            'product': product,
            'received': received,
            'sold': sold,
            'returned': returned,
            'damaged': damaged,
            'adjusted': adjusted,
            'current': current_qty,
            'closing_value_cost': current_qty * float(product.cost_price or 0)
        }
        balance_sheet.append(row)

    outlets = Outlet.query.all() if current_user.role in ['super_admin', 'general_manager', 'accountant'] else []

    return render_template('reports/inventory_balance_sheet.html',
                         balance_sheet=balance_sheet,
                         pagination=products_pagination,
                         outlets=outlets,
                         selected_outlet=outlet_id,
                         date_from=date_from,
                         date_to=date_to)

@reports_bp.route('/inventory/low-stock')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin'])
def low_stock_alert():
    """Low Stock Alert Report"""
    outlet_id = request.args.get('outlet_id', type=int)
    
    if current_user.role == 'outlet_admin':
        outlet_id = current_user.outlet_id
        
    query = db.session.query(Product, Inventory).join(Inventory).filter(
        Inventory.quantity <= Product.reorder_level,
        Product.is_active == True
    )
    
    if outlet_id:
        query = query.filter(Inventory.outlet_id == outlet_id)
        
    low_stock_items = query.all()
    
    outlets = Outlet.query.all() if current_user.role in ['super_admin', 'general_manager'] else []
    
    return render_template('reports/inventory_low_stock.html',
                         items=low_stock_items,
                         outlets=outlets,
                         selected_outlet=outlet_id)

@reports_bp.route('/sales/credit-vs-cash')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'accountant'])
def credit_vs_cash():
    """Credit vs Cash Analysis"""
    date_from, date_to = get_date_range()
    
    payment_stats = db.session.query(
        PaymentMode.name,
        PaymentMode.is_credit,
        func.count(Sale.id).label('count'),
        func.sum(Sale.total_amount).label('total')
    ).join(Sale).filter(
        Sale.status == 'completed',
        func.date(Sale.sale_date) >= date_from,
        func.date(Sale.sale_date) <= date_to
    ).group_by(PaymentMode.id).all()
    
    return render_template('reports/sales_credit_vs_cash.html',
                         stats=payment_stats,
                         date_from=date_from,
                         date_to=date_to)

# ─────────────────────────────────────────────────────────────────────────────
# NEW REPORT 1: Stock Received (Per Outlet, Date Range)
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route('/stock/receive')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin'])
def stock_receive():
    """Report: All stock received into an outlet within a date range."""
    date_from, date_to = get_date_range()
    outlet_id = request.args.get('outlet_id', type=int)

    # Outlet-admin is always locked to their own outlet
    if current_user.role == 'outlet_admin':
        outlet_id = current_user.outlet_id

    # ── Transfers received (completed stock transfers TO outlet) ──────────────
    transfer_query = db.session.query(
        Product.name.label('product_name'),
        Product.sku,
        Product.unit,
        StockTransfer.quantity,
        StockTransfer.transfer_number,
        StockTransfer.received_at.label('date'),
        Outlet.name.label('from_outlet'),
        db.literal('Transfer').label('source_type')
    ).join(Product, StockTransfer.product_id == Product.id)\
     .join(Outlet, StockTransfer.from_outlet_id == Outlet.id)\
     .filter(
        StockTransfer.status == 'completed',
        func.date(StockTransfer.received_at) >= date_from,
        func.date(StockTransfer.received_at) <= date_to
    )
    if outlet_id:
        transfer_query = transfer_query.filter(StockTransfer.to_outlet_id == outlet_id)

    receive_rows = transfer_query.order_by(StockTransfer.received_at.desc()).all()

    # Totals per product (pivot for summary)
    product_totals = {}
    for row in receive_rows:
        key = (row.product_name, row.sku, row.unit)
        product_totals[key] = product_totals.get(key, 0) + row.quantity

    grand_total_qty = sum(r.quantity for r in receive_rows)
    grand_total_lines = len(receive_rows)

    # Outlet dropdown (platform-wide roles only)
    outlets = Outlet.query.filter_by(is_active=True).order_by(Outlet.name).all() \
        if current_user.role in ['super_admin', 'general_manager'] else []

    selected_outlet = Outlet.query.get(outlet_id) if outlet_id else None

    return render_template('reports/stock_receive.html',
                           rows=receive_rows,
                           product_totals=product_totals,
                           grand_total_qty=grand_total_qty,
                           grand_total_lines=grand_total_lines,
                           outlets=outlets,
                           selected_outlet=selected_outlet,
                           outlet_id=outlet_id,
                           date_from=date_from,
                           date_to=date_to)


# ─────────────────────────────────────────────────────────────────────────────
# NEW REPORT 2: Sold Products (Per Outlet, Date Range)
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route('/products/sold')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin'])
def products_sold():
    """Report: Summary of products sold within a date range (per outlet)."""
    date_from, date_to = get_date_range()
    outlet_id = request.args.get('outlet_id', type=int)

    if current_user.role == 'outlet_admin':
        outlet_id = current_user.outlet_id

    query = db.session.query(
        Product.name.label('product_name'),
        Product.sku,
        Product.unit,
        func.sum(SaleItem.quantity).label('qty_sold'),
        func.sum(SaleItem.subtotal).label('revenue'),
        func.min(SaleItem.unit_price).label('min_price'),
        func.max(SaleItem.unit_price).label('max_price'),
        func.avg(SaleItem.unit_price).label('avg_price'),
        func.count(func.distinct(Sale.id)).label('num_transactions')
    ).join(SaleItem, Product.id == SaleItem.product_id)\
     .join(Sale, SaleItem.sale_id == Sale.id)\
     .filter(
        Sale.status == 'completed',
        func.date(Sale.sale_date) >= date_from,
        func.date(Sale.sale_date) <= date_to
    )

    if outlet_id:
        query = query.filter(Sale.outlet_id == outlet_id)

    rows = query.group_by(Product.id).order_by(func.sum(SaleItem.subtotal).desc()).all()

    grand_qty = sum(r.qty_sold for r in rows)
    grand_revenue = sum(float(r.revenue) for r in rows)
    grand_tx = sum(r.num_transactions for r in rows)

    outlets = Outlet.query.filter_by(is_active=True).order_by(Outlet.name).all() \
        if current_user.role in ['super_admin', 'general_manager'] else []

    selected_outlet = Outlet.query.get(outlet_id) if outlet_id else None

    return render_template('reports/products_sold.html',
                           rows=rows,
                           grand_qty=grand_qty,
                           grand_revenue=grand_revenue,
                           grand_tx=grand_tx,
                           outlets=outlets,
                           selected_outlet=selected_outlet,
                           outlet_id=outlet_id,
                           date_from=date_from,
                           date_to=date_to)


# ─────────────────────────────────────────────────────────────────────────────
# NEW REPORT 3: Sales by Period / Outlet
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route('/sales/by-outlet')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin'])
def sales_by_outlet():
    """Report: Sales aggregated per outlet over a date range, with daily breakdown."""
    date_from, date_to = get_date_range()
    outlet_id = request.args.get('outlet_id', type=int)

    if current_user.role == 'outlet_admin':
        outlet_id = current_user.outlet_id

    # ── Per-outlet totals ─────────────────────────────────────────────────────
    outlet_query = db.session.query(
        Outlet.id.label('outlet_id'),
        Outlet.name.label('outlet_name'),
        func.count(Sale.id).label('transactions'),
        func.sum(Sale.total_amount).label('revenue')
    ).join(Sale, Outlet.id == Sale.outlet_id)\
     .filter(
        Sale.status == 'completed',
        func.date(Sale.sale_date) >= date_from,
        func.date(Sale.sale_date) <= date_to,
        Outlet.is_warehouse == False
    )
    if outlet_id:
        outlet_query = outlet_query.filter(Sale.outlet_id == outlet_id)

    outlet_totals = outlet_query.group_by(Outlet.id).order_by(
        func.sum(Sale.total_amount).desc()
    ).all()

    # ── Daily breakdown (one row per day per outlet) ──────────────────────────
    daily_query = db.session.query(
        func.date(Sale.sale_date).label('sale_day'),
        Outlet.name.label('outlet_name'),
        func.count(Sale.id).label('transactions'),
        func.sum(Sale.total_amount).label('revenue')
    ).join(Outlet, Sale.outlet_id == Outlet.id)\
     .filter(
        Sale.status == 'completed',
        func.date(Sale.sale_date) >= date_from,
        func.date(Sale.sale_date) <= date_to,
        Outlet.is_warehouse == False
    )
    if outlet_id:
        daily_query = daily_query.filter(Sale.outlet_id == outlet_id)

    daily_rows = daily_query.group_by(
        func.date(Sale.sale_date), Outlet.id
    ).order_by(func.date(Sale.sale_date).desc()).all()

    grand_revenue = sum(float(r.revenue) for r in outlet_totals)
    grand_transactions = sum(r.transactions for r in outlet_totals)

    outlets = Outlet.query.filter_by(is_active=True).order_by(Outlet.name).all() \
        if current_user.role in ['super_admin', 'general_manager'] else []

    selected_outlet = Outlet.query.get(outlet_id) if outlet_id else None

    return render_template('reports/sales_by_outlet.html',
                           outlet_totals=outlet_totals,
                           daily_rows=daily_rows,
                           grand_revenue=grand_revenue,
                           grand_transactions=grand_transactions,
                           outlets=outlets,
                           selected_outlet=selected_outlet,
                           outlet_id=outlet_id,
                           date_from=date_from,
                           date_to=date_to)

