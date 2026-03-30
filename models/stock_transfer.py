from datetime import datetime
from .base import db

class StockTransfer(db.Model):
    __tablename__ = 'stock_transfers'

    id = db.Column(db.Integer, primary_key=True)
    transfer_number = db.Column(db.String(50), unique=True, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    from_outlet_id = db.Column(db.Integer, db.ForeignKey('outlets.id'), nullable=False)
    to_outlet_id = db.Column(db.Integer, db.ForeignKey('outlets.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending') # pending, approved, in_transit, completed, rejected, cancelled
    
    # Request Details
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)

    # Workflow Details
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    received_at = db.Column(db.DateTime, nullable=True)
    
    rejected_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    rejected_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)

    # Relationships
    product = db.relationship('Product', backref='transfers')
    from_outlet = db.relationship('Outlet', foreign_keys=[from_outlet_id], backref='transfers_sent')
    to_outlet = db.relationship('Outlet', foreign_keys=[to_outlet_id], backref='transfers_received')
    
    requester = db.relationship('User', foreign_keys=[requested_by], backref='transfers_requested')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='transfers_approved')
    receiver = db.relationship('User', foreign_keys=[received_by], backref='transfers_received_by')
    rejector = db.relationship('User', foreign_keys=[rejected_by], backref='transfers_rejected')

    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='check_transfer_quantity_positive'),
        db.CheckConstraint('from_outlet_id != to_outlet_id', name='check_transfer_source_dest_diff'),
        db.CheckConstraint("status IN ('pending', 'approved', 'in_transit', 'completed', 'rejected', 'cancelled')", name='check_transfer_status_valid'),
    )

    def __repr__(self):
        return f'<StockTransfer {self.transfer_number}: {self.product.sku} ({self.quantity})>'
