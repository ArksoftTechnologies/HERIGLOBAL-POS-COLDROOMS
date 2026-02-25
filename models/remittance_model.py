from datetime import datetime
from .base import db

class CashCollection(db.Model):
    __tablename__ = 'cash_collections'

    id = db.Column(db.Integer, primary_key=True)
    collection_number = db.Column(db.String(50), unique=True, nullable=False)
    sales_rep_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    outlet_id = db.Column(db.Integer, db.ForeignKey('outlets.id'), nullable=False)
    collection_date = db.Column(db.Date, nullable=False)
    collection_type = db.Column(db.String(50), nullable=False)  # 'cash', 'bank_transfer', 'mobile_money', 'other', 'return_reversal'
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_mode_id = db.Column(db.Integer, db.ForeignKey('payment_modes.id'))
    transaction_reference = db.Column(db.String(100))
    source_description = db.Column(db.Text)
    notes = db.Column(db.Text)
    # Auto-collection traceability
    source_type = db.Column(db.String(30), nullable=True)   # 'sale', 'repayment', 'return_reversal', None (manual)
    source_id = db.Column(db.Integer, nullable=True)         # ID of originating sale / repayment / return
    is_reversal = db.Column(db.Boolean, default=False, nullable=False)  # True => debit (reduces balance)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    sales_rep = db.relationship('User', foreign_keys=[sales_rep_id], backref='cash_collections')
    outlet = db.relationship('Outlet', backref='cash_collections')
    payment_mode = db.relationship('PaymentMode', backref='cash_collections')

    __table_args__ = (
        db.CheckConstraint('amount > 0', name='check_collection_amount_positive'),
        db.CheckConstraint(
            "collection_type IN ('cash', 'bank_transfer', 'mobile_money', 'other', 'return_reversal')",
            name='check_collection_type_valid'
        ),
    )

    def __repr__(self):
        return f'<CashCollection {self.collection_number}>'


class Remittance(db.Model):
    __tablename__ = 'remittances'

    id = db.Column(db.Integer, primary_key=True)
    remittance_number = db.Column(db.String(50), unique=True, nullable=False)
    sales_rep_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    outlet_id = db.Column(db.Integer, db.ForeignKey('outlets.id'), nullable=False)
    remittance_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    remittance_method = db.Column(db.String(50), nullable=False)  # 'cash_deposit', 'bank_transfer', 'cheque', 'mobile_transfer', 'other'
    payment_mode_id = db.Column(db.Integer, db.ForeignKey('payment_modes.id'))
    bank_name = db.Column(db.String(100))
    account_number = db.Column(db.String(50))
    transaction_reference = db.Column(db.String(100))
    receipt_attachment = db.Column(db.String(255))
    notes = db.Column(db.Text)
    status = db.Column(db.String(20), default='recorded')  # 'recorded', 'verified', 'rejected'
    verified_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    verified_at = db.Column(db.DateTime)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    sales_rep = db.relationship('User', foreign_keys=[sales_rep_id], backref='remittances')
    outlet = db.relationship('Outlet', backref='remittances')
    payment_mode = db.relationship('PaymentMode', backref='remittances')
    verifier = db.relationship('User', foreign_keys=[verified_by], backref='verified_remittances')

    __table_args__ = (
        db.CheckConstraint('amount > 0', name='check_remittance_amount_positive'),
        db.CheckConstraint("remittance_method IN ('cash_deposit', 'bank_transfer', 'cheque', 'mobile_transfer', 'other')", name='check_remittance_method_valid'),
        db.CheckConstraint("status IN ('recorded', 'verified', 'rejected')", name='check_remittance_status_valid'),
    )

    def __repr__(self):
        return f'<Remittance {self.remittance_number}>'
