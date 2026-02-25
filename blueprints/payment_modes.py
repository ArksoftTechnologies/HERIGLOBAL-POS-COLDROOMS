from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, PaymentMode

payment_modes_bp = Blueprint('payment_modes', __name__, url_prefix='/payment-modes')

@payment_modes_bp.route('/')
@login_required
def index():
    if current_user.role != 'super_admin':
        return render_template('errors/403.html'), 403
        
    modes = PaymentMode.query.all()
    return render_template('payment_modes/list.html', modes=modes)

@payment_modes_bp.route('/create', methods=['POST'])
@login_required
def create():
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Unauthorized'}), 403
        
    name = request.form.get('name')
    code = request.form.get('code')
    requires_reference = request.form.get('requires_reference') == 'on'
    
    if not name or not code:
        flash('Name and Code are required', 'error')
        return redirect(url_for('payment_modes.index'))
        
    if PaymentMode.query.filter_by(code=code.upper()).first():
        flash('Code already exists', 'error')
        return redirect(url_for('payment_modes.index'))
        
    mode = PaymentMode(
        name=name,
        code=code.upper(),
        is_credit=False,
        is_system_default=False,
        requires_reference=requires_reference,
        created_by=current_user.id
    )
    db.session.add(mode)
    db.session.commit()
    pass
    flash('Payment mode created', 'success')
    return redirect(url_for('payment_modes.index'))

@payment_modes_bp.route('/<int:id>/toggle', methods=['POST'])
@login_required
def toggle(id):
    if current_user.role != 'super_admin':
        return jsonify({'error': 'Unauthorized'}), 403
        
    mode = PaymentMode.query.get_or_404(id)
    if mode.is_system_default:
        flash('Cannot disable system default modes', 'error')
        return redirect(url_for('payment_modes.index'))
        
    mode.is_active = not mode.is_active
    db.session.commit()
    flash(f'Payment mode {"enabled" if mode.is_active else "disabled"}', 'success')
    return redirect(url_for('payment_modes.index'))
