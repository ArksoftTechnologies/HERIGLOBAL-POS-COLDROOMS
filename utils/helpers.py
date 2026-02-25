import re

def validate_username(username):
    """
    Validate username format
    - 3-50 characters
    - Alphanumeric and underscore only
    
    Returns (is_valid, error_message)
    """
    if not username:
        return False, "Username is required"
    
    if len(username) < 3:
        return False, "Username must be at least 3 characters long"
    
    if len(username) > 50:
        return False, "Username must not exceed 50 characters"
    
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Username can only contain letters, numbers, and underscores"
    
    return True, None

def validate_password(password):
    """
    Validate password strength
    - Minimum 8 characters
    
    Returns (is_valid, error_message)
    """
    if not password:
        return False, "Password is required"
    
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    return True, None

def get_password_strength(password):
    """
    Calculate password strength for UI indicator
    Returns: 'weak', 'medium', 'strong'
    """
    if not password:
        return 'weak'
    
    strength = 0
    
    # Length check
    if len(password) >= 8:
        strength += 1
    if len(password) >= 12:
        strength += 1
    
    # Character variety checks
    if re.search(r'[a-z]', password):
        strength += 1
    if re.search(r'[A-Z]', password):
        strength += 1
    if re.search(r'[0-9]', password):
        strength += 1
    if re.search(r'[^a-zA-Z0-9]', password):
        strength += 1
    
    if strength <= 2:
        return 'weak'
    elif strength <= 4:
        return 'medium'
    else:
        return 'strong'
