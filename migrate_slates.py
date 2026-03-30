import sqlite3
import os

db_path = 'instance/heriglobal_pos.db'
if not os.path.exists(db_path):
    db_path = 'heriglobal_pos.db' # Try root if not in instance

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print(f"Updating database at {db_path}...")

try:
    # 1. Update products table
    print("Adding slate columns to products table...")
    cursor.execute("ALTER TABLE products ADD COLUMN has_slates BOOLEAN DEFAULT 0")
    cursor.execute("ALTER TABLE products ADD COLUMN slates_per_unit INTEGER DEFAULT 1")
    print("Slate columns added successfully.")
except sqlite3.OperationalError as e:
    print(f"Note: {e} (Columns might already exist)")

try:
    # 2. Create system_settings table
    print("Creating system_settings table...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key VARCHAR(100) UNIQUE NOT NULL,
        value TEXT NOT NULL,
        description TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)
    print("system_settings table created successfully.")
except Exception as e:
    print(f"Error creating system_settings table: {e}")

conn.commit()
conn.close()
print("Migration completed.")
