import sqlite3
conn = sqlite3.connect('checkout.db')
c = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print("Tables:", [t[0] for t in tables])
print()

for t in tables:
    tname = t[0]
    print(f"--- {tname} ---")
    c.execute(f"PRAGMA table_info({tname})")
    for col in c.fetchall():
        print(f"  {col[1]:20s} {col[2]:15s} notnull={col[3]} default={col[4]} pk={col[5]}")
    print()

# Check transaction data
try:
    c.execute("SELECT COUNT(*) FROM transactions")
    print("Transaction count:", c.fetchone()[0])
    c.execute("SELECT * FROM transactions LIMIT 5")
    rows = c.fetchall()
    for r in rows:
        print("  ", r)
except Exception as e:
    print("No transactions table:", e)

try:
    c.execute("SELECT COUNT(*) FROM sale_items")
    print("Sale items count:", c.fetchone()[0])
except Exception as e:
    print("No sale_items table:", e)

# Check products
c.execute("SELECT COUNT(*) FROM products")
print("\nProduct count:", c.fetchone()[0])
c.execute("SELECT * FROM products LIMIT 15")
for r in c.fetchall():
    print("  ", tuple(r))

# Check inventory
c.execute("SELECT COUNT(*) FROM inventory")
print("\nInventory count:", c.fetchone()[0])
c.execute("SELECT * FROM inventory LIMIT 15")
for r in c.fetchall():
    print("  ", tuple(r))

conn.close()
