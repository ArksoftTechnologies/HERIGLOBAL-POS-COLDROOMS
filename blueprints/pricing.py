from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from models import db, Product, Outlet, ProductPriceTier, OutletProductPrice
from utils.decorators import role_required
from decimal import Decimal, InvalidOperation
from sqlalchemy.exc import IntegrityError

pricing_bp = Blueprint('pricing', __name__, url_prefix='/admin/pricing')

VALID_TIER_NAMES = ['consumer', 'retail', 'wholesale']


# ─── Helpers ────────────────────────────────────────────────────────────────

def _validate_tier_ranges(tiers_for_product, exclude_id=None):
    """
    Ensure no two active tiers for the same product have overlapping ranges.
    Returns (True, None) if ok, else (False, error_message).
    """
    active = [t for t in tiers_for_product if t.is_active and t.id != exclude_id]
    for i, a in enumerate(active):
        a_max = a.max_qty if a.max_qty is not None else float('inf')
        for b in active[i + 1:]:
            b_max = b.max_qty if b.max_qty is not None else float('inf')
            # Overlap test: a starts before b ends AND b starts before a ends
            if a.min_qty <= b_max and b.min_qty <= a_max:
                return False, (
                    f"Quantity range {a.min_qty}–{a.max_qty or '∞'} ({a.tier_name}) "
                    f"overlaps with {b.min_qty}–{b.max_qty or '∞'} ({b.tier_name})."
                )
    return True, None


# ─── Global Pricing Overview ────────────────────────────────────────────────

@pricing_bp.route('/')
@login_required
@role_required(['super_admin'])
def index():
    """List all products with their tier configurations."""
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    q = Product.query.filter_by(is_active=True)
    if search:
        q = q.filter(
            db.or_(
                Product.name.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%')
            )
        )
    pagination = q.order_by(Product.name.asc()).paginate(page=page, per_page=per_page, error_out=False)

    # Attach tier counts for display
    products_with_tiers = []
    for product in pagination.items:
        tier_count = ProductPriceTier.query.filter_by(product_id=product.id, is_active=True).count()
        products_with_tiers.append({
            'product': product,
            'tier_count': tier_count,
        })

    return render_template(
        'pricing/index.html',
        products_with_tiers=products_with_tiers,
        pagination=pagination,
        search=search,
    )


# ─── Global Tiers for a Product ─────────────────────────────────────────────

@pricing_bp.route('/product/<int:product_id>/tiers')
@login_required
@role_required(['super_admin'])
def product_tiers(product_id):
    """View and manage global price tiers for a specific product."""
    product = Product.query.get_or_404(product_id)
    tiers = (
        ProductPriceTier.query
        .filter_by(product_id=product_id)
        .order_by(ProductPriceTier.min_qty.asc())
        .all()
    )
    return render_template(
        'pricing/product_tiers.html',
        product=product,
        tiers=tiers,
        valid_tier_names=VALID_TIER_NAMES,
    )


@pricing_bp.route('/product/<int:product_id>/tiers/create', methods=['POST'])
@login_required
@role_required(['super_admin'])
def create_tier(product_id):
    product = Product.query.get_or_404(product_id)

    tier_name = request.form.get('tier_name', '').strip().lower()
    min_qty_str = request.form.get('min_qty', '').strip()
    max_qty_str = request.form.get('max_qty', '').strip()
    price_str = request.form.get('price', '').strip()

    # Validation
    if tier_name not in VALID_TIER_NAMES:
        flash(f'Invalid tier name. Must be one of: {", ".join(VALID_TIER_NAMES)}.', 'danger')
        return redirect(url_for('pricing.product_tiers', product_id=product_id))

    try:
        min_qty = int(min_qty_str)
        if min_qty < 1:
            raise ValueError
    except (ValueError, TypeError):
        flash('Minimum quantity must be a positive integer.', 'danger')
        return redirect(url_for('pricing.product_tiers', product_id=product_id))

    max_qty = None
    if max_qty_str:
        try:
            max_qty = int(max_qty_str)
            if max_qty < min_qty:
                flash('Maximum quantity cannot be less than minimum quantity.', 'danger')
                return redirect(url_for('pricing.product_tiers', product_id=product_id))
        except (ValueError, TypeError):
            flash('Maximum quantity must be a positive integer or blank (for unlimited).', 'danger')
            return redirect(url_for('pricing.product_tiers', product_id=product_id))

    try:
        price = Decimal(price_str)
        if price < 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        flash('Price must be a valid positive number.', 'danger')
        return redirect(url_for('pricing.product_tiers', product_id=product_id))

    # Overlap check
    existing_tiers = ProductPriceTier.query.filter_by(product_id=product_id).all()
    # Build a temp tier object for overlap checking
    class _TempTier:
        def __init__(self):
            self.id = None
            self.is_active = True
            self.min_qty = min_qty
            self.max_qty = max_qty
            self.tier_name = tier_name
    existing_tiers.append(_TempTier())
    ok, err = _validate_tier_ranges(existing_tiers, exclude_id=None)
    if not ok:
        flash(f'Range conflict: {err}', 'danger')
        return redirect(url_for('pricing.product_tiers', product_id=product_id))

    # Check that this tier_name is not already defined for this product (rename if needed)
    existing_same_name = ProductPriceTier.query.filter_by(
        product_id=product_id, tier_name=tier_name, is_active=True
    ).first()
    if existing_same_name:
        flash(f'A tier named "{tier_name}" already exists for this product. Edit or delete the existing one first.', 'danger')
        return redirect(url_for('pricing.product_tiers', product_id=product_id))

    tier = ProductPriceTier(
        product_id=product_id,
        tier_name=tier_name,
        min_qty=min_qty,
        max_qty=max_qty,
        price=price,
        is_active=True,
        created_by=current_user.id,
    )
    db.session.add(tier)
    db.session.commit()
    flash(f'Price tier "{tier_name}" created successfully.', 'success')
    return redirect(url_for('pricing.product_tiers', product_id=product_id))


@pricing_bp.route('/product/<int:product_id>/tiers/<int:tier_id>/edit', methods=['POST'])
@login_required
@role_required(['super_admin'])
def edit_tier(product_id, tier_id):
    product = Product.query.get_or_404(product_id)
    tier = ProductPriceTier.query.filter_by(id=tier_id, product_id=product_id).first_or_404()

    min_qty_str = request.form.get('min_qty', '').strip()
    max_qty_str = request.form.get('max_qty', '').strip()
    price_str = request.form.get('price', '').strip()
    tier_name = request.form.get('tier_name', tier.tier_name).strip().lower()

    if tier_name not in VALID_TIER_NAMES:
        flash(f'Invalid tier name.', 'danger')
        return redirect(url_for('pricing.product_tiers', product_id=product_id))

    try:
        min_qty = int(min_qty_str)
        if min_qty < 1:
            raise ValueError
    except (ValueError, TypeError):
        flash('Minimum quantity must be a positive integer.', 'danger')
        return redirect(url_for('pricing.product_tiers', product_id=product_id))

    max_qty = None
    if max_qty_str:
        try:
            max_qty = int(max_qty_str)
            if max_qty < min_qty:
                flash('Maximum quantity cannot be less than minimum quantity.', 'danger')
                return redirect(url_for('pricing.product_tiers', product_id=product_id))
        except (ValueError, TypeError):
            flash('Max quantity must be a positive integer or blank.', 'danger')
            return redirect(url_for('pricing.product_tiers', product_id=product_id))

    try:
        price = Decimal(price_str)
        if price < 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        flash('Price must be a valid positive number.', 'danger')
        return redirect(url_for('pricing.product_tiers', product_id=product_id))

    # Overlap check (exclude self)
    all_tiers = ProductPriceTier.query.filter_by(product_id=product_id).all()
    # Temporarily update tier values for check
    tier.min_qty = min_qty
    tier.max_qty = max_qty
    tier.tier_name = tier_name
    ok, err = _validate_tier_ranges(all_tiers, exclude_id=None)  # exclude_id already handled via tier update
    if not ok:
        db.session.rollback()
        flash(f'Range conflict: {err}', 'danger')
        return redirect(url_for('pricing.product_tiers', product_id=product_id))

    tier.price = price
    db.session.commit()
    flash(f'Price tier "{tier_name}" updated successfully.', 'success')
    return redirect(url_for('pricing.product_tiers', product_id=product_id))


@pricing_bp.route('/product/<int:product_id>/tiers/<int:tier_id>/delete', methods=['POST'])
@login_required
@role_required(['super_admin'])
def delete_tier(product_id, tier_id):
    tier = ProductPriceTier.query.filter_by(id=tier_id, product_id=product_id).first_or_404()
    tier_name = tier.tier_name

    # Also remove any outlet overrides referencing this tier
    OutletProductPrice.query.filter_by(
        product_id=product_id, tier_name=tier_name
    ).delete()

    db.session.delete(tier)
    db.session.commit()
    flash(f'Price tier "{tier_name}" deleted (and any outlet overrides for it).', 'success')
    return redirect(url_for('pricing.product_tiers', product_id=product_id))


# ─── Outlet-Specific Price Overrides ────────────────────────────────────────

@pricing_bp.route('/outlets')
@login_required
@role_required(['super_admin'])
def outlets_index():
    """List all active outlets for outlet-specific pricing management."""
    outlets = Outlet.query.filter_by(is_active=True).order_by(Outlet.is_warehouse.asc(), Outlet.name.asc()).all()
    return render_template('pricing/outlets_index.html', outlets=outlets)


@pricing_bp.route('/outlet/<int:outlet_id>')
@login_required
@role_required(['super_admin'])
def outlet_prices(outlet_id):
    """Manage outlet-specific price overrides."""
    outlet = Outlet.query.get_or_404(outlet_id)
    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    q = Product.query.filter_by(is_active=True)
    if search:
        q = q.filter(
            db.or_(
                Product.name.ilike(f'%{search}%'),
                Product.sku.ilike(f'%{search}%')
            )
        )
    pagination = q.order_by(Product.name.asc()).paginate(page=page, per_page=per_page, error_out=False)

    # Build quick-lookup of existing outlet overrides
    outlet_overrides = {
        (op.product_id, op.tier_name): op
        for op in OutletProductPrice.query.filter_by(outlet_id=outlet_id).all()
    }

    rows = []
    for product in pagination.items:
        tiers = (
            ProductPriceTier.query
            .filter_by(product_id=product.id, is_active=True)
            .order_by(ProductPriceTier.min_qty.asc())
            .all()
        )
        tier_rows = []
        for tier in tiers:
            override = outlet_overrides.get((product.id, tier.tier_name))
            tier_rows.append({
                'tier': tier,
                'override': override,
            })
        # 'default' override (no tiers or base price override)
        default_override = outlet_overrides.get((product.id, 'default'))
        rows.append({
            'product': product,
            'tiers': tier_rows,
            'default_override': default_override,
        })

    return render_template(
        'pricing/outlet_prices.html',
        outlet=outlet,
        rows=rows,
        pagination=pagination,
        search=search,
        valid_tier_names=VALID_TIER_NAMES,
    )


@pricing_bp.route('/outlet/<int:outlet_id>/product/<int:product_id>/set', methods=['POST'])
@login_required
@role_required(['super_admin'])
def set_outlet_price(outlet_id, product_id):
    """Create or update an outlet-specific price override."""
    outlet = Outlet.query.get_or_404(outlet_id)
    product = Product.query.get_or_404(product_id)

    tier_name = request.form.get('tier_name', '').strip().lower()
    price_str = request.form.get('price', '').strip()

    valid_names = VALID_TIER_NAMES + ['default']
    if tier_name not in valid_names:
        flash(f'Invalid tier name "{tier_name}".', 'danger')
        return redirect(url_for('pricing.outlet_prices', outlet_id=outlet_id))

    try:
        price = Decimal(price_str)
        if price < 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        flash('Price must be a valid positive number.', 'danger')
        return redirect(url_for('pricing.outlet_prices', outlet_id=outlet_id))

    # If it's a named tier (not 'default'), verify the global tier exists
    if tier_name != 'default':
        global_tier = ProductPriceTier.query.filter_by(
            product_id=product_id, tier_name=tier_name, is_active=True
        ).first()
        if not global_tier:
            flash(f'No global "{tier_name}" tier exists for this product. Create the global tier first.', 'danger')
            return redirect(url_for('pricing.outlet_prices', outlet_id=outlet_id))

    # Upsert
    existing = OutletProductPrice.query.filter_by(
        outlet_id=outlet_id, product_id=product_id, tier_name=tier_name
    ).first()

    if existing:
        existing.price = price
        existing.is_active = True
        existing.created_by = current_user.id
        flash(f'Outlet price override for "{tier_name}" updated.', 'success')
    else:
        override = OutletProductPrice(
            outlet_id=outlet_id,
            product_id=product_id,
            tier_name=tier_name,
            price=price,
            is_active=True,
            created_by=current_user.id,
        )
        db.session.add(override)
        flash(f'Outlet price override for "{tier_name}" created.', 'success')

    db.session.commit()
    return redirect(url_for('pricing.outlet_prices', outlet_id=outlet_id))


@pricing_bp.route('/outlet/<int:outlet_id>/product/<int:product_id>/override/<int:override_id>/delete', methods=['POST'])
@login_required
@role_required(['super_admin'])
def delete_outlet_price(outlet_id, product_id, override_id):
    """Remove an outlet-specific price override."""
    override = OutletProductPrice.query.filter_by(
        id=override_id, outlet_id=outlet_id, product_id=product_id
    ).first_or_404()
    tier_name = override.tier_name
    db.session.delete(override)
    db.session.commit()
    flash(f'Outlet price override for "{tier_name}" removed.', 'success')
    return redirect(url_for('pricing.outlet_prices', outlet_id=outlet_id))


# ─── API: Price preview for POS ─────────────────────────────────────────────

@pricing_bp.route('/api/product/<int:product_id>/price')
@login_required
def api_product_price(product_id):
    """
    AJAX: Return the effective price for a product+outlet+quantity combo.
    Used by the POS frontend for live price preview.
    """
    from utils.pricing import get_effective_price, get_all_tiers_for_product

    outlet_id = request.args.get('outlet_id', type=int)
    quantity = request.args.get('quantity', 1, type=int)

    if not outlet_id:
        outlet_id = current_user.outlet_id or 1

    price = get_effective_price(product_id, outlet_id, quantity)
    tiers = get_all_tiers_for_product(product_id, outlet_id)

    return jsonify({
        'product_id': product_id,
        'outlet_id': outlet_id,
        'quantity': quantity,
        'effective_price': float(price),
        'tiers': tiers,
    })
