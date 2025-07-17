"""
Centralized Authentication Service

This module provides a centralized authentication system for admin access control.
Replaces duplicated is_admin methods across multiple admin modules.
"""

import logging
from typing import List, Optional
from database.database import Database

logger = logging.getLogger(__name__)


class AuthService:
    """Centralized authentication service for admin access control"""
    
    def __init__(self, database: Database, admin_ids: List[int]):
        self.database = database
        self.admin_ids = admin_ids
    
    def is_admin(self, user_id: int) -> bool:
        """
        Check if user is an admin
        
        Args:
            user_id: Telegram user ID to check
            
        Returns:
            bool: True if user is admin, False otherwise
        """
        try:
            # Check if user ID is in the config admin list
            if user_id in self.admin_ids:
                return True
            
            # Check if user is marked as admin in database
            user_data = self.database.get_user(user_id)
            if user_data and user_data.get('is_admin', False):
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking admin status for user {user_id}: {e}")
            return False
    
    def get_all_admins(self) -> List[int]:
        """
        Get list of all admin user IDs from both config and database
        
        Returns:
            List[int]: List of admin user IDs
        """
        try:
            admin_set = set(self.admin_ids)
            
            # Add database admins
            db_admins = self.database.get_all_admins()
            if db_admins:
                for admin in db_admins:
                    admin_id = admin.get('user_id')
                    if admin_id:
                        admin_set.add(admin_id)
            
            return list(admin_set)
            
        except Exception as e:
            logger.error(f"Error getting all admins: {e}")
            return self.admin_ids
    
    def is_super_admin(self, user_id: int) -> bool:
        """
        Check if user is a super admin (from config file)
        
        Args:
            user_id: Telegram user ID to check
            
        Returns:
            bool: True if user is super admin, False otherwise
        """
        return user_id in self.admin_ids
    
    def add_admin_to_database(self, user_id: int) -> bool:
        """
        Add user as admin to database
        
        Args:
            user_id: Telegram user ID to promote
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            return self.database.add_admin(user_id)
        except Exception as e:
            logger.error(f"Error adding admin {user_id}: {e}")
            return False
    
    def remove_admin_from_database(self, user_id: int) -> bool:
        """
        Remove user as admin from database
        
        Args:
            user_id: Telegram user ID to demote
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            return self.database.remove_admin(user_id)
        except Exception as e:
            logger.error(f"Error removing admin {user_id}: {e}")
            return False
    
    def get_admin_count(self) -> int:
        """
        Get total count of admins
        
        Returns:
            int: Total number of admins
        """
        return len(self.get_all_admins())