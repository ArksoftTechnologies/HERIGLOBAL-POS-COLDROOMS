from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from werkzeug.security import generate_password_hash
from models import db, User, Outlet
from utils.decorators import role_required
from utils.helpers import validate_username, validate_password

auth = Blueprint('auth', __name__, url_prefix='/auth')


def _get_serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def _send_password_reset_email(user):
    """Generate token and dispatch the beautiful HTML password reset email via direct SMTP_SSL."""
    import smtplib, ssl
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    serializer = _get_serializer()
    salt = current_app.config.get('PASSWORD_RESET_SALT', 'heriglobal-password-reset-salt-2026')
    token = serializer.dumps(user.email, salt=salt)
    reset_url = url_for('auth.reset_password', token=token, _external=True)

    html_body = render_template(
        'email/password_reset.html',
        user=user,
        reset_url=reset_url,
    )

    mail_server   = current_app.config['MAIL_SERVER']
    mail_port     = int(current_app.config['MAIL_PORT'])
    mail_username = current_app.config['MAIL_USERNAME']
    mail_password = current_app.config['MAIL_PASSWORD']
    mail_sender   = current_app.config.get('MAIL_DEFAULT_SENDER', f'{current_app.config.get("APP_NAME", "Heriglobal POS")} <{mail_username}>')

    # Build MIME message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'Password Reset Request - {current_app.config.get("APP_NAME", "Heriglobal POS")}'
    msg['From']    = mail_sender
    msg['To']      = user.email
    msg.attach(MIMEText(
        f'Click the following link to reset your password: {reset_url}\n\nThis link expires in 1 hour.',
        'plain'
    ))
    msg.attach(MIMEText(html_body, 'html'))

    # Determine SSL vs STARTTLS based on port
    context = ssl._create_unverified_context()
    if mail_port == 465:
        with smtplib.SMTP_SSL(mail_server, mail_port, context=context, timeout=15) as server:
            server.login(mail_username, mail_password)
            server.sendmail(mail_username, [user.email], msg.as_string())
    else:
        with smtplib.SMTP(mail_server, mail_port, timeout=15) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(mail_username, mail_password)
            server.sendmail(mail_username, [user.email], msg.as_string())
            
    current_app.logger.info(f'Password reset email sent to {user.email}')



@auth.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and authentication"""
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        username_or_email = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember', False) == 'on'
        
        # Validate input
        if not username_or_email or not password:
            flash('Please enter both username/email and password', 'danger')
            return render_template('auth/login.html')
        
        # Find user by username or email
        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()
        
        # Check if user exists and password is correct
        if not user or not user.check_password(password):
            flash('Invalid username or password', 'danger')
            return render_template('auth/login.html')
        
        # Check if user is active
        if not user.is_active:
            flash('Account is inactive. Contact administrator.', 'danger')
            return render_template('auth/login.html')
        
        # Login user
        login_user(user, remember=remember)
        
        # Set session data
        session['user_id'] = user.id
        session['role'] = user.role
        session['full_name'] = user.full_name
        session['username'] = user.username
        session['outlet_id'] = user.outlet_id
        session.permanent = True  # Use permanent session lifetime from config
        
        flash(f'Welcome back, {user.full_name}!', 'success')
        
        # Redirect to dashboard
        next_page = request.args.get('next')
        if next_page:
            return redirect(next_page)
        return redirect(url_for('dashboard.index'))
    
    return render_template('auth/login.html')


@auth.route('/logout')
@login_required
def logout():
    """Logout user and clear session"""
    logout_user()
    for key in list(session.keys()):
        session.pop(key, None)
    flash('You have been logged out successfully', 'info')
    return redirect(url_for('auth.login'))


@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Send password reset link to user's email."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Please enter your email address.', 'danger')
            return render_template('auth/forgot_password.html')

        user = User.query.filter_by(email=email).first()
        # Always show success even if email not found (security best practice)
        if user and user.is_active:
            try:
                _send_password_reset_email(user)
            except Exception as e:
                import traceback
                current_app.logger.error(f'Password reset email error: {e}\n{traceback.format_exc()}')
                flash('Unable to send email at this time. Please contact your administrator.', 'danger')
                return render_template('auth/forgot_password.html')

        flash(
            'If that email is registered, a password reset link has been sent. '
            'Please check your inbox (and spam folder).',
            'success'
        )
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@auth.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Validate reset token and allow user to set a new password."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    serializer = _get_serializer()
    salt = current_app.config.get('PASSWORD_RESET_SALT', 'heriglobal-password-reset-salt-2026')
    expiry = current_app.config.get('PASSWORD_RESET_EXPIRY', 3600)

    try:
        email = serializer.loads(token, salt=salt, max_age=expiry)
    except SignatureExpired:
        flash('The password reset link has expired. Please request a new one.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    except BadSignature:
        flash('Invalid or tampered reset link. Please request a new one.', 'danger')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.filter_by(email=email).first()
    if not user or not user.is_active:
        flash('User account not found or inactive.', 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')

        is_valid, error = validate_password(password)
        if not is_valid:
            flash(error, 'danger')
            return render_template('auth/reset_password.html', token=token)

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('auth/reset_password.html', token=token)

        user.set_password(password)
        db.session.commit()
        flash('Your password has been reset successfully! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)


@auth.route('/register', methods=['GET', 'POST'])
@login_required
@role_required(['super_admin'])
def register():
    """User registration - Super Admin only"""
    if request.method == 'POST':
        # Get form data
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        role = request.form.get('role', '').strip()
        outlet_id = request.form.get('outlet_id', '').strip()
        
        # Convert outlet_id to int or None
        outlet_id = int(outlet_id) if outlet_id else None
        
        # Validate required fields
        if not all([full_name, username, email, password, confirm_password, role]):
            flash('All fields are required', 'danger')
            return render_template('auth/register.html', outlets=Outlet.query.filter_by(is_active=True).all())
        
        # Validate username
        is_valid, error = validate_username(username)
        if not is_valid:
            flash(error, 'danger')
            return render_template('auth/register.html', outlets=Outlet.query.filter_by(is_active=True).all())
        
        # Validate password
        is_valid, error = validate_password(password)
        if not is_valid:
            flash(error, 'danger')
            return render_template('auth/register.html', outlets=Outlet.query.filter_by(is_active=True).all())
        
        # Check password confirmation
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('auth/register.html', outlets=Outlet.query.filter_by(is_active=True).all())
        
        # Validate role-outlet relationship
        is_valid, error = User.validate_role_outlet_relationship(role, outlet_id)
        if not is_valid:
            flash(error, 'danger')
            return render_template('auth/register.html', outlets=Outlet.query.filter_by(is_active=True).all())
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return render_template('auth/register.html', outlets=Outlet.query.filter_by(is_active=True).all())
        
        # Check if email already exists
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'danger')
            return render_template('auth/register.html', outlets=Outlet.query.filter_by(is_active=True).all())
        
        # Create new user
        new_user = User(
            username=username,
            email=email,
            full_name=full_name,
            role=role,
            outlet_id=outlet_id,
            created_by=current_user.id
        )
        new_user.set_password(password)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash(f'User {username} registered successfully!', 'success')
            return redirect(url_for('dashboard.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating user: {str(e)}', 'danger')
            return render_template('auth/register.html', outlets=Outlet.query.filter_by(is_active=True).all())
    
    # GET request - show form
    outlets = Outlet.query.filter_by(is_active=True).all()
    return render_template('auth/register.html', outlets=outlets)


# ─── DEV-ONLY: Super Admin Password Reset ──────────────────────────────────── #
@auth.route('/reset-super-admin')
def reset_super_admin():
    """DEBUG-only: reset super_admin password to a known temp value."""
    if not current_app.debug:
        from flask import abort
        abort(404)

    TEMP_PASSWORD = 'Admin@1234'

    admin = User.query.filter_by(role='super_admin').first()
    if not admin:
        return '<h2>No super_admin user found in the database.</h2>', 404

    admin.set_password(TEMP_PASSWORD)
    db.session.commit()

    return f'''
        <html><body style="font-family:sans-serif;padding:40px;max-width:500px;margin:auto">
        <h2 style="color:#16a34a">✅ Super Admin Password Reset</h2>
        <p><b>Username:</b> <code>{admin.username}</code></p>
        <p><b>New Password:</b> <code>{TEMP_PASSWORD}</code></p>
        <p style="color:#dc2626"><b>⚠ Change this password immediately after logging in!</b></p>
        <a href="/auth/login" style="display:inline-block;margin-top:12px;padding:10px 20px;
            background:#4f46e5;color:white;border-radius:8px;text-decoration:none">
            Go to Login
        </a>
        </body></html>
    ''', 200
