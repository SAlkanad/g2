#!/usr/bin/env python3
"""
Firebase Data Sync Script
Syncs countries, rules, and updates from SQLite to Firebase
"""

import os
import sys
import logging
from database.database import Database

# Use centralized logging
from logging_config import get_logger
logger = get_logger(__name__)

def main():
    """Main function to sync data to Firebase"""
    try:
        logger.info("🔄 Starting Firebase data sync...")
        
        # Initialize database
        db = Database()
        
        if not db.firebase_enabled:
            logger.error("❌ Firebase is not enabled. Please check your configuration.")
            return False
        
        # Sync countries to Firebase
        logger.info("📍 Syncing countries to Firebase...")
        db.sync_countries_to_firebase()
        
        # Sync content (rules, updates, support) to Firebase
        logger.info("📝 Syncing content to Firebase...")
        db.sync_content_to_firebase()
        
        logger.info("✅ Firebase data sync completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error during Firebase sync: {e}")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1)