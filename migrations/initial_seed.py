"""
Initial data seeding script to populate essential system data.
Run this after database migration.
"""

from app import create_app
from models import db, Outlet, PaymentMode, ExpenseCategory, Customer, User

def seed_initial_data():
    app = create_app()
    with app.app_context():
        print("Seeding initial data...")
        
        # 1. Create Warehouse
        if not Outlet.query.filter_by(code='WH-MAIN').first():
            warehouse = Outlet(
                name='Central Warehouse',
                code='WH-MAIN',
                address='Main Street, Lagos',
                city='Lagos',
                state='Lagos',
                is_warehouse=True,
                is_active=True
            )
            db.session.add(warehouse)
            print("  Created Warehouse")

        # 2. Default Payment Modes
        default_modes = [
            {'name': 'Cash', 'code': 'CASH', 'is_credit': False, 'requires_reference': False},
            {'name': 'Credit', 'code': 'CREDIT', 'is_credit': True, 'requires_reference': False},
            {'name': 'Bank Transfer', 'code': 'BANK', 'is_credit': False, 'requires_reference': True},
            {'name': 'POS Terminal', 'code': 'POS', 'is_credit': False, 'requires_reference': True}
        ]
        
        for mode_data in default_modes:
            if not PaymentMode.query.filter_by(code=mode_data['code']).first():
                mode = PaymentMode(
                    name=mode_data['name'],
                    code=mode_data['code'],
                    is_credit=mode_data['is_credit'],
                    requires_reference=mode_data['requires_reference'],
                    is_system_default=True,
                    is_active=True
                )
                db.session.add(mode)
                print(f"  Created Payment Mode: {mode_data['name']}")

        # 3. Default Expense Categories
        categories = ['Transportation', 'Logistics', 'Fuel', 'Meals', 'Communication', 'Supplies', 'Emergency', 'Other']
        for cat_name in categories:
            if not ExpenseCategory.query.filter_by(name=cat_name).first():
                cat = ExpenseCategory(name=cat_name, description=f'{cat_name} expenses', is_active=True)
                db.session.add(cat)
                print(f"  Created Expense Category: {cat_name}")

        # 4. Walk-In Customer
        if not Customer.query.filter_by(is_walk_in=True).first():
            walk_in = Customer(
                customer_number='CUST-WALKIN',
                first_name='Walk-In',
                last_name='Customer',
                phone='0000000000',
                credit_limit=0.0,
                current_balance=0.0,
                is_walk_in=True,
                is_active=True
            )
            db.session.add(walk_in)
            print("  Created Walk-In Customer")
            
        db.session.commit()
        print("Initial data seeding completed successfully!")

if __name__ == '__main__':
    seed_initial_data()
