from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, current_app, make_response
from flask_login import login_required, current_user
from sqlalchemy import func, case, extract, desc, and_
from models import db, User, Outlet, Product, Category, Sale, SaleItem, SalePayment, PaymentMode, Inventory, InventoryAdjustment, StockTransfer, Return, ReturnItem, Customer, Expense, Remittance, CashCollection
from utils.decorators import role_required
import csv
import io

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
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'accountant', 'sales_rep'])
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
    
    if request.args.get('format') == 'pdf':
        response = make_response(render_template('reports/pdf/sales_summary.html',
                         summary=summary,
                         payment_breakdown=payment_breakdown,
                         outlet_breakdown=outlet_breakdown,
                         top_products=top_products,
                         outlets=outlets,
                         sales_reps=sales_reps,
                         date_from=date_from,
                         date_to=date_to,
                         selected_outlet=outlet_id,
                         selected_rep=sales_rep_id,
                         app_name=current_app.config.get('APP_NAME', 'Point of Sale'),
                         company_name=current_app.config.get('COMPANY_NAME', 'POS System'),
                         generated_by=current_user.full_name,
                         generated_at=datetime.now()))
        response.headers['Content-Type'] = 'text/html'
        return response

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
    
    if request.args.get('format') == 'pdf':
        response = make_response(render_template('reports/pdf/sales_detailed.html',
                         sales=sales_pagination, # Warning: might need to bypass pagination for full PDF export later
                         outlets=outlets,
                         sales_reps=sales_reps,
                         date_from=date_from,
                         date_to=date_to,
                         selected_outlet=outlet_id,
                         selected_rep=sales_rep_id,
                         app_name=current_app.config.get('APP_NAME', 'Point of Sale'),
                         company_name=current_app.config.get('COMPANY_NAME', 'POS System'),
                         generated_by=current_user.full_name,
                         generated_at=datetime.now()))
        response.headers['Content-Type'] = 'text/html'
        return response

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
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'accountant', 'sales_rep'])
def inventory_balance_sheet():
    """Inventory Balance Sheet"""
    date_from, date_to = get_date_range()
    outlet_id = request.args.get('outlet_id', type=int)
    
    # Default to first outlet if None and admin
    if current_user.role in ['outlet_admin', 'sales_rep']:
        outlet_id = current_user.outlet_id
    elif not outlet_id:
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

    if request.args.get('format') == 'csv':
        # Export ALL products (no pagination) with the same movement queries
        all_products = Product.query.filter_by(is_active=True).order_by(Product.name).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Product', 'SKU',
            'Received', 'Sold', 'Returned', 'Damaged', 'Adjusted',
            'Current Stock', 'Value at Cost (NGN)'
        ])

        for product in all_products:
            p_received = db.session.query(func.sum(StockTransfer.quantity)).filter(
                StockTransfer.product_id == product.id,
                StockTransfer.to_outlet_id == outlet_id,
                StockTransfer.status == 'completed',
                func.date(StockTransfer.received_at) >= date_from,
                func.date(StockTransfer.received_at) <= date_to
            ).scalar() or 0

            p_sold = db.session.query(func.sum(SaleItem.quantity)).join(Sale).filter(
                SaleItem.product_id == product.id,
                Sale.outlet_id == outlet_id,
                Sale.status == 'completed',
                func.date(Sale.sale_date) >= date_from,
                func.date(Sale.sale_date) <= date_to
            ).scalar() or 0

            p_returned = db.session.query(func.sum(ReturnItem.quantity_returned)).join(Return).filter(
                ReturnItem.product_id == product.id,
                Return.outlet_id == outlet_id,
                ReturnItem.condition == 'resellable',
                Return.status == 'completed',
                func.date(Return.return_date) >= date_from,
                func.date(Return.return_date) <= date_to
            ).scalar() or 0

            p_damaged = db.session.query(func.sum(ReturnItem.quantity_returned)).join(Return).filter(
                ReturnItem.product_id == product.id,
                Return.outlet_id == outlet_id,
                ReturnItem.condition == 'damaged',
                Return.status == 'completed',
                func.date(Return.return_date) >= date_from,
                func.date(Return.return_date) <= date_to
            ).scalar() or 0

            p_adjusted = db.session.query(func.sum(InventoryAdjustment.quantity_change)).filter(
                InventoryAdjustment.product_id == product.id,
                InventoryAdjustment.outlet_id == outlet_id,
                func.date(InventoryAdjustment.adjusted_at) >= date_from,
                func.date(InventoryAdjustment.adjusted_at) <= date_to
            ).scalar() or 0

            current_inv = Inventory.query.filter_by(product_id=product.id, outlet_id=outlet_id).first()
            current_qty = current_inv.quantity if current_inv else 0
            closing_value = current_qty * float(product.cost_price or 0)

            writer.writerow([
                product.name,
                product.sku,
                p_received,
                p_sold,
                p_returned,
                p_damaged,
                p_adjusted,
                current_qty,
                f"{closing_value:.2f}"
            ])

        outlet_obj = Outlet.query.get(outlet_id)
        outlet_label = outlet_obj.name.replace(' ', '_') if outlet_obj else 'Unknown'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"Inventory_Balance_Sheet_{outlet_label}_{date_from}_to_{date_to}_{timestamp}.csv"

        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    if request.args.get('format') == 'pdf':
        response = make_response(render_template('reports/pdf/inventory_balance_sheet.html',
                         balance_sheet=balance_sheet,
                         pagination=products_pagination,
                         outlets=outlets,
                         selected_outlet=outlet_id,
                         date_from=date_from,
                         date_to=date_to,
                         app_name=current_app.config.get('APP_NAME', 'Point of Sale'),
                         company_name=current_app.config.get('COMPANY_NAME', 'POS System'),
                         generated_by=current_user.full_name,
                         generated_at=datetime.now()))
        response.headers['Content-Type'] = 'text/html'
        return response

    return render_template('reports/inventory_balance_sheet.html',
                         balance_sheet=balance_sheet,
                         pagination=products_pagination,
                         outlets=outlets,
                         selected_outlet=outlet_id,
                         date_from=date_from,
                         date_to=date_to)

@reports_bp.route('/inventory/low-stock')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'accountant'])
def inventory_low_stock():
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
    
    outlets = Outlet.query.all() if current_user.role in ['super_admin', 'general_manager', 'accountant'] else []
    
    if request.args.get('format') == 'pdf':
        response = make_response(render_template('reports/pdf/inventory_low_stock.html',
                         items=low_stock_items,
                         outlets=outlets,
                         selected_outlet=outlet_id,
                         app_name=current_app.config.get('APP_NAME', 'Point of Sale'),
                         company_name=current_app.config.get('COMPANY_NAME', 'POS System'),
                         generated_by=current_user.full_name,
                         generated_at=datetime.now()))
        response.headers['Content-Type'] = 'text/html'
        return response
        
    return render_template('reports/inventory_low_stock.html',
                         items=low_stock_items,
                         outlets=outlets,
                         selected_outlet=outlet_id)

@reports_bp.route('/sales/credit-vs-cash')
@login_required
@role_required(['super_admin', 'general_manager', 'accountant'])
def sales_credit_vs_cash():
    """Credit vs Cash Sales Comparison Report"""
    date_from, date_to = get_date_range()
    
    # Unified query: Single Payments + Split Payments
    from sqlalchemy import union_all
    
    # Subquery 1: Single payments (directly on Sale)
    single_payments = db.session.query(
        Sale.id.label('sale_id'),
        Sale.payment_mode_id.label('pm_id'),
        Sale.total_amount.label('amt'),
        Sale.sale_date.label('dt'),
        Sale.status.label('st')
    ).filter(Sale.is_split_payment == False)
    
    # Subquery 2: Split payments (from SalePayment)
    split_payments = db.session.query(
        Sale.id.label('sale_id'),
        SalePayment.payment_mode_id.label('pm_id'),
        SalePayment.amount.label('amt'),
        Sale.sale_date.label('dt'),
        Sale.status.label('st')
    ).join(SalePayment, Sale.id == SalePayment.sale_id)
    
    unified = union_all(single_payments, split_payments).alias('unified')
    
    payment_stats = db.session.query(
        PaymentMode.name,
        PaymentMode.is_credit,
        func.count(func.distinct(unified.c.sale_id)).label('count'),
        func.sum(unified.c.amt).label('total')
    ).join(unified, PaymentMode.id == unified.c.pm_id).filter(
        unified.c.st == 'completed',
        func.date(unified.c.dt) >= date_from,
        func.date(unified.c.dt) <= date_to
    ).group_by(PaymentMode.id).all()
    
    if request.args.get('format') == 'pdf':
        response = make_response(render_template('reports/pdf/sales_credit_vs_cash.html',
                         stats=payment_stats,
                         date_from=date_from,
                         date_to=date_to,
                         app_name=current_app.config.get('APP_NAME', 'Point of Sale'),
                         company_name=current_app.config.get('COMPANY_NAME', 'POS System'),
                         generated_by=current_user.full_name,
                         generated_at=datetime.now()))
        response.headers['Content-Type'] = 'text/html'
        return response

    return render_template('reports/sales_credit_vs_cash.html',
                         stats=payment_stats,
                         date_from=date_from,
                         date_to=date_to)

# ─────────────────────────────────────────────────────────────────────────────
# NEW REPORT 0: Central Warehouse Receive (Adjustments)
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route('/warehouse/receive')
@login_required
@role_required(['super_admin', 'general_manager', 'accountant'])
def warehouse_receive():
    """Report: Stock received into central warehouse via adjustments."""
    date_from, date_to = get_date_range()
    
    warehouse = Outlet.query.filter_by(is_warehouse=True).first()
    if not warehouse:
        warehouse = Outlet.query.get(1)

    # Query InventoryAdjustment where quantity_change > 0 and outlet_id == warehouse.id
    # Exclude transfers and sales (Request: only adjustments, not transfers)
    exclude_types = ['transfer_in', 'transfer_out', 'transfer_cancelled', 'sale']
    
    query = db.session.query(
        Product.name.label('product_name'),
        Product.sku,
        Product.unit,
        InventoryAdjustment.quantity_change.label('quantity'),
        InventoryAdjustment.reference_number,
        InventoryAdjustment.adjusted_at.label('date'),
        InventoryAdjustment.adjustment_type.label('source_type')
    ).join(Product, InventoryAdjustment.product_id == Product.id)\
     .filter(
        InventoryAdjustment.outlet_id == warehouse.id,
        InventoryAdjustment.quantity_change > 0,
        InventoryAdjustment.adjustment_type.notin_(exclude_types),
        func.date(InventoryAdjustment.adjusted_at) >= date_from,
        func.date(InventoryAdjustment.adjusted_at) <= date_to
    )

    receive_rows = query.order_by(InventoryAdjustment.adjusted_at.desc()).all()

    product_totals = {}
    for row in receive_rows:
        key = (row.product_name, row.sku, row.unit)
        product_totals[key] = product_totals.get(key, 0) + row.quantity

    grand_total_qty = sum(r.quantity for r in receive_rows)
    grand_total_lines = len(receive_rows)

    if request.args.get('format') == 'pdf':
        response = make_response(render_template('reports/pdf/warehouse_receive.html',
                           rows=receive_rows,
                           product_totals=product_totals,
                           grand_total_qty=grand_total_qty,
                           grand_total_lines=grand_total_lines,
                           warehouse=warehouse,
                           date_from=date_from,
                           date_to=date_to,
                           app_name=current_app.config.get('APP_NAME', 'Point of Sale'),
                           company_name=current_app.config.get('COMPANY_NAME', 'POS System'),
                           generated_by=current_user.full_name,
                           generated_at=datetime.now()))
        response.headers['Content-Type'] = 'text/html'
        return response

    return render_template('reports/warehouse_receive.html',
                         rows=receive_rows,
                         product_totals=product_totals,
                         grand_total_qty=grand_total_qty,
                         grand_total_lines=grand_total_lines,
                         warehouse=warehouse,
                         date_from=date_from,
                         date_to=date_to)


@reports_bp.route('/inventory/trial-balance')
@login_required
@role_required(['super_admin', 'general_manager', 'accountant'])
def inventory_trial_balance():
    """Report: Reconciliation of Receives vs Sales vs Current Stock."""
    date_from, date_to = get_date_range()
    outlet_id = request.args.get('outlet_id', type=int)
    
    # Filter by outlet if provided, otherwise default/all depending on business logic
    # For a trial balance, we usually show by outlet
    if not outlet_id:
        outlet = Outlet.query.filter_by(is_warehouse=True).first() or Outlet.query.get(1)
        outlet_id = outlet.id
    else:
        outlet = Outlet.query.get_or_404(outlet_id)

    # 1. Opening Balance (Total change before date_from)
    opening_subquery = db.session.query(
        InventoryAdjustment.product_id,
        func.sum(InventoryAdjustment.quantity_change).label('opening_bal')
    ).filter(
        InventoryAdjustment.outlet_id == outlet_id,
        func.date(InventoryAdjustment.adjusted_at) < date_from
    ).group_by(InventoryAdjustment.product_id).subquery()

    # 2. Total Inward in period (All positive changes)
    received_subquery = db.session.query(
        InventoryAdjustment.product_id,
        func.sum(InventoryAdjustment.quantity_change).label('total_received')
    ).filter(
        InventoryAdjustment.outlet_id == outlet_id,
        InventoryAdjustment.quantity_change > 0,
        func.date(InventoryAdjustment.adjusted_at) >= date_from,
        func.date(InventoryAdjustment.adjusted_at) <= date_to
    ).group_by(InventoryAdjustment.product_id).subquery()

    # 3. Total Sold in period (Sales adjustments)
    sold_subquery = db.session.query(
        InventoryAdjustment.product_id,
        func.sum(func.abs(InventoryAdjustment.quantity_change)).label('total_sold')
    ).filter(
        InventoryAdjustment.outlet_id == outlet_id,
        InventoryAdjustment.adjustment_type == 'sale',
        func.date(InventoryAdjustment.adjusted_at) >= date_from,
        func.date(InventoryAdjustment.adjusted_at) <= date_to
    ).group_by(InventoryAdjustment.product_id).subquery()

    # 4. Total Transferred Out in period
    transfers_out_subquery = db.session.query(
        InventoryAdjustment.product_id,
        func.sum(func.abs(InventoryAdjustment.quantity_change)).label('total_transferred_out')
    ).filter(
        InventoryAdjustment.outlet_id == outlet_id,
        InventoryAdjustment.adjustment_type == 'transfer_out',
        func.date(InventoryAdjustment.adjusted_at) >= date_from,
        func.date(InventoryAdjustment.adjusted_at) <= date_to
    ).group_by(InventoryAdjustment.product_id).subquery()

    # 5. Other Outward (Damages, etc.) - Net of other negative changes
    other_out_subquery = db.session.query(
        InventoryAdjustment.product_id,
        func.sum(func.abs(InventoryAdjustment.quantity_change)).label('total_other_out')
    ).filter(
        InventoryAdjustment.outlet_id == outlet_id,
        InventoryAdjustment.quantity_change < 0,
        InventoryAdjustment.adjustment_type.notin_(['sale', 'transfer_out']),
        func.date(InventoryAdjustment.adjusted_at) >= date_from,
        func.date(InventoryAdjustment.adjusted_at) <= date_to
    ).group_by(InventoryAdjustment.product_id).subquery()

    # 6. Sum of changes AFTER the period (to reconcile with current stock)
    closing_adj_subquery = db.session.query(
        InventoryAdjustment.product_id,
        func.sum(InventoryAdjustment.quantity_change).label('future_change')
    ).filter(
        InventoryAdjustment.outlet_id == outlet_id,
        func.date(InventoryAdjustment.adjusted_at) > date_to
    ).group_by(InventoryAdjustment.product_id).subquery()

    # 7. Main Query: Product + Inventory + All Subqueries
    results = db.session.query(
        Product.id,
        Product.name,
        Product.sku,
        Inventory.quantity.label('current_stock'),
        func.coalesce(opening_subquery.c.opening_bal, 0).label('opening'),
        func.coalesce(received_subquery.c.total_received, 0).label('received'),
        func.coalesce(sold_subquery.c.total_sold, 0).label('sold'),
        func.coalesce(transfers_out_subquery.c.total_transferred_out, 0).label('transferred_out'),
        func.coalesce(other_out_subquery.c.total_other_out, 0).label('other_out'),
        func.coalesce(closing_adj_subquery.c.future_change, 0).label('future_change')
    ).join(Inventory, Product.id == Inventory.product_id)\
     .filter(Inventory.outlet_id == outlet_id)\
     .outerjoin(opening_subquery, Product.id == opening_subquery.c.product_id)\
     .outerjoin(received_subquery, Product.id == received_subquery.c.product_id)\
     .outerjoin(sold_subquery, Product.id == sold_subquery.c.product_id)\
     .outerjoin(transfers_out_subquery, Product.id == transfers_out_subquery.c.product_id)\
     .outerjoin(other_out_subquery, Product.id == other_out_subquery.c.product_id)\
     .outerjoin(closing_adj_subquery, Product.id == closing_adj_subquery.c.product_id)\
     .order_by(Product.name.asc()).all()

    # Format for template
    report_data = []
    for r in results:
        # Simple math for the main table
        calc_balance = r.received - r.sold
        # Correct math for auditing
        system_expected = r.opening + r.received - r.sold - r.transferred_out - r.other_out
        is_balanced = (calc_balance == r.current_stock)
        
        # Reasons for imbalance check
        reasons = []
        if r.opening != 0:
            reasons.append(f"Opening stock of {r.opening} existed before {date_from}")
        if r.transferred_out != 0:
            reasons.append(f"Transferred out {r.transferred_out} units in this period")
        if r.other_out != 0:
            reasons.append(f"Other adjustments (damages/manual) reduced stock by {r.other_out}")
        if r.future_change != 0:
            reasons.append(f"Stock moved by {r.future_change} after {date_to}")
            
        report_data.append({
            'id': r.id,
            'name': r.name,
            'sku': r.sku,
            'opening': r.opening,
            'received': r.received,
            'sold': r.sold,
            'transferred_out': r.transferred_out,
            'other_out': r.other_out,
            'calc_balance': calc_balance,
            'system_expected': system_expected,
            'actual_stock': r.current_stock,
            'future_change': r.future_change,
            'is_balanced': is_balanced,
            'reasons': reasons
        })

    all_outlets = Outlet.query.filter_by(is_active=True).all()

    if request.args.get('format') == 'pdf':
        response = make_response(render_template('reports/pdf/inventory_trial_balance.html',
                           data=report_data,
                           outlet=outlet,
                           date_from=date_from,
                           date_to=date_to,
                           app_name=current_app.config.get('APP_NAME', 'Point of Sale'),
                           company_name=current_app.config.get('COMPANY_NAME', 'POS System'),
                           generated_by=current_user.full_name,
                           generated_at=datetime.now()))
        response.headers['Content-Type'] = 'text/html'
        return response

    return render_template('reports/inventory_trial_balance.html',
                         data=report_data,
                         outlet=outlet,
                         all_outlets=all_outlets,
                         date_from=date_from,
                         date_to=date_to,
                         app_name=current_app.config.get('APP_NAME', 'Point of Sale'),
                         company_name=current_app.config.get('COMPANY_NAME', 'POS System'),
                         generated_by=current_user.full_name,
                         generated_at=datetime.now())


# ─────────────────────────────────────────────────────────────────────────────
# NEW REPORT 1: Stock Received (Per Outlet, Date Range)
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route('/stock/receive')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'accountant'])
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
        if current_user.role in ['super_admin', 'general_manager', 'accountant'] else []

    selected_outlet = Outlet.query.get(outlet_id) if outlet_id else None

    if request.args.get('format') == 'pdf':
        response = make_response(render_template('reports/pdf/stock_receive.html',
                           rows=receive_rows,
                           product_totals=product_totals,
                           grand_total_qty=grand_total_qty,
                           grand_total_lines=grand_total_lines,
                           outlets=outlets,
                           selected_outlet=selected_outlet,
                           outlet_id=outlet_id,
                           date_from=date_from,
                           date_to=date_to,
                           app_name=current_app.config.get('APP_NAME', 'Point of Sale'),
                           company_name=current_app.config.get('COMPANY_NAME', 'POS System'),
                           generated_by=current_user.full_name,
                           generated_at=datetime.now()))
        response.headers['Content-Type'] = 'text/html'
        return response

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
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'accountant', 'sales_rep'])
def products_sold():
    """Report: Summary of products sold within a date range (per outlet)."""
    date_from, date_to = get_date_range()
    outlet_id = request.args.get('outlet_id', type=int)
    sales_rep_id = request.args.get('sales_rep_id', type=int)

    if current_user.role in ['outlet_admin', 'sales_rep']:
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

    if sales_rep_id:
        query = query.filter(Sale.sales_rep_id == sales_rep_id)

    rows = query.group_by(Product.id).order_by(func.sum(SaleItem.subtotal).desc()).all()

    grand_qty = sum(r.qty_sold for r in rows)
    grand_revenue = sum(float(r.revenue) for r in rows)
    grand_tx = sum(r.num_transactions for r in rows)

    outlets = Outlet.query.filter_by(is_active=True).order_by(Outlet.name).all() \
        if current_user.role in ['super_admin', 'general_manager', 'accountant'] else []

    selected_outlet = Outlet.query.get(outlet_id) if outlet_id else None

    # Fetch sales reps for filtering
    sales_reps = User.query.filter_by(role='sales_rep').all()
    if current_user.role in ['outlet_admin', 'sales_rep']:
        sales_reps = [u for u in sales_reps if u.outlet_id == current_user.outlet_id]

    if request.args.get('format') == 'pdf':
        response = make_response(render_template('reports/pdf/products_sold.html',
                           rows=rows,
                           grand_qty=grand_qty,
                           grand_revenue=grand_revenue,
                           grand_tx=grand_tx,
                           outlets=outlets,
                           sales_reps=sales_reps,
                           selected_outlet=selected_outlet,
                           outlet_id=outlet_id,
                           sales_rep_id=sales_rep_id,
                           date_from=date_from,
                           date_to=date_to,
                           app_name=current_app.config.get('APP_NAME', 'Point of Sale'),
                           company_name=current_app.config.get('COMPANY_NAME', 'POS System'),
                           generated_by=current_user.full_name,
                           generated_at=datetime.now()))
        response.headers['Content-Type'] = 'text/html'
        return response

    return render_template('reports/products_sold.html',
                           rows=rows,
                           grand_qty=grand_qty,
                           grand_revenue=grand_revenue,
                           grand_tx=grand_tx,
                           outlets=outlets,
                           sales_reps=sales_reps,
                           selected_outlet=selected_outlet,
                           outlet_id=outlet_id,
                           sales_rep_id=sales_rep_id,
                           date_from=date_from,
                           date_to=date_to)


# ─────────────────────────────────────────────────────────────────────────────
# NEW REPORT 3: Sales by Period / Outlet
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route('/sales/by-outlet')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'accountant'])
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
        if current_user.role in ['super_admin', 'general_manager', 'accountant'] else []

    selected_outlet = Outlet.query.get(outlet_id) if outlet_id else None

    if request.args.get('format') == 'pdf':
        response = make_response(render_template('reports/pdf/sales_by_outlet.html',
                           outlet_totals=outlet_totals,
                           daily_rows=daily_rows,
                           grand_revenue=grand_revenue,
                           grand_transactions=grand_transactions,
                           outlets=outlets,
                           selected_outlet=selected_outlet,
                           outlet_id=outlet_id,
                           date_from=date_from,
                           date_to=date_to,
                           app_name=current_app.config.get('APP_NAME', 'Point of Sale'),
                           company_name=current_app.config.get('COMPANY_NAME', 'POS System'),
                           generated_by=current_user.full_name,
                           generated_at=datetime.now()))
        response.headers['Content-Type'] = 'text/html'
        return response

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


# ─────────────────────────────────────────────────────────────────────────────
# NEW REPORT 4: Daily Balance Sheet
# ─────────────────────────────────────────────────────────────────────────────
@reports_bp.route('/sales/daily-balance-sheet')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'accountant', 'sales_rep'])
def daily_balance_sheet():
    """Report: Calculate daily balance leftover for easy accounting."""
    date_from, date_to = get_date_range()
    # For a *daily* report, we usually care about a single day.
    # We will use date_from as "The Date" if user selects only one, or process the range if needed.
    # To keep the logic simple corresponding to "Today", we will force date_to = date_from (or just use date_from).
    selected_date_str = request.args.get('date_from')
    target_date = date_from if selected_date_str else datetime.now().date()
    # Reset date_to so ui matches target
    date_from = target_date
    date_to = target_date

    outlet_id = request.args.get('outlet_id', type=int)
    sales_rep_id = request.args.get('sales_rep_id', type=int)

    if current_user.role in ['outlet_admin', 'sales_rep']:
        outlet_id = current_user.outlet_id
    if current_user.role == 'sales_rep':
        sales_rep_id = current_user.id

    if not sales_rep_id and current_user.role not in ['sales_rep']:
        # If admin doesn't select a rep, show a placeholder or force them to pick one.
        # It's a reps' balance sheet. Let's redirect if none picked, or give empty state.
        pass

    report_data = []

    # Prepare user lists for dropdowns
    outlets = Outlet.query.filter_by(is_active=True).order_by(Outlet.name).all() \
        if current_user.role in ['super_admin', 'general_manager', 'accountant'] else []
        
    sales_reps = User.query.filter_by(role='sales_rep').all()
    if current_user.role == 'outlet_admin':
        sales_reps = [u for u in sales_reps if u.outlet_id == current_user.outlet_id]
        
    if sales_rep_id:
        target_reps = [User.query.get(sales_rep_id)]
    elif current_user.role in ['outlet_admin', 'super_admin', 'general_manager', 'accountant']:
        # Admin didn't pick: optionally compute for all reps in selected outlet, or just demand selection.
        # Demanding selection is safer and cleaner for detailed views.
        if outlet_id:
            target_reps = [u for u in sales_reps if u.outlet_id == outlet_id]
        else:
            target_reps = []
    else:
        target_reps = []

    for rep in target_reps:
        if not rep:
            continue
            
        # 1. Total Collections up to yesterday (Exclude today)
        total_col_past = db.session.query(func.sum(CashCollection.amount))\
            .filter(CashCollection.sales_rep_id == rep.id, CashCollection.is_reversal == False, CashCollection.collection_date < target_date)\
            .scalar() or 0
        total_col_rev_past = db.session.query(func.sum(CashCollection.amount))\
            .filter(CashCollection.sales_rep_id == rep.id, CashCollection.is_reversal == True, CashCollection.collection_date < target_date)\
            .scalar() or 0
            
        # 2. Total Remittances + Expenses up to yesterday
        total_rem_past = db.session.query(func.sum(Remittance.amount))\
            .filter(Remittance.sales_rep_id == rep.id, Remittance.remittance_date < target_date)\
            .scalar() or 0
        total_exp_past = db.session.query(func.sum(Expense.amount))\
            .filter(Expense.recorded_by == rep.id, Expense.expense_date < target_date, Expense.status != 'rejected')\
            .scalar() or 0
            
        yesterday_outstanding = max(0, (total_col_past - total_col_rev_past) - (total_rem_past + total_exp_past))
        
        # 3. Today's Collections (split into actual sales and repayments)
        today_collections = CashCollection.query.filter(
            CashCollection.sales_rep_id == rep.id,
            CashCollection.collection_date == target_date,
            CashCollection.is_reversal == False
        ).all()
        
        today_sales_revenue = sum(c.amount for c in today_collections if c.source_type == 'sale')
        today_repayments = sum(c.amount for c in today_collections if c.source_type == 'repayment')
        today_other_in = sum(c.amount for c in today_collections if c.source_type not in ['sale', 'repayment'])
        
        # 4. Today's Expenses and Remittances
        today_exp = db.session.query(func.sum(Expense.amount))\
            .filter(Expense.recorded_by == rep.id, Expense.expense_date == target_date, Expense.status != 'rejected')\
            .scalar() or 0
            
        today_rem = db.session.query(func.sum(Remittance.amount))\
            .filter(Remittance.sales_rep_id == rep.id, Remittance.remittance_date == target_date)\
            .scalar() or 0
            
        # Leftover matching the prompt: non-credit sales + repayment + yesterday - today expenses - today remittance
        leftover = yesterday_outstanding + today_sales_revenue + today_repayments + today_other_in - today_exp - today_rem
        
        report_data.append({
            'sales_rep': rep,
            'yesterday_outstanding': yesterday_outstanding,
            'today_sales': today_sales_revenue,
            'today_repayments': today_repayments,
            'today_other_in': today_other_in,
            'today_exp': today_exp,
            'today_rem': today_rem,
            'leftover': leftover
        })

    selected_outlet = Outlet.query.get(outlet_id) if outlet_id else None

    cumulative_data = None
    if report_data and current_user.role != 'sales_rep' and len(report_data) >= 1:
        cumulative_data = {
            'yesterday_outstanding': sum(r['yesterday_outstanding'] for r in report_data),
            'today_sales': sum(r['today_sales'] for r in report_data),
            'today_repayments': sum(r['today_repayments'] for r in report_data),
            'today_other_in': sum(r['today_other_in'] for r in report_data),
            'today_exp': sum(r['today_exp'] for r in report_data),
            'today_rem': sum(r['today_rem'] for r in report_data),
            'leftover': sum(r['leftover'] for r in report_data),
            'outlet_name': selected_outlet.name if selected_outlet else 'All Outlets'
        }

    if request.args.get('format') == 'pdf':
        response = make_response(render_template('reports/pdf/daily_balance_sheet.html',
                           report_data=report_data,
                           cumulative_data=cumulative_data,
                           outlets=outlets,
                           sales_reps=sales_reps,
                           selected_outlet=selected_outlet,
                           outlet_id=outlet_id,
                           sales_rep_id=sales_rep_id,
                           target_date=target_date,
                           app_name=current_app.config.get('APP_NAME', 'Point of Sale'),
                           company_name=current_app.config.get('COMPANY_NAME', 'POS System'),
                           generated_by=current_user.full_name,
                           generated_at=datetime.now()))
        response.headers['Content-Type'] = 'text/html'
        return response

    return render_template('reports/daily_balance_sheet.html',
                           report_data=report_data,
                           cumulative_data=cumulative_data,
                           outlets=outlets,
                           sales_reps=sales_reps,
                           selected_outlet=selected_outlet,
                           outlet_id=outlet_id,
                           sales_rep_id=sales_rep_id,
                           target_date=target_date)

