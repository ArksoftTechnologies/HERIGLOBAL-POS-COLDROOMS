import os
from flask import Flask, redirect, url_for, request
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_mail import Mail
from config import config
from models import db, User
from datetime import datetime

# Global mail instance (imported by blueprints)
mail = Mail()


def create_app(config_name='development'):
    """Application factory"""
    app = Flask(__name__)
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    db.init_app(app)
    mail.init_app(app)
    
    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)

    # Initialize CSRF Protection
    csrf = CSRFProtect(app)
    
    # Make csrf_token available in all templates
    @app.context_processor
    def inject_csrf_token():
        return dict(csrf_token=generate_csrf, app_name=app.config.get('APP_NAME'))
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please login to access this page'
    login_manager.login_message_category = 'warning'
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Register blueprints
    from blueprints.auth import auth
    from blueprints.dashboard import dashboard_bp as dashboard
    from blueprints.repayments import repayments_bp
    from blueprints.returns import returns_bp
    from blueprints.expenses import expenses_bp
    from blueprints.remittance import remittance_bp
    
    app.register_blueprint(auth)
    app.register_blueprint(dashboard)
    app.register_blueprint(repayments_bp)
    app.register_blueprint(returns_bp)
    app.register_blueprint(expenses_bp)
    app.register_blueprint(remittance_bp)
    
    from blueprints.reports import reports_bp
    app.register_blueprint(reports_bp)
    
    from blueprints.admin_dashboard import admin_dashboard_bp
    app.register_blueprint(admin_dashboard_bp)
    
    from blueprints.outlets import outlets
    from blueprints.products import products
    from blueprints.inventory import inventory_bp
    from blueprints.transfers import transfers_bp
    
    app.register_blueprint(outlets)
    app.register_blueprint(products)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(transfers_bp)
    
    from blueprints.customers import customers_bp
    app.register_blueprint(customers_bp)

    from blueprints.users import users_bp
    app.register_blueprint(users_bp)

    from blueprints.pos import pos_bp
    from blueprints.sales import sales_bp
    from blueprints.payment_modes import payment_modes_bp
    
    app.register_blueprint(pos_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(payment_modes_bp)

    from blueprints.settings import settings_bp
    app.register_blueprint(settings_bp)

    from blueprints.pricing import pricing_bp
    app.register_blueprint(pricing_bp)
    
    # Root route redirect
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))
        
    # Static file caching
    @app.after_request
    def add_header(response):
        if request.path.startswith('/static/'):
            response.cache_control.max_age = app.config.get('SEND_FILE_MAX_AGE_DEFAULT', 31536000)
        return response
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5003)
