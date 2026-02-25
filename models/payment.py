from . import db
from datetime import datetime

class PaymentMode(db.Model):
    __tablename__ = 'payment_modes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    is_credit = db.Column(db.Boolean, default=False)
    is_system_default = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    requires_reference = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    __table_args__ = (
        db.CheckConstraint("name != ''", name='check_payment_mode_name_not_empty'),
        db.CheckConstraint("code != ''", name='check_payment_mode_code_not_empty'),
    )

    def __repr__(self):
        return f'<PaymentMode {self.name}>'
