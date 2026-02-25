import sys
import os
import json

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from models import db, User

def run_tests():
    app = create_app()
    client = app.test_client()
    
    with app.app_context():
        # Setup: Login as admin
        print("Logging in as admin...")
        response = client.post('/auth/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
        
        # Check login success by checking current_user or session, or looking for dashboard text
        # Since we followed redirects, we should be at dashboard
        if response.status_code == 200 and b'Dashboard' in response.data:
            print("[PASS] Login successful")
        else:
            # Fallback check
            if b'Welcome back' in response.data or b'Logout' in response.data:
                 print("[PASS] Login successful (fallback check)")
            else:
                print(f"[FAIL] Login failed. Status: {response.status_code}")
                # print(response.data.decode('utf-8'))
                return

        # Test 1: Search Products
        print("\nTesting Product Search...")
        # Search for 'product' or empty string to get all
        response = client.get('/pos/products/search?q=&outlet_id=1')
        if response.status_code == 200:
            try:
                data = response.json
                print(f"[PASS] Product search returned {len(data)} items")
                if len(data) > 0:
                    print(f"Sample product: {data[0]}")
                    if 'available_stock' in data[0]:
                        print("[PASS] 'available_stock' field present")
                    else:
                        print("[FAIL] 'available_stock' field MISSING")
                    
                    if 'unit_price' in data[0] and isinstance(data[0]['unit_price'], float):
                        print("[PASS] 'unit_price' field present and is float")
                    else:
                         print(f"[FAIL] 'unit_price' check failed: {data[0].get('unit_price')}")
                         
                    if isinstance(data[0]['selling_price'], float):
                        print("[PASS] 'selling_price' is float")
                    else:
                        print(f"[FAIL] 'selling_price' is NOT float: {type(data[0].get('selling_price'))}")
                else:
                    print("[WARN] No products returned - ensure DB is seeded")
            except Exception as e:
                print(f"[FAIL] JSON decode error: {e}")
        else:
            print(f"[FAIL] Product search failed: {response.status_code}")

        # Test 2: Search Customers
        print("\nTesting Customer Search...")
        response = client.get('/customers/search?q=walk')
        if response.status_code == 200:
            try:
                data = response.json
                print(f"[PASS] Customer search returned {len(data)} items")
                if len(data) > 0:
                    print(f"Sample customer: {data[0]}")
                    if 'credit_limit' in data[0] and 'available_credit' in data[0]:
                        print("[PASS] Credit fields present")
                    else:
                        print("[FAIL] Credit fields MISSING")
            except Exception as e:
                print(f"[FAIL] JSON decode error: {e}")
        else:
            print(f"[FAIL] Customer search failed: {response.status_code}")

        # Test 3: Cart Operations
        print("\nTesting Cart Operations...")
        
        # Clear cart first
        client.post('/pos/cart/clear')
        
        # Get cart (should be empty)
        response = client.get('/pos/cart')
        print(f"Initial cart response: {response.json}")
        
        # Add item (need a valid product ID, let's pick from search results)
        products_res = client.get('/pos/products/search?q=&outlet_id=1')
        if products_res.json and len(products_res.json) > 0:
            p = products_res.json[0]
            print(f"Adding product ID {p['id']} to cart...")
            
            res = client.post('/pos/cart/add', json={'product_id': p['id'], 'quantity': 1, 'outlet_id': 1})
            print(f"Add to cart response: {res.json}")
            
            if res.json.get('success'):
                print("[PASS] Added to cart")
            else:
                print(f"[FAIL] Failed to add to cart: {res.json.get('error')}")
                
            # Verify cart persistence
            res = client.get('/pos/cart')
            if len(res.json.get('cart', [])) > 0:
                print("[PASS] Cart has items after fetch")
            else:
                print("[FAIL] Cart is empty after fetch")
                
            # Clear cart
            res = client.post('/pos/cart/clear')
            if res.json.get('success') and res.json.get('cart_count') == 0:
                print("[PASS] Cart cleared successfully")
            else:
                print("[FAIL] Cart clear failed")
        else:
            print("[WARN] No products found to test cart")

if __name__ == '__main__':
    run_tests()
