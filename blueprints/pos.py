from flask import Blueprint, render_template, request, jsonify, session, url_for
from flask_login import login_required, current_user
from models import db, Product, Sale, SaleItem, SalePayment, Inventory, Customer, PaymentMode, InventoryAdjustment
from models.remittance_model import CashCollection
from utils.pricing import get_effective_price, get_all_tiers_for_product
from datetime import datetime, date
from decimal import Decimal
from functools import wraps
from sqlalchemy import or_

pos_bp = Blueprint('pos', __name__, url_prefix='/pos')

# Roles with cross-outlet (platform-wide) access
POS_PLATFORM_WIDE_ROLES = ['super_admin', 'general_manager']


def _collection_type_from_mode(payment_mode):
    """Map a PaymentMode to a CashCollection collection_type string."""
    if payment_mode is None:
        return 'other'
    code = (payment_mode.code or '').lower()
    name = (payment_mode.name or '').lower()
    if 'cash' in code or 'cash' in name:
        return 'cash'
    if 'bank' in code or 'transfer' in code or 'bank' in name or 'transfer' in name:
        return 'bank_transfer'
    if 'mobile' in code or 'mobile' in name or 'momo' in code:
        return 'mobile_money'
    return 'other'


def _generate_collection_number():
    """Generate unique COL-YYYY-NNNN number (local copy to avoid circular import)."""
    year = datetime.now().year
    last = CashCollection.query.filter(
        CashCollection.collection_number.like(f'COL-{year}-%')
    ).order_by(CashCollection.id.desc()).first()
    if last:
        try:
            num = int(last.collection_number.split('-')[-1]) + 1
        except ValueError:
            num = 1
    else:
        num = 1
    return f'COL-{year}-{num:04d}'


def _auto_collect_sale(sale, amount, outlet_id, payment_mode, split_payments_data=None):
    """
    Create a CashCollection entry for the sales rep after a non-credit sale.
    For split payments, we create one aggregated entry.
    This must be called BEFORE db.session.commit() so it participates in the same transaction.
    """
    if payment_mode and getattr(payment_mode, 'is_credit', False):
        return  # Credit sale — nothing to collect

    if sale.is_split_payment:
        col_type = 'other'  # split → aggregate as 'other'
    else:
        col_type = _collection_type_from_mode(payment_mode)

    collection = CashCollection(
        collection_number=_generate_collection_number(),
        sales_rep_id=sale.sales_rep_id,
        outlet_id=outlet_id,
        collection_date=date.today(),
        collection_type=col_type,
        amount=amount,
        payment_mode_id=payment_mode.id if (payment_mode and not sale.is_split_payment) else None,
        source_description=f'Auto-collected from Sale #{sale.sale_number}',
        source_type='sale',
        source_id=sale.id,
        is_reversal=False,
        notes='Automatically credited from POS checkout'
    )
    db.session.add(collection)

def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                return jsonify({'error': 'Unauthorized access'}), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@pos_bp.route('/')
@login_required
def index():
    if current_user.role not in ['super_admin', 'general_manager', 'outlet_admin', 'sales_rep']:
        return render_template('errors/403.html'), 403
        
    # Get products with stock for current outlet
    # For Super Admin/GM, prompt to select outlet? Or default to Warehouse? 
    # Requirement says they can access any. For now, let's assume they pick one or we show all? 
    # Implementation Plan says "Outlet Admin: own outlet", "Sales Rep: own outlet".
    # For Super/GM, maybe they need to context switch. 
    # For v1, let's use current_user.outlet_id. If None (Super/GM), maybe default to Warehouse or allow selection?
    # Let's assume for now they operate on a specific outlet context. 
    # If outlet_id is None, we might need a selector. 
    # Simplified: Use query param ?outlet_id=X or session. 
    # For this chunk, let's stick to current_user.outlet_id if present, else 1 (Warehouse) or handle gracefully.
    
    outlet_id = current_user.outlet_id or 1 # Default to warehouse or handle selection later
    
    # Fetch active payment modes
    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
    
    return render_template('pos/checkout.html', 
                           outlet_id=outlet_id,
                           payment_modes=payment_modes)

@pos_bp.route('/products/search', methods=['GET'])
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def search_products():
    """AJAX endpoint for product search in POS"""
    query = request.args.get('q', '').strip()
    outlet_id = request.args.get('outlet_id', type=int)
    
    # Validate outlet access
    if current_user.role in ['outlet_admin', 'sales_rep']:
        if outlet_id and outlet_id != current_user.outlet_id:
             # Ideally we enforce this, but for now let's just default to their outlet if mismatch?
             # Or return error. The request says "Validate outlet access".
             return jsonify({'error': 'Unauthorized outlet access'}), 403
        if not outlet_id:
            outlet_id = current_user.outlet_id
    
    # Build query
    products_query = Product.query.filter(Product.is_active == True)
    
    # Search filter (if query provided)
    if query:
        search_filter = db.or_(
            Product.sku.ilike(f'%{query}%'),
            Product.name.ilike(f'%{query}%')
        )
        products_query = products_query.filter(search_filter)
    
    # Join with inventory to get stock at outlet
    # We must alias Inventory or just use it directly if no conflict
    products_query = products_query.join(
        Inventory,
        db.and_(
            Inventory.product_id == Product.id,
            Inventory.outlet_id == outlet_id
        ),
        isouter=False  # Only products with inventory at this outlet? User code says isouter=False
    ).filter(Inventory.quantity > 0)  # Only in-stock products
    
    # Limit results
    limit = request.args.get('limit', 50, type=int)
    products = products_query.all()
    
    # Format response
    results = []
    for product in products:
        inventory = Inventory.query.filter_by(
            product_id=product.id,
            outlet_id=outlet_id
        ).first()
        
        # Only include products with stock at this outlet
        if inventory and inventory.quantity > 0:
            # Get default price (quantity=1 gives consumer/lowest tier or fallback)
            default_price = get_effective_price(product.id, outlet_id, 1)
            tiers = get_all_tiers_for_product(product.id, outlet_id)
            results.append({
                'id': product.id,
                'sku': product.sku,
                'name': product.name,
                'selling_price': float(default_price),
                'unit_price': float(default_price),
                'available_stock': float(inventory.quantity),
                'unit': product.unit or 'piece',
                'has_slates': product.has_slates,
                'slates_per_unit': product.slates_per_unit or 1,
                'price_tiers': tiers,  # Tiers for POS to show price breaks
            })
    
    # Sort by name and limit
    results.sort(key=lambda x: x['name'])
    results = results[:limit]
    
    return jsonify(results)

@pos_bp.route('/cart/add', methods=['POST'])
@login_required
def add_to_cart():
    data = request.json
    product_id = data.get('product_id')
    quantity = float(data.get('quantity', 1))
    outlet_id = data.get('outlet_id') or current_user.outlet_id or 1
    
    if quantity <= 0:
        return jsonify({'error': 'Quantity must be positive'}), 400

    product = Product.query.get_or_404(product_id)
    if not product.is_active:
         return jsonify({'error': 'Product is not active'}), 400

    # Check stock
    inventory = Inventory.query.filter_by(product_id=product_id, outlet_id=outlet_id).first()
    available_stock = inventory.quantity if inventory else 0
    
    cart = session.get('cart', [])
    
    # Check existing
    existing_item = next((item for item in cart if item['product_id'] == product_id), None)
    current_qty_in_cart = existing_item['quantity'] if existing_item else 0
    
    if current_qty_in_cart + quantity > available_stock:
        return jsonify({'error': f'Insufficient stock. Only {available_stock} available.'}), 400

    if existing_item:
        new_qty = existing_item['quantity'] + quantity
        # Recalculate price for the new total quantity (tier may change)
        effective_price = float(get_effective_price(product.id, outlet_id, new_qty))
        existing_item['quantity'] = new_qty
        existing_item['unit_price'] = effective_price
        existing_item['subtotal'] = effective_price * new_qty
    else:
        effective_price = float(get_effective_price(product.id, outlet_id, quantity))
        cart.append({
            'product_id': product.id,
            'sku': product.sku,
            'name': product.name,
            'unit_price': effective_price,
            'quantity': quantity,
            'subtotal': effective_price * quantity,
            'available_stock': available_stock
        })
    
    session['cart'] = cart
    session.modified = True
    
    return jsonify({
        'success': True, 
        'cart': cart, 
        'cart_total': sum(item['subtotal'] for item in cart),
        'cart_count': len(cart)
    })

@pos_bp.route('/cart/update', methods=['POST'])
@login_required
def update_cart():
    data = request.json
    product_id = data.get('product_id')
    quantity = float(data.get('quantity'))
    outlet_id = data.get('outlet_id') or current_user.outlet_id or 1
    
    if quantity <= 0:
        return jsonify({'error': 'Quantity must be positive'}), 400

    inventory = Inventory.query.filter_by(product_id=product_id, outlet_id=outlet_id).first()
    available_stock = inventory.quantity if inventory else 0
    
    if quantity > available_stock:
         return jsonify({'error': f'Insufficient stock. Only {available_stock} available.'}), 400

    cart = session.get('cart', [])
    existing_item = next((item for item in cart if item['product_id'] == product_id), None)
    
    if existing_item:
        # Recalculate price for the new total quantity (tier may change)
        effective_price = float(get_effective_price(product_id, outlet_id, quantity))
        existing_item['quantity'] = quantity
        existing_item['unit_price'] = effective_price
        existing_item['subtotal'] = effective_price * quantity
        session['cart'] = cart
        session.modified = True
        return jsonify({
            'success': True, 
            'cart': cart, 
            'cart_total': sum(item['subtotal'] for item in cart)
        })
    
    return jsonify({'error': 'Item not in cart'}), 404

@pos_bp.route('/cart/remove', methods=['POST'])
@login_required
def remove_from_cart():
    data = request.json
    product_id = data.get('product_id')
    
    cart = session.get('cart', [])
    cart = [item for item in cart if item['product_id'] != product_id]
    
    session['cart'] = cart
    session.modified = True
    
    return jsonify({
        'success': True, 
        'cart': cart, 
        'cart_total': sum(item['subtotal'] for item in cart),
        'cart_count': len(cart)
    })

@pos_bp.route('/cart', methods=['GET'])
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def get_cart():
    """Get current cart from session"""
    cart = session.get('cart', [])
    cart_total = sum(item['subtotal'] for item in cart)
    
    return jsonify({
        'success': True,
        'cart': cart,
        'cart_total': cart_total,
        'cart_count': len(cart)
    })

@pos_bp.route('/cart/clear', methods=['POST'])
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def clear_cart():
    """Clear cart from session"""
    session.pop('cart', None)
    session.modified = True
    
    return jsonify({
        'success': True,
        'cart': [],
        'cart_total': 0,
        'cart_count': 0
    })

@pos_bp.route('/customers/search', methods=['GET'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def search_customers():
    """
    AJAX endpoint for customer search during POS checkout.
    Outlet-scoped roles (outlet_admin, sales_rep) only see customers
    belonging to their assigned outlet.
    Platform-wide roles see all customers.
    """
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 10, type=int)

    if not query:
        return jsonify([])

    search_term = f"%{query}%"

    base_query = Customer.query.filter(
        Customer.is_active == True,
        or_(
            Customer.first_name.ilike(search_term),
            Customer.last_name.ilike(search_term),
            Customer.phone.ilike(search_term),
            Customer.customer_number.ilike(search_term),
            Customer.email.ilike(search_term)
        )
    )

    # Apply outlet scoping for non-platform-wide roles
    if current_user.role not in POS_PLATFORM_WIDE_ROLES:
        # Include walk-in customer always (it's the catch-all), plus own-outlet customers
        base_query = base_query.filter(
            db.or_(
                Customer.primary_outlet_id == current_user.outlet_id,
                Customer.is_walk_in == True
            )
        )

    customers = base_query.limit(limit).all()

    results = []
    for customer in customers:
        available_credit = customer.credit_limit - customer.current_balance
        results.append({
            'id': customer.id,
            'customer_number': customer.customer_number,
            'name': f'{customer.first_name} {customer.last_name}',
            'phone': customer.phone,
            'email': customer.email,
            'credit_limit': float(customer.credit_limit),
            'current_balance': float(customer.current_balance),
            'available_credit': float(available_credit),
            'is_walk_in': customer.is_walk_in
        })

    return jsonify(results)


@pos_bp.route('/walkin-customer', methods=['GET'])
@login_required
def get_walkin_customer():
    """
    Returns the walk-in customer record.
    No outlet-scoping applied — the walk-in customer is universal and must always
    be accessible from any outlet's POS screen.
    """
    walk_in = Customer.query.filter_by(is_walk_in=True, is_active=True).first()
    if not walk_in:
        return jsonify({'error': 'Walk-in customer not configured. Contact administrator.'}), 404

    return jsonify({
        'id': walk_in.id,
        'customer_number': walk_in.customer_number,
        'name': f'{walk_in.first_name} {walk_in.last_name}',
        'phone': walk_in.phone,
        'email': walk_in.email,
        'credit_limit': 0,
        'current_balance': 0,
        'available_credit': 0,
        'is_walk_in': True
    })


def generate_sale_number():
    year = datetime.now().year
    # Find last sale number for this year
    last_sale = Sale.query.filter(Sale.sale_number.like(f'SALE-{year}-%')).order_by(Sale.id.desc()).first()
    if last_sale:
        last_num = int(last_sale.sale_number.split('-')[-1])
        new_num = last_num + 1
    else:
        new_num = 1
    return f'SALE-{year}-{new_num:04d}'

@pos_bp.route('/checkout', methods=['POST'])
@login_required
def checkout():
    data = request.json
    customer_id = data.get('customer_id')
    payment_type = data.get('payment_type') # 'single' or 'split'
    payment_mode_id = data.get('payment_mode_id')
    split_payments = data.get('split_payments', [])
    transaction_reference = data.get('transaction_reference')
    notes = data.get('notes')
    outlet_id = data.get('outlet_id') or current_user.outlet_id or 1

    cart = session.get('cart', [])
    if not cart:
        return jsonify({'error': 'Cart is empty'}), 400

    if not customer_id:
        return jsonify({'error': 'Customer is required'}), 400
        
    customer = Customer.query.get(customer_id)
    if not customer or not customer.is_active:
        return jsonify({'error': 'Invalid customer'}), 400

    # Outlet-scope enforcement: outlet_admin and sales_rep can only sell
    # to their own outlet's customers (walk-in customers are always allowed)
    if current_user.role not in POS_PLATFORM_WIDE_ROLES:
        if not customer.is_walk_in and customer.primary_outlet_id != current_user.outlet_id:
            return jsonify({'error': 'You can only sell to customers registered at your outlet.'}), 403

    cart_total = sum(item['subtotal'] for item in cart)
    
    # Payment Validation
    if payment_type == 'single':
        mode = PaymentMode.query.get(payment_mode_id)
        if not mode or not mode.is_active:
            return jsonify({'error': 'Invalid payment mode'}), 400
        
        if customer.is_walk_in and mode.is_credit:
            return jsonify({'error': 'Walk-in customers cannot use Credit'}), 400

        if mode.requires_reference and not transaction_reference:
            return jsonify({'error': f'Reference required for {mode.name}'}), 400
            
        if mode.is_credit:
            available_credit = customer.credit_limit - customer.current_balance
            if cart_total > available_credit:
                return jsonify({'error': f'Credit limit exceeded. Available: {available_credit}'}), 400
                
    elif payment_type == 'split':
        if len(split_payments) < 2:
            return jsonify({'error': 'Split payment requires at least 2 modes'}), 400
            
        split_total = sum(float(p['amount']) for p in split_payments)
        if abs(split_total - cart_total) > 0.01:
            return jsonify({'error': f'Payment total ({split_total}) does not match cart ({cart_total})'}), 400
            
        for p in split_payments:
            pm = PaymentMode.query.get(p['payment_mode_id'])
            if pm.is_credit:
                return jsonify({'error': 'Credit cannot be used in split payments'}), 400
            if pm.requires_reference and not p.get('reference'):
                return jsonify({'error': f'Reference required for {pm.name}'}), 400

    try:
        # Atomic Transaction
        sale_number = generate_sale_number()
        
        sale = Sale(
            sale_number=sale_number,
            outlet_id=outlet_id,
            customer_id=customer_id,
            sales_rep_id=current_user.id,
            total_amount=cart_total,
            payment_mode_id=payment_mode_id if payment_type == 'single' else None,
            is_split_payment=(payment_type == 'split'),
            transaction_reference=transaction_reference if payment_type == 'single' else None,
            notes=notes,
            status='completed'
        )
        db.session.add(sale)
        db.session.flush()

        # Deduct Inventory & Create Items
        # SERVER-SIDE PRICE VALIDATION: re-compute the authoritative price for each item
        # and reject if the submitted price deviates beyond a rounding tolerance (₦0.01).
        # This prevents any client-side price manipulation.
        server_cart_total = Decimal('0')
        for item in cart:
            # Lock inventory row (prevents race conditions)
            inventory = Inventory.query.filter_by(
                product_id=item['product_id'], 
                outlet_id=outlet_id
            ).with_for_update().first()
            
            if not inventory or inventory.quantity < item['quantity']:
                raise Exception(f"Insufficient stock for {item['name']}")
            
            # ── Anti-Fraud: Server-Side Price Enforcement ──────────────────
            authoritative_price = get_effective_price(
                item['product_id'], outlet_id, item['quantity']
            )
            submitted_price = Decimal(str(item.get('unit_price', 0)))
            if abs(authoritative_price - submitted_price) > Decimal('0.01'):
                raise Exception(
                    f"Price mismatch for '{item['name']}': "
                    f"submitted ₦{submitted_price:.2f} but server computed ₦{authoritative_price:.2f}. "
                    f"Please refresh the POS and try again."
                )
            # ──────────────────────────────────────────────────────────────

            authoritative_subtotal = authoritative_price * Decimal(str(item['quantity']))
            server_cart_total += authoritative_subtotal

            inventory.quantity -= item['quantity']
            
            # Log adjustment
            adj = InventoryAdjustment(
                product_id=item['product_id'],
                outlet_id=outlet_id,
                adjustment_type='sale',
                quantity_before=inventory.quantity + item['quantity'],
                quantity_change=-item['quantity'],
                quantity_after=inventory.quantity,
                reason=f'Sale: {sale_number}',
                reference_number=sale_number,
                adjusted_by=current_user.id
            )
            db.session.add(adj)
            
            # Sale Item — always uses the server-computed authoritative price
            sale_item = SaleItem(
                sale_id=sale.id,
                product_id=item['product_id'],
                quantity=item['quantity'],
                unit_price=authoritative_price,
                subtotal=authoritative_subtotal
            )
            db.session.add(sale_item)

        # Use server-computed total (not client-submitted cart_total)
        sale.total_amount = server_cart_total
        cart_total = float(server_cart_total)  # Update local var for payment logic below
            
        # Handle Payments
        if payment_type == 'split':
            for p in split_payments:
                sp = SalePayment(
                    sale_id=sale.id,
                    payment_mode_id=p['payment_mode_id'],
                    amount=p['amount'],
                    transaction_reference=p.get('reference')
                )
                db.session.add(sp)
        
        # Update Credit Balance
        if payment_type == 'single':
            mode = PaymentMode.query.get(payment_mode_id)
            if mode.is_credit:
                customer.current_balance = float(customer.current_balance) + cart_total
            else:
                # Non-credit single payment → auto-collect for sales rep
                _auto_collect_sale(sale, cart_total, outlet_id, mode)
        elif payment_type == 'split':
            # Split payment is never credit → auto-collect aggregate
            _auto_collect_sale(sale, cart_total, outlet_id, None)
                
        db.session.commit()
        session.pop('cart', None)
        
        return jsonify({
            'success': True,
            'sale_id': sale.id,
            'redirect': url_for('sales.detail', id=sale.id)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
