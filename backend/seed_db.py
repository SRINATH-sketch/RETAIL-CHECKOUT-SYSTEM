import os
import sys

# Add the parent folder to the system path to allow importing the app module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import db
from app.utils.logger import logger

def seed():
    """
    Populates SQLite database with default product names and prices.
    """
    # Define products: (id/class_name, display_name, price)
    seed_products = [
        # Custom frontend demo products
        ("bananas", "Organic Bananas (Bunch)", 60.00),
        ("banana", "Organic Bananas (Bunch)", 60.00),
        ("milk", "Fresh Milk 1L", 50.00),
        ("bread", "Whole Wheat Bread", 45.00),
        ("cookies", "Chocolate Cookies (Pack)", 80.00),
        
        # Standard COCO classes (useful if using yolo11n.pt)
        ("bottle", "Fresh Milk 1L", 50.00),   # Map bottle to milk
        ("apple", "Fresh Red Apple", 40.00),
        ("orange", "Fresh Orange", 35.00),
        ("cup", "Disposable Cup", 15.00),
        ("sandwich", "Fresh Club Sandwich", 75.00),
        ("pizza", "Large Cheese Pizza", 249.00),
        ("donut", "Glazed Donut", 45.00),
        ("cake", "Chocolate Cake Slice", 120.00),
        ("broccoli", "Organic Broccoli Head", 55.00),
        ("carrot", "Organic Carrot", 25.00)
    ]
    
    logger.info("Initializing database tables for seeding...")
    db.init_db()
    
    logger.info("Seeding product prices into SQLite database...")
    for class_id, name, price in seed_products:
        db.upsert_product(class_id, name, price)
        logger.info(f"Registered: {class_id} -> '{name}' @ Rs. {price:.2f}")
        
    logger.info("Database seeding completed successfully.")

if __name__ == '__main__':
    seed()
