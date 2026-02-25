from functools import wraps
from flask import session, redirect, url_for, flash
from flask_login import current_user

def role_required(allowed_roles):
    """
    Decorator to enforce role-based access control
    
    Usage:
        @role_required(['super_admin', 'general_manager'])
        def some_route():
            ...
    
    Args:
        allowed_roles: List of role names that are allowed to access the route
    
    Returns:
        Decorated function that checks user role before execution
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check if user is authenticated
            if not current_user.is_authenticated:
                flash('Please login to access this page', 'warning')
                return redirect(url_for('auth.login'))
            
            # Check if user has required role
            if current_user.role not in allowed_roles:
                flash('You do not have permission to access this page', 'danger')
                return redirect(url_for('dashboard.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
