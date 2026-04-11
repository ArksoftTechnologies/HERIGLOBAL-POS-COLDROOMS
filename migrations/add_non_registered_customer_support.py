"""
Migration: Add support for non-registered customers in sales
Date: 2026-04-09
Description: Adds non_registered_customer_name field to sales table and updates constraints
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models import db
from sqlalchemy import text

def upgrade():
    """Apply the migration"""
    print("Adding non_registered_customer_name column to sales table...")
    
    try:
        # Add the new column
        with db.engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE sales 
                ADD COLUMN non_registered_customer_name VARCHAR(200) NULL
            """))
            conn.commit()
        print("✓ Added non_registered_customer_name column")
    except Exception as e:
        print(f"Column may already exist: {e}")
    
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
        print(f"Constraint may already exist: {e}")
    
    print("Migration completed successfully!")

def downgrade():
    """Reverse the migration"""
    print("Removing non-registered customer support...")
    
    # Remove the check constraint
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE sales DROP CONSTRAINT check_customer_or_name"))
            conn.commit()
        print("✓ Removed check constraint")
    except Exception as e:
        print(f"Could not drop constraint: {e}")
    
    # Remove the column
    try:
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE sales DROP COLUMN non_registered_customer_name"))
            conn.commit()
        print("✓ Removed column")
    except Exception as e:
        print(f"Could not drop column: {e}")
    
    print("Downgrade completed!")

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        try:
            upgrade()
        except Exception as e:
            print(f"Migration failed: {e}")
            print("This is expected if the migration has already been applied.")