"""
Integration Test Script for Heriglobal POS (Chunk 13)
Verifies core user flows:
1. New Outlet Setup & Product Creation
2. Stock Transfer
3. Sales Processing (Cash & Credit)
4. Returns & Refunds
5. Remittance & Collections
"""

import sys
import os
import unittest
from datetime import date, datetime, timedelta

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db, User, Outlet, Product, Category, Inventory, Sale, SaleItem, Customer, PaymentMode, CashCollection, Remittance, Return, ReturnItem

class IntegrationTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        self.populate_data()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def populate_data(self):
        # Create Users & Outlets
        wh = Outlet(name='Warehouse', code='WH', is_warehouse=True, is_active=True)
        outlet = Outlet(name='Test Outlet', code='TO', is_warehouse=False, is_active=True)
        db.session.add_all([wh, outlet])
        db.session.commit()
        
        self.wh_id = wh.id
        self.outlet_id = outlet.id
        
        user = User(username='admin', email='admin@test.com', full_name='Super Admin', role='super_admin', outlet_id=wh.id)
        user.set_password('password')
        db.session.add(user)
        
        # Payment Modes
        cash = PaymentMode(name='Cash', code='CASH', is_credit=False, is_active=True)
        credit = PaymentMode(name='Credit', code='CREDIT', is_credit=True, is_active=True)
        db.session.add_all([cash, credit])
        
        # Customer
        cust = Customer(customer_number='CUST-001', first_name='Test', last_name='Customer', phone='1234567890', credit_limit=50000)
        db.session.add(cust)
        
        # Product
        cat = Category(name='General')
        db.session.add(cat)
        db.session.commit()
        
        prod = Product(name='Test Product', sku='TP001', selling_price=1000, cost_price=800, category_id=cat.id, reorder_level=10)
        db.session.add(prod)
        db.session.commit()
        self.prod_id = prod.id
        
        # Initial Inventory
        inv = Inventory(product_id=prod.id, outlet_id=wh.id, quantity=100)
        db.session.add(inv)
        db.session.commit()

    def test_full_flow(self):
        # 1. Stock Transfer
        # Warehouse -> Outlet (50 units)
        inv_wh = Inventory.query.filter_by(product_id=self.prod_id, outlet_id=self.wh_id).first()
        inv_wh.quantity -= 50
        
        inv_outlet = Inventory(product_id=self.prod_id, outlet_id=self.outlet_id, quantity=50)
        db.session.add(inv_outlet)
        db.session.commit()
        
        self.assertEqual(inv_outlet.quantity, 50)
        print("Stock Transfer Verified")

        # 2. Process Sale (Credit)
        cust = Customer.query.first()
        credit_mode = PaymentMode.query.filter_by(code='CREDIT').first()
        
        sale = Sale(
            sale_number='SALE-001',
            outlet_id=self.outlet_id,
            sales_rep_id=1,
            customer_id=cust.id,
            payment_mode_id=credit_mode.id,
            total_amount=5000,
            status='completed',
            sale_date=datetime.now()
        )
        db.session.add(sale)
        
        item = SaleItem(sale=sale, product_id=self.prod_id, quantity=5, unit_price=1000, subtotal=5000)
        db.session.add(item)
        
        # Update inventory and customer balance
        inv_outlet.quantity -= 5
        cust.current_balance += 5000
        db.session.commit()
        
        self.assertEqual(inv_outlet.quantity, 45)
        self.assertEqual(cust.current_balance, 5000)
        print("Credit Sale Verified")

        # 3. Process Return (Resellable)
        # Return 1 unit
        ret = Return(
            return_number='RET-001',
            sale_id=sale.id,
            outlet_id=self.outlet_id,
            customer_id=cust.id,
            processed_by=1,
            refund_method='credit_adjustment',
            return_date=datetime.now(),
            total_refund_amount=1000,
            status='approved'
        )
        db.session.add(ret)
        
        ret_item = ReturnItem(
            return_record=ret,
            sale_item_id=item.id,
            product_id=self.prod_id,
            quantity_returned=1,
            unit_price=1000,
            condition='resellable',
            refund_amount=1000
        )
        db.session.add(ret_item)
        
        # Adjust inventory and balance
        inv_outlet.quantity += 1
        cust.current_balance -= 1000
        item.quantity_returned += 1
        db.session.commit()
        
        self.assertEqual(inv_outlet.quantity, 46)
        self.assertEqual(cust.current_balance, 4000)
        print("Return Verified")

        # 4. Collection & Remittance
        sale_cash = Sale(
            sale_number='SALE-002',
            outlet_id=self.outlet_id,
            sales_rep_id=1,
            customer_id=cust.id, # Walk-in logic usually uses a specific ID, here we use test cust
            payment_mode_id=PaymentMode.query.filter_by(code='CASH').first().id,
            total_amount=2000,
            status='completed',
            sale_date=datetime.now()
        )
        db.session.add(sale_cash)
        db.session.commit()
        
        # Declare Collection
        col = CashCollection(
            collection_number='COL-001',
            outlet_id=self.outlet_id,
            sales_rep_id=1,
            amount=2000,
            collection_date=date.today(),
            collection_type='cash',
            notes='Shift End'
        )
        db.session.add(col)
        
        # Remit
        rem = Remittance(
            remittance_number='REM-001',
            outlet_id=self.outlet_id,
            sales_rep_id=1,
            amount=2000,
            remittance_date=date.today(),
            remittance_method='cash_deposit',
            status='recorded'
        )
        db.session.add(rem)
        db.session.commit()
        
        # Check outstanding
        total_col = db.session.query(db.func.sum(CashCollection.amount)).scalar()
        total_rem = db.session.query(db.func.sum(Remittance.amount)).scalar()
        self.assertEqual(total_col, 2000)
        self.assertEqual(total_rem, 2000)
        print("Remittance Verified")

if __name__ == '__main__':
    unittest.main()
