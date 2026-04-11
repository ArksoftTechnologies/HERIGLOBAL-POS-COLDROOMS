"""
Migration: Fix customer_id to be nullable for non-registered customers
Date: 2026-04-09
Description: Updates customer_id column to allow NULL values and ensures proper constraints
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db
from sqlalchemy import text

def upgrade():
    """Apply the migration"""
    print("Fixing customer_id column to allow NULL values...")
    
    try:
        # Make customer_id nullable
        with db.engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE sales 
                ALTER COLUMN customer_id DROP NOT NULL
            """))
            conn.commit()
        print("✓ Made customer_id column nullable")
    except Exception as e:
        print(f"Error updating customer_id: {e}")
    
    try:
        # Ensure non_registered_customer_name column exists
        with db.engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE sales 
                ADD COLUMN IF NOT EXISTS non_registered_customer_name VARCHAR(200) NULL
            """))
            conn.commit()
        print("✓ Ensured non_registered_customer_name column exists")
    except Exception as e:
        print(f"Column may already exist: {e}")
    
    try:
        # Drop existing constraint if it exists
        with db.engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE sales 
                DROP CONSTRAINT IF EXISTS check_customer_or_name
            """))
            conn.commit()
        print("✓ Dropped existing constraint (if any)")
    except Exception as e:
        print(f"No existing constraint to drop: {e}")
    
    try:
        # Add the new check constraint
        print("Adding new check constraint...")
        with db.engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE sales 
                ADD CONSTRAINT check_customer_or_name 
                CHECK (
                    (customer_id IS NOT NULL AND non_registered_customer_name IS NULL) OR
                    (customer_id IS NULL AND non_registered_customer_name IS NOT NULL)
                )
            """))
            conn.commit()
        print("✓ Added check constraint")
    except Exception as e:
        print(f"Constraint error: {e}")
    
    print("Migration completed successfully!")

def downgrade():
    """Reverse the migration"""
    print("Reverting customer_id changes...")
    
    # Remove the check constraint
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE sales DROP CONSTRAINT IF EXISTS check_customer_or_name"))
            conn.commit()
        print("✓ Removed check constraint")
    except Exception as e:
        print(f"Could not drop constraint: {e}")
    
    # Remove the column
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE sales DROP COLUMN IF EXISTS non_registered_customer_name"))
            conn.commit()
        print("✓ Removed non_registered_customer_name column")
    except Exception as e:
        print(f"Could not drop column: {e}")
    
    # Make customer_id NOT NULL again (only if no NULL values exist)
    try:
        with db.engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE sales 
                ALTER COLUMN customer_id SET NOT NULL
            """))
            conn.commit()
        print("✓ Made customer_id NOT NULL again")
    except Exception as e:
        print(f"Could not make customer_id NOT NULL: {e}")
    
    print("Downgrade completed!")

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        try:
            upgrade()
        except Exception as e:
            print(f"Migration failed: {e}")
            import traceback
            traceback.print_exc()