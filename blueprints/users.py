from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, User, Outlet
from werkzeug.security import generate_password_hash
from utils.decorators import role_required
from datetime import datetime

users_bp = Blueprint('users', __name__)

@users_bp.route('/users')
@role_required(['super_admin'])
def list_users():
    """List all users with filters"""
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Filters
    role_filter = request.args.get('role')
    outlet_filter = request.args.get('outlet_id', type=int)
    status_filter = request.args.get('status')
    search = request.args.get('search', '').strip()
    
    # Base query
    query = User.query
    
    # Apply filters
    if role_filter:
        query = query.filter_by(role=role_filter)
    
    if outlet_filter:
        query = query.filter_by(outlet_id=outlet_filter)
    
    if status_filter == 'active':
        query = query.filter_by(is_active=True)
    elif status_filter == 'inactive':
        query = query.filter_by(is_active=False)
    
    if search:
        query = query.filter(
            db.or_(
                User.username.ilike(f'%{search}%'),
                User.full_name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%')
            )
        )
    
    # Paginate
    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    users = pagination.items
    
    # Get all outlets for filter dropdown
    outlets = Outlet.query.filter_by(is_active=True, is_warehouse=False).all()
    
    return render_template(
        'users/list.html',
        users=users,
        pagination=pagination,
        outlets=outlets,
        role_filter=role_filter,
        outlet_filter=outlet_filter,
        status_filter=status_filter,
        search=search
    )


@users_bp.route('/users/create', methods=['GET', 'POST'])
@role_required(['super_admin'])
def create_user():
    """Create new user"""
    
    if request.method == 'GET':
        outlets = Outlet.query.filter_by(is_active=True, is_warehouse=False).all()
        return render_template('users/create.html', outlets=outlets)
    
    # POST - Create user
    try:
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        full_name = request.form.get('full_name', '').strip()
        password = request.form.get('password')
        role = request.form.get('role')
        outlet_id = request.form.get('outlet_id', type=int)
        
        # Validation
        if not username or len(username) < 3:
            flash('Username must be at least 3 characters', 'error')
            return redirect(url_for('users.create_user'))
        
        if not password or len(password) < 8:
            flash('Password must be at least 8 characters', 'error')
            return redirect(url_for('users.create_user'))
        
        if not role or role not in ['super_admin', 'general_manager', 'outlet_admin', 'sales_rep', 'accountant']:
            flash('Invalid role selected', 'error')
            return redirect(url_for('users.create_user'))
        
        # Check username uniqueness
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists', 'error')
            return redirect(url_for('users.create_user'))
        
        # Check email uniqueness (if provided)
        if email:
            existing_email = User.query.filter_by(email=email).first()
            if existing_email:
                flash('Email already exists', 'error')
                return redirect(url_for('users.create_user'))
        
        # Outlet validation
        if role in ['outlet_admin', 'sales_rep']:
            if not outlet_id:
                flash('Outlet is required for Outlet Admin and Sales Rep roles', 'error')
                return redirect(url_for('users.create_user'))
        else:
            outlet_id = None  # Other roles don't need outlet assignment
        
        # Create user
        user = User(
            username=username,
            email=email if email else None,
            full_name=full_name,
            password_hash=generate_password_hash(password),
            role=role,
            outlet_id=outlet_id,
            is_active=True
        )
        
        db.session.add(user)
        db.session.commit()
        
        flash(f'User {username} created successfully', 'success')
        return redirect(url_for('users.list_users'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error creating user: {str(e)}', 'error')
        return redirect(url_for('users.create_user'))


@users_bp.route('/users/<int:id>')
@role_required(['super_admin'])
def view_user(id):
    """View user details"""
    user = User.query.get_or_404(id)
    
    # Get user's sales stats if sales rep
    sales_stats = None
    if user.role == 'sales_rep':
        from sqlalchemy import func
        from models import Sale
        
        sales_stats = db.session.query(
            func.count(Sale.id).label('total_sales'),
            func.sum(Sale.total_amount).label('total_revenue')
        ).filter_by(sales_rep_id=id, status='completed').first()
    
    return render_template('users/detail.html', user=user, sales_stats=sales_stats)


@users_bp.route('/users/<int:id>/edit', methods=['GET', 'POST'])
@role_required(['super_admin'])
def edit_user(id):
    """Edit user"""
    user = User.query.get_or_404(id)
    
    # Permission check: GM cannot edit Super Admin
    if current_user.role == 'general_manager' and user.role == 'super_admin':
        flash('General Managers cannot manage Super Admins', 'error')
        return redirect(url_for('users.list_users'))
    
    if request.method == 'GET':
        outlets = Outlet.query.filter_by(is_active=True, is_warehouse=False).all()
        return render_template('users/edit.html', user=user, outlets=outlets)
    
    # POST - Update user
    try:
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        role = request.form.get('role')
        outlet_id = request.form.get('outlet_id', type=int)
        new_password = request.form.get('new_password', '').strip()
        
        # Update fields
        user.full_name = full_name
        user.email = email if email else None
        user.role = role
        
        # Outlet validation
        if role in ['outlet_admin', 'sales_rep']:
            if not outlet_id:
                flash('Outlet is required for Outlet Admin and Sales Rep roles', 'error')
                return redirect(url_for('users.edit_user', id=id))
            user.outlet_id = outlet_id
        else:
            user.outlet_id = None
        
        # Update password if provided
        if new_password:
            if len(new_password) < 8:
                flash('Password must be at least 8 characters', 'error')
                return redirect(url_for('users.edit_user', id=id))
            user.password_hash = generate_password_hash(new_password)
        
        user.updated_at = datetime.now()
        
        db.session.commit()
        
        flash(f'User {user.username} updated successfully', 'success')
        return redirect(url_for('users.view_user', id=id))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating user: {str(e)}', 'error')
        return redirect(url_for('users.edit_user', id=id))


@users_bp.route('/users/<int:id>/deactivate', methods=['POST'])
@role_required(['super_admin'])
def deactivate_user(id):
    """Deactivate user"""
    user = User.query.get_or_404(id)
    
    # Permission check: GM cannot deactivate Super Admin
    if current_user.role == 'general_manager' and user.role == 'super_admin':
        flash('General Managers cannot manage Super Admins', 'error')
        return redirect(url_for('users.list_users'))
    
    # Prevent deactivating self
    if user.id == current_user.id:
        flash('You cannot deactivate yourself', 'error')
        return redirect(url_for('users.list_users'))
    
    user.is_active = False
    user.updated_at = datetime.now()
    
    db.session.commit()
    
    flash(f'User {user.username} deactivated successfully', 'success')
    return redirect(url_for('users.list_users'))


@users_bp.route('/users/<int:id>/activate', methods=['POST'])
@role_required(['super_admin'])
def activate_user(id):
    """Activate user"""
    user = User.query.get_or_404(id)
    
    # Permission check: GM cannot activate Super Admin
    if current_user.role == 'general_manager' and user.role == 'super_admin':
        flash('General Managers cannot manage Super Admins', 'error')
        return redirect(url_for('users.list_users'))
    
    user.is_active = True
    user.updated_at = datetime.now()
    
    db.session.commit()
    
    flash(f'User {user.username} activated successfully', 'success')
    return redirect(url_for('users.list_users'))

@users_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User Profile settings"""
    if request.method == 'GET':
        return render_template('users/profile.html', user=current_user)
        
    # POST - Update profile
    try:
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        
        # Passwords
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Update basics
        if full_name:
            current_user.full_name = full_name
        if email:
            # check email uniqueness among OTHER users
            existing_email = User.query.filter_by(email=email).first()
            if existing_email and existing_email.id != current_user.id:
                flash('Email already belongs to another account', 'error')
                return redirect(url_for('users.profile'))
            current_user.email = email
            
        # Update password if provided
        if current_password or new_password or confirm_password:
            if not current_password:
                flash('Please provide your current password to set a new password', 'error')
                return redirect(url_for('users.profile'))
            if not current_user.check_password(current_password):
                flash('Incorrect current password', 'error')
                return redirect(url_for('users.profile'))
            if not new_password or len(new_password) < 8:
                flash('New password must be at least 8 characters', 'error')
                return redirect(url_for('users.profile'))
            if new_password != confirm_password:
                flash('New passwords do not match', 'error')
                return redirect(url_for('users.profile'))
                
            current_user.password_hash = generate_password_hash(new_password)
            flash('Password updated successfully', 'success')
            
        current_user.updated_at = datetime.now()
        db.session.commit()
        
        flash('Profile updated successfully', 'success')
        return redirect(url_for('users.profile'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating profile: {str(e)}', 'error')
        return redirect(url_for('users.profile'))
