#!/usr/bin/env python3
"""
Database migration script for fixing missing columns
Run this before starting the bot if you get column errors
"""
import sqlite3
import logging
import os

logger = logging.getLogger(__name__)

def migrate_database(db_path="bot_database_v2.db"):
    """Migrate existing database to add missing columns"""
    try:
        if not os.path.exists(db_path):
            print(f"Database {db_path} not found - no migration needed")
            return True
            
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check if firebase_sync_failed column exists in pending_numbers
            cursor.execute("PRAGMA table_info(pending_numbers)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'firebase_sync_failed' not in columns:
                cursor.execute("ALTER TABLE pending_numbers ADD COLUMN firebase_sync_failed BOOLEAN DEFAULT 0")
                cursor.execute("ALTER TABLE pending_numbers ADD COLUMN firebase_sync_error TEXT")
                conn.commit()
                print("✅ Added firebase_sync_failed and firebase_sync_error columns to pending_numbers")
            else:
                print("✅ Database already up to date")
                
        return True
        
    except Exception as e:
        print(f"❌ Error during database migration: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Running database migration...")
    success = migrate_database()
    if success:
        print("✅ Migration completed successfully")
    else:
        print("❌ Migration failed")
        exit(1)
