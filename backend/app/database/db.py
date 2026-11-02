import sqlite3
import os
from flask import current_app
from app.config import Config

def get_db_connection():
    try:
        from flask import current_app
        db_path = current_app.config.get('DB_PATH')
    except RuntimeError:
        db_path = Config.DB_PATH

    if not db_path:
        db_path = Config.DB_PATH

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. New Tables for Auth & Multi-store
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # --- Migration: add role column if missing (existing databases) ---
    cursor.execute("PRAGMA table_info(users)")
    user_cols = [col['name'] for col in cursor.fetchall()]
    if 'role' not in user_cols and user_cols:  # table exists but lacks the column
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS store_members (
            user_id INTEGER NOT NULL,
            store_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            PRIMARY KEY (user_id, store_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (store_id) REFERENCES stores(id)
        )
    ''')

    # Migration for Products, Inventory, and Cart
    # Check if products table has store_id
    cursor.execute("PRAGMA table_info(products)")
    columns = [col['name'] for col in cursor.fetchall()]
    
    if 'store_id' not in columns:
        # Perform Migration
        print("Migrating database to multi-store schema...")
        # Create a default store and user
        cursor.execute("INSERT INTO stores (name, address) VALUES ('Default Store', '123 Main St')")
        default_store_id = cursor.lastrowid
        
        cursor.execute("INSERT INTO users (full_name, email, password_hash) VALUES ('Admin', 'admin@example.com', 'scrypt:32768:8:1$random$hash')")
        default_user_id = cursor.lastrowid
        
        cursor.execute("INSERT INTO store_members (user_id, store_id, role) VALUES (?, ?, 'owner')", (default_user_id, default_store_id))
        
        # Products Migration
        cursor.execute('''
            CREATE TABLE products_new (
                store_id INTEGER NOT NULL,
                id TEXT NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                PRIMARY KEY (store_id, id),
                FOREIGN KEY (store_id) REFERENCES stores(id)
            )
        ''')
        cursor.execute(f"INSERT INTO products_new (store_id, id, name, price) SELECT {default_store_id}, id, name, price FROM products")
        cursor.execute("DROP TABLE products")
        cursor.execute("ALTER TABLE products_new RENAME TO products")

        # Inventory Migration
        cursor.execute('''
            CREATE TABLE inventory_new (
                store_id INTEGER NOT NULL,
                product_id TEXT NOT NULL,
                stock INTEGER DEFAULT 100,
                PRIMARY KEY (store_id, product_id),
                FOREIGN KEY (store_id) REFERENCES stores(id)
            )
        ''')
        cursor.execute(f"INSERT INTO inventory_new (store_id, product_id, stock) SELECT {default_store_id}, product_id, stock FROM inventory")
        cursor.execute("DROP TABLE inventory")
        cursor.execute("ALTER TABLE inventory_new RENAME TO inventory")

        # Cart Migration (Empty the old global cart, as it's unsafe to map to a random user)
        cursor.execute('''
            CREATE TABLE cart_new (
                store_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                track_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (store_id, user_id, track_id),
                FOREIGN KEY (store_id) REFERENCES stores(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        cursor.execute("DROP TABLE cart")
        cursor.execute("ALTER TABLE cart_new RENAME TO cart")

        print("Migration complete. Default store created.")
    else:
        # Ensure tables exist if starting fresh
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                store_id INTEGER NOT NULL,
                id TEXT NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                PRIMARY KEY (store_id, id),
                FOREIGN KEY (store_id) REFERENCES stores(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory (
                store_id INTEGER NOT NULL,
                product_id TEXT NOT NULL,
                stock INTEGER DEFAULT 100,
                PRIMARY KEY (store_id, product_id),
                FOREIGN KEY (store_id) REFERENCES stores(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cart (
                store_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                track_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                quantity INTEGER DEFAULT 1,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (store_id, user_id, track_id),
                FOREIGN KEY (store_id) REFERENCES stores(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

    # Transactions & Sale Items tables — created for all databases
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            store_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'completed',
            payment_method TEXT NOT NULL DEFAULT 'Card',
            customer_name TEXT,
            customer_email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (store_id) REFERENCES stores(id)
        )
    ''')

    # Ensure payment_method, customer_name, customer_email columns exist if table existed previously
    cursor.execute("PRAGMA table_info(transactions)")
    tx_cols = [col['name'] for col in cursor.fetchall()]
    if tx_cols and 'payment_method' not in tx_cols:
        cursor.execute("ALTER TABLE transactions ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'Card'")
    if tx_cols and 'customer_name' not in tx_cols:
        cursor.execute("ALTER TABLE transactions ADD COLUMN customer_name TEXT")
    if tx_cols and 'customer_email' not in tx_cols:
        cursor.execute("ALTER TABLE transactions ADD COLUMN customer_email TEXT")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            product_id TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')

    conn.commit()

    # Seed complementary products for store 1 if it exists
    cursor.execute("SELECT id FROM stores LIMIT 1")
    store_row = cursor.fetchone()
    if store_row:
        _seed_complementary_products(cursor, conn, store_row['id'])

    conn.close()


_COMPLEMENTARY_SEED = [
    ("cup",    "Tea Cup",          30.00,  50),
    ("yogurt", "Fresh Yogurt",     45.00,  60),
    ("butter", "Salted Butter",    55.00,  40),
    ("tea",    "Masala Tea Packet", 35.00,  80),
    ("honey",  "Natural Honey",    120.00, 30),
    ("milk",   "Fresh Milk",       50.00, 100),
    ("banana", "Organic Bananas",  60.00,  75),
    ("apple",  "Red Apple",        40.00,  90),
    ("bread",  "Whole Wheat Bread",70.00,  50),
    ("biscuits","Cream Biscuits",  30.00,  60),
]


def _seed_complementary_products(cursor, conn, store_id):
    for pid, name, price, stock in _COMPLEMENTARY_SEED:
        cursor.execute(
            'INSERT OR IGNORE INTO products (store_id, id, name, price) VALUES (?, ?, ?, ?)',
            (store_id, pid, name, price)
        )
        cursor.execute(
            'INSERT OR IGNORE INTO inventory (store_id, product_id, stock) VALUES (?, ?, ?)',
            (store_id, pid, stock)
        )
    conn.commit()

# --- Products ---
def get_product(store_id, product_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE store_id = ? AND id = ?', (store_id, product_id))
    row = cursor.fetchone()
    conn.close()
    return row

def upsert_product(store_id, product_id, name, price):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO products (store_id, id, name, price)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(store_id, id) DO UPDATE SET
            name = excluded.name,
            price = excluded.price
    ''', (store_id, product_id, name, price))
    conn.commit()
    conn.close()

def get_all_products(store_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE store_id = ?', (store_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# --- Cart ---
def add_to_cart(store_id, user_id, track_id, product_id, quantity=1):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR IGNORE INTO cart (store_id, user_id, track_id, product_id, quantity)
        VALUES (?, ?, ?, ?, ?)
    ''', (store_id, user_id, track_id, product_id, quantity))
    conn.commit()
    inserted = cursor.rowcount > 0
    conn.close()
    return inserted

def get_cart_summary(store_id, user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 
            p.id as product_id,
            p.name as product_name,
            COUNT(c.track_id) as quantity,
            p.price as unit_price
        FROM cart c
        JOIN products p ON c.product_id = p.id AND c.store_id = p.store_id
        WHERE c.store_id = ? AND c.user_id = ?
        GROUP BY p.id
    ''', (store_id, user_id))
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

def clear_cart(store_id, user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM cart WHERE store_id = ? AND user_id = ?', (store_id, user_id))
    conn.commit()
    conn.close()

def remove_from_cart(store_id, user_id, track_id: str) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM cart WHERE store_id = ? AND user_id = ? AND track_id = ?', (store_id, user_id, track_id))
    conn.commit()
    removed = cursor.rowcount > 0
    conn.close()
    return removed

# --- Inventory ---
def get_stock(store_id, product_id: str) -> int | None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT stock FROM inventory WHERE store_id = ? AND product_id = ?', (store_id, product_id))
    row = cursor.fetchone()
    conn.close()
    return row['stock'] if row else None

def update_stock(store_id, product_id: str, delta: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE inventory SET stock = MAX(0, stock + ?) WHERE store_id = ? AND product_id = ?',
        (delta, store_id, product_id)
    )
    conn.commit()
    updated = cursor.rowcount > 0
    conn.close()
    return updated

# --- Users & Auth ---
def get_user_by_email(email):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_user_by_id(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def create_user(full_name, email, password_hash, role='user'):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)',
            (full_name, email, password_hash, role)
        )
        user_id = cursor.lastrowid
        conn.commit()
        return user_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_user_stores(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.*, sm.role
        FROM stores s
        JOIN store_members sm ON s.id = sm.store_id
        WHERE sm.user_id = ?
    ''', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def check_store_membership(user_id, store_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT role FROM store_members WHERE user_id = ? AND store_id = ?', (user_id, store_id))
    row = cursor.fetchone()
    conn.close()
    return row['role'] if row else None

# --- Admin helpers ---
def set_user_role(user_id, role):
    """Promote or demote a user's platform role ('admin' | 'user')."""
    assert role in ('admin', 'user'), "role must be 'admin' or 'user'"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET role = ? WHERE id = ?', (role, user_id))
    conn.commit()
    conn.close()
    return cursor.rowcount > 0

def get_all_users():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, full_name, email, role, created_at
        FROM users
        ORDER BY created_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_stores_admin():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT s.id, s.name, s.address, s.created_at,
               COUNT(DISTINCT sm.user_id) as member_count
        FROM stores s
        LEFT JOIN store_members sm ON s.id = sm.store_id
        GROUP BY s.id
        ORDER BY s.id
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_admin_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as total FROM users')
    total_users = cursor.fetchone()['total']
    cursor.execute('SELECT COUNT(*) as total FROM stores')
    total_stores = cursor.fetchone()['total']
    cursor.execute('SELECT COUNT(*) as total FROM products')
    total_products = cursor.fetchone()['total']
    cursor.execute('SELECT COUNT(DISTINCT user_id || "-" || store_id) as total FROM cart WHERE quantity > 0')
    active_carts = cursor.fetchone()['total']
    cursor.execute("SELECT COUNT(*) as total FROM users WHERE role = 'admin'")
    total_admins = cursor.fetchone()['total']
    conn.close()
    return {
        'total_users': total_users,
        'total_stores': total_stores,
        'total_products': total_products,
        'active_carts': active_carts,
        'total_admins': total_admins
    }

def get_all_inventory_admin():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT i.store_id, s.name as store_name, i.product_id, p.name as product_name,
               p.price, i.stock
        FROM inventory i
        JOIN products p ON i.product_id = p.id AND i.store_id = p.store_id
        JOIN stores s ON i.store_id = s.id
        ORDER BY s.id, p.name
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Transactions & Retail Analytics Helpers ---

def create_transaction(user_id, store_id, amount, items, payment_method='Card', created_at=None, status='completed', customer_name=None, customer_email=None):
    """
    Records a completed checkout transaction, creates sale items, and decrements stock.
    items: list of dicts with keys: product_id (or id), quantity, unit_price (or price)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    if not customer_name or not customer_email:
        cursor.execute('SELECT full_name, email FROM users WHERE id = ?', (user_id,))
        u = cursor.fetchone()
        if u:
            if not customer_name:
                customer_name = u['full_name']
            if not customer_email:
                customer_email = u['email']

    if not customer_name:
        customer_name = 'Customer'
    if not customer_email:
        customer_email = 'customer@store.com'

    if created_at:
        cursor.execute('''
            INSERT INTO transactions (user_id, store_id, amount, status, payment_method, customer_name, customer_email, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, store_id, amount, status, payment_method, customer_name, customer_email, created_at, created_at))
    else:
        cursor.execute('''
            INSERT INTO transactions (user_id, store_id, amount, status, payment_method, customer_name, customer_email)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, store_id, amount, status, payment_method, customer_name, customer_email))

    transaction_id = cursor.lastrowid

    for item in items:
        pid = item.get('product_id') or item.get('id')
        qty = item.get('quantity', 1)
        price = item.get('unit_price') or item.get('price', 0.0)

        cursor.execute('''
            INSERT INTO sale_items (transaction_id, product_id, quantity, unit_price)
            VALUES (?, ?, ?, ?)
        ''', (transaction_id, pid, qty, price))

        # Decrement stock in inventory
        cursor.execute('''
            UPDATE inventory SET stock = MAX(0, stock - ?)
            WHERE store_id = ? AND product_id = ?
        ''', (qty, store_id, pid))

    conn.commit()
    conn.close()
    return transaction_id


def _build_date_clause(date_range, col_name='created_at'):
    """Helper to return SQL WHERE clause condition based on date range string."""
    dr = (date_range or '7d').lower()
    if dr == 'today':
        return f"date(datetime({col_name}, 'localtime')) = date('now', 'localtime')", []
    elif dr == '7d':
        return f"{col_name} >= datetime('now', '-7 days')", []
    elif dr == '30d':
        return f"{col_name} >= datetime('now', '-30 days')", []
    else:  # 'all'
        return "1=1", []


def get_analytics_overview(store_id=None, date_range='7d'):
    conn = get_db_connection()
    cursor = conn.cursor()

    date_where, params = _build_date_clause(date_range, 'created_at')
    where_clauses = ["status = 'completed'", date_where]
    where_params = []

    if store_id and store_id != 'all' and str(store_id).lower() != 'all':
        where_clauses.append("store_id = ?")
        where_params.append(int(store_id))

    where_sql = " AND ".join(where_clauses)

    # Total revenue, transactions, and active customers from transactions table
    tx_query = f'''
        SELECT 
            COALESCE(SUM(amount), 0) as total_revenue,
            COUNT(id) as total_transactions,
            COUNT(DISTINCT COALESCE(customer_email, CAST(user_id AS TEXT))) as active_customers
        FROM transactions
        WHERE {where_sql}
    '''
    cursor.execute(tx_query, where_params)
    tx_row = dict(cursor.fetchone() or {})
    total_rev = float(tx_row.get('total_revenue', 0.0))
    total_tx = int(tx_row.get('total_transactions', 0))
    active_cust = int(tx_row.get('active_customers', 0))
    aov = (total_rev / total_tx) if total_tx > 0 else 0.0

    # Total items sold from sale_items joined with transactions
    si_date_where, _ = _build_date_clause(date_range, 't.created_at')
    si_clauses = ["t.status = 'completed'", si_date_where]
    si_where_params = []
    if store_id and store_id != 'all' and str(store_id).lower() != 'all':
        si_clauses.append("t.store_id = ?")
        si_where_params.append(int(store_id))

    si_where_sql = " AND ".join(si_clauses)
    si_query = f'''
        SELECT COALESCE(SUM(si.quantity), 0) as total_items_sold
        FROM sale_items si
        JOIN transactions t ON si.transaction_id = t.id
        WHERE {si_where_sql}
    '''
    cursor.execute(si_query, si_where_params)
    si_row = dict(cursor.fetchone() or {})
    total_items = int(si_row.get('total_items_sold', 0))

    # Count low stock products (< 20)
    low_stock_sql = "SELECT COUNT(*) as count FROM inventory WHERE stock < 20"
    low_params = []
    if store_id and store_id != 'all' and str(store_id).lower() != 'all':
        low_stock_sql += " AND store_id = ?"
        low_params.append(int(store_id))

    cursor.execute(low_stock_sql, low_params)
    low_stock_row = cursor.fetchone()
    low_stock_count = low_stock_row['count'] if low_stock_row else 0

    conn.close()
    return {
        'total_revenue': round(total_rev, 2),
        'total_transactions': total_tx,
        'total_items_sold': total_items,
        'average_order_value': round(aov, 2),
        'active_customers': active_cust,
        'low_stock_count': low_stock_count
    }


def get_sales_trends(store_id=None, date_range='7d'):
    conn = get_db_connection()
    cursor = conn.cursor()

    date_where, params = _build_date_clause(date_range, 'created_at')
    where_clauses = ["status = 'completed'", date_where]

    if store_id and store_id != 'all' and str(store_id).lower() != 'all':
        where_clauses.append("store_id = ?")
        params.insert(0, int(store_id))

    where_sql = " AND ".join(where_clauses)

    query = f'''
        SELECT 
            date(datetime(created_at, 'localtime')) as date,
            COALESCE(SUM(amount), 0) as revenue,
            COUNT(id) as transactions
        FROM transactions
        WHERE {where_sql}
        GROUP BY date
        ORDER BY date ASC
    '''
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_hourly_sales_trends(store_id=None, date_range='7d'):
    conn = get_db_connection()
    cursor = conn.cursor()

    date_where, params = _build_date_clause(date_range, 'created_at')
    where_clauses = ["status = 'completed'", date_where]

    if store_id and store_id != 'all' and str(store_id).lower() != 'all':
        where_clauses.append("store_id = ?")
        params.insert(0, int(store_id))

    where_sql = " AND ".join(where_clauses)

    query = f'''
        SELECT 
            strftime('%H:00', datetime(created_at, 'localtime')) as hour,
            COALESCE(SUM(amount), 0) as revenue,
            COUNT(id) as transactions
        FROM transactions
        WHERE {where_sql}
        GROUP BY hour
        ORDER BY hour ASC
    '''
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_top_products(store_id=None, date_range='7d', limit=8):
    conn = get_db_connection()
    cursor = conn.cursor()

    date_where, params = _build_date_clause(date_range, 't.created_at')
    where_clauses = ["t.status = 'completed'", date_where]

    if store_id and store_id != 'all' and str(store_id).lower() != 'all':
        where_clauses.append("t.store_id = ?")
        params.insert(0, int(store_id))

    where_sql = " AND ".join(where_clauses)

    query = f'''
        SELECT 
            si.product_id,
            COALESCE(p.name, si.product_id) as product_name,
            SUM(si.quantity) as units_sold,
            SUM(si.quantity * si.unit_price) as total_revenue
        FROM sale_items si
        JOIN transactions t ON si.transaction_id = t.id
        LEFT JOIN products p ON si.product_id = p.id AND (t.store_id = p.store_id OR p.store_id = 1)
        WHERE {where_sql}
        GROUP BY si.product_id
        ORDER BY units_sold DESC
        LIMIT {int(limit)}
    '''
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_low_stock_products(store_id=None, threshold=20):
    conn = get_db_connection()
    cursor = conn.cursor()

    where_clauses = ["i.stock <= ?"]
    params = [int(threshold)]

    if store_id and store_id != 'all' and str(store_id).lower() != 'all':
        where_clauses.append("i.store_id = ?")
        params.insert(0, int(store_id))

    where_sql = " AND ".join(where_clauses)

    query = f'''
        SELECT 
            i.store_id,
            s.name as store_name,
            i.product_id,
            COALESCE(p.name, i.product_id) as product_name,
            COALESCE(p.price, 0.0) as price,
            i.stock
        FROM inventory i
        LEFT JOIN products p ON i.product_id = p.id AND i.store_id = p.store_id
        LEFT JOIN stores s ON i.store_id = s.id
        WHERE {where_sql}
        ORDER BY i.stock ASC
    '''
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def restock_inventory(store_id, product_id, quantity):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO inventory (store_id, product_id, stock)
        VALUES (?, ?, ?)
        ON CONFLICT(store_id, product_id) DO UPDATE SET
            stock = stock + excluded.stock
    ''', (store_id, product_id, quantity))
    conn.commit()
    conn.close()
    return True


def get_transactions_list(store_id=None, date_range='all', search='', limit=100):
    conn = get_db_connection()
    cursor = conn.cursor()

    date_where, params = _build_date_clause(date_range, 't.created_at')
    where_clauses = [date_where]

    if store_id and store_id != 'all' and str(store_id).lower() != 'all':
        where_clauses.append("t.store_id = ?")
        params.insert(0, int(store_id))

    if search:
        search_pattern = f"%{search}%"
        where_clauses.append("(CAST(t.id AS TEXT) LIKE ? OR t.customer_name LIKE ? OR u.full_name LIKE ? OR t.customer_email LIKE ? OR u.email LIKE ? OR s.name LIKE ?)")
        params.extend([search_pattern, search_pattern, search_pattern, search_pattern, search_pattern, search_pattern])

    where_sql = " AND ".join(where_clauses)

    query = f'''
        SELECT 
            t.id,
            t.user_id,
            COALESCE(t.customer_name, u.full_name, 'Guest Customer') as customer_name,
            COALESCE(t.customer_email, u.email, 'guest@store.com') as customer_email,
            t.store_id,
            COALESCE(s.name, 'Store #' || t.store_id) as store_name,
            t.amount,
            t.status,
            t.payment_method,
            t.created_at,
            COUNT(si.id) as item_types_count,
            COALESCE(SUM(si.quantity), 0) as total_units
        FROM transactions t
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN stores s ON t.store_id = s.id
        LEFT JOIN sale_items si ON t.id = si.transaction_id
        WHERE {where_sql}
        GROUP BY t.id
        ORDER BY t.created_at DESC
        LIMIT {int(limit)}
    '''
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def get_transaction_details(transaction_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.id, t.user_id, 
               COALESCE(t.customer_name, u.full_name, 'Guest Customer') as customer_name, 
               COALESCE(t.customer_email, u.email, 'guest@store.com') as customer_email,
               t.store_id, COALESCE(s.name, 'Store #' || t.store_id) as store_name, 
               t.amount, t.status, t.payment_method, t.created_at
        FROM transactions t
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN stores s ON t.store_id = s.id
        WHERE t.id = ?
    ''', (transaction_id,))
    tx = cursor.fetchone()
    if not tx:
        conn.close()
        return None

    tx_dict = dict(tx)

    cursor.execute('''
        SELECT si.id, si.product_id, COALESCE(p.name, si.product_id) as product_name, 
               si.quantity, si.unit_price,
               (si.quantity * si.unit_price) as subtotal
        FROM sale_items si
        LEFT JOIN products p ON si.product_id = p.id AND (p.store_id = ? OR p.store_id = 1)
        WHERE si.transaction_id = ?
    ''', (tx_dict['store_id'], transaction_id))
    items = [dict(r) for r in cursor.fetchall()]
    conn.close()

    tx_dict['items'] = items
    return tx_dict


def reset_store_analytics(store_id=None):
    """
    Resets all transactions, sale_items, and active carts for the given store (or all stores).
    Resets inventory stock back to normal baseline (100 units).
    All dashboard metrics become zero.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    if store_id and store_id != 'all' and str(store_id).lower() != 'all':
        sid = int(store_id)
        cursor.execute('''
            DELETE FROM sale_items 
            WHERE transaction_id IN (SELECT id FROM transactions WHERE store_id = ?)
        ''', (sid,))
        cursor.execute('DELETE FROM transactions WHERE store_id = ?', (sid,))
        cursor.execute('DELETE FROM cart WHERE store_id = ?', (sid,))
        cursor.execute('UPDATE inventory SET stock = 100 WHERE store_id = ?', (sid,))
    else:
        cursor.execute('DELETE FROM sale_items')
        cursor.execute('DELETE FROM transactions')
        cursor.execute('DELETE FROM cart')
        cursor.execute('UPDATE inventory SET stock = 100')

    conn.commit()
    conn.close()
    return True


def seed_demo_analytics(store_id=None):
    """
    Generates rich, realistic demo transactions, amounts, customers, and inventory
    for the store so all metrics and charts on the dashboard are populated.
    """
    import datetime
    conn = get_db_connection()
    cursor = conn.cursor()

    if not store_id or store_id == 'all' or str(store_id).lower() == 'all':
        cursor.execute("SELECT id FROM stores LIMIT 1")
        s_row = cursor.fetchone()
        target_store = s_row['id'] if s_row else 1
    else:
        target_store = int(store_id)

    # 1. Ensure complementary products exist
    _seed_complementary_products(cursor, conn, target_store)

    # 2. Reset transactions & items for this store before seeding
    cursor.execute('''
        DELETE FROM sale_items 
        WHERE transaction_id IN (SELECT id FROM transactions WHERE store_id = ?)
    ''', (target_store,))
    cursor.execute('DELETE FROM transactions WHERE store_id = ?', (target_store,))
    cursor.execute('DELETE FROM cart WHERE store_id = ?', (target_store,))
    cursor.execute('UPDATE inventory SET stock = 100 WHERE store_id = ?', (target_store,))
    conn.commit()

    # 3. Demo customers pool
    customers = [
        ("Rahul Sharma", "rahul.sharma@gmail.com", "UPI"),
        ("Priya Patel", "priya.p@outlook.com", "Card"),
        ("Amit Verma", "amit.verma@gmail.com", "UPI"),
        ("Sneha Reddy", "sneha.reddy@yahoo.com", "Card"),
        ("Vikram Malhotra", "vikram.m@gmail.com", "Cash"),
        ("Ananya Iyer", "ananya.iyer@gmail.com", "UPI"),
        ("Karan Mehta", "karan.mehta@gmail.com", "Card"),
        ("Pooja Nair", "pooja.nair@hotmail.com", "UPI"),
        ("Rohan Gupta", "rohan.gupta@gmail.com", "UPI"),
        ("Meera Joshi", "meera.j@gmail.com", "Card"),
        ("Suresh Raina", "suresh.r@gmail.com", "Cash"),
        ("Divya Sundaram", "divya.sundaram@gmail.com", "UPI"),
        ("Neha Kapoor", "neha.k@gmail.com", "Card"),
        ("Aditya Rao", "aditya.rao@gmail.com", "UPI"),
        ("Ritu Deshmukh", "ritu.d@gmail.com", "Card"),
        ("Manoj Tiwari", "manoj.t@gmail.com", "UPI"),
        ("Swati Chawla", "swati.c@gmail.com", "Card"),
        ("Gaurav Bhatia", "gaurav.b@gmail.com", "UPI"),
    ]

    # Pre-defined realistic baskets
    baskets = [
        # 1. Morning Breakfast
        [("milk", 2, 50.00), ("bread", 1, 70.00), ("butter", 1, 55.00)],
        # 2. Tea time
        [("tea", 1, 35.00), ("cup", 2, 30.00), ("biscuits", 2, 30.00)],
        # 3. Fresh Fruits & Healthy
        [("banana", 2, 60.00), ("apple", 3, 40.00), ("yogurt", 2, 45.00)],
        # 4. Big Grocery Run
        [("milk", 3, 50.00), ("bread", 2, 70.00), ("honey", 1, 120.00), ("butter", 1, 55.00)],
        # 5. Quick essentials
        [("milk", 1, 50.00), ("biscuits", 2, 30.00)],
        # 6. Natural honey & yogurt
        [("yogurt", 2, 45.00), ("honey", 1, 120.00), ("banana", 1, 60.00)],
        # 7. Tea & snacks
        [("tea", 2, 35.00), ("biscuits", 3, 30.00), ("milk", 2, 50.00)],
        # 8. Weekly dairy & bakery
        [("milk", 4, 50.00), ("bread", 2, 70.00), ("butter", 2, 55.00), ("apple", 2, 40.00)],
        # 9. Fruit basket
        [("apple", 4, 40.00), ("banana", 3, 60.00)],
        # 10. Honey & tea luxury
        [("honey", 2, 120.00), ("tea", 2, 35.00), ("cup", 4, 30.00)],
    ]

    now = datetime.datetime.now()
    tx_specs = [
        # Today (Day 0) - 5 transactions
        (0, 9, 15, 0, 0),
        (0, 11, 30, 1, 1),
        (0, 14, 45, 2, 2),
        (0, 17, 20, 3, 3),
        (0, 20, 10, 4, 4),
        # 1 day ago - 4 transactions
        (1, 10, 5, 5, 5),
        (1, 13, 15, 6, 6),
        (1, 18, 40, 7, 7),
        (1, 21, 0, 8, 8),
        # 2 days ago - 4 transactions
        (2, 9, 45, 9, 9),
        (2, 12, 10, 10, 0),
        (2, 16, 30, 11, 1),
        (2, 19, 50, 12, 2),
        # 3 days ago - 3 transactions
        (3, 11, 0, 13, 3),
        (3, 15, 25, 14, 4),
        (3, 20, 30, 15, 5),
        # 4 days ago - 3 transactions
        (4, 10, 30, 16, 6),
        (4, 14, 15, 17, 7),
        (4, 18, 45, 0, 8),
        # 5 days ago - 3 transactions
        (5, 9, 20, 1, 9),
        (5, 13, 40, 2, 0),
        (5, 19, 15, 3, 1),
        # 6 days ago - 3 transactions
        (6, 10, 10, 4, 2),
        (6, 16, 5, 5, 3),
        (6, 21, 15, 6, 4),
    ]

    total_revenue = 0.0
    total_tx_count = len(tx_specs)
    total_units_sold = 0

    for days_ago, hour, minute, cust_idx, basket_idx in tx_specs:
        cust_name, cust_email, pay_method = customers[cust_idx % len(customers)]
        basket_items = baskets[basket_idx % len(baskets)]

        tx_time = now - datetime.timedelta(days=days_ago)
        tx_time = tx_time.replace(hour=hour, minute=minute, second=25, microsecond=0)
        time_str = tx_time.strftime('%Y-%m-%d %H:%M:%S')

        tx_amount = sum(qty * price for _, qty, price in basket_items)
        total_revenue += tx_amount

        cursor.execute('''
            INSERT INTO transactions (user_id, store_id, amount, status, payment_method, customer_name, customer_email, created_at, updated_at)
            VALUES (?, ?, ?, 'completed', ?, ?, ?, ?, ?)
        ''', (1, target_store, round(tx_amount, 2), pay_method, cust_name, cust_email, time_str, time_str))
        
        tx_id = cursor.lastrowid

        for pid, qty, price in basket_items:
            total_units_sold += qty
            cursor.execute('''
                INSERT INTO sale_items (transaction_id, product_id, quantity, unit_price)
                VALUES (?, ?, ?, ?)
            ''', (tx_id, pid, qty, price))
            cursor.execute('''
                UPDATE inventory SET stock = MAX(0, stock - ?)
                WHERE store_id = ? AND product_id = ?
            ''', (qty, target_store, pid))

    # Set 2 specific items to low stock (<20) for demonstration
    cursor.execute('UPDATE inventory SET stock = 8 WHERE store_id = ? AND product_id = "cup"', (target_store,))
    cursor.execute('UPDATE inventory SET stock = 14 WHERE store_id = ? AND product_id = "honey"', (target_store,))

    conn.commit()
    conn.close()

    return {
        "store_id": target_store,
        "total_revenue": round(total_revenue, 2),
        "total_transactions": total_tx_count,
        "total_items_sold": total_units_sold
    }


