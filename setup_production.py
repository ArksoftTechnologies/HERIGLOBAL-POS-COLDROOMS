import os
import sys
from getpass import getpass

# Ensure we're running in the right context
app_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, app_dir)

from app import create_app
from models import db, User, Outlet, PaymentMode, Customer

def setup_production():
    """
    Production-safe script to:
    1. Create database tables if they don't exist
    2. Create or reset the super_admin user
    3. Seed essential system data (Warehouse, Walk-in Customer)
    """
    # Force production mode just in case
    os.environ['FLASK_ENV'] = 'production'
    app = create_app('production')
    
    with app.app_context():
        # Ensure database tables are created (this does NOT drop existing tables)
        print("Creating database tables if they don't exist...")
        db.create_all()

        print("\n=== Heriglobal POS Production Setup ===")
        print("This script will create a super admin account safely.")
        print("Leave fields blank to use defaults.\n")
        
        username = input("Enter username [admin]: ").strip() or "admin"
        email = input("Enter email [admin@heriglobal.com]: ").strip() or "admin@heriglobal.com"
        full_name = input("Enter full name [System Administrator]: ").strip() or "System Administrator"
        
        while True:
            password = getpass("Enter password: ").strip()
            confirm = getpass("Confirm password: ").strip()
            if not password:
                print("Password cannot be empty.")
                continue
            if password != confirm:
                print("Passwords do not match. Try again.")
                continue
            break

        # Check if user already exists
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            print(f"\n[INFO] User with username '{username}' or email '{email}' already exists.")
            print("Updating their password, ensuring they are active, and setting role to super_admin...")
            existing_user.set_password(password)
            existing_user.role = 'super_admin'
            existing_user.is_active = True
        else:
            admin = User(
                username=username,
                email=email,
                full_name=full_name,
                role='super_admin',
                outlet_id=None,
                is_active=True
            )
            admin.set_password(password)
            db.session.add(admin)

        # Essential Seed Data for a blank production DB
        if not Outlet.query.get(1):
            print("\n[INFO] Seeding Central Warehouse (Required)...")
            warehouse = Outlet(
                id=1,
                name='Central Warehouse',
                code='WH-MAIN',
                address='Head Office',
                city='',
                state='',
                is_warehouse=True,
                is_active=True
            )
            db.session.add(warehouse)

        if not Customer.query.get(1):
            print("[INFO] Seeding Walk-In Customer (Required)...")
            walk_in = Customer(
                id=1,
                customer_number='CUST-WALKIN',
                first_name='Walk-In',
                last_name='Customer',
                phone='0000000000',
                credit_limit=0.00,
                current_balance=0.00,
                is_walk_in=True,
                is_active=True
            )
            db.session.add(walk_in)

        # Payment Modes
        payment_modes = [
            {'name': 'Cash', 'code': 'CASH', 'is_credit': False, 'is_system_default': True, 'requires_reference': False},
            {'name': 'Credit', 'code': 'CREDIT', 'is_credit': True, 'is_system_default': True, 'requires_reference': False},
            {'name': 'Bank Transfer', 'code': 'BANK', 'is_credit': False, 'is_system_default': True, 'requires_reference': True}
        ]
        
        for mode_data in payment_modes:
            mode = PaymentMode.query.filter_by(code=mode_data['code']).first()
            if not mode:
                mode = PaymentMode(
                    name=mode_data['name'],
                    code=mode_data['code'],
                    is_credit=mode_data['is_credit'],
                    is_system_default=mode_data['is_system_default'],
                    requires_reference=mode_data['requires_reference'],
                    created_by=None
                )
                db.session.add(mode)

        try:
            db.session.commit()
            print(f"\n[SUCCESS] Super admin account '{username}' created/updated successfully.")
            print("[SUCCESS] Core system data seeded successfully.")
            print("You can now login at /auth/login in production.")
        except Exception as e:
            db.session.rollback()
            print(f"\n[ERROR] Failed during setup: {str(e)}")

if __name__ == '__main__':
    setup_production()
