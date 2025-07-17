#!/usr/bin/env python3
"""
Migration Script: Set All Countries to Inactive by Default

This script updates existing countries in the database to set is_active = False (0)
unless they have been explicitly activated by an admin.

Run this script once after updating the database schema to ensure all 
existing countries follow the new default behavior.
"""

import sqlite3
import logging
import os
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def migrate_countries_to_inactive(db_path: str = "bot_database_v2.db"):
    """
    Set all countries to inactive by default
    
    Args:
        db_path: Path to the SQLite database
    """
    if not os.path.exists(db_path):
        logger.error(f"Database file not found: {db_path}")
        return False
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check if countries table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='countries'
            """)
            
            if not cursor.fetchone():
                logger.warning("Countries table does not exist. No migration needed.")
                return True
            
            # Get current count of countries
            cursor.execute("SELECT COUNT(*) FROM countries")
            total_countries = cursor.fetchone()[0]
            
            if total_countries == 0:
                logger.info("No countries found in database. No migration needed.")
                return True
            
            # Get count of currently active countries
            cursor.execute("SELECT COUNT(*) FROM countries WHERE is_active = 1")
            active_countries = cursor.fetchone()[0]
            
            logger.info(f"Found {total_countries} countries, {active_countries} currently active")
            
            # Show which countries are currently active (for admin reference)
            if active_countries > 0:
                cursor.execute("""
                    SELECT country_code, country_name 
                    FROM countries 
                    WHERE is_active = 1 
                    ORDER BY country_name
                """)
                
                active_list = cursor.fetchall()
                logger.info("Currently active countries:")
                for code, name in active_list:
                    logger.info(f"  - {code}: {name}")
                
                # Ask for confirmation before proceeding
                print(f"\n⚠️  WARNING: This will set ALL {total_countries} countries to INACTIVE by default.")
                print(f"   Currently {active_countries} countries are active and will be deactivated.")
                print("   Admins will need to manually reactivate countries as needed.")
                
                confirm = input("\nProceed with migration? (yes/no): ").strip().lower()
                if confirm not in ['yes', 'y']:
                    logger.info("Migration cancelled by user")
                    return False
            
            # Update all countries to be inactive
            cursor.execute("""
                UPDATE countries 
                SET is_active = 0, 
                    updated_at = CURRENT_TIMESTAMP 
                WHERE is_active = 1
            """)
            
            updated_count = cursor.rowcount
            conn.commit()
            
            logger.info(f"✅ Migration completed successfully!")
            logger.info(f"   - Updated {updated_count} countries to inactive")
            logger.info(f"   - All {total_countries} countries are now inactive by default")
            logger.info("   - Admins can reactivate countries through the admin panel")
            
            return True
            
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        return False

def verify_migration(db_path: str = "bot_database_v2.db"):
    """Verify that the migration was successful"""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Get counts
            cursor.execute("SELECT COUNT(*) FROM countries")
            total = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM countries WHERE is_active = 1")
            active = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM countries WHERE is_active = 0")
            inactive = cursor.fetchone()[0]
            
            logger.info(f"Migration verification:")
            logger.info(f"  - Total countries: {total}")
            logger.info(f"  - Active countries: {active}")
            logger.info(f"  - Inactive countries: {inactive}")
            
            if active == 0 and inactive == total:
                logger.info("✅ Migration verified: All countries are inactive")
                return True
            else:
                logger.warning(f"⚠️  Migration verification failed: Expected all countries to be inactive")
                return False
                
    except Exception as e:
        logger.error(f"Error during verification: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Starting Countries Migration: Set All to Inactive by Default")
    print("=" * 60)
    
    # Run migration
    success = migrate_countries_to_inactive()
    
    if success:
        print("\n🔍 Verifying migration...")
        verify_migration()
        print("\n✅ Migration completed successfully!")
        print("\n📝 Next steps:")
        print("   1. Use the admin panel to activate specific countries")
        print("   2. Only activated countries will be visible to users")
        print("   3. Users will see 'no countries available' until countries are activated")
    else:
        print("\n❌ Migration failed!")
        print("   Please check the logs and try again")
        
    print("\n" + "=" * 60)