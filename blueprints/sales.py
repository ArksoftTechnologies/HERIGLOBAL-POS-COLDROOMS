from flask import Blueprint, render_template, request, jsonify, abort
from flask_login import login_required, current_user
from models import Sale, PaymentMode, SaleItem, Customer, User, Outlet
from sqlalchemy import or_
from utils.decorators import role_required
from utils.pdf_generator import PDFGenerator

sales_bp = Blueprint('sales', __name__, url_prefix='/sales')

@sales_bp.route('/')
@login_required
def index():
    if current_user.role == 'accountant': # Only role excluded in plan, but typically accounts see sales? Plan says "All except Accountant". OK.
         return render_template('errors/403.html'), 403

    page = request.args.get('page', 1, type=int)
    
    query = Sale.query
    
    # Filter by Outlet/Role
    if current_user.role == 'sales_rep':
        # Sales reps see ONLY their own sales
        query = query.filter_by(sales_rep_id=current_user.id)
    elif current_user.role == 'outlet_admin':
        query = query.filter_by(outlet_id=current_user.outlet_id)
        
    # Search/Filters
    search = request.args.get('search')
    if search:
        query = query.filter(Sale.sale_number.ilike(f'%{search}%'))
        
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    if date_from:
        from datetime import datetime
        try:
            from_dt = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Sale.sale_date >= from_dt)
        except ValueError:
            pass
            
    if date_to:
        from datetime import datetime, timedelta
        try:
            to_dt = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Sale.sale_date < to_dt)
        except ValueError:
            pass
            
    sales = query.order_by(Sale.sale_date.desc()).paginate(page=page, per_page=20)
    
    return render_template('sales/list.html', sales=sales)

@sales_bp.route('/<int:id>')
@login_required
def detail(id):
    sale = Sale.query.get_or_404(id)
    
    # Access Control
    if current_user.role == 'sales_rep':
        # Sales reps can only view their own sales
        if sale.sales_rep_id != current_user.id:
            abort(403)
    elif current_user.role == 'outlet_admin':
        if sale.outlet_id != current_user.outlet_id:
            abort(403)
            
    return render_template('sales/detail.html', sale=sale)

@sales_bp.route('/<int:id>/pdf')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep', 'accountant'])
def download_sale_pdf(id):
    """View sale receipt for print/download"""
    
    sale = Sale.query.get_or_404(id)
    
    # Check access
    if current_user.role in ['outlet_admin', 'sales_rep']:
        if sale.outlet_id != current_user.outlet_id:
            abort(403)
    
    # Get outlet
    outlet = Outlet.query.get(sale.outlet_id)
    
    # Generate HTML
    return PDFGenerator.generate_sale_receipt(sale, outlet)
