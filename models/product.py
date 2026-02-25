from datetime import datetime
from .base import db

class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    products = db.relationship('Product', backref='category', lazy=True)

    def __repr__(self):
        return f'<Category {self.name}>'

class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    cost_price = db.Column(db.Numeric(10, 2), nullable=False)
    selling_price = db.Column(db.Numeric(10, 2), nullable=False)
    reorder_level = db.Column(db.Integer, default=10)
    unit = db.Column(db.String(20), default='piece')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Check constraints are handled at DB level, but explicit validation is good practice
    __table_args__ = (
        db.CheckConstraint('cost_price >= 0', name='check_cost_price_positive'),
        db.CheckConstraint('selling_price >= 0', name='check_selling_price_positive'),
    )

    def __repr__(self):
        return f'<Product {self.sku} - {self.name}>'

    def calculate_margin(self):
        if self.cost_price == 0:
            return 100 if self.selling_price > 0 else 0
        return ((self.selling_price - self.cost_price) / self.cost_price) * 100
