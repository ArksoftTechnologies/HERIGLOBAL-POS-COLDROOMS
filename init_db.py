from app import create_app
from models import db, User, Outlet, Category, Customer
import os

def init_database():
    """Initialize database with tables and seed data for Chunk 2"""
    # Delete existing database to ensure clean schema update
    db_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance', 'pos_v2.db')
    if os.path.exists(db_path):
        print(f"Removing existing database at {db_path} to apply Chunk 2 schema...")
        try:
            os.remove(db_path)
        except PermissionError:
            print("Error: Keep the database file closed! close any DB viewers.")
            
    app = create_app()
    
    with app.app_context():
        # Drop all tables and recreate (for development only)
        print("Dropping all tables to ensure clean state...")
        db.drop_all()
        print("Creating database tables...")
        db.create_all()
        
        # 1. Create Central Warehouse (ID 1) - SYSTEM CRITICAL
        print("Seeding Central Warehouse (ID 1)...")
        warehouse = Outlet(
            id=1,
            name='Central Warehouse',
            code='WH-MAIN',
            address='Industrial Estate, Main Logistics Hub',
            city='Lagos',
            state='Lagos',
            is_warehouse=True,
            is_active=True
        )
        db.session.add(warehouse)
        
        # 2. Create Active Outlets for Testing
        print("Seeding Test Outlets...")
        outlets = [
            Outlet(
                name='Lekki Branch',
                code='OUT-001',
                address='14 Admiralty Way',
                city='Lagos',
                manager_name='Ahmed Johnson',
                phone='+234 800 123 4567',
                is_active=True
            ),
            Outlet(
                name='Ikeja City Mall',
                code='OUT-002',
                address='Obafemi Awolowo Way',
                city='Lagos',
                manager_name='Sarah Williams',
                phone='+234 800 987 6543',
                is_active=True
            ),
            Outlet(
                name='Abuja Central',
                code='OUT-003',
                address='Garki Area 11',
                city='Abuja',
                manager_name='Musa Ibrahim',
                is_active=True
            ),
        ]
        
        for outlet in outlets:
            db.session.add(outlet)
        
        db.session.commit()
        print(f"Created Warehouse + {len(outlets)} outlets")
        
        # 3. Create Super Admin user
        print("Creating Super Admin user...")
        admin = User(
            username='admin',
            email='admin@heriglobal.com',
            full_name='System Administrator',
            role='super_admin',
            outlet_id=None,
            is_active=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
        
        # 4. Create General Manager
        print("Creating General Manager...")
        gm = User(
            username='manager',
            email='gm@heriglobal.com',
            full_name='General Manager',
            role='general_manager',
            outlet_id=None,
            is_active=True
        )
        gm.set_password('manager123')
        db.session.add(gm)
        
        db.session.commit()
        
        # 5. Create Outlet Admin (assigned to OUT-001)
        # Need to fetch outlet first to be safe, though we just added it
        outlet_1 = Outlet.query.filter_by(code='OUT-001').first()
        
        print("Creating Outlet Admin...")
        outlet_admin = User(
            username='outlet_admin',
            email='store@heriglobal.com',
            full_name='Lekki Store Manager',
            role='outlet_admin',
            outlet_id=outlet_1.id,
            is_active=True
        )
        outlet_admin.set_password('store123')
        db.session.add(outlet_admin)
        
        # 6. Seed Product Categories
        print("Seeding Product Categories...")
        categories = ['Electronics', 'Beverages', 'Food Items', 'Household', 'Personal Care']
        for cat_name in categories:
            if not Category.query.filter_by(name=cat_name).first():
                db.session.add(Category(name=cat_name))
        
        db.session.commit()

        # 7. Seed Walk-In Customer (ID 1)
        print("Seeding Walk-In Customer...")
        if not Customer.query.get(1):
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
            db.session.commit()
            print("Walk-In Customer created.")
        else:
             print("Walk-In Customer already exists.")
        
        print("Seeding Payment Modes...")
        from models import PaymentMode
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
                    created_by=admin.id
                )
                db.session.add(mode)
                print(f"Seeded Payment Mode: {mode.name}")
            else:
                print(f"Payment Mode {mode.name} already exists.")

        db.session.commit()
        
        print("Database initialized successfully for Chunk 2!")
        print("-" * 40)
        print("Credentials:")
        print("Super Admin: admin / admin123")
        print("Manager: manager / manager123")
        print("Outlet Admin: outlet_admin / store123")
        print("-" * 40)

if __name__ == '__main__':
    init_database()
