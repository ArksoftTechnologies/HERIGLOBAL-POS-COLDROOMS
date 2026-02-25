from flask import Blueprint, render_template, request, abort
from flask_login import login_required, current_user
from models import db, Product, Inventory, Outlet
from utils.decorators import role_required

inventory_bp = Blueprint('inventory', __name__)

@inventory_bp.route('/inventory/warehouse')
@login_required
@role_required(['super_admin', 'general_manager'])
def warehouse():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    stock_status = request.args.get('stock_status', 'all')
    
    warehouse = Outlet.query.get(1)
    query = db.session.query(Product, Inventory).join(Inventory).filter(Inventory.outlet_id == warehouse.id)
    
    # Stock Filters
    if stock_status == 'out_of_stock':
        query = query.filter(Inventory.quantity == 0)
    elif stock_status == 'low_stock':
        query = query.filter(Inventory.quantity <= Product.reorder_level, Inventory.quantity > 0)
        
    pagination = query.order_by(Product.name.asc()).paginate(page=page, per_page=per_page, error_out=False)
    
    # Summary Stats
    total_products = Inventory.query.filter_by(outlet_id=warehouse.id).count()
    total_value = 0
    all_items = db.session.query(Product, Inventory).join(Inventory).filter(Inventory.outlet_id == warehouse.id).all()
    for p, i in all_items:
        total_value += (p.cost_price * i.quantity)
        
    low_stock_count = db.session.query(Inventory).join(Product).filter(
        Inventory.outlet_id == warehouse.id,
        Inventory.quantity <= Product.reorder_level,
        Inventory.quantity > 0
    ).count()
    
    out_of_stock_count = Inventory.query.filter_by(outlet_id=warehouse.id, quantity=0).count()

    return render_template('inventory/warehouse.html', 
                           inventory=pagination.items, 
                           pagination=pagination,
                           total_products=total_products,
                           total_value=total_value,
                           low_stock_count=low_stock_count,
                           out_of_stock_count=out_of_stock_count,
                           stock_status=stock_status)

@inventory_bp.route('/inventory/warehouse/valuation')
@login_required
@role_required(['super_admin', 'general_manager', 'accountant'])
def valuation():
    warehouse = Outlet.query.get(1)
    inventory_items = db.session.query(Product, Inventory).join(Inventory).filter(Inventory.outlet_id == warehouse.id).all()
    
    total_cost_value = 0
    total_potential_revenue = 0
    
    valuation_data = []
    for p, i in inventory_items:
        cost_value = p.cost_price * i.quantity
        potential_rev = p.selling_price * i.quantity
        
        total_cost_value += cost_value
        total_potential_revenue += potential_rev
        
        valuation_data.append({
            'product': p,
            'quantity': i.quantity,
            'cost_value': cost_value,
            'potential_revenue': potential_rev,
            'potential_profit': potential_rev - cost_value
        })
        
    return render_template('inventory/valuation.html', 
                           valuation_data=valuation_data,
                           total_cost_value=total_cost_value,
                           total_potential_revenue=total_potential_revenue,
                           total_potential_profit=total_potential_revenue - total_cost_value)

@inventory_bp.route('/inventory/outlets')
@login_required
@role_required(['super_admin', 'general_manager'])
def outlets():
    # Only active outlets (excluding warehouse for this specific view if desired, but usually good to show all)
    all_outlets = Outlet.query.filter_by(is_active=True).order_by(Outlet.id).all()
    products = Product.query.filter_by(is_active=True).all()
    
    # Efficiently fetch all inventory
    inventory_records = Inventory.query.all()
    
    # Build a look-up map: {(product_id, outlet_id): quantity}
    stock_map = {(inv.product_id, inv.outlet_id): inv.quantity for inv in inventory_records}
    
    return render_template('inventory/outlets.html', 
                           outlets=all_outlets, 
                           products=products, 
                           stock_map=stock_map)

@inventory_bp.route('/inventory/outlet/<int:id>')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def outlet_detail(id):
    # Permission check for Outlet Admin and Sales Rep
    if current_user.role in ['outlet_admin', 'sales_rep'] and current_user.outlet_id != id:
        abort(403)
        
    outlet = Outlet.query.get_or_404(id)
    inventory = Inventory.query.filter_by(outlet_id=id).join(Product).all()
    
    # Stats
    total_items = len(inventory)
    total_value = sum(item.quantity * item.product.cost_price for item in inventory)
    low_stock = sum(1 for item in inventory if item.quantity <= item.product.reorder_level and item.quantity > 0)
    
    return render_template('inventory/outlet_detail.html', 
                           outlet=outlet, 
                           inventory=inventory,
                           total_items=total_items,
                           total_value=total_value,
                           low_stock=low_stock)
