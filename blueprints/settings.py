from flask import Blueprint, render_template
from flask_login import login_required
from models import db, User, Outlet, Product, Category, PaymentMode
from utils.decorators import role_required

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')


@settings_bp.route('/')
@login_required
@role_required(['super_admin'])
def index():
    """System Settings Page - Super Admin Only"""
    # System stats for overview card
    total_users = User.query.filter_by(is_active=True).count()
    total_outlets = Outlet.query.filter_by(is_active=True).count()
    total_products = Product.query.filter_by(is_active=True).count()
    total_categories = Category.query.filter_by(is_active=True).count()
    payment_modes = PaymentMode.query.filter_by(is_active=True).all()

    return render_template(
        'settings/index.html',
        total_users=total_users,
        total_outlets=total_outlets,
        total_products=total_products,
        total_categories=total_categories,
        payment_modes=payment_modes,
    )
