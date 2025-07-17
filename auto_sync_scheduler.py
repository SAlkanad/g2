#!/usr/bin/env python3
"""
Auto-sync scheduler for database synchronization
Runs in the background to periodically sync data to Firebase
"""

import asyncio
import logging
from datetime import datetime, timedelta
from database.database import db

logger = logging.getLogger(__name__)

class AutoSyncScheduler:
    """Background scheduler for auto-sync"""
    
    def __init__(self, check_interval_minutes: int = 60):
        self.check_interval_minutes = check_interval_minutes
        self.running = False
        self.task = None
    
    async def start(self):
        """Start the auto-sync scheduler"""
        if self.running:
            logger.warning("Auto-sync scheduler is already running")
            return
        
        self.running = True
        self.task = asyncio.create_task(self._scheduler_loop())
        logger.info(f"Auto-sync scheduler started (check every {self.check_interval_minutes} minutes)")
    
    async def stop(self):
        """Stop the auto-sync scheduler"""
        if not self.running:
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("Auto-sync scheduler stopped")
    
    async def _scheduler_loop(self):
        """Main scheduler loop"""
        while self.running:
            try:
                # Check if sync is needed
                await self._check_and_sync()
                
                # Wait for next check
                await asyncio.sleep(self.check_interval_minutes * 60)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in auto-sync scheduler: {e}")
                # Continue running even if there's an error
                await asyncio.sleep(self.check_interval_minutes * 60)
    
    async def _check_and_sync(self):
        """Check if sync is needed and perform it"""
        try:
            sync_status = db.get_sync_status()
            
            # Only proceed if Firebase is enabled and auto-sync is enabled
            if not sync_status['firebase_enabled'] or not sync_status['auto_sync_enabled']:
                return
            
            # Check if sync is due
            if sync_status['next_sync_due']:
                logger.info("Auto-sync is due, starting synchronization...")
                
                success = db.sync_all_data_to_firebase()
                
                if success:
                    logger.info("Auto-sync completed successfully")
                else:
                    logger.error("Auto-sync failed")
            else:
                hours_since = sync_status.get('hours_since_last_sync', 0)
                logger.debug(f"Auto-sync not due yet ({hours_since:.1f} hours since last sync)")
                
        except Exception as e:
            logger.error(f"Error checking auto-sync: {e}")

# Global scheduler instance
auto_sync_scheduler = AutoSyncScheduler()