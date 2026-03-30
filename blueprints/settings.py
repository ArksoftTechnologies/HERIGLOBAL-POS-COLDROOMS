from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required
from models import db, User, Outlet, Product, Category, PaymentMode, SystemSetting
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
    
    # Fetch settings
    allow_returns = SystemSetting.query.filter_by(key='allow_sales_rep_returns').first()
    if not allow_returns:
        allow_returns = SystemSetting(key='allow_sales_rep_returns', value='true')
        db.session.add(allow_returns)
        db.session.commit()

    return render_template(
        'settings/index.html',
        total_users=total_users,
        total_outlets=total_outlets,
        total_products=total_products,
        total_categories=total_categories,
        payment_modes=payment_modes,
        allow_sales_rep_returns=(allow_returns.value == 'true')
    )

@settings_bp.route('/update-policy', methods=['POST'])
@login_required
@role_required(['super_admin'])
def update_policy():
    key = request.form.get('key')
    # If using the 'hidden + checkbox' pattern, we check for 'true' in the list
    values = request.form.getlist('value')
    value = 'true' if 'true' in values else 'false'
    
    setting = SystemSetting.query.filter_by(key=key).first()
    if setting:
        setting.value = value
        db.session.commit()
        flash(f"Policy updated successfully.", "success")
    else:
        # Create if it doesn't exist for some reason
        new_setting = SystemSetting(key=key, value=value)
        db.session.add(new_setting)
        db.session.commit()
        flash(f"Policy configured successfully.", "success")
    
    return redirect(url_for('settings.index'))
