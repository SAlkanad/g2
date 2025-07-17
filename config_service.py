"""
Centralized Configuration Service

This module provides a centralized configuration management system for API credentials
and other bot settings. Replaces hardcoded fallbacks and ensures consistent 
configuration loading across all modules.
"""

import os
import logging
from typing import Optional, Dict, Any
from database.database import Database

logger = logging.getLogger(__name__)


class ConfigService:
    """Centralized configuration service for API credentials and bot settings"""
    
    def __init__(self, database: Database):
        self.database = database
        self._config_cache = {}
        self._load_config()
    
    def _load_config(self):
        """Load configuration from database and environment variables"""
        try:
            # Load from database first
            db_settings = self.database.get_bot_settings()
            if db_settings:
                self._config_cache.update(db_settings)
            
            # Load from environment variables
            env_config = {
                'api_id': os.getenv('API_ID'),
                'api_hash': os.getenv('API_HASH'),
                'bot_token': os.getenv('BOT_TOKEN'),
                'admin_ids': os.getenv('ADMIN_IDS'),
                'admin_chat_id': os.getenv('ADMIN_CHAT_ID'),
                'database_path': os.getenv('DATABASE_PATH', 'bot_database_v2.db'),
                'session_encryption_key': os.getenv('SESSION_ENCRYPTION_KEY'),
                'firebase_service_account_path': os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH'),
                'firebase_database_url': os.getenv('FIREBASE_DATABASE_URL'),
                'firebase_storage_bucket': os.getenv('FIREBASE_STORAGE_BUCKET'),
            }
            
            # Environment variables override database settings
            for key, value in env_config.items():
                if value is not None:
                    self._config_cache[key] = value
                    
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
    
    def get_api_id(self) -> str:
        """
        Get API ID with proper fallback handling
        
        Returns:
            str: API ID
            
        Raises:
            ValueError: If API ID is not configured
        """
        api_id = self._config_cache.get('api_id')
        if not api_id or api_id in ['Not set', '12345']:
            raise ValueError(
                "API_ID is not properly configured. Please set it in environment variables or database settings."
            )
        return str(api_id)
    
    def get_api_hash(self) -> str:
        """
        Get API Hash with proper fallback handling
        
        Returns:
            str: API Hash
            
        Raises:
            ValueError: If API Hash is not configured
        """
        api_hash = self._config_cache.get('api_hash')
        if not api_hash or api_hash in ['Not set', 'default_hash']:
            raise ValueError(
                "API_HASH is not properly configured. Please set it in environment variables or database settings."
            )
        return api_hash
    
    def get_bot_token(self) -> str:
        """
        Get Bot Token
        
        Returns:
            str: Bot Token
            
        Raises:
            ValueError: If Bot Token is not configured
        """
        bot_token = self._config_cache.get('bot_token')
        if not bot_token or bot_token == 'Not set':
            raise ValueError(
                "BOT_TOKEN is not properly configured. Please set it in environment variables or database settings."
            )
        return bot_token
    
    def get_admin_chat_id(self) -> Optional[str]:
        """
        Get Admin Chat ID
        
        Returns:
            Optional[str]: Admin Chat ID or None if not configured
        """
        return self._config_cache.get('admin_chat_id')
    
    def get_admin_ids(self) -> list:
        """
        Get Admin IDs as a list
        
        Returns:
            list: List of admin user IDs
        """
        admin_ids_str = self._config_cache.get('admin_ids', '')
        if not admin_ids_str or admin_ids_str == 'Not set':
            return []
        
        try:
            # Parse comma-separated admin IDs
            admin_ids = [int(id_str.strip()) for id_str in admin_ids_str.split(',') if id_str.strip().isdigit()]
            return admin_ids
        except (ValueError, AttributeError) as e:
            logger.error(f"Error parsing admin IDs '{admin_ids_str}': {e}")
            return []
    
    def get_session_encryption_key(self) -> str:
        """
        Get Session Encryption Key
        
        Returns:
            str: Session encryption key
            
        Raises:
            ValueError: If encryption key is not configured
        """
        key = self._config_cache.get('session_encryption_key')
        if not key:
            raise ValueError(
                "SESSION_ENCRYPTION_KEY is not configured. Please set it in environment variables."
            )
        return key
    
    def get_database_path(self) -> str:
        """
        Get Database Path
        
        Returns:
            str: Database file path
        """
        return self._config_cache.get('database_path', 'bot_database_v2.db')
    
    def get_firebase_config(self) -> Dict[str, Optional[str]]:
        """
        Get Firebase configuration
        
        Returns:
            Dict[str, Optional[str]]: Firebase configuration dictionary
        """
        return {
            'service_account_path': self._config_cache.get('firebase_service_account_path'),
            'database_url': self._config_cache.get('firebase_database_url'),
            'storage_bucket': self._config_cache.get('firebase_storage_bucket'),
        }
    
    def get_global_2fa_password(self) -> Optional[str]:
        """
        Get global 2FA password from multiple sources
        
        Returns:
            Optional[str]: Global 2FA password or None if not set
        """
        # Try database first
        try:
            global_2fa = self.database.get_global_2fa_password()
            if global_2fa:
                return global_2fa
        except Exception as e:
            logger.error(f"Error getting global 2FA from database: {e}")
        
        # Fallback to bot settings
        try:
            bot_settings = self.database.get_bot_settings()
            if bot_settings and bot_settings.get('global_2fa_password'):
                return bot_settings['global_2fa_password']
        except Exception as e:
            logger.error(f"Error getting global 2FA from bot settings: {e}")
        
        # Fallback to settings table
        try:
            settings_2fa = self.database.get_setting('2fa')
            if settings_2fa:
                return settings_2fa
        except Exception as e:
            logger.error(f"Error getting global 2FA from settings: {e}")
        
        return None
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Any: Configuration value or default
        """
        return self._config_cache.get(key, default)
    
    def update_setting(self, key: str, value: Any) -> bool:
        """
        Update a configuration value
        
        Args:
            key: Configuration key
            value: New value
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Update cache
            self._config_cache[key] = value
            
            # Update database
            return self.database.update_bot_setting(key, value)
            
        except Exception as e:
            logger.error(f"Error updating setting {key}: {e}")
            return False
    
    def reload_config(self):
        """Reload configuration from database and environment"""
        self._config_cache.clear()
        self._load_config()
    
    def validate_required_config(self) -> tuple:
        """
        Validate that all required configuration is present
        
        Returns:
            tuple: (is_valid, error_messages)
        """
        errors = []
        
        try:
            self.get_api_id()
        except ValueError as e:
            errors.append(str(e))
        
        try:
            self.get_api_hash()
        except ValueError as e:
            errors.append(str(e))
        
        try:
            self.get_bot_token()
        except ValueError as e:
            errors.append(str(e))
        
        try:
            self.get_session_encryption_key()
        except ValueError as e:
            errors.append(str(e))
        
        admin_ids = self.get_admin_ids()
        if not admin_ids:
            errors.append("No admin IDs configured. Please set ADMIN_IDS environment variable.")
        
        return len(errors) == 0, errors