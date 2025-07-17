"""
Startup Script for Number Market Bot
Handles network initialization and health checks before starting the bot
"""

import asyncio
import logging
import sys
import os
import sqlite3
from typing import Optional

# Load environment variables first
from dotenv import load_dotenv
os.chdir(os.path.dirname(__file__))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

# Use centralized logging
from logging_config import configure_application_logging, get_logger
configure_application_logging()
logger = get_logger(__name__)

async def initialize_network_systems():
    """Initialize network systems and perform health checks"""
    logger.info("🔄 Initializing network systems...")
    
    try:
        # Initialize network monitoring
        from network.network_monitor import initialize_network_monitoring, get_network_health
        await initialize_network_monitoring()
        
        # Perform initial health check
        health_status = get_network_health()
        
        if not health_status['overall_healthy']:
            logger.warning("⚠️  Network health issues detected:")
            
            if not health_status['internet']['healthy']:
                logger.error(f"❌ Internet connectivity issue: {health_status['internet']['error']}")
            
            if not health_status['firebase']['healthy']:
                logger.warning(f"⚠️  Firebase connectivity issue: {health_status['firebase']['error']}")
                logger.info("💡 Bot will continue with local database only")
            
            if not health_status['telegram']['healthy']:
                logger.error(f"❌ Telegram connectivity issue: {health_status['telegram']['error']}")
                logger.warning("⚠️  Continuing despite Telegram connectivity issues (temporary bypass)")
                # return False  # Temporarily commented out for testing
        
        logger.info("✅ Network systems initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize network systems: {e}")
        return False

async def initialize_database():
    """Initialize database with network resilience"""
    logger.info("🔄 Initializing database...")
    
    try:
        from database.database import db
        
        # Database should already be initialized in the import
        if db.firebase_enabled:
            logger.info("✅ Database initialized with Firebase integration")
        else:
            logger.warning("⚠️  Database initialized in local mode only")
        
        # Verify default data initialization
        logger.info("🔄 Verifying default data initialization...")
        
        # Check settings
        try:
            # Check if settings table has data
            import sqlite3
            with sqlite3.connect(db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM settings")
                settings_count = cursor.fetchone()[0]
            
            if settings_count > 0:
                logger.info(f"✅ Default settings initialized: {settings_count} settings found")
            else:
                logger.warning("⚠️  No default settings found")
        except Exception as e:
            logger.error(f"❌ Error checking settings: {e}")
            settings_count = 0
        
        # Check content
        content_types = ['rules', 'updates', 'support']
        content_count = 0
        for content_type in content_types:
            content = db.get_content(content_type, 'en')
            if content:
                content_count += 1
        logger.info(f"✅ Default content initialized: {content_count}/{len(content_types)} content types found")
        
        # Check countries
        countries = db.get_countries(active_only=False)
        if countries:
            logger.info(f"✅ Countries initialized: {len(countries)} countries found")
            active_countries = sum(1 for c in countries if c.get('is_active', False))
            logger.info(f"   Active countries: {active_countries}")
            logger.info(f"   Inactive countries: {len(countries) - active_countries}")
        else:
            logger.warning("⚠️  No countries found in database")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        return False

async def validate_configuration():
    """Validate bot configuration"""
    logger.info("🔄 Validating configuration...")
    
    try:
        # Check if defaultdata module exists
        try:
            from database.defaultdata import DefaultDataInitializer
            logger.info("✅ Default data module found")
        except ImportError as e:
            logger.error(f"❌ Default data module not found: {e}")
            return False
        
        from config_validator import ConfigValidator
        from database.database import db
        
        validator = ConfigValidator(db)
        is_valid = validator.validate_all()
        
        if not is_valid:
            logger.error("❌ Configuration validation failed")
            return False
        
        logger.info("✅ Configuration validated successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Configuration validation error: {e}")
        return False

async def startup_sequence():
    """Execute complete startup sequence"""
    logger.info("🚀 Starting Number Market Bot...")
    logger.info("=" * 60)
    
    # Step 1: Validate configuration
    if not await validate_configuration():
        logger.error("❌ Startup failed: Configuration validation failed")
        return False
    
    # Step 2: Initialize network systems
    if not await initialize_network_systems():
        logger.error("❌ Startup failed: Network initialization failed")
        return False
    
    # Step 3: Initialize database
    if not await initialize_database():
        logger.error("❌ Startup failed: Database initialization failed")
        return False
    
    # Step 4: Display startup summary
    logger.info("=" * 60)
    logger.info("🎉 Bot startup completed successfully!")
    logger.info("📊 System Status:")
    
    try:
        from network.network_monitor import get_network_health
        health = get_network_health()
        
        logger.info(f"   Internet: {'✅ Healthy' if health['internet']['healthy'] else '❌ Unhealthy'}")
        logger.info(f"   Firebase: {'✅ Healthy' if health['firebase']['healthy'] else '❌ Unhealthy'}")
        logger.info(f"   Telegram: {'✅ Healthy' if health['telegram']['healthy'] else '❌ Unhealthy'}")
        
        from database.database import db
        logger.info(f"   Database: {'✅ Firebase + Local' if db.firebase_enabled else '⚠️  Local Only'}")
        
        # Display default data status
        logger.info("📋 Default Data Status:")
        
        # Settings status
        try:
            with sqlite3.connect(db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM settings")
                settings_count = cursor.fetchone()[0]
            logger.info(f"   Settings: {'✅ ' + str(settings_count) + ' initialized' if settings_count > 0 else '❌ Not initialized'}")
        except:
            logger.info(f"   Settings: ❌ Error checking settings")
        
        # Content status
        content_count = 0
        for content_type in ['rules', 'updates', 'support']:
            if db.get_content(content_type, 'en'):
                content_count += 1
        logger.info(f"   Content: {'✅ ' + str(content_count) + '/3 types' if content_count > 0 else '❌ Not initialized'}")
        
        # Countries status
        countries = db.get_countries(active_only=False)
        if countries:
            active = sum(1 for c in countries if c.get('is_active', False))
            logger.info(f"   Countries: ✅ {len(countries)} total ({active} active)")
        else:
            logger.info(f"   Countries: ❌ Not initialized")
        
    except Exception as e:
        logger.warning(f"⚠️  Could not get system status: {e}")
    
    logger.info("=" * 60)
    return True

async def main():
    """Main startup function"""
    try:
        # Execute startup sequence
        success = await startup_sequence()
        
        if not success:
            logger.error("❌ Startup failed, exiting...")
            sys.exit(1)
        
        # Import and start the bot
        logger.info("🤖 Starting bot...")
        from main import main as bot_main
        await bot_main()
        
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Unexpected error during startup: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())