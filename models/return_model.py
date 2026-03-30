from .base import db
from datetime import datetime

class Return(db.Model):
    __tablename__ = 'returns'

    id = db.Column(db.Integer, primary_key=True)
    return_number = db.Column(db.String(50), unique=True, nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    outlet_id = db.Column(db.Integer, db.ForeignKey('outlets.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    processed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    return_date = db.Column(db.DateTime, default=datetime.utcnow)
    total_refund_amount = db.Column(db.Numeric(10, 2), nullable=False)
    refund_method = db.Column(db.String(20), nullable=False) # 'cash', 'bank_transfer', 'credit_adjustment', 'split'
    status = db.Column(db.String(20), default='completed') # 'pending', 'approved', 'completed', 'rejected'
    notes = db.Column(db.Text)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    sale = db.relationship('Sale', backref='returns')
    outlet = db.relationship('Outlet', backref='returns')
    customer = db.relationship('Customer', backref='returns')
    processor = db.relationship('User', foreign_keys=[processed_by], backref='processed_returns')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_returns')
    items = db.relationship('ReturnItem', backref='return_record', cascade='all, delete-orphan')
    payments = db.relationship('ReturnPayment', backref='return_record', cascade='all, delete-orphan')

class ReturnItem(db.Model):
    __tablename__ = 'return_items'

    id = db.Column(db.Integer, primary_key=True)
    return_id = db.Column(db.Integer, db.ForeignKey('returns.id'), nullable=False)
    sale_item_id = db.Column(db.Integer, db.ForeignKey('sale_items.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity_returned = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    refund_amount = db.Column(db.Numeric(10, 2), nullable=False)
    condition = db.Column(db.String(20), nullable=False) # 'resellable', 'damaged'
    reason = db.Column(db.String(50))
    notes = db.Column(db.Text)

    # Relationships
    sale_item = db.relationship('SaleItem', backref='return_items')
    product = db.relationship('Product', backref='return_items')

class ReturnPayment(db.Model):
    __tablename__ = 'return_payments'

    id = db.Column(db.Integer, primary_key=True)
    return_id = db.Column(db.Integer, db.ForeignKey('returns.id'), nullable=False)
    payment_mode_id = db.Column(db.Integer, db.ForeignKey('payment_modes.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    transaction_reference = db.Column(db.String(100))

    # Relationships
    payment_mode = db.relationship('PaymentMode')

class DamagedGoodsLedger(db.Model):
    __tablename__ = 'damaged_goods_ledger'

    id = db.Column(db.Integer, primary_key=True)
    return_item_id = db.Column(db.Integer, db.ForeignKey('return_items.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    outlet_id = db.Column(db.Integer, db.ForeignKey('outlets.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    disposal_status = db.Column(db.String(20), default='pending') # 'pending', 'disposed', 'salvaged'
    disposal_date = db.Column(db.DateTime)
    disposal_notes = db.Column(db.Text)

    # Relationships
    return_item = db.relationship('ReturnItem', backref='damaged_entry')
    product = db.relationship('Product', backref='damaged_entries')
    outlet = db.relationship('Outlet', backref='damaged_entries')
    recorder = db.relationship('User', backref='recorded_damaged_goods')
