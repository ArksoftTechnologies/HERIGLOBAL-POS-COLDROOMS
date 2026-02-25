from datetime import datetime
from .base import db


class ProductPriceTier(db.Model):
    """
    Global three-level selling price tiers for a product.
    Super admin sets min/max quantity ranges with a corresponding price.
    Tier names should be: 'consumer', 'retail', 'wholesale' (but are flexible).
    """
    __tablename__ = 'product_price_tiers'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    tier_name = db.Column(db.String(50), nullable=False)   # e.g. 'consumer', 'retail', 'wholesale'
    min_qty = db.Column(db.Integer, nullable=False)         # inclusive lower bound
    max_qty = db.Column(db.Integer, nullable=True)          # inclusive upper bound; NULL = no upper limit
    price = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    product = db.relationship('Product', backref=db.backref('price_tiers', lazy='dynamic'))
    creator = db.relationship('User', foreign_keys=[created_by])

    __table_args__ = (
        db.CheckConstraint('min_qty >= 1', name='check_tier_min_qty_positive'),
        db.CheckConstraint('price >= 0', name='check_tier_price_positive'),
    )

    def __repr__(self):
        return f'<PriceTier product={self.product_id} tier={self.tier_name} qty={self.min_qty}-{self.max_qty} price={self.price}>'

    @property
    def max_qty_display(self):
        return self.max_qty if self.max_qty is not None else '∞'


class OutletProductPrice(db.Model):
    """
    Outlet-specific price overrides.
    When set, overrides the global ProductPriceTier price for a specific outlet.
    Also allows the super admin to override the base selling_price for a specific outlet
    (using tier_name='default').
    """
    __tablename__ = 'outlet_product_prices'

    id = db.Column(db.Integer, primary_key=True)
    outlet_id = db.Column(db.Integer, db.ForeignKey('outlets.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    tier_name = db.Column(db.String(50), nullable=False)   # matches ProductPriceTier.tier_name or 'default'
    price = db.Column(db.Numeric(10, 2), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    outlet = db.relationship('Outlet', backref=db.backref('outlet_product_prices', lazy='dynamic'))
    product = db.relationship('Product', backref=db.backref('outlet_prices', lazy='dynamic'))
    creator = db.relationship('User', foreign_keys=[created_by])

    __table_args__ = (
        db.UniqueConstraint('outlet_id', 'product_id', 'tier_name',
                            name='uq_outlet_product_tier'),
        db.CheckConstraint('price >= 0', name='check_outlet_price_positive'),
    )

    def __repr__(self):
        return f'<OutletProductPrice outlet={self.outlet_id} product={self.product_id} tier={self.tier_name} price={self.price}>'
