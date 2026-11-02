import sys
import os
import json
import uuid

# Add the parent folder to the system path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app import create_app
from app.database import db

app = create_app()

def test_auth_and_carts():
    with app.test_client() as client:
        # 1. Registration Test
        res = client.post('/api/auth/register', json={
            "full_name": "Test User 1",
            "email": f"test1_{uuid.uuid4().hex[:4]}@example.com",
            "password": "password123"
        })
        assert res.status_code == 200, f"Register failed: {res.json}"
        print("Registration successful.")

        res = client.post('/api/auth/register', json={
            "full_name": "Test User 2",
            "email": f"test2_{uuid.uuid4().hex[:4]}@example.com",
            "password": "password123"
        })
        assert res.status_code == 200, "Register 2 failed"
        
        # 2. Login Test
        email1 = res.json.get('email', "test1_@example.com") # fallback, actual email is in request but we don't save it. Wait, the response doesn't return email.
        pass

        # Since we generated dynamic emails, let's track them
        email1 = f"u1_{uuid.uuid4().hex[:6]}@example.com"
        email2 = f"u2_{uuid.uuid4().hex[:6]}@example.com"
        
        client.post('/api/auth/register', json={"full_name": "U1", "email": email1, "password": "pw"})
        client.post('/api/auth/register', json={"full_name": "U2", "email": email2, "password": "pw"})

        res1 = client.post('/api/auth/login', json={"email": email1, "password": "pw"})
        assert res1.status_code == 200
        token1 = res1.json['token']
        store1 = res1.json['stores'][0]['id']

        res2 = client.post('/api/auth/login', json={"email": email2, "password": "pw"})
        assert res2.status_code == 200
        token2 = res2.json['token']
        store2 = res2.json['stores'][0]['id']

        print("Login successful. Tokens generated.")

        # 3. Test isolation and concurrent carts
        # U1 adds product to their store
        client.post('/api/products', json={"id": "apple", "name": "Apple", "price": 40}, headers={"Authorization": f"Bearer {token1}", "X-Store-ID": str(store1)})
        # U2 adds product to their store with DIFFERENT price
        client.post('/api/products', json={"id": "apple", "name": "Premium Apple", "price": 60}, headers={"Authorization": f"Bearer {token2}", "X-Store-ID": str(store2)})

        # Manually add to cart using db.add_to_cart for test (or hit detect-frame, but detect frame is complex with image)
        # We can just check products list first
        p1 = client.get('/api/products', headers={"Authorization": f"Bearer {token1}", "X-Store-ID": str(store1)}).json
        p2 = client.get('/api/products', headers={"Authorization": f"Bearer {token2}", "X-Store-ID": str(store2)}).json
        
        assert any(p['price'] == 40 for p in p1['products']), "U1 product price mismatch"
        assert any(p['price'] == 60 for p in p2['products']), "U2 product price mismatch"
        print("Product isolation verified.")

        # Test cart independence
        from app.database import db
        with app.app_context():
            u1_id = res1.json['user']['id']
            u2_id = res2.json['user']['id']
            db.add_to_cart(store1, u1_id, "track_1", "apple", 1)
            db.add_to_cart(store2, u2_id, "track_1", "apple", 1) # Same track ID but different user/store

        cart1 = client.get('/api/cart', headers={"Authorization": f"Bearer {token1}", "X-Store-ID": str(store1)}).json
        cart2 = client.get('/api/cart', headers={"Authorization": f"Bearer {token2}", "X-Store-ID": str(store2)}).json

        assert cart1['total_bill'] == 40.0
        assert cart2['total_bill'] == 60.0
        print("Concurrent carts isolation verified.")

if __name__ == '__main__':
    test_auth_and_carts()
    print("ALL TESTS PASSED")
