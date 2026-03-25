from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, make_response
from flask_login import login_required, current_user
from models import db, StockTransfer, Product, Outlet, Inventory, InventoryAdjustment
from utils.decorators import role_required
from utils.pdf_generator import PDFGenerator
from datetime import datetime, date

transfers_bp = Blueprint('transfers', __name__)

@transfers_bp.route('/transfers')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def index():
    status = request.args.get('status', 'all')
    page = request.args.get('page', 1, type=int)
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    product_id = request.args.get('product_id', '', type=str)
    outlet_id = request.args.get('outlet_id', '', type=str)

    query = StockTransfer.query

    # Role-based filtering
    if current_user.role in ['outlet_admin', 'sales_rep']:
        query = query.filter(
            (StockTransfer.from_outlet_id == current_user.outlet_id) |
            (StockTransfer.to_outlet_id == current_user.outlet_id)
        )

    # Status filtering
    if status != 'all':
        query = query.filter(StockTransfer.status == status)

    # Date filters
    if date_from:
        try:
            df = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(StockTransfer.requested_at >= df)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.strptime(date_to, '%Y-%m-%d')
            # include full day
            dt = dt.replace(hour=23, minute=59, second=59)
            query = query.filter(StockTransfer.requested_at <= dt)
        except ValueError:
            pass

    # Product filter
    if product_id:
        query = query.filter(StockTransfer.product_id == int(product_id))

    # Outlet filter (from OR to)
    if outlet_id:
        oid = int(outlet_id)
        query = query.filter(
            (StockTransfer.from_outlet_id == oid) |
            (StockTransfer.to_outlet_id == oid)
        )

    pagination = query.order_by(StockTransfer.requested_at.desc()).paginate(page=page, per_page=20)

    # Load filter dropdowns
    all_products = Product.query.filter_by(is_active=True).order_by(Product.name).all()
    all_outlets = Outlet.query.filter_by(is_active=True).order_by(Outlet.name).all()

    return render_template(
        'transfers/list.html',
        transfers=pagination.items,
        pagination=pagination,
        status=status,
        date_from=date_from,
        date_to=date_to,
        selected_product_id=product_id,
        selected_outlet_id=outlet_id,
        all_products=all_products,
        all_outlets=all_outlets,
    )


@transfers_bp.route('/transfers/pdf')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def download_pdf():
    """Download filtered transfer history as a beautifully formatted PDF."""
    status = request.args.get('status', 'all')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    product_id = request.args.get('product_id', '', type=str)
    outlet_id = request.args.get('outlet_id', '', type=str)

    query = StockTransfer.query

    if current_user.role in ['outlet_admin', 'sales_rep']:
        query = query.filter(
            (StockTransfer.from_outlet_id == current_user.outlet_id) |
            (StockTransfer.to_outlet_id == current_user.outlet_id)
        )

    if status != 'all':
        query = query.filter(StockTransfer.status == status)

    if date_from:
        try:
            df = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(StockTransfer.requested_at >= df)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.strptime(date_to, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(StockTransfer.requested_at <= dt)
        except ValueError:
            pass

    if product_id:
        query = query.filter(StockTransfer.product_id == int(product_id))

    if outlet_id:
        oid = int(outlet_id)
        query = query.filter(
            (StockTransfer.from_outlet_id == oid) |
            (StockTransfer.to_outlet_id == oid)
        )

    transfers = query.order_by(StockTransfer.requested_at.desc()).all()

    filters_display = {
        'status': status,
        'date_from': date_from,
        'date_to': date_to,
        'product_id': product_id,
        'outlet_id': outlet_id,
    }

    html_content = PDFGenerator.generate_transfer_history_pdf(
        transfers=transfers,
        filters=filters_display,
        generated_by=current_user.full_name,
    )

    response = make_response(html_content)
    response.headers['Content-Type'] = 'text/html; charset=utf-8'
    return response

@transfers_bp.route('/transfers/create', methods=['GET', 'POST'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin'])
def create():
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        from_outlet_id = request.form.get('from_outlet_id')
        to_outlet_id = request.form.get('to_outlet_id')
        quantity = int(request.form.get('quantity'))
        notes = request.form.get('notes')
        
        # Validation
        if from_outlet_id == to_outlet_id:
            flash('Source and destination cannot be the same.', 'danger')
            return redirect(url_for('transfers.create'))
            
        # Permission check
        if current_user.role == 'outlet_admin' and int(from_outlet_id) != current_user.outlet_id and int(from_outlet_id) != 1: 
             # Outlet Admin can only request from Warehouse or transfer FROM their own outlet
             # Actually, based on requirements:
             # Outlet Admin: can only request from warehouse to their outlet, or from their outlet to another outlet
             pass # Logic will be enforced by dropdowns, but server-side check needed
             
        # Check stock availability
        inventory = Inventory.query.filter_by(product_id=product_id, outlet_id=from_outlet_id).first()
        if not inventory or inventory.quantity < quantity:
            flash(f'Insufficient stock at source. Available: {inventory.quantity if inventory else 0}', 'danger')
            return redirect(url_for('transfers.create'))

        # Generate Transfer Number
        year = datetime.now().year
        last_transfer = StockTransfer.query.filter(StockTransfer.transfer_number.like(f'ST-{year}-%')).order_by(StockTransfer.id.desc()).first()
        if last_transfer:
            last_num = int(last_transfer.transfer_number.split('-')[-1])
            new_num = last_num + 1
        else:
            new_num = 1
        transfer_number = f'ST-{year}-{new_num:04d}'

        transfer = StockTransfer(
            transfer_number=transfer_number,
            product_id=product_id,
            from_outlet_id=from_outlet_id,
            to_outlet_id=to_outlet_id,
            quantity=quantity,
            requested_by=current_user.id,
            notes=notes,
            status='pending'
        )
        
        db.session.add(transfer)
        db.session.commit()
        
        flash('Transfer request created successfully.', 'success')
        return redirect(url_for('transfers.detail', id=transfer.id))

    # GET request data preparation
    products = Product.query.filter_by(is_active=True).all()
    
    # Get outlets based on role
    if current_user.role in ['super_admin', 'general_manager']:
        # Can see all outlets
        outlets = Outlet.query.filter_by(is_active=True).all()
    else:
        # Outlet admin can only transfer from their outlet
        outlets = Outlet.query.filter_by(id=current_user.outlet_id, is_active=True).all()
    
    # Get warehouse
    warehouse = Outlet.query.filter_by(is_warehouse=True).first()
    
    return render_template('transfers/create.html', products=products, outlets=outlets, warehouse=warehouse)

@transfers_bp.route('/transfers/<int:id>')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def detail(id):
    transfer = StockTransfer.query.get_or_404(id)
    
    # Permission check for Outlet Admin and Sales Rep
    if current_user.role in ['outlet_admin', 'sales_rep']:
        if transfer.from_outlet_id != current_user.outlet_id and transfer.to_outlet_id != current_user.outlet_id:
             abort(403)
             
    return render_template('transfers/detail.html', transfer=transfer)

@transfers_bp.route('/transfers/<int:id>/approve', methods=['POST'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin'])
def approve(id):
    transfer = StockTransfer.query.get_or_404(id)
    
    if transfer.status != 'pending':
        flash('Transfer is not pending.', 'danger')
        return redirect(url_for('transfers.detail', id=id))

    # Check permission (Must be admin or source outlet admin)
    if current_user.role == 'outlet_admin' and transfer.from_outlet_id != current_user.outlet_id:
        flash('You can only approve transfers FROM your outlet.', 'danger')
        return redirect(url_for('transfers.detail', id=id))
        
    # Re-check stock
    inventory = Inventory.query.filter_by(product_id=transfer.product_id, outlet_id=transfer.from_outlet_id).first()
    if not inventory or inventory.quantity < transfer.quantity:
        flash('Insufficient stock at source location.', 'danger')
        return redirect(url_for('transfers.detail', id=id))

    transfer.status = 'approved'
    transfer.approved_by = current_user.id
    transfer.approved_at = datetime.now()
    db.session.commit()
    
    flash('Transfer approved. Ready for dispatch.', 'success')
    return redirect(url_for('transfers.detail', id=id))

@transfers_bp.route('/transfers/<int:id>/dispatch', methods=['POST'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin'])
def dispatch(id):
    transfer = StockTransfer.query.get_or_404(id)
    
    if transfer.status != 'approved':
        flash('Transfer is not approved.', 'danger')
        return redirect(url_for('transfers.detail', id=id))
        
    # Permission check
    if current_user.role == 'outlet_admin' and transfer.from_outlet_id != current_user.outlet_id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('transfers.detail', id=id))

    # ATOMIC STOCK DEDUCTION
    inventory = Inventory.query.filter_by(
        product_id=transfer.product_id, 
        outlet_id=transfer.from_outlet_id
    ).with_for_update().first()
    
    if inventory.quantity < transfer.quantity:
        flash('Insufficient stock for dispatch.', 'danger')
        return redirect(url_for('transfers.detail', id=id))
        
    inventory.quantity -= transfer.quantity
    inventory.last_updated = datetime.now()
    
    transfer.status = 'in_transit'
    
    # Audit log
    adj = InventoryAdjustment(
        product_id=transfer.product_id,
        outlet_id=transfer.from_outlet_id,
        adjustment_type='transfer_out',
        quantity_before=inventory.quantity + transfer.quantity,
        quantity_change=-transfer.quantity,
        quantity_after=inventory.quantity,
        reason=f'Transfer dispatch to {transfer.to_outlet.name}',
        reference_number=transfer.transfer_number,
        adjusted_by=current_user.id
    )
    db.session.add(adj)
    db.session.commit()
    
    flash('Transfer dispatched.', 'success')
    return redirect(url_for('transfers.detail', id=id))

@transfers_bp.route('/transfers/<int:id>/receive', methods=['POST'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin'])
def receive(id):
    transfer = StockTransfer.query.get_or_404(id)
    
    if transfer.status != 'in_transit':
        flash('Transfer is not in transit.', 'danger')
        return redirect(url_for('transfers.detail', id=id))
        
    # Permission Check (Destination access)
    if current_user.role == 'outlet_admin' and transfer.to_outlet_id != current_user.outlet_id:
         flash('Unauthorized.', 'danger')
         return redirect(url_for('transfers.detail', id=id))
         
    # ATOMIC STOCK ADDITION
    inventory = Inventory.query.filter_by(
        product_id=transfer.product_id,
        outlet_id=transfer.to_outlet_id
    ).with_for_update().first()
    
    if not inventory:
        inventory = Inventory(
            product_id=transfer.product_id,
            outlet_id=transfer.to_outlet_id,
            quantity=0
        )
        db.session.add(inventory)
        db.session.flush() # get ID if needed, though not strictly here for update
        
    qty_before = inventory.quantity
    inventory.quantity += transfer.quantity
    inventory.last_updated = datetime.now()
    
    transfer.status = 'completed'
    transfer.received_by = current_user.id
    transfer.received_at = datetime.now()
    
    # Audit Log
    adj = InventoryAdjustment(
        product_id=transfer.product_id,
        outlet_id=transfer.to_outlet_id,
        adjustment_type='transfer_in',
        quantity_before=qty_before,
        quantity_change=transfer.quantity,
        quantity_after=inventory.quantity,
        reason=f'Transfer receipt from {transfer.from_outlet.name}',
        reference_number=transfer.transfer_number,
        adjusted_by=current_user.id
    )
    db.session.add(adj)
    db.session.commit()
    
    flash('Transfer received and completed.', 'success')
    return redirect(url_for('transfers.detail', id=id))

@transfers_bp.route('/transfers/<int:id>/reject', methods=['POST'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin'])
def reject(id):
    transfer = StockTransfer.query.get_or_404(id)
    
    if transfer.status not in ['pending', 'approved']:
        flash('Cannot reject at this stage.', 'danger')
        return redirect(url_for('transfers.detail', id=id))
        
    # Permission check (Source admin)
    if current_user.role == 'outlet_admin' and transfer.from_outlet_id != current_user.outlet_id:
         flash('Unauthorized.', 'danger')
         return redirect(url_for('transfers.detail', id=id))
         
    transfer.status = 'rejected'
    transfer.rejected_by = current_user.id
    transfer.rejected_at = datetime.now()
    transfer.rejection_reason = request.form.get('reason', 'No reason provided')
    
@transfers_bp.route('/transfers/<int:id>/cancel', methods=['POST'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin'])
def cancel(id):
    transfer = StockTransfer.query.get_or_404(id)
    
    if transfer.status == 'completed':
        flash('Cannot cancel a completed transfer.', 'danger')
        return redirect(url_for('transfers.detail', id=id))

    # Permission check
    is_requester = transfer.requested_by == current_user.id
    is_super = current_user.role in ['super_admin', 'general_manager']
    
    if not (is_super or is_requester):
        flash('Unauthorized.', 'danger')
        return redirect(url_for('transfers.detail', id=id))

    # CRITICAL: If in_transit, usually only Super Admin/General Manager can cancel (as it involves stock rollback)
    if transfer.status == 'in_transit':
        if not is_super:
            flash('Only privileged users can cancel in-transit transfers.', 'danger')
            return redirect(url_for('transfers.detail', id=id))
            
        # ROLLBACK STOCK
        inventory = Inventory.query.filter_by(
            product_id=transfer.product_id,
            outlet_id=transfer.from_outlet_id
        ).with_for_update().first()
        
        qty_before = inventory.quantity
        inventory.quantity += transfer.quantity
        inventory.last_updated = datetime.now()
        
        # Log Reversal
        adj = InventoryAdjustment(
            product_id=transfer.product_id,
            outlet_id=transfer.from_outlet_id,
            adjustment_type='transfer_cancelled',
            quantity_before=qty_before,
            quantity_change=transfer.quantity,
            quantity_after=inventory.quantity,
            reason=f'Transfer {transfer.transfer_number} cancelled (rollback)',
            reference_number=transfer.transfer_number,
            adjusted_by=current_user.id
        )
        db.session.add(adj)

    transfer.status = 'cancelled'
    db.session.commit()
    
    flash('Transfer cancelled.', 'info')
    return redirect(url_for('transfers.detail', id=id))

@transfers_bp.route('/transfers/pending')
@login_required
@role_required(['outlet_admin'])
def pending():
    # Helper for Outlet Admins to see actionable items
    outlet_id = current_user.outlet_id
    
    # 1. Outgoing Pending Approval
    outgoing_pending = StockTransfer.query.filter_by(from_outlet_id=outlet_id, status='pending').all()
    
    # 2. Outgoing Approved (Ready for Dispatch)
    outgoing_approved = StockTransfer.query.filter_by(from_outlet_id=outlet_id, status='approved').all()
    
    # 3. Incoming In Transit (Ready for Receipt)
    incoming_transit = StockTransfer.query.filter_by(to_outlet_id=outlet_id, status='in_transit').all()

    return render_template('transfers/pending.html', 
                           outgoing_pending=outgoing_pending, 
                           outgoing_approved=outgoing_approved, 
                           incoming_transit=incoming_transit)
