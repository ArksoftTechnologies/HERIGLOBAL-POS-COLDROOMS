from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from models import db, Customer, Outlet, Sale, Repayment, Return
from utils.decorators import role_required
from utils.generators import generate_customer_number
from sqlalchemy import or_

customers_bp = Blueprint('customers', __name__)

# Roles that have platform-wide (cross-outlet) access to customers
PLATFORM_WIDE_ROLES = ['super_admin', 'general_manager']
# Roles that are restricted to their own outlet's customers
OUTLET_SCOPED_ROLES = ['outlet_admin', 'sales_rep']


def is_platform_wide():
    """Returns True if the current user has cross-outlet (platform-wide) access."""
    return current_user.role in PLATFORM_WIDE_ROLES


def get_outlet_scoped_query():
    """
    Returns a Customer query scoped to the current user's outlet.
    For platform-wide roles (super_admin, general_manager), returns all customers.
    For outlet-scoped roles (outlet_admin, sales_rep), returns only their outlet's customers.
    """
    query = Customer.query.order_by(Customer.created_at.desc())
    if not is_platform_wide():
        # Restrict to the user's assigned outlet
        query = query.filter_by(primary_outlet_id=current_user.outlet_id)
    return query


def assert_customer_outlet_access(customer):
    """
    Abort with 403 if the current user is outlet-scoped and the customer
    does not belong to their outlet.
    """
    if not is_platform_wide():
        if customer.primary_outlet_id != current_user.outlet_id:
            abort(403)


@customers_bp.route('/customers')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def index():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '')
    status = request.args.get('status', 'all')
    credit_status = request.args.get('credit_status', 'all')

    # Base query — already scoped by outlet if needed
    query = get_outlet_scoped_query()

    # Platform-wide users can also filter by a specific outlet
    outlet_id = None
    if is_platform_wide():
        outlet_id = request.args.get('outlet_id', type=int)
        if outlet_id and outlet_id > 0:
            query = query.filter_by(primary_outlet_id=outlet_id)

    # Search
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Customer.first_name.ilike(search_term),
                Customer.last_name.ilike(search_term),
                Customer.phone.ilike(search_term),
                Customer.email.ilike(search_term),
                Customer.customer_number.ilike(search_term)
            )
        )

    # Status filter
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_active=False)

    # Credit filter
    if credit_status == 'has_credit':
        query = query.filter(Customer.current_balance > 0)
    elif credit_status == 'no_credit':
        query = query.filter(Customer.current_balance == 0)

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    # Only platform-wide admins get the outlet filter dropdown
    outlets = Outlet.query.filter_by(is_active=True).all() if is_platform_wide() else []

    return render_template('customers/list.html',
                           customers=pagination.items,
                           pagination=pagination,
                           outlets=outlets,
                           search=search,
                           current_outlet_id=outlet_id,
                           status=status,
                           is_platform_wide=is_platform_wide())


@customers_bp.route('/customers/create', methods=['GET', 'POST'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def create():
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        phone = request.form.get('phone')
        email = request.form.get('email')
        address = request.form.get('address')
        city = request.form.get('city')
        state = request.form.get('state')
        credit_limit = request.form.get('credit_limit', 0.0)
        notes = request.form.get('notes')

        # Outstanding (opening) balance — only privileged roles may set a non-zero value
        raw_outstanding = request.form.get('outstanding_balance', 0.0)
        try:
            outstanding_balance = float(raw_outstanding) if raw_outstanding else 0.0
        except (ValueError, TypeError):
            outstanding_balance = 0.0
        # Enforce: sales_rep cannot seed an opening balance
        if current_user.role == 'sales_rep':
            outstanding_balance = 0.0

        # Determine outlet assignment
        if is_platform_wide():
            # Admins can choose any outlet (or leave blank)
            primary_outlet_id = request.form.get('primary_outlet_id') or None
        else:
            # Outlet-scoped users: always assigned to their own outlet
            primary_outlet_id = current_user.outlet_id

        # Basic Validation
        if not first_name or not last_name or not phone:
            flash('Name and Phone are required.', 'danger')
            return redirect(url_for('customers.create'))

        # Normalization
        phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        email = email.lower().strip() if email else None

        # Uniqueness Check
        if Customer.query.filter_by(phone=phone).first():
            flash('Phone number already exists.', 'danger')
            return redirect(url_for('customers.create'))

        if email and Customer.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('customers.create'))

        customer_number = generate_customer_number()

        customer = Customer(
            customer_number=customer_number,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            email=email,
            address=address,
            city=city,
            state=state,
            primary_outlet_id=primary_outlet_id,
            credit_limit=float(credit_limit) if credit_limit else 0.0,
            outstanding_balance=outstanding_balance,
            current_balance=outstanding_balance,  # Seed from legacy opening balance
            notes=notes,
            created_by=current_user.id
        )

        db.session.add(customer)
        db.session.commit()

        flash('Customer registered successfully.', 'success')
        return redirect(url_for('customers.detail', id=customer.id))

    # For platform-wide admins, pass all active outlets
    # For outlet-scoped users, pass their outlet only (for display purposes)
    if is_platform_wide():
        outlets = Outlet.query.filter_by(is_active=True).all()
    else:
        outlets = Outlet.query.filter_by(id=current_user.outlet_id, is_active=True).all()

    return render_template('customers/create.html',
                           outlets=outlets,
                           is_platform_wide=is_platform_wide(),
                           user_outlet_id=current_user.outlet_id)


@customers_bp.route('/customers/<int:id>')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def detail(id):
    customer = Customer.query.get_or_404(id)
    # Enforce outlet access for non-admin roles
    assert_customer_outlet_access(customer)

    # Pagination params
    purchase_page = request.args.get('purchase_page', 1, type=int)
    payment_page  = request.args.get('payment_page',  1, type=int)
    per_page = 10

    # Purchase history — all sales for this customer
    purchase_history = Sale.query.filter_by(
        customer_id=id, status='completed'
    ).order_by(Sale.sale_date.desc()).paginate(
        page=purchase_page, per_page=per_page, error_out=False
    )

    # Payment history — all repayments for this customer
    payment_history = Repayment.query.filter_by(
        customer_id=id
    ).order_by(Repayment.repayment_date.desc()).paginate(
        page=payment_page, per_page=per_page, error_out=False
    )

    return render_template(
        'customers/detail.html',
        customer=customer,
        purchase_history=purchase_history,
        payment_history=payment_history,
    )


@customers_bp.route('/customers/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin'])
def edit(id):
    customer = Customer.query.get_or_404(id)

    # Enforce outlet scoping for outlet_admin
    assert_customer_outlet_access(customer)

    if customer.is_walk_in:
        flash('Cannot edit the system Walk-In Customer.', 'warning')
        return redirect(url_for('customers.detail', id=id))

    if request.method == 'POST':
        phone = request.form.get('phone')
        phone = phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        email = request.form.get('email')
        email = email.lower().strip() if email else None

        # Unique check excluding self
        existing_phone = Customer.query.filter(Customer.phone == phone, Customer.id != id).first()
        if existing_phone:
            flash('Phone number used by another customer.', 'danger')
            return redirect(url_for('customers.edit', id=id))

        if email:
            existing_email = Customer.query.filter(Customer.email == email, Customer.id != id).first()
            if existing_email:
                flash('Email used by another customer.', 'danger')
                return redirect(url_for('customers.edit', id=id))

        customer.first_name = request.form.get('first_name')
        customer.last_name = request.form.get('last_name')
        customer.phone = phone
        customer.email = email
        customer.address = request.form.get('address')
        customer.city = request.form.get('city')
        customer.state = request.form.get('state')

        # Outlet reassignment: only platform-wide admins can change the outlet
        if is_platform_wide():
            outlet_id = request.form.get('primary_outlet_id')
            customer.primary_outlet_id = outlet_id if outlet_id else None
        # Outlet-scoped users cannot change the outlet; it stays as-is

        limit = request.form.get('credit_limit')
        customer.credit_limit = float(limit) if limit else 0.0

        customer.notes = request.form.get('notes')

        db.session.commit()
        flash('Customer updated successfully.', 'success')
        return redirect(url_for('customers.detail', id=id))

    # Pass outlets for dropdown only to platform-wide admins
    outlets = Outlet.query.filter_by(is_active=True).all() if is_platform_wide() else []
    return render_template('customers/edit.html',
                           customer=customer,
                           outlets=outlets,
                           is_platform_wide=is_platform_wide())


@customers_bp.route('/customers/<int:id>/toggle_status', methods=['POST'])
@login_required
@role_required(['super_admin', 'general_manager'])
def toggle_status(id):
    customer = Customer.query.get_or_404(id)

    if customer.is_walk_in:
        flash('Cannot deactivate Walk-In Customer.', 'danger')
        return redirect(url_for('customers.detail', id=id))

    # Toggle
    customer.is_active = not customer.is_active
    db.session.commit()

    status_msg = "activated" if customer.is_active else "deactivated"
    flash(f'Customer {status_msg} successfully.', 'success')
    return redirect(url_for('customers.detail', id=id))


@customers_bp.route('/customers/<int:id>/ledger')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def ledger(id):
    """Customer statement of account (full chronological ledger)."""
    from datetime import datetime as dt
    customer = Customer.query.get_or_404(id)
    assert_customer_outlet_access(customer)

    # Date filters
    date_from_str = request.args.get('date_from', '')
    date_to_str   = request.args.get('date_to', '')
    page = request.args.get('page', 1, type=int)
    per_page = 20

    date_from = None
    date_to   = None
    if date_from_str:
        try:
            date_from = dt.strptime(date_from_str, '%Y-%m-%d')
        except ValueError:
            pass
    if date_to_str:
        try:
            date_to = dt.strptime(date_to_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            pass

    # --- Collect all ledger entries ---
    entries = []

    # 1. Sales as DEBITS
    sales_q = Sale.query.filter_by(customer_id=id, status='completed')
    if date_from:
        sales_q = sales_q.filter(Sale.sale_date >= date_from)
    if date_to:
        sales_q = sales_q.filter(Sale.sale_date <= date_to)
    for sale in sales_q.all():
        pm_name = sale.payment_mode.name if sale.payment_mode else ('Split' if sale.is_split_payment else 'N/A')
        entries.append({
            'date': sale.sale_date,
            'type': 'Sale',
            'reference': sale.sale_number,
            'description': f'{len(sale.items)} item(s) — {pm_name}',
            'debit':  float(sale.total_amount) if (sale.payment_mode and sale.payment_mode.is_credit) else 0,
            'credit': 0,
            'cash_debit': float(sale.total_amount) if not (sale.payment_mode and sale.payment_mode.is_credit) else 0,
        })

    # 2. Repayments as CREDITS
    rep_q = Repayment.query.filter_by(customer_id=id)
    if date_from:
        rep_q = rep_q.filter(Repayment.repayment_date >= date_from)
    if date_to:
        rep_q = rep_q.filter(Repayment.repayment_date <= date_to)
    for rep in rep_q.all():
        pm_name = rep.payment_mode.name if rep.payment_mode else ('Split' if rep.is_split_payment else 'N/A')
        entries.append({
            'date': rep.repayment_date,
            'type': 'Repayment',
            'reference': rep.repayment_number,
            'description': f'Payment received — {pm_name}',
            'debit': 0,
            'credit': float(rep.amount),
            'cash_debit': 0,
        })

    # 3. Credit-adjustment Returns as CREDITS (reduce outstanding balance)
    ret_q = Return.query.filter_by(customer_id=id, status='completed', refund_method='credit_adjustment')
    if date_from:
        ret_q = ret_q.filter(Return.return_date >= date_from)
    if date_to:
        ret_q = ret_q.filter(Return.return_date <= date_to)
    for ret in ret_q.all():
        entries.append({
            'date': ret.return_date,
            'type': 'Return',
            'reference': ret.return_number,
            'description': f'Credit return — balance adjusted',
            'debit': 0,
            'credit': float(ret.total_refund_amount),
            'cash_debit': 0,
        })

    # Sort chronologically
    entries.sort(key=lambda x: x['date'])

    # Calculate running balance (credit sales increase balance; repayments/returns decrease it)
    running_balance = 0.0
    for entry in entries:
        running_balance += entry['debit'] - entry['credit']
        entry['balance'] = running_balance

    # Totals
    total_debit  = sum(e['debit']  for e in entries)
    total_credit = sum(e['credit'] for e in entries)

    # Manual pagination on the assembled list
    total_entries = len(entries)
    total_pages   = max(1, (total_entries + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    paged_entries = list(reversed(entries))[start: start + per_page]  # newest first for display

    return render_template(
        'customers/ledger.html',
        customer=customer,
        entries=paged_entries,
        total_debit=total_debit,
        total_credit=total_credit,
        current_balance=customer.current_balance,
        now=dt.utcnow(),
        date_from=date_from_str,
        date_to=date_to_str,
        page=page,
        total_pages=total_pages,
        total_entries=total_entries,
    )


@customers_bp.route('/customers/search')
@login_required
def search():
    """
    AJAX customer search endpoint.
    Outlet-scoped roles only see customers from their own outlet.
    Platform-wide roles see all customers.
    """
    query = request.args.get('q', '')
    limit = request.args.get('limit', 10, type=int)

    if not query:
        return jsonify([])

    search_term = f"%{query}%"

    base_query = Customer.query.filter(
        Customer.is_active == True,
        or_(
            Customer.first_name.ilike(search_term),
            Customer.last_name.ilike(search_term),
            Customer.phone.ilike(search_term),
            Customer.customer_number.ilike(search_term),
            Customer.email.ilike(search_term)
        )
    )

    # Apply outlet scope for non-admin roles
    if not is_platform_wide():
        base_query = base_query.filter_by(primary_outlet_id=current_user.outlet_id)

    customers = base_query.limit(limit).all()

    results = []
    for customer in customers:
        available_credit = customer.credit_limit - customer.current_balance
        results.append({
            'id': customer.id,
            'customer_number': customer.customer_number,
            'name': f'{customer.first_name} {customer.last_name}',
            'phone': customer.phone,
            'email': customer.email,
            'credit_limit': float(customer.credit_limit),
            'current_balance': float(customer.current_balance),
            'available_credit': float(available_credit),
            'is_walk_in': customer.is_walk_in
        })

    return jsonify(results)


@customers_bp.route('/customers/<int:id>/data', methods=['GET'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def get_customer_json(id):
    """Get customer data as JSON — enforces outlet scope."""
    customer = Customer.query.get_or_404(id)

    # Ensure outlet-scoped users can only fetch their outlet's customers
    if not is_platform_wide():
        if customer.primary_outlet_id != current_user.outlet_id and not customer.is_walk_in:
            return jsonify({'error': 'Access denied to this customer'}), 403

    return jsonify({
        'id': customer.id,
        'customer_number': customer.customer_number,
        'name': f'{customer.first_name} {customer.last_name}',
        'phone': customer.phone,
        'email': customer.email,
        'credit_limit': float(customer.credit_limit),
        'current_balance': float(customer.current_balance),
        'available_credit': float(customer.credit_limit - customer.current_balance),
        'is_walk_in': customer.is_walk_in
    })
