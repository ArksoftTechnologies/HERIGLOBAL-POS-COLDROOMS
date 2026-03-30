from datetime import datetime
from .base import db

class Inventory(db.Model):
    __tablename__ = 'inventory'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    outlet_id = db.Column(db.Integer, db.ForeignKey('outlets.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False, default=0.0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    product = db.relationship('Product', backref=db.backref('inventory_records', lazy=True))
    outlet = db.relationship('Outlet', backref=db.backref('inventory_stock', lazy=True))

    __table_args__ = (
        db.UniqueConstraint('product_id', 'outlet_id', name='uq_product_outlet_inventory'),
        db.CheckConstraint('quantity >= 0', name='check_inventory_quantity_positive'),
    )

    def __repr__(self):
        return f'<Inventory {self.product.sku} @ {self.outlet.name}: {self.quantity}>'

class InventoryAdjustment(db.Model):
    __tablename__ = 'inventory_adjustments'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    outlet_id = db.Column(db.Integer, db.ForeignKey('outlets.id'), nullable=False)
    adjustment_type = db.Column(db.String(20), nullable=False) # 'initial_stock', 'manual_adjustment', 'damage', etc.
    quantity_before = db.Column(db.Float, nullable=False)
    quantity_change = db.Column(db.Float, nullable=False)
    quantity_after = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    reference_number = db.Column(db.String(50), nullable=True)
    adjusted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    adjusted_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship('Product', backref='adjustments')
    outlet = db.relationship('Outlet', backref='adjustments')
    user = db.relationship('User', backref='adjustments')

    __table_args__ = (
        db.CheckConstraint('quantity_after >= 0', name='check_adjustment_result_positive'),
    )

    def __repr__(self):
        return f'<Adjustment {self.product.sku}: {self.quantity_change}>'
