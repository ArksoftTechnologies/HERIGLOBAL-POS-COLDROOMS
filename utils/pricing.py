"""
Pricing utility: resolves the effective selling price for a product
at a given outlet for a given quantity.

Priority order:
  1. Outlet-specific price override (OutletProductPrice) for the matching tier
  2. Global price tier (ProductPriceTier) for the matching tier
  3. Outlet-specific 'default' override (OutletProductPrice, tier_name='default')
  4. Product.selling_price  (original fallback — never broken)
"""
from decimal import Decimal
from models.pricing import ProductPriceTier, OutletProductPrice


def get_effective_price(product_id: int, outlet_id: int, quantity: int) -> Decimal:
    """
    Return the effective unit selling price for a product at an outlet
    for a given quantity, applying tier and outlet-override rules.
    """
    # Load all active global tiers for this product, ordered by min_qty
    tiers = (
        ProductPriceTier.query
        .filter_by(product_id=product_id, is_active=True)
        .order_by(ProductPriceTier.min_qty.asc())
        .all()
    )

    matched_tier = None
    for tier in tiers:
        if tier.min_qty <= quantity:
            if tier.max_qty is None or quantity <= tier.max_qty:
                matched_tier = tier
                # Don't break — a later (higher min_qty) tier might also match
                # (overlapping ranges are admin's problem, but we pick the last match
                #  so that more specific high-qty tiers win over low-qty ones)

    if matched_tier:
        # Check for outlet-specific override for this tier
        outlet_override = (
            OutletProductPrice.query
            .filter_by(
                outlet_id=outlet_id,
                product_id=product_id,
                tier_name=matched_tier.tier_name,
                is_active=True
            )
            .first()
        )
        if outlet_override:
            return Decimal(str(outlet_override.price))
        return Decimal(str(matched_tier.price))

    # No tier matched — check for outlet-level 'default' override
    default_override = (
        OutletProductPrice.query
        .filter_by(
            outlet_id=outlet_id,
            product_id=product_id,
            tier_name='default',
            is_active=True
        )
        .first()
    )
    if default_override:
        return Decimal(str(default_override.price))

    # Ultimate fallback: product's base selling_price
    from models.product import Product
    product = Product.query.get(product_id)
    if product:
        return Decimal(str(product.selling_price))
    return Decimal('0')


def get_all_tiers_for_product(product_id: int, outlet_id: int) -> list:
    """
    Return a list of dicts describing every active tier for a product,
    with the effective price for the given outlet already applied.
    Used by the POS frontend to show price previews.
    """
    from models.product import Product

    tiers = (
        ProductPriceTier.query
        .filter_by(product_id=product_id, is_active=True)
        .order_by(ProductPriceTier.min_qty.asc())
        .all()
    )

    result = []
    for tier in tiers:
        outlet_override = (
            OutletProductPrice.query
            .filter_by(
                outlet_id=outlet_id,
                product_id=product_id,
                tier_name=tier.tier_name,
                is_active=True
            )
            .first()
        )
        effective_price = float(outlet_override.price if outlet_override else tier.price)
        result.append({
            'tier_name': tier.tier_name,
            'min_qty': tier.min_qty,
            'max_qty': tier.max_qty,   # None means unlimited
            'global_price': float(tier.price),
            'effective_price': effective_price,
            'has_outlet_override': outlet_override is not None,
        })

    # Check for outlet 'default' override if no tiers configured
    if not result:
        product = Product.query.get(product_id)
        default_override = (
            OutletProductPrice.query
            .filter_by(
                outlet_id=outlet_id,
                product_id=product_id,
                tier_name='default',
                is_active=True
            )
            .first()
        )
        base_price = float(default_override.price if default_override else product.selling_price)
        result.append({
            'tier_name': 'default',
            'min_qty': 1,
            'max_qty': None,
            'global_price': float(product.selling_price),
            'effective_price': base_price,
            'has_outlet_override': default_override is not None,
        })

    return result
