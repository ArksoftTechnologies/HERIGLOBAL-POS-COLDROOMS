import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

class Config:
    """Base configuration"""
    APP_NAME = os.environ.get('APP_NAME', 'Heriglobal POS')
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///heriglobal_pos.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Session configuration (8 hours timeout)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False') == 'True'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # WTF Forms CSRF protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # No time limit for CSRF tokens

    # Flask-Mail configuration (read from .env)
    MAIL_SERVER   = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT     = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS  = os.environ.get('MAIL_USE_TLS', 'True') == 'True'
    MAIL_USE_SSL  = os.environ.get('MAIL_USE_SSL', 'False') == 'True'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    app_name = os.environ.get('APP_NAME', 'Heriglobal POS')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', f'{app_name} <noreply@heriglobal.com>')

    # Password reset token config
    PASSWORD_RESET_SALT = os.environ.get('PASSWORD_RESET_SALT', 'heriglobal-password-reset-salt-2026')
    PASSWORD_RESET_EXPIRY = 3600  # 1 hour in seconds

    
class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_ECHO = False  # Set to True to see SQL queries

class TestingConfig(Config):
    """Testing configuration"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:' # Use memory DB for tests
    WTF_CSRF_ENABLED = False # Disable CSRF for tests
    SERVER_NAME = 'localhost.localdomain' # Required for url_for in tests

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True  # Require HTTPS in production
    REMEMBER_COOKIE_SECURE = True
    REMEMBER_COOKIE_HTTPONLY = True
    
    # Database pooling for production
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True
    }
    
    # Performance
    SEND_FILE_MAX_AGE_DEFAULT = 31536000 # 1 year

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
