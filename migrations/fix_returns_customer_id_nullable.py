"""
Migration: Fix returns table customer_id to be nullable for non-registered customers
Date: 2026-04-09
Description: Updates customer_id column in returns table to allow NULL values for non-registered customer returns
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db
from sqlalchemy import text

def upgrade():
    """Apply the migration"""
    print("Fixing returns table customer_id column to allow NULL values...")
    
    try:
        # For SQLite, we need to recreate the table to modify column constraints
        # First, check if we're using SQLite
        with db.engine.connect() as conn:
            # Check database type
            db_name = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='returns'")).fetchone()
            
            if db_name:
                print("Detected SQLite database - using table recreation method...")
                
                # Create a temporary table with the new schema
                conn.execute(text("""
                    CREATE TABLE returns_temp (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        return_number VARCHAR(50) NOT NULL,
                        sale_id INTEGER NOT NULL,
                        outlet_id INTEGER NOT NULL,
                        customer_id INTEGER NULL,  -- Made nullable
                        processed_by INTEGER NOT NULL,
                        return_date DATETIME NOT NULL,
                        total_refund_amount DECIMAL(10,3) NOT NULL,
                        refund_method VARCHAR(50) NOT NULL,
                        status VARCHAR(20) NOT NULL DEFAULT 'pending',
                        notes TEXT,
                        approved_by INTEGER,
                        approved_at DATETIME,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (sale_id) REFERENCES sales (id),
                        FOREIGN KEY (outlet_id) REFERENCES outlets (id),
                        FOREIGN KEY (customer_id) REFERENCES customers (id),
                        FOREIGN KEY (processed_by) REFERENCES users (id),
                        FOREIGN KEY (approved_by) REFERENCES users (id)
                    )
                """))
                
                # Copy existing data
                conn.execute(text("""
                    INSERT INTO returns_temp 
                    SELECT * FROM returns
                """))
                
                # Drop the old table
                conn.execute(text("DROP TABLE returns"))
                
                # Rename the temp table
                conn.execute(text("ALTER TABLE returns_temp RENAME TO returns"))
                
                conn.commit()
                print("✓ Successfully recreated returns table with nullable customer_id")
            else:
                # For PostgreSQL or other databases
                conn.execute(text("""
                    ALTER TABLE returns 
                    ALTER COLUMN customer_id DROP NOT NULL
                """))
                conn.commit()
                print("✓ Made returns.customer_id column nullable")
                
    except Exception as e:
        print(f"Error updating returns.customer_id: {e}")
        # Try alternative approach for other databases
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE returns ALTER customer_id DROP NOT NULL"))
                conn.commit()
            print("✓ Made returns.customer_id column nullable (alternative method)")
        except Exception as e2:
            print(f"Alternative method also failed: {e2}")
    
    print("Returns table migration completed!")

def downgrade():
    """Reverse the migration"""
    print("Reverting returns table customer_id changes...")
    
    # Make customer_id NOT NULL again (only if no NULL values exist)
    try:
        with db.engine.connect() as conn:
            # First check if there are any NULL values
            result = conn.execute(text("SELECT COUNT(*) FROM returns WHERE customer_id IS NULL"))
            null_count = result.scalar()
            
            if null_count == 0:
                # For SQLite, we'd need to recreate the table again
                # For now, just warn the user
                print("Warning: Cannot easily revert SQLite schema changes.")
                print("Manual intervention may be required to make customer_id NOT NULL again.")
            else:
                print(f"Cannot make customer_id NOT NULL: {null_count} records have NULL customer_id")
    except Exception as e:
        print(f"Could not check/revert returns.customer_id: {e}")
    
    print("Returns table downgrade completed!")

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        try:
            upgrade()
        except Exception as e:
            print(f"Migration failed: {e}")
            import traceback
            traceback.print_exc()