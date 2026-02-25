from flask import Blueprint, render_template, redirect, url_for, flash, request, make_response
from flask_login import login_required, current_user
from models import db, Product, Category, Inventory, InventoryAdjustment, Outlet, StockTransfer
from utils.decorators import role_required
from sqlalchemy.exc import IntegrityError
from decimal import Decimal
from datetime import datetime

products = Blueprint('products', __name__)

@products.route('/products/categories', methods=['GET', 'POST'])
@login_required
@role_required(['super_admin', 'general_manager'])
def categories():
    """Manage product categories"""
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'create':
            name = request.form.get('name')
            description = request.form.get('description', '')
            
            if Category.query.filter_by(name=name).first():
                flash('Category already exists.', 'danger')
            else:
                new_cat = Category(name=name, description=description)
                db.session.add(new_cat)
                db.session.commit()
                flash('Category created successfully.', 'success')
                
        elif action == 'toggle_status':
            cat_id = request.form.get('category_id')
            cat = Category.query.get(cat_id)
            if cat:
                cat.is_active = not cat.is_active
                db.session.commit()
                flash(f"Category {'activated' if cat.is_active else 'deactivated'} successfully.", 'success')
                
        return redirect(url_for('products.categories'))

    categories = Category.query.all()
    return render_template('products/categories.html', categories=categories)

@products.route('/products')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    category_id = request.args.get('category_id', type=int)
    stock_status = request.args.get('stock_status', 'all')
    
    query = Product.query
    
    # Filter by search
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Product.name.ilike(search_term)) |
            (Product.sku.ilike(search_term)) |
            (Product.description.ilike(search_term))
        )
    
    # Filter by category
    if category_id:
        query = query.filter_by(category_id=category_id)
        
    # Filter by stock status (Warehouse level for now)
    if stock_status != 'all':
        warehouse = Outlet.query.get(1) # Central Warehouse
        if warehouse:
            if stock_status == 'out_of_stock':
                query = query.join(Inventory).filter(Inventory.outlet_id == 1, Inventory.quantity == 0)
            elif stock_status == 'low_stock':
                query = query.join(Inventory).filter(Inventory.outlet_id == 1, Inventory.quantity <= Product.reorder_level, Inventory.quantity > 0)
            elif stock_status == 'in_stock':
                 query = query.join(Inventory).filter(Inventory.outlet_id == 1, Inventory.quantity > Product.reorder_level)

    # Ordering
    pagination = query.order_by(Product.name.asc()).paginate(page=page, per_page=per_page, error_out=False)
    categories = Category.query.filter_by(is_active=True).all()
    
    return render_template('products/list.html', products=pagination.items, pagination=pagination, categories=categories, search=search, category_id=category_id, stock_status=stock_status)

@products.route('/products/create', methods=['GET', 'POST'])
@login_required
@role_required(['super_admin'])
def create():
    categories = Category.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        sku = request.form.get('sku').upper()
        name = request.form.get('name')
        category_id = request.form.get('category_id')
        cost_price = Decimal(request.form.get('cost_price'))
        selling_price = Decimal(request.form.get('selling_price'))
        reorder_level = int(request.form.get('reorder_level', 10))
        unit = request.form.get('unit', 'piece')
        description = request.form.get('description')
        initial_stock = int(request.form.get('initial_stock', 0))
        
        # Validation
        if Product.query.filter_by(sku=sku).first():
            flash('SKU already exists.', 'danger')
            return render_template('products/create.html', categories=categories)
            
        new_product = Product(
            sku=sku,
            name=name,
            category_id=category_id,
            cost_price=cost_price,
            selling_price=selling_price,
            reorder_level=reorder_level,
            unit=unit,
            description=description,
            created_by=current_user.id
        )
        
        try:
            db.session.add(new_product)
            db.session.flush() # Get ID
            
            # Initial Stock (Warehouse)
            if initial_stock > 0:
                warehouse = Outlet.query.get(1)
                inventory = Inventory(
                    product_id=new_product.id,
                    outlet_id=warehouse.id,
                    quantity=initial_stock
                )
                db.session.add(inventory)
                
                # Audit Trail
                adjustment = InventoryAdjustment(
                    product_id=new_product.id,
                    outlet_id=warehouse.id,
                    adjustment_type='initial_stock',
                    quantity_before=0,
                    quantity_change=initial_stock,
                    quantity_after=initial_stock,
                    reason='Initial stock on product creation',
                    adjusted_by=current_user.id
                )
                db.session.add(adjustment)
            
            db.session.commit()
            flash('Product created successfully.', 'success')
            return redirect(url_for('products.detail', id=new_product.id))
            
        except IntegrityError:
            db.session.rollback()
            flash('Error creating product. Please check inputs.', 'danger')
            
    return render_template('products/create.html', categories=categories)

@products.route('/products/<int:id>')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def detail(id):
    product = Product.query.get_or_404(id)
    warehouse = Outlet.query.get(1)

    # Get warehouse inventory
    inventory = Inventory.query.filter_by(product_id=id, outlet_id=warehouse.id).first()
    warehouse_stock = inventory.quantity if inventory else 0

    # ── Inventory History (Super Admin & General Manager only) ──────────────
    history = []
    outlets = []
    total_history = 0
    ADMIN_ROLES = ['super_admin', 'general_manager']

    # Pagination / filter params
    page         = request.args.get('page', 1, type=int)
    per_page     = 20
    filter_outlet= request.args.get('outlet_id', '', type=str)
    date_from    = request.args.get('date_from', '')
    date_to      = request.args.get('date_to', '')
    filter_type  = request.args.get('type', 'all')  # all | adjustment | transfer

    if current_user.role in ADMIN_ROLES:
        outlets = Outlet.query.filter_by(is_active=True).order_by(Outlet.id).all()

        # ── Parse dates ────────────────────────────────────────────────────
        dt_from = None
        dt_to   = None
        try:
            if date_from:
                dt_from = datetime.strptime(date_from, '%Y-%m-%d')
            if date_to:
                dt_to   = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

        outlet_id_int = int(filter_outlet) if filter_outlet else None

        # ── Adjustments query ───────────────────────────────────────────────
        adj_rows = []
        if filter_type in ('all', 'adjustment'):
            aq = InventoryAdjustment.query.filter_by(product_id=id)
            if outlet_id_int:
                aq = aq.filter(InventoryAdjustment.outlet_id == outlet_id_int)
            if dt_from:
                aq = aq.filter(InventoryAdjustment.adjusted_at >= dt_from)
            if dt_to:
                aq = aq.filter(InventoryAdjustment.adjusted_at <= dt_to)
            for a in aq.all():
                adj_rows.append({
                    'date':      a.adjusted_at,
                    'type':      'Adjustment',
                    'subtype':   a.adjustment_type.replace('_', ' ').title(),
                    'outlet':    a.outlet.name if a.outlet else '—',
                    'reference': a.reference_number or '—',
                    'change':    a.quantity_change,
                    'before':    a.quantity_before,
                    'after':     a.quantity_after,
                    'note':      a.reason,
                    'by':        a.user.full_name if a.user else '—',
                })

        # ── Transfers query ─────────────────────────────────────────────────
        tr_rows = []
        if filter_type in ('all', 'transfer'):
            from sqlalchemy import or_ as sql_or
            tq = StockTransfer.query.filter(
                StockTransfer.product_id == id,
                StockTransfer.status == 'completed'
            )
            if outlet_id_int:
                tq = tq.filter(
                    sql_or(
                        StockTransfer.from_outlet_id == outlet_id_int,
                        StockTransfer.to_outlet_id   == outlet_id_int
                    )
                )
            if dt_from:
                tq = tq.filter(StockTransfer.received_at >= dt_from)
            if dt_to:
                tq = tq.filter(StockTransfer.received_at <= dt_to)
            for t in tq.all():
                direction = 'Sent' if (outlet_id_int and t.from_outlet_id == outlet_id_int) else 'Received'
                tr_rows.append({
                    'date':      t.received_at or t.requested_at,
                    'type':      'Transfer',
                    'subtype':   direction,
                    'outlet':    f"{t.from_outlet.name} → {t.to_outlet.name}",
                    'reference': t.transfer_number,
                    'change':    -t.quantity if direction == 'Sent' else t.quantity,
                    'before':    None,
                    'after':     None,
                    'note':      t.notes or '—',
                    'by':        t.requester.full_name if t.requester else '—',
                })

        # ── Merge, sort, paginate ───────────────────────────────────────────
        merged = sorted(adj_rows + tr_rows, key=lambda x: x['date'] or datetime.min, reverse=True)
        total_history = len(merged)
        total_pages   = max(1, (total_history + per_page - 1) // per_page)
        page          = min(page, total_pages)
        start         = (page - 1) * per_page
        history       = merged[start: start + per_page]
    else:
        total_pages = 1

    return render_template(
        'products/detail.html',
        product=product,
        warehouse_stock=warehouse_stock,
        # legacy name kept so existing template lines still work if any
        adjustments=history,
        # new names for enhanced template
        history=history,
        outlets=outlets,
        filter_outlet=filter_outlet,
        date_from=date_from,
        date_to=date_to,
        filter_type=filter_type,
        page=page,
        total_pages=total_pages,
        total_history=total_history,
        per_page=per_page,
        now=datetime.now(),
    )


@products.route('/products/<int:id>/history/pdf')
@login_required
@role_required(['super_admin', 'general_manager'])
def history_pdf(id):
    """Renders a print-ready A4 inventory history page (browser prints/saves to PDF)."""
    product = Product.query.get_or_404(id)

    filter_outlet = request.args.get('outlet_id', '', type=str)
    date_from     = request.args.get('date_from', '')
    date_to       = request.args.get('date_to', '')
    filter_type   = request.args.get('type', 'all')

    dt_from = None
    dt_to   = None
    try:
        if date_from:
            dt_from = datetime.strptime(date_from, '%Y-%m-%d')
        if date_to:
            dt_to   = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    except ValueError:
        pass

    outlet_id_int = int(filter_outlet) if filter_outlet else None
    outlet_name   = ''
    if outlet_id_int:
        o = Outlet.query.get(outlet_id_int)
        outlet_name = o.name if o else ''

    adj_rows = []
    if filter_type in ('all', 'adjustment'):
        aq = InventoryAdjustment.query.filter_by(product_id=id)
        if outlet_id_int:
            aq = aq.filter(InventoryAdjustment.outlet_id == outlet_id_int)
        if dt_from:
            aq = aq.filter(InventoryAdjustment.adjusted_at >= dt_from)
        if dt_to:
            aq = aq.filter(InventoryAdjustment.adjusted_at <= dt_to)
        for a in aq.all():
            adj_rows.append({
                'date':      a.adjusted_at,
                'type':      'Adjustment',
                'subtype':   a.adjustment_type.replace('_', ' ').title(),
                'outlet':    a.outlet.name if a.outlet else '—',
                'reference': a.reference_number or '—',
                'change':    a.quantity_change,
                'before':    a.quantity_before,
                'after':     a.quantity_after,
                'note':      a.reason,
                'by':        a.user.full_name if a.user else '—',
            })

    tr_rows = []
    if filter_type in ('all', 'transfer'):
        from sqlalchemy import or_ as sql_or
        tq = StockTransfer.query.filter(
            StockTransfer.product_id == id,
            StockTransfer.status == 'completed'
        )
        if outlet_id_int:
            tq = tq.filter(
                sql_or(
                    StockTransfer.from_outlet_id == outlet_id_int,
                    StockTransfer.to_outlet_id   == outlet_id_int
                )
            )
        if dt_from:
            tq = tq.filter(StockTransfer.received_at >= dt_from)
        if dt_to:
            tq = tq.filter(StockTransfer.received_at <= dt_to)
        for t in tq.all():
            direction = 'Sent' if (outlet_id_int and t.from_outlet_id == outlet_id_int) else 'Received'
            tr_rows.append({
                'date':      t.received_at or t.requested_at,
                'type':      'Transfer',
                'subtype':   direction,
                'outlet':    f"{t.from_outlet.name} → {t.to_outlet.name}",
                'reference': t.transfer_number,
                'change':    -t.quantity if direction == 'Sent' else t.quantity,
                'before':    None,
                'after':     None,
                'note':      t.notes or '—',
                'by':        t.requester.full_name if t.requester else '—',
            })

    history = sorted(adj_rows + tr_rows, key=lambda x: x['date'] or datetime.min, reverse=True)

    html = render_template(
        'products/history_pdf.html',
        product=product,
        history=history,
        outlet_name=outlet_name,
        date_from=date_from,
        date_to=date_to,
        filter_type=filter_type,
        now=datetime.now(),
        generated_by=current_user.full_name,
    )
    response = make_response(html)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response

@products.route('/products/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(['super_admin'])
def edit(id):
    product = Product.query.get_or_404(id)
    categories = Category.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        product.name = request.form.get('name')
        product.category_id = request.form.get('category_id')
        product.cost_price = Decimal(request.form.get('cost_price'))
        product.selling_price = Decimal(request.form.get('selling_price'))
        product.reorder_level = int(request.form.get('reorder_level'))
        product.unit = request.form.get('unit')
        product.description = request.form.get('description')
        
        db.session.commit()
        flash('Product updated successfully.', 'success')
        return redirect(url_for('products.detail', id=product.id))
        
    return render_template('products/edit.html', product=product, categories=categories)

@products.route('/products/<int:id>/adjust-inventory', methods=['GET', 'POST'])
@login_required
@role_required(['super_admin'])
def adjust_inventory(id):
    product = Product.query.get_or_404(id)
    warehouse = Outlet.query.get(1)
    
    # Ensure inventory record exists
    inventory = Inventory.query.filter_by(product_id=id, outlet_id=warehouse.id).first()
    if not inventory:
        inventory = Inventory(product_id=id, outlet_id=warehouse.id, quantity=0)
        db.session.add(inventory)
        db.session.commit()
    
    if request.method == 'POST':
        adjustment_type = request.form.get('adjustment_type')
        quantity_change = int(request.form.get('quantity_change'))
        reason = request.form.get('reason')
        reference_number = request.form.get('reference_number')
        
        quantity_before = inventory.quantity
        quantity_after = quantity_before + quantity_change
        
        if quantity_after < 0:
            flash(f'Adjustment would result in negative inventory ({quantity_after}).', 'danger')
            return render_template('products/adjust_inventory.html', product=product, current_stock=quantity_before)
            
        inventory.quantity = quantity_after
        
        adjustment = InventoryAdjustment(
            product_id=product.id,
            outlet_id=warehouse.id,
            adjustment_type=adjustment_type,
            quantity_before=quantity_before,
            quantity_change=quantity_change,
            quantity_after=quantity_after,
            reason=reason,
            reference_number=reference_number,
            adjusted_by=current_user.id
        )
        
        db.session.add(adjustment)
        db.session.commit()
        
        flash('Inventory adjusted successfully.', 'success')
        return redirect(url_for('products.detail', id=product.id))

    return render_template('products/adjust_inventory.html', product=product, current_stock=inventory.quantity)
