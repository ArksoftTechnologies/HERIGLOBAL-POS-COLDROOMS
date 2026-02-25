from datetime import datetime
from .base import db

class ExpenseCategory(db.Model):
    __tablename__ = 'expense_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __repr__(self):
        return f'<ExpenseCategory {self.name}>'

class Expense(db.Model):
    __tablename__ = 'expenses'

    id = db.Column(db.Integer, primary_key=True)
    expense_number = db.Column(db.String(50), unique=True, nullable=False)
    outlet_id = db.Column(db.Integer, db.ForeignKey('outlets.id'), nullable=False)
    recorded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('expense_categories.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    expense_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=False)
    payment_mode_id = db.Column(db.Integer, db.ForeignKey('payment_modes.id'))
    reference_number = db.Column(db.String(100))
    receipt_attachment = db.Column(db.String(255))
    status = db.Column(db.String(20), default='recorded')
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    rejection_reason = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    outlet = db.relationship('Outlet', backref='expenses')
    recorder = db.relationship('User', foreign_keys=[recorded_by], backref='recorded_expenses')
    category = db.relationship('ExpenseCategory', backref='expenses')
    payment_mode = db.relationship('PaymentMode', backref='expenses')
    approver = db.relationship('User', foreign_keys=[approved_by], backref='approved_expenses')

    __table_args__ = (
        db.CheckConstraint('amount > 0', name='check_expense_amount_positive'),
        db.CheckConstraint("status IN ('recorded', 'pending_approval', 'approved', 'rejected', 'reimbursed')", name='check_expense_status_valid'),
    )

    def __repr__(self):
        return f'<Expense {self.expense_number}>'
