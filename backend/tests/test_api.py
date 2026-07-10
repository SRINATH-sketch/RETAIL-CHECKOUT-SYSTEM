import unittest
import json
import os
import sys
import tempfile
import cv2
import numpy as np

# Add parent directory to system path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.config import Config
from app.database import db

class SmartCheckoutTestCase(unittest.TestCase):
    def setUp(self):
        # Create a temporary database file
        self.db_fd, self.db_path = tempfile.mkstemp()
        
        # Override configuration
        class TestConfig(Config):
            DB_PATH = self.db_path
            SQLALCHEMY_DATABASE_URI = f'sqlite:///{self.db_path}'
            # Use same uploads folder
            
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        
        # Seed test database manually
        with self.app.app_context():
            db.init_db()
            db.upsert_product("apple", "Fresh Red Apple", 40.00)
            db.upsert_product("banana", "Organic Bananas", 60.00)
            db.upsert_product("milk", "Fresh Milk", 50.00)

    def tearDown(self):
        # Close and delete the database file
        os.close(self.db_fd)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_get_products(self):
        """Test listing products from database"""
        response = self.client.get('/api/products')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        # DB now seeds complementary products too, so just verify list is non-empty
        # and contains the apple that setUp inserted
        self.assertGreater(len(data['products']), 0)
        product_ids = [p['id'] for p in data['products']]
        self.assertIn('apple', product_ids)
        apple = next(p for p in data['products'] if p['id'] == 'apple')
        self.assertEqual(apple['price'], 40.00)

    def test_add_product(self):
        """Test inserting/updating product details"""
        payload = {"id": "orange", "name": "Fresh Orange", "price": 35.00}
        response = self.client.post('/api/products', 
                                    data=json.dumps(payload),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        
        # Verify it was added
        response = self.client.get('/api/products')
        data = json.loads(response.data)
        product_ids = [p['id'] for p in data['products']]
        self.assertIn('orange', product_ids)
        
        # Verify updating price
        payload = {"id": "orange", "name": "Fresh Orange", "price": 38.00}
        self.client.post('/api/products', 
                         data=json.dumps(payload),
                         content_type='application/json')
        
        with self.app.app_context():
            prod = db.get_product("orange")
            self.assertEqual(prod['price'], 38.00)

    def test_cart_management(self):
        """Test adding items, checking summary, and clearing cart"""
        with self.app.app_context():
            # Add unique track items
            db.add_to_cart("track_1", "apple")
            db.add_to_cart("track_2", "apple")  # Should increment quantity to 2
            db.add_to_cart("track_1", "apple")  # Should be ignored (duplicate track ID)
            db.add_to_cart("track_3", "banana")
            
        response = self.client.get('/api/cart')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        
        # Check details
        products = data['products']
        self.assertEqual(len(products), 2)
        
        # Sort to test consistently
        products.sort(key=lambda x: x['id'])
        
        # Apple
        self.assertEqual(products[0]['id'], 'apple')
        self.assertEqual(products[0]['quantity'], 2)
        self.assertEqual(products[0]['price'], 40.00)
        self.assertEqual(products[0]['subtotal'], 80.00)
        
        # Banana
        self.assertEqual(products[1]['id'], 'banana')
        self.assertEqual(products[1]['quantity'], 1)
        self.assertEqual(products[1]['price'], 60.00)
        self.assertEqual(products[1]['subtotal'], 60.00)
        
        # Total bill = 80 + 60 = 140
        self.assertEqual(data['total_bill'], 140.00)
        
        # Clear cart
        response = self.client.delete('/api/cart')
        self.assertEqual(response.status_code, 200)
        
        # Verify cart is empty
        response = self.client.get('/api/cart')
        data = json.loads(response.data)
        self.assertEqual(len(data['products']), 0)
        self.assertEqual(data['total_bill'], 0.00)

    def test_detect_frame(self):
        """Test processing single frame image (webcam endpoint)"""
        # Create a dummy blank image in memory
        img = np.zeros((300, 300, 3), dtype=np.uint8)
        _, img_encoded = cv2.imencode('.jpg', img)
        img_bytes = img_encoded.tobytes()
        
        # Send post request with file
        data = {
            'file': (tempfile.NamedTemporaryFile(suffix='.jpg'), 'test.jpg')
        }
        
        # Recreate test file payload correctly
        import io
        response = self.client.post(
            '/api/detect-frame',
            data={'file': (io.BytesIO(img_bytes), 'test.jpg')},
            content_type='multipart/form-data'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertIn('detections', data)
        self.assertIn('products', data)
        self.assertEqual(data['total_bill'], 0.00)

    def _make_synthetic_video(self):
        """Create a small synthetic MP4 video in a temp file for testing."""
        tmp = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
        tmp.close()
        width, height, fps, num_frames = 320, 240, 10, 15
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(tmp.name, fourcc, fps, (width, height))
        for i in range(num_frames):
            # Simple gradient frame so video is non-empty
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            frame[:, :, 1] = int(255 * i / num_frames)  # green gradient
            writer.write(frame)
        writer.release()
        return tmp.name

    def test_detect_video_upload(self):
        """Test processing an uploaded video file end-to-end (network-free)."""
        video_path = self._make_synthetic_video()
        try:
            with open(video_path, 'rb') as vf:
                import io
                video_bytes = vf.read()
            response = self.client.post(
                '/api/detect',
                data={'file': (io.BytesIO(video_bytes), 'test_video.mp4')},
                content_type='multipart/form-data'
            )
            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertTrue(data['success'])
            self.assertIn('video_url', data)
            self.assertIn('products', data)
            self.assertIn('total_bill', data)
        finally:
            if os.path.exists(video_path):
                os.unlink(video_path)

if __name__ == '__main__':
    unittest.main()

