from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .base import db

# Valid user roles
VALID_ROLES = ['super_admin', 'general_manager', 'outlet_admin', 'sales_rep', 'accountant']

# Roles that require outlet assignment
OUTLET_REQUIRED_ROLES = ['outlet_admin', 'sales_rep']

# Roles that must NOT have outlet assignment
OUTLET_FORBIDDEN_ROLES = ['super_admin', 'general_manager', 'accountant']

class User(UserMixin, db.Model):
    """
    User model with role-based access control
    """
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    outlet_id = db.Column(db.Integer, db.ForeignKey('outlets.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Relationship to creator
    creator = db.relationship('User', remote_side=[id], backref='created_users')
    
    def set_password(self, password):
        """Hash and set the user's password"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Verify the user's password"""
        return check_password_hash(self.password_hash, password)
    
    @staticmethod
    def validate_role_outlet_relationship(role, outlet_id):
        """
        Validate that role and outlet_id relationship is correct
        Returns (is_valid, error_message)
        """
        if role not in VALID_ROLES:
            return False, f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}"
        
        if role in OUTLET_REQUIRED_ROLES and outlet_id is None:
            return False, f"{role.replace('_', ' ').title()} must be assigned to an outlet"
        
        if role in OUTLET_FORBIDDEN_ROLES and outlet_id is not None:
            return False, f"{role.replace('_', ' ').title()} cannot be assigned to an outlet"
            
        # Strict rule: No users can be assigned to the Central Warehouse (ID 1)
        if outlet_id == 1:
            return False, "Users cannot be assigned to the Central Warehouse (Inventory Only)"
        
        return True, None
    
    def get_role_display(self):
        """Get human-readable role name"""
        return self.role.replace('_', ' ').title()
    
    def __repr__(self):
        return f'<User {self.username} ({self.role})>'
