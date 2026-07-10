import sqlite3
import os
from flask import current_app
from app.config import Config

def get_db_connection():
    """
    Establish a connection to the SQLite database and set row_factory to sqlite3.Row
    to enable dictionary-like access to query results.
    """
    try:
        from flask import current_app
        # Check if there is an active Flask app context and get DB_PATH from it
        db_path = current_app.config.get('DB_PATH')
    except RuntimeError:
        # Fallback if we are running outside a Flask app context (e.g., seeding script)
        db_path = Config.DB_PATH

    if not db_path:
        db_path = Config.DB_PATH

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Initialize SQLite tables:
    1. products  – product prices mapped to YOLO class labels.
    2. cart      – active checkout items; track_id is PRIMARY KEY (no double-counting).
    3. inventory – stock levels per product, checked by the RetailAgent.
    Also seeds complementary products (cup, yogurt, butter, tea, honey) so
    RetailAgent recommendations always resolve to real DB entries.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Products table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id    TEXT PRIMARY KEY,
            name  TEXT NOT NULL,
            price REAL NOT NULL
        )
    ''')

    # 2. Cart table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cart (
            track_id   TEXT PRIMARY KEY,
            product_id TEXT NOT NULL,
            quantity   INTEGER DEFAULT 1,
            added_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')

    # 3. Inventory table (stock per product)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            product_id TEXT PRIMARY KEY,
            stock      INTEGER DEFAULT 100,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')

    conn.commit()

    # Seed complementary / suggested products so recommendations always
    # resolve to real DB rows with prices and names.
    _seed_complementary_products(cursor, conn)

    conn.close()


# Complementary products seeded at startup
_COMPLEMENTARY_SEED = [
    ("cup",    "Tea Cup",          30.00,  50),
    ("yogurt", "Fresh Yogurt",     45.00,  60),
    ("butter", "Salted Butter",    55.00,  40),
    ("tea",    "Masala Tea Packet", 35.00,  80),
    ("honey",  "Natural Honey",    120.00, 30),
    # Core detectable products with stock
    ("milk",   "Fresh Milk",       50.00, 100),
    ("banana", "Organic Bananas",  60.00,  75),
    ("apple",  "Red Apple",        40.00,  90),
    ("bread",  "Whole Wheat Bread",70.00,  50),
    ("biscuits","Cream Biscuits",  30.00,  60),
]


def _seed_complementary_products(cursor, conn):
    """
    Upsert complementary products into `products` and `inventory` tables.
    Uses INSERT OR IGNORE so existing rows (with real prices) are never overwritten.
    """
    for pid, name, price, stock in _COMPLEMENTARY_SEED:
        cursor.execute(
            'INSERT OR IGNORE INTO products (id, name, price) VALUES (?, ?, ?)',
            (pid, name, price)
        )
        cursor.execute(
            'INSERT OR IGNORE INTO inventory (product_id, stock) VALUES (?, ?)',
            (pid, stock)
        )
    conn.commit()

def get_product(product_id):
    """
    Retrieve product details by product_id (YOLO class name/ID).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE id = ?', (product_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def upsert_product(product_id, name, price):
    """
    Insert or update a product.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO products (id, name, price)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            price = excluded.price
    ''', (product_id, name, price))
    conn.commit()
    conn.close()

def get_all_products():
    """
    Fetch all products from database.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def add_to_cart(track_id, product_id, quantity=1):
    """
    Insert a tracked item into the cart. 
    Use INSERT OR IGNORE to ensure track_id is added EXACTLY ONCE.
    If track_id already exists in the cart, this operation is ignored.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO cart (track_id, product_id, quantity)
        VALUES (?, ?, ?)
    ''', (track_id, product_id, quantity))
    conn.commit()
    inserted = cursor.rowcount > 0
    conn.close()
    return inserted

def get_cart_summary():
    """
    Query the cart database and summarize items.
    Returns a dictionary with:
    - products: list of {id, name, quantity, price, subtotal}
    - total_bill: float
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Summarize quantities by grouping by product_id
    cursor.execute('''
        SELECT 
            p.id as product_id,
            p.name as product_name,
            COUNT(c.track_id) as quantity,
            p.price as unit_price
        FROM cart c
        JOIN products p ON c.product_id = p.id
        GROUP BY p.id
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    products_list = []
    total_bill = 0.0
    
    for row in rows:
        subtotal = row['quantity'] * row['unit_price']
        total_bill += subtotal
        products_list.append({
            'id': row['product_id'],
            'name': row['product_name'],
            'quantity': row['quantity'],
            'price': row['unit_price'],
            'subtotal': round(subtotal, 2)
        })
        
    return {
        'products': products_list,
        'total_bill': round(total_bill, 2)
    }

def clear_cart():
    """
    Clear all items in the shopping cart.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM cart')
    conn.commit()
    conn.close()

def remove_from_cart(track_id: str) -> bool:
    """
    Remove a single tracked item from the cart by its DeepSORT track_id.
    Called by ShoppingAgent when an item exits the basket.
    Returns True if a row was actually deleted.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM cart WHERE track_id = ?', (track_id,))
    conn.commit()
    removed = cursor.rowcount > 0
    conn.close()
    return removed


def get_stock(product_id: str) -> int | None:
    """
    Return current stock level for a product from the inventory table.
    Returns None if the product has no inventory record.
    Used by RetailAgent for stock availability checks.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT stock FROM inventory WHERE product_id = ?', (product_id,))
    row = cursor.fetchone()
    conn.close()
    return row['stock'] if row else None


def update_stock(product_id: str, delta: int) -> bool:
    """
    Adjust stock by `delta` (negative to decrement, positive to restock).
    Clamps stock to 0 minimum.
    Returns True if the row was updated.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE inventory SET stock = MAX(0, stock + ?) WHERE product_id = ?',
        (delta, product_id)
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated


