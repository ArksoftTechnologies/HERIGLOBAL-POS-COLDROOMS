import requests
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from models import User, Customer, Repayment, Outlet, PaymentMode, Sale
from datetime import datetime

def verify_repayments():
    app = create_app()
    with app.app_context():
        print("Starting Verification for Chunk 7: Credit Repayments...")

        # 1. Setup Test Data
        admin = User.query.filter_by(username='admin').first()
        outlet = Outlet.query.first()
        customer = Customer.query.filter_by(customer_number='CUST-TEST-REP').first()
        
        if not customer:
            customer = Customer(
                first_name='Test',
                last_name='Repayment Customer',
                customer_number='CUST-TEST-REP',
                email='test@repay.com',
                phone='09099998888',
                address='Test Address',
                primary_outlet_id=outlet.id,
                created_by=admin.id,
                credit_limit=50000.00,
                current_balance=10000.00, # Initial Balance
                is_active=True
            )
            db.session.add(customer)
            db.session.commit()
            print(f"Created test customer with balance: {customer.current_balance}")
        else:
            customer.current_balance = 10000.00
            db.session.commit()
            print(f"Reset test customer balance to: {customer.current_balance}")

        # Ensure Payment Modes
        cash_mode = PaymentMode.query.filter_by(name='Cash').first()
        bank_mode = PaymentMode.query.filter_by(name='Bank Transfer').first()
        
        if not cash_mode or not bank_mode:
            print("Error: Required payment modes (Cash, Bank Transfer) not found.")
            return

        # 2. Test Atomic Repayment (Single)
        print("\nTest 1: Single Repayment (Cash)...")
        with app.test_client() as client:
            client.post('/auth/login', data={'username': 'admin', 'password': 'admin123'})
            
            payload = {
                'customer_id': customer.id,
                'amount': 2000.00,
                'payment_type': 'single',
                'payment_mode_id': cash_mode.id,
                'notes': 'Test Cash Payment'
            }
            
            resp = client.post('/repayments/create', json=payload)
            if resp.status_code == 200:
                print("[PASS] Repayment created successfully.")
                data = resp.get_json()
                print(f"Repayment ID: {data['repayment_id']}, Number: {data['repayment_number']}")
                
                # Check Balance
                updated_customer = Customer.query.get(customer.id)
                if updated_customer.current_balance == 8000.00:
                    print(f"[PASS] Balance updated correctly: {updated_customer.current_balance}")
                else:
                    print(f"[FAIL] Balance incorrect: {updated_customer.current_balance} (Expected 8000.00)")
            else:
                print(f"[FAIL] Repayment failed: {resp.data}")

        # 3. Test Overpayment Prevention
        print("\nTest 2: Overpayment Prevention...")
        with app.test_client() as client:
            client.post('/auth/login', data={'username': 'admin', 'password': 'admin123'})
            
            payload = {
                'customer_id': customer.id,
                'amount': 9000.00, # Exceeds 8000
                'payment_type': 'single',
                'payment_mode_id': cash_mode.id
            }
            
            resp = client.post('/repayments/create', json=payload)
            if resp.status_code == 400:
                print("[PASS] Overpayment blocked successfully.")
            else:
                print(f"[FAIL] Overpayment NOT blocked! Status: {resp.status_code}")

        # 4. Test Split Repayment
        print("\nTest 3: Split Repayment...")
        with app.test_client() as client:
            client.post('/auth/login', data={'username': 'admin', 'password': 'admin123'})
            
            payload = {
                'customer_id': customer.id,
                'amount': 5000.00,
                'payment_type': 'split',
                'split_payments': [
                    {'payment_mode_id': cash_mode.id, 'amount': 2000.00, 'reference': ''},
                    {'payment_mode_id': bank_mode.id, 'amount': 3000.00, 'reference': 'REF123'}
                ]
            }
            
            resp = client.post('/repayments/create', json=payload)
            if resp.status_code == 200:
                print("[PASS] Split Repayment created successfully.")
                
                # Check Balance
                updated_customer = Customer.query.get(customer.id)
                if updated_customer.current_balance == 3000.00: # 8000 - 5000
                    print(f"[PASS] Balance updated correctly: {updated_customer.current_balance}")
                else:
                    print(f"[FAIL] Balance incorrect: {updated_customer.current_balance} (Expected 3000.00)")
            else:
                print(f"[FAIL] Split Repayment failed: {resp.data}")

        # 5. Test Ledger View
        print("\nTest 4: Ledger View...")
        with app.test_client() as client:
            client.post('/auth/login', data={'username': 'admin', 'password': 'admin123'})
            
            resp = client.get(f'/repayments/customers/{customer.id}/ledger')
            if resp.status_code == 200:
                print("[PASS] Ledger view loaded successfully.")
                if b'Transaction History' in resp.data:
                    print("[PASS] Ledger content found.")
            else:
                print(f"[FAIL] Ledger view failed: {resp.status_code}")

if __name__ == "__main__":
    verify_repayments()
