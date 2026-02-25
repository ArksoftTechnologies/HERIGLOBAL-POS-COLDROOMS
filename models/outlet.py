from datetime import datetime
from .base import db

class Outlet(db.Model):
    """
    Outlet model for multi-outlet management.
    Includes support for central warehouse and physical store locations.
    """
    __tablename__ = 'outlets'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(50), nullable=True)
    state = db.Column(db.String(50), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(100), nullable=True)
    manager_name = db.Column(db.String(100), nullable=True)
    is_warehouse = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Relationship to users
    users = db.relationship('User', backref='outlet', lazy=True, foreign_keys='User.outlet_id')
    
    def __repr__(self):
        return f'<Outlet {self.code} - {self.name}>'
