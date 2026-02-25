from datetime import datetime
from models import db

class Customer(db.Model):
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    customer_number = db.Column(db.String(50), unique=True, nullable=False)  # CUST-0001
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(50), nullable=True)
    state = db.Column(db.String(50), nullable=True)
    
    primary_outlet_id = db.Column(db.Integer, db.ForeignKey('outlets.id'), nullable=True)
    
    credit_limit = db.Column(db.Numeric(10, 2), default=0.00)
    current_balance = db.Column(db.Numeric(10, 2), default=0.00)
    outstanding_balance = db.Column(db.Numeric(10, 2), default=0.00)  # Opening/legacy balance at registration
    
    is_walk_in = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relationships
    primary_outlet = db.relationship('Outlet', backref='customers')
    creator = db.relationship('User', backref='created_customers')

    __table_args__ = (
        db.CheckConstraint('credit_limit >= 0', name='check_credit_limit_positive'),
        db.CheckConstraint('current_balance >= 0', name='check_current_balance_positive'),
    )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def available_credit(self):
        return self.credit_limit - self.current_balance
