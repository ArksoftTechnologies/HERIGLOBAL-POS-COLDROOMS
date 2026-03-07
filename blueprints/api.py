from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from models import db, User, Outlet, Product, Inventory, Sale, StockTransfer, SaleItem
from datetime import datetime, timedelta

api_bp = Blueprint('api', __name__, url_prefix='/api/v1')

@api_bp.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({"msg": "Missing username or password"}), 400
        
    username = data.get('username')
    password = data.get('password')
    
    user = User.query.filter((User.username == username) | (User.email == username)).first()
    
    if not user or not user.check_password(password):
        return jsonify({"msg": "Invalid credentials"}), 401
        
    if not user.is_active:
        return jsonify({"msg": "Account is inactive"}), 403
        
    # Only allow Sales Reps for the mobile app (or others if needed, but keeping it strict for now)
    if user.role not in ['sales_rep', 'super_admin', 'general_manager', 'outlet_admin']:
        return jsonify({"msg": "Unauthorized role for mobile app"}), 403

    # Generate token
    # Identity can be a string or JSON serializable object
    identity = {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "outlet_id": user.outlet_id,
        "full_name": user.full_name
    }
    access_token = create_access_token(identity=identity, expires_delta=timedelta(days=7))
    
    return jsonify({
        "token": access_token,
        "user": identity
    }), 200

@api_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def dashboard():
    """Returns quick stats for the Sales Rep's dashboard."""
    current_user = get_jwt_identity()
    outlet_id = current_user.get('outlet_id')
    
    if not outlet_id:
        return jsonify({"msg": "User has no assigned outlet"}), 400
        
    today = datetime.now().date()
    
    # Check today's sales for this user
    from sqlalchemy import func
    today_sales = db.session.query(func.sum(Sale.total_amount)).filter(
        Sale.sales_rep_id == current_user['id'],
        Sale.status == 'completed',
        func.date(Sale.sale_date) == today
    ).scalar() or 0
    
    today_transactions = db.session.query(func.count(Sale.id)).filter(
        Sale.sales_rep_id == current_user['id'],
        Sale.status == 'completed',
        func.date(Sale.sale_date) == today
    ).scalar() or 0
    
    return jsonify({
        "today_sales": today_sales,
        "today_transactions": today_transactions,
        "outlet_name": Outlet.query.get(outlet_id).name if Outlet.query.get(outlet_id) else "Unknown"
    }), 200

@api_bp.route('/inventory', methods=['GET'])
@jwt_required()
def get_inventory():
    """Returns inventory for the user's assigned outlet."""
    current_user = get_jwt_identity()
    outlet_id = current_user.get('outlet_id')
    
    if not outlet_id:
        return jsonify({"msg": "User has no assigned outlet"}), 400
        
    search = request.args.get('search', '').lower()
    
    # Join Inventory with Product
    query = db.session.query(Inventory, Product).join(Product, Inventory.product_id == Product.id).filter(
        Inventory.outlet_id == outlet_id,
        Product.is_active == True
    )
    
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%') | Product.sku.ilike(f'%{search}%'))
        
    results = query.all()
    
    inventory_data = []
    for inv, prod in results:
        inventory_data.append({
            "id": inv.id,
            "product_id": prod.id,
            "product_name": prod.name,
            "sku": prod.sku,
            "quantity": inv.quantity,
            "price": prod.selling_price
        })
        
    return jsonify(inventory_data), 200

@api_bp.route('/transfers', methods=['GET'])
@jwt_required()
def get_transfers():
    """Returns transfers involving the user's outlet."""
    current_user = get_jwt_identity()
    outlet_id = current_user.get('outlet_id')
    
    if not outlet_id:
         return jsonify({"msg": "User has no assigned outlet"}), 400
         
    transfers = StockTransfer.query.filter(
        (StockTransfer.from_outlet_id == outlet_id) |
        (StockTransfer.to_outlet_id == outlet_id)
    ).order_by(StockTransfer.requested_at.desc()).limit(50).all()
    
    transfer_data = []
    for t in transfers:
        transfer_data.append({
            "id": t.id,
            "transfer_number": t.transfer_number,
            "status": t.status,
            "product_name": t.product.name,
            "quantity": t.quantity,
            "from_outlet": t.from_outlet.name,
            "to_outlet": t.to_outlet.name,
            "date": t.requested_at.strftime('%Y-%m-%d %H:%M')
        })
        
    return jsonify(transfer_data), 200

# Additional endpoints (e.g., creating a sale) can be added here
