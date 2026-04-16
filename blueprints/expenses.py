from flask import Blueprint, render_template, request, jsonify, url_for, flash, redirect, current_app, send_file, abort, make_response
from flask_login import login_required, current_user
from app import db
from models.expense import Expense, ExpenseCategory
from models.outlet import Outlet
from models.user import User
from models.payment import PaymentMode
from datetime import datetime, date, timedelta
from sqlalchemy import func, desc
from functools import wraps
from utils.pdf_generator import PDFGenerator
import io
import csv

expenses_bp = Blueprint('expenses', __name__, url_prefix='/expenses')

def role_required(roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                flash('Access denied. You do not have permission to view this page.', 'error')
                return redirect(url_for('dashboard.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def generate_expense_number():
    """Generate unique expense number in format EXP-YYYY-NNNN"""
    year = datetime.now().year
    last_expense = Expense.query.filter(
        Expense.expense_number.like(f'EXP-{year}-%')
    ).order_by(Expense.id.desc()).first()
    
    if last_expense:
        try:
            last_num = int(last_expense.expense_number.split('-')[-1])
            new_num = last_num + 1
        except ValueError:
            new_num = 1
    else:
        new_num = 1
    
    return f'EXP-{year}-{new_num:04d}'

@expenses_bp.route('/', methods=['GET'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep', 'accountant'])
def index():
    """List expenses with filtering"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    outlet_id = request.args.get('outlet_id', type=int)
    category_id = request.args.get('category_id', type=int)
    recorded_by = request.args.get('recorded_by', type=int)
    
    query = Expense.query

    # Role-based filtering
    if current_user.role in ['outlet_admin', 'sales_rep']:
        if current_user.role == 'sales_rep':
            # Sales reps see ONLY the expenses they personally recorded
            query = query.filter(Expense.recorded_by == current_user.id)
        else:
            # Outlet admin sees all expenses for their outlet
            query = query.filter(Expense.outlet_id == current_user.outlet_id)

    # Apply filters
    if date_from:
        query = query.filter(Expense.expense_date >= date_from)
    if date_to:
        query = query.filter(Expense.expense_date <= date_to)
    if outlet_id and current_user.role in ['super_admin', 'general_manager', 'accountant']:
        query = query.filter(Expense.outlet_id == outlet_id)
    if category_id:
        query = query.filter(Expense.category_id == category_id)
    if recorded_by:
        query = query.filter(Expense.recorded_by == recorded_by)
        
    # Get totals for summary cards (before pagination)
    total_amount = db.session.query(func.sum(Expense.amount)).filter(Expense.id.in_([e.id for e in query.all()])).scalar() or 0
    today = date.today()
    today_amount = db.session.query(func.sum(Expense.amount)).filter(Expense.id.in_([e.id for e in query.all()]), Expense.expense_date == today).scalar() or 0
    
    pagination = query.order_by(Expense.expense_date.desc(), Expense.id.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    outlets = Outlet.query.filter_by(is_active=True).all()
    categories = ExpenseCategory.query.filter_by(is_active=True).all()
    users = User.query.filter(User.role.in_(['sales_rep', 'outlet_admin'])).all()

    return render_template('expenses/list.html', 
                           expenses=pagination.items, 
                           pagination=pagination,
                           outlets=outlets,
                           categories=categories,
                           users=users,
                           total_amount=total_amount,
                           today_amount=today_amount,
                           today=date.today())


@expenses_bp.route('/export/csv', methods=['GET'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep', 'accountant'])
def export_csv():
    """Export the current expenses view as a CSV download.
    Respects the same role-based scoping and GET filter params as index().
    """
    date_from   = request.args.get('date_from')
    date_to     = request.args.get('date_to')
    outlet_id   = request.args.get('outlet_id', type=int)
    category_id = request.args.get('category_id', type=int)
    recorded_by = request.args.get('recorded_by', type=int)

    query = Expense.query

    # Role-based filtering — mirrors index()
    if current_user.role in ['outlet_admin', 'sales_rep']:
        if current_user.role == 'sales_rep':
            query = query.filter(Expense.recorded_by == current_user.id)
        else:
            query = query.filter(Expense.outlet_id == current_user.outlet_id)

    # Apply filters
    if date_from:
        query = query.filter(Expense.expense_date >= date_from)
    if date_to:
        query = query.filter(Expense.expense_date <= date_to)
    if outlet_id and current_user.role in ['super_admin', 'general_manager', 'accountant']:
        query = query.filter(Expense.outlet_id == outlet_id)
    if category_id:
        query = query.filter(Expense.category_id == category_id)
    if recorded_by:
        query = query.filter(Expense.recorded_by == recorded_by)

    expenses = query.order_by(Expense.expense_date.desc(), Expense.id.desc()).all()

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        'Expense #', 'Date', 'Recorded By', 'Outlet',
        'Category', 'Description', 'Amount (NGN)', 'Status'
    ])

    grand_total = 0.0
    for expense in expenses:
        amount = float(expense.amount)
        grand_total += amount
        writer.writerow([
            expense.expense_number,
            expense.expense_date.strftime('%Y-%m-%d'),
            expense.recorder.full_name if expense.recorder else '',
            expense.outlet.name if expense.outlet else '',
            expense.category.name if expense.category else '',
            expense.description,
            f"{amount:.2f}",
            expense.status.capitalize() if expense.status else ''
        ])

    # Totals row
    writer.writerow([])
    writer.writerow(['TOTAL', '', '', '', '', '', f"{grand_total:.2f}", ''])

    # Dynamic filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"Expenses_Export_{timestamp}.csv"

    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@expenses_bp.route('/create', methods=['GET', 'POST'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep'])
def create():
    """Record new expense"""
    if request.method == 'POST':
        try:
            data = request.get_json()
            
            # Validation
            amount = float(data.get('amount', 0))
            if amount <= 0:
                raise ValueError("Amount must be greater than zero")
            if amount > 1000000:
                raise ValueError("Amount exceeds maximum allowed (₦1,000,000)")
                
            expense_date_str = data.get('expense_date')
            expense_date = datetime.strptime(expense_date_str, '%Y-%m-%d').date()
            if expense_date > date.today():
                raise ValueError("Expense date cannot be in the future")
            if (date.today() - expense_date).days > 90:
                raise ValueError("Expense date cannot be more than 90 days ago")
                
            description = data.get('description', '').strip()
            if len(description) < 10:
                raise ValueError("Description must be at least 10 characters")
                
            category_id = int(data.get('category_id'))
            category = ExpenseCategory.query.get(category_id)
            if not category or not category.is_active:
                raise ValueError("Invalid expense category")
            
            # Outcome determination
            if current_user.role in ['outlet_admin', 'sales_rep']:
                outlet_id = current_user.outlet_id
            else:
                outlet_id = data.get('outlet_id') or current_user.outlet_id
                if not outlet_id:
                     raise ValueError("Outlet is required")

            expense_number = generate_expense_number()
            
            expense = Expense(
                expense_number=expense_number,
                outlet_id=outlet_id,
                recorded_by=current_user.id,
                category_id=category_id,
                amount=amount,
                expense_date=expense_date,
                description=description,
                payment_mode_id=data.get('payment_mode_id'),
                reference_number=data.get('reference_number'),
                notes=data.get('notes'),
                status='recorded'
            )
            
            db.session.add(expense)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Expense recorded successfully. Expense #{expense_number}',
                'expense_id': expense.id,
                'redirect': url_for('expenses.detail', id=expense.id)
            })
            
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Expense creation failed: {e}")
            return jsonify({'error': 'Failed to record expense'}), 500

    # GET request
    categories = ExpenseCategory.query.filter_by(is_active=True).all()
    payment_modes = PaymentMode.query.filter_by(is_active=True).all()
    outlets = Outlet.query.filter_by(is_active=True).all()
    
    return render_template('expenses/create.html',
                           categories=categories,
                           payment_modes=payment_modes,
                           outlets=outlets,
                           today=date.today())

@expenses_bp.route('/<int:id>', methods=['GET'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep', 'accountant'])
def detail(id):
    """View expense details"""
    expense = Expense.query.get_or_404(id)
    
    # Access control
    if current_user.role in ['outlet_admin', 'sales_rep'] and expense.outlet_id != current_user.outlet_id:
        flash('Access denied.', 'error')
        return redirect(url_for('expenses.index'))
        
    return render_template('expenses/detail.html', expense=expense)

@expenses_bp.route('/summary', methods=['GET'])
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'accountant'])
def summary():
    """Expense summary report"""
    date_from_str = request.args.get('date_from', (date.today() - timedelta(days=30)).strftime('%Y-%m-%d'))
    date_to_str = request.args.get('date_to', date.today().strftime('%Y-%m-%d'))
    outlet_id = request.args.get('outlet_id', type=int)

    date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
    date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()

    query = db.session.query(Expense).filter(Expense.expense_date >= date_from, Expense.expense_date <= date_to)

    if current_user.role == 'outlet_admin':
        query = query.filter(Expense.outlet_id == current_user.outlet_id)
    elif outlet_id:
        query = query.filter(Expense.outlet_id == outlet_id)

    expenses = query.all()
    
    # Summary calculations
    total_expenses = sum(e.amount for e in expenses)
    total_count = len(expenses)
    
    # Category breakdown
    category_data = {}
    for e in expenses:
        cat_name = e.category.name
        if cat_name not in category_data:
            category_data[cat_name] = 0
        category_data[cat_name] += float(e.amount)
    
    # User breakdown
    user_data = {}
    for e in expenses:
        user_name = f"{e.recorder.first_name} {e.recorder.last_name}"
        if user_name not in user_data:
            user_data[user_name] = {'amount': 0, 'count': 0}
        user_data[user_name]['amount'] += float(e.amount)
        user_data[user_name]['count'] += 1
        
    # Sort user data by amount
    sorted_users = sorted(user_data.items(), key=lambda x: x[1]['amount'], reverse=True)[:5]
    
    outlets = Outlet.query.filter_by(is_active=True).all()

    return render_template('expenses/summary.html',
                           total_expenses=total_expenses,
                           total_count=total_count,
                           category_data=category_data,
                           user_data=sorted_users,
                           outlets=outlets,
                           date_from=date_from_str,
                           date_to=date_to_str,
                           current_outlet_id=outlet_id)

@expenses_bp.route('/categories', methods=['GET', 'POST'])
@login_required
@role_required(['super_admin'])
def categories():
    """Manage expense categories"""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'create':
            name = request.form.get('name')
            description = request.form.get('description')
            
            if ExpenseCategory.query.filter_by(name=name).first():
                flash('Category already exists', 'error')
            else:
                cat = ExpenseCategory(name=name, description=description, created_by=current_user.id)
                db.session.add(cat)
                db.session.commit()
                flash('Category created successfully', 'success')
                
        elif action == 'toggle_status':
            cat_id = request.form.get('category_id')
            cat = ExpenseCategory.query.get(cat_id)
            if cat:
                cat.is_active = not cat.is_active
                db.session.commit()
                flash(f"Category {'activated' if cat.is_active else 'deactivated'}", 'success')
                
        return redirect(url_for('expenses.categories'))

    categories = ExpenseCategory.query.all()
    return render_template('expenses/categories.html', categories=categories)

@expenses_bp.route('/<int:id>/pdf')
@login_required
@role_required(['super_admin', 'general_manager', 'outlet_admin', 'sales_rep', 'accountant'])
def download_expense_pdf(id):
    """Download expense record as PDF"""
    
    expense = Expense.query.get_or_404(id)
    
    # Check access
    if current_user.role in ['outlet_admin', 'sales_rep']:
        if expense.outlet_id != current_user.outlet_id:
            abort(403)
    
    # Get outlet
    outlet = Outlet.query.get(expense.outlet_id)
    
    # Generate HTML
    return PDFGenerator.generate_expense_record(expense, outlet)
