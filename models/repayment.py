from . import db
from datetime import datetime

class Repayment(db.Model):
    __tablename__ = 'repayments'

    id = db.Column(db.Integer, primary_key=True)
    repayment_number = db.Column(db.String(50), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    outlet_id = db.Column(db.Integer, db.ForeignKey('outlets.id'), nullable=False)
    received_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    repayment_date = db.Column(db.DateTime, default=datetime.utcnow)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_mode_id = db.Column(db.Integer, db.ForeignKey('payment_modes.id'), nullable=True)  # Null for split
    is_split_payment = db.Column(db.Boolean, default=False)
    transaction_reference = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    balance_before = db.Column(db.Numeric(10, 2), nullable=False)
    balance_after = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    customer = db.relationship('Customer', backref='repayments')
    outlet = db.relationship('Outlet', backref='repayments')
    receiver = db.relationship('User', backref='processed_repayments')
    payment_mode = db.relationship('PaymentMode', backref='repayments')
    payments = db.relationship('RepaymentPayment', backref='repayment', cascade='all, delete-orphan')

    __table_args__ = (
        db.CheckConstraint('amount > 0', name='check_repayment_amount_positive'),
        db.CheckConstraint('balance_before >= 0', name='check_repayment_balance_before_non_negative'),
        db.CheckConstraint('balance_after >= 0', name='check_repayment_balance_after_non_negative'),
    )

    def __repr__(self):
        return f'<Repayment {self.repayment_number}>'

class RepaymentPayment(db.Model):
    __tablename__ = 'repayment_payments'

    id = db.Column(db.Integer, primary_key=True)
    repayment_id = db.Column(db.Integer, db.ForeignKey('repayments.id'), nullable=False)
    payment_mode_id = db.Column(db.Integer, db.ForeignKey('payment_modes.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    transaction_reference = db.Column(db.String(100), nullable=True)

    # Relationships
    payment_mode = db.relationship('PaymentMode')

    __table_args__ = (
        db.CheckConstraint('amount > 0', name='check_repayment_payment_amount_positive'),
    )
