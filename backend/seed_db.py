import os
import sys
import random
from datetime import datetime, timedelta
from flask_bcrypt import Bcrypt

# Add the parent folder to the system path to allow importing the app module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import db
from app.utils.logger import logger

bcrypt = Bcrypt()

def seed():
    """
    Populates SQLite database with default products, inventory, users, and realistic sales transactions.
    """
    logger.info("Initializing database tables for seeding...")
    db.init_db()

    # 1. Ensure Default Store exists
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM stores WHERE id = 1")
    store = cursor.fetchone()
    if not store:
        cursor.execute("INSERT INTO stores (id, name, address) VALUES (1, 'SuperMart Flagship Store', '742 Evergreen Terrace')")
        conn.commit()
    conn.close()

    # 2. Ensure Users exist
    users_to_seed = [
        ("Store Owner", "store1@gmail.com", "admin123", "admin"),
        ("Regular Customer", "user1@gmail.com", "user123", "user"),
        ("Sarah Jenkins", "sarah@example.com", "user123", "user"),
        ("John Doe", "john@example.com", "user123", "user"),
        ("Emma Watson", "emma@example.com", "user123", "user"),
        ("Michael Scott", "michael@example.com", "user123", "user")
    ]

    user_ids = []
    for name, email, password, role in users_to_seed:
        user = db.get_user_by_email(email)
        if not user:
            hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
            uid = db.create_user(name, email, hashed_pw, role)
            user_ids.append(uid)
            c = db.get_db_connection()
            cur = c.cursor()
            cur.execute("INSERT OR IGNORE INTO store_members (user_id, store_id, role) VALUES (?, 1, ?)", 
                        (uid, 'owner' if role == 'admin' else 'customer'))
            c.commit()
            c.close()
        else:
            user_ids.append(user['id'])

    # 3. Seed Products & Inventory
    seed_products = [
        ("bananas", "Organic Bananas (Bunch)", 60.00, 75),
        ("banana", "Organic Bananas (Bunch)", 60.00, 75),
        ("milk", "Fresh Milk 1L", 50.00, 15),       # Low stock!
        ("bread", "Whole Wheat Bread", 45.00, 12),     # Low stock!
        ("cookies", "Chocolate Cookies (Pack)", 80.00, 45),
        ("bottle", "Fresh Milk 1L", 50.00, 15),
        ("apple", "Fresh Red Apple", 40.00, 85),
        ("orange", "Fresh Orange", 35.00, 8),          # Low stock!
        ("cup", "Disposable Cup", 15.00, 120),
        ("sandwich", "Fresh Club Sandwich", 75.00, 5), # Low stock!
        ("pizza", "Large Cheese Pizza", 249.00, 30),
        ("donut", "Glazed Donut", 45.00, 50),
        ("cake", "Chocolate Cake Slice", 120.00, 18),  # Low stock!
        ("broccoli", "Organic Broccoli Head", 55.00, 40),
        ("carrot", "Organic Carrot", 25.00, 60),
        ("yogurt", "Fresh Greek Yogurt", 45.00, 60),
        ("butter", "Salted Butter 200g", 55.00, 40),
        ("tea", "Masala Tea Packet", 35.00, 80),
        ("honey", "Natural Organic Honey", 120.00, 30),
        ("biscuits", "Cream Biscuits Pack", 30.00, 60)
    ]

    c = db.get_db_connection()
    cur = c.cursor()
    for class_id, name, price, stock in seed_products:
        cur.execute('''
            INSERT INTO products (store_id, id, name, price)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(store_id, id) DO UPDATE SET name=excluded.name, price=excluded.price
        ''', (class_id, name, price))
        cur.execute("INSERT OR REPLACE INTO inventory (store_id, product_id, stock) VALUES (1, ?, ?)", (class_id, stock))
    c.commit()
    c.close()

    # 4. Seed Historical Transactions if empty or sparse
    c = db.get_db_connection()
    cur = c.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM transactions")
    tx_count = cur.fetchone()['cnt']
    c.close()

    if tx_count < 10:
        logger.info("Seeding historical transactions over past 30 days...")
        payment_methods = ['Card', 'UPI', 'Cash', 'Apple Pay']
        now = datetime.now()

        # Product sampling pool
        product_pool = [
            ("bananas", 60.00), ("milk", 50.00), ("bread", 45.00), ("cookies", 80.00),
            ("apple", 40.00), ("orange", 35.00), ("sandwich", 75.00), ("pizza", 249.00),
            ("donut", 45.00), ("cake", 120.00), ("tea", 35.00), ("honey", 120.00)
        ]

        # Generate ~60 transactions across 30 days
        for day_offset in range(30, -1, -1):
            tx_per_day = random.randint(1, 4)
            date_base = now - timedelta(days=day_offset)

            for _ in range(tx_per_day):
                hour = random.randint(9, 21)
                minute = random.randint(0, 59)
                tx_time = date_base.replace(hour=hour, minute=minute, second=random.randint(0, 59))
                formatted_time = tx_time.strftime("%Y-%m-%d %H:%M:%S")

                uid = random.choice(user_ids)
                method = random.choice(payment_methods)

                item_count = random.randint(1, 4)
                chosen_products = random.sample(product_pool, item_count)

                items = []
                total_amount = 0.0
                for pid, price in chosen_products:
                    qty = random.randint(1, 3)
                    subtotal = price * qty
                    total_amount += subtotal
                    items.append({
                        'product_id': pid,
                        'quantity': qty,
                        'unit_price': price
                    })

                db.create_transaction(
                    user_id=uid,
                    store_id=1,
                    amount=round(total_amount, 2),
                    items=items,
                    payment_method=method,
                    created_at=formatted_time,
                    status='completed'
                )

        logger.info("Successfully seeded 60+ historical sales transactions.")

    logger.info("Database seeding completed successfully.")

if __name__ == '__main__':
    seed()
