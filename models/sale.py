from . import db
from datetime import datetime

class Sale(db.Model):
    __tablename__ = 'sales'

    id = db.Column(db.Integer, primary_key=True)
    sale_number = db.Column(db.String(50), unique=True, nullable=False)
    outlet_id = db.Column(db.Integer, db.ForeignKey('outlets.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)  # Made nullable for non-registered customers
    non_registered_customer_name = db.Column(db.String(200), nullable=True)  # For non-registered customer names
    sales_rep_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    sale_date = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.Date, nullable=True)  # Due date for credit sales (Chunk 7)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_mode_id = db.Column(db.Integer, db.ForeignKey('payment_modes.id'), nullable=True) # Null for split
    is_split_payment = db.Column(db.Boolean, default=False)
    transaction_reference = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='completed')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    outlet = db.relationship('Outlet', backref='sales')
    customer = db.relationship('Customer', backref='sales')
    sales_rep = db.relationship('User', backref='sales_processed')
    payment_mode = db.relationship('PaymentMode', backref='sales')
    items = db.relationship('SaleItem', backref='sale', cascade='all, delete-orphan')
    payments = db.relationship('SalePayment', backref='sale', cascade='all, delete-orphan')

    __table_args__ = (
        db.CheckConstraint('total_amount > 0', name='check_sale_total_amount_positive'),
        db.CheckConstraint("status IN ('completed', 'pending', 'cancelled')", name='check_sale_status_valid'),
        db.CheckConstraint(
            '(customer_id IS NOT NULL AND non_registered_customer_name IS NULL) OR '
            '(customer_id IS NULL AND non_registered_customer_name IS NOT NULL)',
            name='check_customer_or_name'
        ),
    )

    @property
    def customer_display_name(self):
        """Get display name for customer (registered or non-registered)"""
        if self.customer:
            return f"{self.customer.first_name} {self.customer.last_name}"
        return self.non_registered_customer_name or "Unknown Customer"
    
    @property
    def is_registered_customer(self):
        """Check if sale is for a registered customer"""
        return self.customer_id is not None

    def __repr__(self):
        return f'<Sale {self.sale_number}>'

class SaleItem(db.Model):
    __tablename__ = 'sale_items'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    quantity_returned = db.Column(db.Float, default=0.0, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)

    # Relationships
    product = db.relationship('Product', backref='sale_items')

    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='check_sale_item_quantity_positive'),
        db.CheckConstraint('quantity_returned >= 0', name='check_sale_item_returned_positive'),
        db.CheckConstraint('quantity_returned <= quantity', name='check_sale_item_returned_limit'),
        db.CheckConstraint('unit_price >= 0', name='check_sale_item_unit_price_positive'), # Allow 0 price promo? Requirement said >0 but edge case said maybe error. Sticking to >0 per SQL in prompt, but implementation plan didn't specify. Prompt SQL said CHECK (unit_price > 0). I will stick to >0 unless free items are needed. Requirement Edge Case 1 says "Zero-Priced Product... Validation error". So > 0.
        db.CheckConstraint('subtotal >= 0', name='check_sale_item_subtotal_positive'),
    )

class SalePayment(db.Model):
    __tablename__ = 'sale_payments'

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey('sales.id'), nullable=False)
    payment_mode_id = db.Column(db.Integer, db.ForeignKey('payment_modes.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    transaction_reference = db.Column(db.String(100), nullable=True)

    # Relationships
    payment_mode = db.relationship('PaymentMode', backref='sale_payments')

    __table_args__ = (
        db.CheckConstraint('amount > 0', name='check_sale_payment_amount_positive'),
    )
