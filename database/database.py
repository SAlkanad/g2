"""
Database models and operations for the account selling bot
Enhanced with Firebase integration for sessions and user data
"""
import os
import json
import sqlite3
import firebase_admin
from firebase_admin import credentials, firestore, storage
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
import base64
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import secrets
import asyncio
import shutil

# Import network resilience modules
from network.network_config import (
    get_network_config,
    FirebaseRetryManager, 
    initialize_network_managers, 
    configure_ssl_warnings,
    RetryConfig
)

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = "bot_database_v2.db"):
        self.db_path = db_path
        self.firebase_enabled = False  # Initialize to False first
        # Require encryption key from environment - fail if not provided
        self.encryption_key = os.getenv('SESSION_ENCRYPTION_KEY')
        if not self.encryption_key:
            raise ValueError("SESSION_ENCRYPTION_KEY environment variable is required")
        self.last_sync_time = None
        self.init_firebase()
        self.init_database()
    
    def init_firebase(self):
        """Initialize Firebase connection with network resilience"""
        try:
            # Configure network settings
            from network.network_config import get_network_config, configure_ssl_warnings
            self.network_config = get_network_config()
            configure_ssl_warnings()
            
            # Check if Firebase app already exists
            try:
                app = firebase_admin.get_app()
                logger.info("Using existing Firebase app")
            except ValueError:
                # Initialize Firebase with service account from environment
                service_account_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH', 'serviceAccountKey.json')
                
                # Check if Firebase service account file exists
                if not os.path.exists(service_account_path):
                    logger.warning(f"Firebase service account file not found at {service_account_path}")
                    logger.info("Firebase initialization skipped - bot will use local database only")
                    return False
                
                database_url = os.getenv('FIREBASE_DATABASE_URL')
                storage_bucket = os.getenv('FIREBASE_STORAGE_BUCKET')
                
                if not database_url or not storage_bucket:
                    logger.warning("FIREBASE_DATABASE_URL and FIREBASE_STORAGE_BUCKET environment variables are required for Firebase functionality")
                    logger.info("Firebase initialization skipped - bot will use local database only")
                    return False
                
                cred = credentials.Certificate(service_account_path)
                app = firebase_admin.initialize_app(cred, {
                    'databaseURL': database_url,
                    'storageBucket': storage_bucket
                })
                logger.info("Firebase app initialized")
            
            # Get Firestore and Storage references
            self.db = firestore.client()
            self.bucket = storage.bucket()
            self.firebase_enabled = True
            
            # Initialize network managers
            initialize_network_managers(self)
            
            logger.info("Firebase integration enabled successfully with network resilience")
        except Exception as e:
            logger.error(f"Firebase initialization failed: {e}")
            self.firebase_enabled = False
    
    def init_database(self):
        """Initialize all database tables"""
        try:
            logger.info(f"Initializing database at: {self.db_path}")
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
            
            # Users table - enhanced with more fields
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language TEXT DEFAULT 'en',
                    balance REAL DEFAULT 0.0,
                    total_sold INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_banned BOOLEAN DEFAULT 0,
                    is_admin BOOLEAN DEFAULT 0,
                    phone_number TEXT,
                    email TEXT,
                    verification_status TEXT DEFAULT 'pending',
                    referral_code TEXT,
                    referred_by INTEGER,
                    total_earnings REAL DEFAULT 0.0
                )
            """)
            
            # Numbers pending approval
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_numbers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    phone_number TEXT UNIQUE,
                    country_code TEXT,
                    session_path TEXT,
                    json_path TEXT,
                    firebase_session_id TEXT,
                    device_info TEXT,
                    session_string TEXT,
                    session_backup TEXT,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    approval_time TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    reject_reason TEXT,
                    has_2fa BOOLEAN DEFAULT 0,
                    has_email BOOLEAN DEFAULT 0,
                    verification_screenshots TEXT,
                    firebase_sync_failed BOOLEAN DEFAULT 0,
                    firebase_sync_error TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Approved numbers for sale
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS approved_numbers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_id INTEGER,
                    phone_number TEXT UNIQUE,
                    country_code TEXT,
                    session_path TEXT,
                    json_path TEXT,
                    firebase_session_id TEXT,
                    session_string TEXT,
                    session_backup TEXT,
                    device_info TEXT,
                    price REAL DEFAULT 1.0,
                    is_sold BOOLEAN DEFAULT 0,
                    buyer_id INTEGER,
                    sold_at TIMESTAMP,
                    listed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    quality_score INTEGER DEFAULT 0,
                    account_age_days INTEGER DEFAULT 0,
                    verification_level TEXT DEFAULT 'basic',
                    FOREIGN KEY (seller_id) REFERENCES users(user_id),
                    FOREIGN KEY (buyer_id) REFERENCES users(user_id)
                )
            """)
            
            # Transactions history - enhanced
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    type TEXT,
                    amount REAL,
                    description TEXT,
                    related_number TEXT,
                    status TEXT DEFAULT 'completed',
                    transaction_hash TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Admin settings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_by INTEGER
                )
            """)
            
            # Countries with enhanced management
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS countries (
                    country_code TEXT PRIMARY KEY,
                    country_name TEXT,
                    dialing_code TEXT,
                    price REAL DEFAULT 1.0,
                    target_quantity INTEGER DEFAULT 100,
                    current_quantity INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT 0,
                    priority INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Multilingual content management
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS content (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_type TEXT NOT NULL,
                    language TEXT NOT NULL,
                    content TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_by INTEGER,
                    UNIQUE(content_type, language),
                    FOREIGN KEY (updated_by) REFERENCES users(user_id)
                )
            """)
            
            # Withdrawal requests
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS withdrawal_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount REAL,
                    payment_details TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP,
                    admin_notes TEXT,
                    transaction_id TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # User sessions for tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    session_data TEXT,
                    firebase_session_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # User violations tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    violation_type TEXT,
                    violation_reason TEXT,
                    phone_number TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    admin_notes TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Notifications table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    title TEXT,
                    message TEXT,
                    notification_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_sent BOOLEAN DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Rejected sessions table for sell account system
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rejected_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    reason TEXT,
                    session_path TEXT,
                    session_info TEXT,
                    firebase_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            conn.commit()
            logger.info("Database tables created successfully")
            
            # Initialize default data using defaultdata module
            from database.defaultdata import DefaultDataInitializer
            initializer = DefaultDataInitializer(self.db_path)
            initializer.init_default_settings()
            # initializer.init_default_countries()  # Commented out - countries will be added manually
            initializer.init_default_content()
            self.init_bot_settings()
            
            # Migrate existing database if needed
            self._migrate_database()
            
            logger.info("Database initialization completed successfully")
            
            # Auto-sync to Firebase if enabled
            if self.firebase_enabled:
                try:
                    logger.info("Auto-syncing initial data to Firebase...")
                    self.sync_countries_to_firebase()
                    self.sync_content_to_firebase()
                except Exception as e:
                    logger.error(f"Error during auto-sync to Firebase: {e}")
                    # Continue without failing the database initialization
        
        except Exception as e:
            logger.error(f"Critical error during database initialization: {e}")
            raise e
    
    # User operations
    def create_user(self, user_id: int, username: str = None, 
                   first_name: str = None, last_name: str = None, language: str = 'en') -> bool:
        """Create a new user with enhanced fields"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO users 
                    (user_id, username, first_name, last_name, language) 
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, username, first_name, last_name, language))
                conn.commit()
                
                if cursor.rowcount > 0:
                    # Sync to Firebase if enabled
                    if self.firebase_enabled:
                        self.log_user_to_firebase(user_id, username, first_name, last_name)
                        self.sync_user_to_firebase(user_id)
                
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return False
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user information"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_user_language(self, user_id: int) -> Optional[str]:
        """Get user's language preference"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                return row[0] if row and row[0] else 'en'
        except Exception as e:
            logger.error(f"Error getting user language: {e}")
            return 'en'
    
    def update_user_language(self, user_id: int, language: str) -> bool:
        """Update user language preference"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users SET language = ?, last_active = CURRENT_TIMESTAMP 
                    WHERE user_id = ?
                """, (language, user_id))
                conn.commit()
                
                if cursor.rowcount > 0:
                    # Sync to Firebase
                    if self.firebase_enabled:
                        self.sync_user_to_firebase(user_id)
                
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating language: {e}")
            return False
    
    def update_user_balance(self, user_id: int, amount: float, 
                          transaction_type: str, description: str,
                          related_number: str = None) -> bool:
        """Update user balance and record transaction"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Update balance
                cursor.execute("""
                    UPDATE users 
                    SET balance = balance + ?, 
                        total_earnings = total_earnings + CASE WHEN ? > 0 THEN ? ELSE 0 END,
                        last_active = CURRENT_TIMESTAMP 
                    WHERE user_id = ?
                """, (amount, amount, amount, user_id))
                
                # Record transaction
                cursor.execute("""
                    INSERT INTO transactions 
                    (user_id, type, amount, description, related_number)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, transaction_type, amount, description, related_number))
                
                conn.commit()
                
                # Sync to Firebase
                if self.firebase_enabled:
                    self.sync_user_to_firebase(user_id)
                    self.sync_transaction_to_firebase(cursor.lastrowid, user_id, transaction_type, amount, description, related_number)
                
                return True
        except Exception as e:
            logger.error(f"Error updating balance: {e}")
            return False
    
    # Content management
    def get_content(self, content_type: str, language: str) -> str:
        """Get content by type and language"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT content FROM content 
                WHERE content_type = ? AND language = ?
            """, (content_type, language))
            result = cursor.fetchone()
            
            if result:
                return result[0]
            
            # Fallback to English if not found
            cursor.execute("""
                SELECT content FROM content 
                WHERE content_type = ? AND language = 'en'
            """, (content_type,))
            result = cursor.fetchone()
            return result[0] if result else f"Content not found: {content_type}"
    
    def get_content_from_firebase(self, content_type: str, language: str) -> str:
        """Get content from Firebase with real-time data"""
        if not self.firebase_enabled:
            logger.warning("Firebase not enabled, falling back to local database")
            return self.get_content(content_type, language)
        
        try:
            # Try to get content for the requested language
            doc_id = f"{content_type}_{language}"
            doc = self.db.collection('content').document(doc_id).get()
            
            if doc.exists:
                content_data = doc.to_dict()
                logger.info(f"Retrieved {content_type} content in {language} from Firebase")
                return content_data.get('content', f"Content not found: {content_type}")
            
            # Fallback to English if not found
            if language != 'en':
                doc_id = f"{content_type}_en"
                doc = self.db.collection('content').document(doc_id).get()
                
                if doc.exists:
                    content_data = doc.to_dict()
                    logger.info(f"Retrieved {content_type} content in English from Firebase (fallback)")
                    return content_data.get('content', f"Content not found: {content_type}")
            
            # Final fallback to local database
            logger.warning(f"Content not found in Firebase for {content_type}_{language}, falling back to local")
            return self.get_content(content_type, language)
            
        except Exception as e:
            logger.error(f"Error fetching content from Firebase: {e}")
            # Fallback to local database
            return self.get_content(content_type, language)
    
    def update_content(self, content_type: str, language: str, content: str, updated_by: int) -> bool:
        """Update content for specific type and language"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO content 
                    (content_type, language, content, updated_by, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (content_type, language, content, updated_by))
                conn.commit()
                
                # Also sync to Firebase
                self.update_content_in_firebase(content_type, language, content, updated_by)
                
                return True
        except Exception as e:
            logger.error(f"Error updating content: {e}")
            return False
    
    # Country management
    def get_countries(self, active_only: bool = True) -> List[Dict]:
        """Get countries with enhanced info"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if active_only:
                cursor.execute("""
                    SELECT * FROM countries WHERE is_active = 1 
                    ORDER BY priority DESC, country_name
                """)
            else:
                cursor.execute("SELECT * FROM countries ORDER BY country_name")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_countries_from_firebase(self, active_only: bool = True) -> List[Dict]:
        """Get countries from Firebase with real-time data"""
        if not self.firebase_enabled:
            logger.warning("Firebase not enabled, falling back to local database")
            return self.get_countries(active_only)
        
        try:
            countries = []
            query = self.db.collection('countries')
            
            if active_only:
                query = query.where('is_active', '==', True)
            
            docs = query.stream()
            
            for doc in docs:
                country_data = doc.to_dict()
                country_data['id'] = doc.id
                # Ensure all required fields exist with defaults
                country_data.setdefault('current_quantity', 0)
                country_data.setdefault('target_quantity', 100)
                country_data.setdefault('price', 1.0)
                country_data.setdefault('priority', 1)
                country_data.setdefault('is_active', False)
                countries.append(country_data)
            
            # Sort in Python instead of Firebase to avoid index requirement
            countries.sort(key=lambda x: (-x.get('priority', 1), x.get('country_name', '')))
            
            logger.info(f"Retrieved {len(countries)} countries from Firebase")
            return countries
        except Exception as e:
            logger.error(f"Error fetching countries from Firebase: {e}")
            # Fallback to local database
            return self.get_countries(active_only)
    
    def get_country_by_code(self, country_code: str) -> Optional[Dict]:
        """Get country information by country code"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM countries WHERE country_code = ?
                """, (country_code,))
                result = cursor.fetchone()
                return dict(result) if result else None
        except Exception as e:
            logger.error(f"Error getting country by code {country_code}: {e}")
            return None
    
    def get_country_price(self, country_code: str) -> float:
        """Get price for a specific country"""
        try:
            country = self.get_country_by_code(country_code)
            return country.get('price', 0.0) if country else 0.0
        except Exception as e:
            logger.error(f"Error getting country price: {e}")
            return 0.0
    
    def update_country(self, country_code: str, **kwargs) -> bool:
        """Update country with any provided fields"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Build dynamic update query
                updates = []
                params = []
                for key, value in kwargs.items():
                    if key in ['country_name', 'dialing_code', 'price', 'target_quantity', 'is_active', 'priority']:
                        updates.append(f"{key} = ?")
                        params.append(value)
                
                if updates:
                    params.append(country_code)
                    cursor.execute(f"""
                        UPDATE countries 
                        SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP
                        WHERE country_code = ?
                    """, params)
                    conn.commit()
                    
                    # Also sync to Firebase
                    if cursor.rowcount > 0:
                        self.update_country_in_firebase(country_code, **kwargs)
                    
                    return cursor.rowcount > 0
                return False
        except Exception as e:
            logger.error(f"Error updating country: {e}")
            return False
    
    def add_country(self, country_code: str, country_name: str, price: float = 1.0, target_quantity: int = 100, dialing_code: str = None) -> bool:
        """Add new country and sync to Firebase"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO countries (country_code, country_name, dialing_code, price, target_quantity, is_active)
                    VALUES (?, ?, ?, ?, ?, 0)
                """, (country_code, country_name, dialing_code, price, target_quantity))
                conn.commit()
                
                # Note: Auto-sync disabled for performance. Use manual sync from admin panel.
                logger.info(f"Country {country_code} added to local database. Use manual sync to update Firebase.")
                
                return True
        except Exception as e:
            logger.error(f"Error adding country: {e}")
            return False
    
    def delete_country(self, country_code: str) -> bool:
        """Delete a country"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM countries WHERE country_code = ?", (country_code,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting country: {e}")
            return False
    
    def toggle_country_status(self, country_code: str) -> bool:
        """Toggle country active status"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE countries 
                    SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE country_code = ?
                """, (country_code,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error toggling country status: {e}")
            return False
    
    # Admin operations
    def get_setting(self, key: str) -> Optional[str]:
        """Get admin setting"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            result = cursor.fetchone()
            return result[0] if result else None
    
    def update_setting(self, key: str, value: str, updated_by: int = None) -> bool:
        """Update admin setting"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO settings (key, value, updated_by, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (key, value, updated_by))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error updating setting: {e}")
            return False
    
    def add_admin(self, user_id: int) -> bool:
        """Add admin privileges to user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users SET is_admin = 1 WHERE user_id = ?
                """, (user_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error adding admin: {e}")
            return False
    
    def get_all_admins(self) -> List[Dict]:
        """Get all admin users"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT user_id, username, first_name, last_name, language, is_admin
                    FROM users 
                    WHERE is_admin = 1 AND is_banned = 0
                """)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting admin users: {e}")
            return []

    def is_admin(self, user_id: int) -> bool:
        """Check if a user is an admin."""
        # First, check the environment variable for master admins
        admin_ids_str = os.getenv('ADMIN_IDS', '')
        if admin_ids_str:
            try:
                admin_ids = [int(admin_id.strip()) for admin_id in admin_ids_str.split(',')]
                if user_id in admin_ids:
                    return True
            except ValueError:
                logger.error("Invalid ADMIN_IDS format in environment variables.")

        # If not a master admin, check the database
        user = self.get_user(user_id)
        return bool(user and user.get('is_admin'))
    
    def _migrate_database(self):
        """Migrate existing database to add missing columns"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if firebase_sync_failed column exists in pending_numbers
                cursor.execute("PRAGMA table_info(pending_numbers)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'firebase_sync_failed' not in columns:
                    cursor.execute("ALTER TABLE pending_numbers ADD COLUMN firebase_sync_failed BOOLEAN DEFAULT 0")
                    cursor.execute("ALTER TABLE pending_numbers ADD COLUMN firebase_sync_error TEXT")
                    conn.commit()
                    logger.info("Added firebase_sync_failed and firebase_sync_error columns to pending_numbers")
                
                # Check if dialing_code column exists in countries
                cursor.execute("PRAGMA table_info(countries)")
                country_columns = [column[1] for column in cursor.fetchall()]
                
                if 'dialing_code' not in country_columns:
                    cursor.execute("ALTER TABLE countries ADD COLUMN dialing_code TEXT")
                    conn.commit()
                    logger.info("Added dialing_code column to countries table")
                
        except Exception as e:
            logger.error(f"Error during database migration: {e}")
    
    def get_admin_stats(self) -> Dict:
        """Get comprehensive admin statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            stats = {}
            
            # User stats
            cursor.execute("SELECT COUNT(*) FROM users")
            stats['total_users'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM users WHERE created_at >= date('now', '-7 days')")
            stats['new_users_week'] = cursor.fetchone()[0]
            
            # Account stats
            cursor.execute("SELECT COUNT(*) FROM pending_numbers WHERE status = 'pending'")
            stats['pending_numbers'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM approved_numbers WHERE is_sold = 0")
            stats['available_numbers'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM approved_numbers WHERE is_sold = 1")
            stats['sold_numbers'] = cursor.fetchone()[0]
            
            # Financial stats
            cursor.execute("SELECT SUM(balance) FROM users")
            stats['total_balance'] = cursor.fetchone()[0] or 0
            
            cursor.execute("""
                SELECT SUM(amount) FROM transactions 
                WHERE type = 'sale' AND amount > 0 AND created_at >= date('now', '-30 days')
            """)
            stats['monthly_sales'] = cursor.fetchone()[0] or 0
            
            return stats
    
    def get_pending_numbers(self, status: str = 'pending') -> List[Dict]:
        """Get pending numbers for admin approval"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT p.*, u.username, u.first_name 
                FROM pending_numbers p
                JOIN users u ON p.user_id = u.user_id
                WHERE p.status = ?
                ORDER BY p.submitted_at DESC
            """, (status,))
            return [dict(row) for row in cursor.fetchall()]
    
    def approve_number(self, pending_id: int, admin_id: int) -> Dict:
        """Approve a pending number and return details for notification"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get pending number info
                cursor.execute("""
                    SELECT * FROM pending_numbers WHERE id = ? AND status = 'pending'
                """, (pending_id,))
                pending = cursor.fetchone()
                
                if not pending:
                    return {'success': False, 'error': 'Pending number not found'}
                
                # Get price for this country (if available) or use default
                country_price = self.get_country_price(pending[3]) or float(self.get_setting('default_price') or 1.0)
                
                # Move to approved numbers
                cursor.execute("""
                    INSERT INTO approved_numbers 
                    (seller_id, phone_number, country_code, session_path, json_path, firebase_session_id, price)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    pending[1], pending[2], pending[3], pending[4], 
                    pending[5], pending[6], country_price
                ))
                approved_id = cursor.lastrowid
                
                # Update pending status
                cursor.execute("""
                    UPDATE pending_numbers 
                    SET status = 'approved', approval_time = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (pending_id,))
                
                # Add balance to user
                cursor.execute("""
                    UPDATE users SET balance = balance + ?, total_sold = total_sold + 1 
                    WHERE user_id = ?
                """, (country_price, pending[1]))
                
                # Get updated user balance
                cursor.execute("SELECT balance FROM users WHERE user_id = ?", (pending[1],))
                new_balance = cursor.fetchone()[0]
                
                # Record transaction
                cursor.execute("""
                    INSERT INTO transactions (user_id, type, amount, description, related_number, status)
                    VALUES (?, 'credit', ?, ?, ?, 'completed')
                """, (pending[1], country_price, f'Account approval payment', pending[2]))
                
                conn.commit()
                
                # Sync to Firebase with new purchased_numbers structure
                if self.firebase_enabled:
                    # Save as purchased number instead of approved number
                    purchase_id = self.save_purchased_number_to_firebase(
                        pending[1], pending[2], pending[6], country_price
                    )
                    self.sync_user_to_firebase(pending[1])
                
                # Update country quantity and check if limit reached
                country_update = self.update_country_quantity(pending[3])
                
                return {
                    'success': True,
                    'user_id': pending[1],
                    'phone': pending[2],
                    'price': country_price,
                    'new_balance': new_balance,
                    'country_code': pending[3],
                    'country_update': country_update
                }
        except Exception as e:
            logger.error(f"Error approving number: {e}")
            return {'success': False, 'error': str(e)}
    
    def reject_number(self, pending_id: int, reason: str, admin_id: int) -> Dict:
        """Reject a pending number and return details for notification"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get pending number info before rejecting
                cursor.execute("""
                    SELECT user_id, phone_number FROM pending_numbers 
                    WHERE id = ? AND status = 'pending'
                """, (pending_id,))
                pending_info = cursor.fetchone()
                
                if not pending_info:
                    return {'success': False, 'error': 'Pending number not found'}
                
                cursor.execute("""
                    UPDATE pending_numbers 
                    SET status = 'rejected', reject_reason = ?
                    WHERE id = ? AND status = 'pending'
                """, (reason, pending_id))
                conn.commit()
                
                if cursor.rowcount > 0:
                    return {
                        'success': True,
                        'user_id': pending_info[0],
                        'phone': pending_info[1],
                        'reason': reason
                    }
                else:
                    return {'success': False, 'error': 'Failed to update record'}
        except Exception as e:
            logger.error(f"Error rejecting number: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_recent_users(self, limit: int = 20) -> List[Dict]:
        """Get recent users for admin management"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM users 
                ORDER BY last_active DESC 
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def search_user(self, query: str) -> List[Dict]:
        """Search for users by username, first name, or user ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM users 
                WHERE user_id LIKE ? OR username LIKE ? OR first_name LIKE ?
                ORDER BY last_active DESC
                LIMIT 20
            """, (f"%{query}%", f"%{query}%", f"%{query}%"))
            return [dict(row) for row in cursor.fetchall()]
    
    def ban_user(self, user_id: int, admin_id: int) -> bool:
        """Ban a user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users SET is_banned = 1 WHERE user_id = ?
                """, (user_id,))
                conn.commit()
                
                if cursor.rowcount > 0 and self.firebase_enabled:
                    self.sync_user_to_firebase(user_id)
                
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error banning user: {e}")
            return False
    
    def unban_user(self, user_id: int, admin_id: int) -> bool:
        """Unban a user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users SET is_banned = 0 WHERE user_id = ?
                """, (user_id,))
                conn.commit()
                
                if cursor.rowcount > 0 and self.firebase_enabled:
                    self.sync_user_to_firebase(user_id)
                
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error unbanning user: {e}")
            return False
    
    def get_withdrawal_requests(self, status: str = 'pending') -> List[Dict]:
        """Get withdrawal requests for admin processing"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT w.*, u.username, u.first_name 
                FROM withdrawal_requests w
                JOIN users u ON w.user_id = u.user_id
                WHERE w.status = ?
                ORDER BY w.created_at DESC
            """, (status,))
            return [dict(row) for row in cursor.fetchall()]
    
    def process_withdrawal(self, withdrawal_id: int, admin_id: int, status: str, admin_notes: str = None) -> bool:
        """Process a withdrawal request"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE withdrawal_requests 
                    SET status = ?, processed_at = CURRENT_TIMESTAMP, admin_notes = ?
                    WHERE id = ?
                """, (status, admin_notes, withdrawal_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error processing withdrawal: {e}")
            return False
    
    # Firebase integration methods
    def log_user_to_firebase(self, user_id: int, username: str, first_name: str, last_name: str):
        """Log user registration to Firebase"""
        if not self.firebase_enabled:
            return
        
        try:
            # Log user to Firestore
            user_data = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'registered_at': datetime.now().isoformat(),
                'last_active': datetime.now().isoformat()
            }
            
            # Save to Firestore users collection
            self.db.collection('users').document(str(user_id)).set(user_data)
            logger.info(f"User {user_id} logged to Firebase successfully")
        except Exception as e:
            logger.error(f"Error logging to Firebase: {e}")
    
    def _get_fernet_key(self) -> Fernet:
        """Generate Fernet key from encryption key"""
        # Use PBKDF2 to derive a proper key from the encryption key
        # Generate or retrieve a random salt for each session
        salt = os.getenv('ENCRYPTION_SALT')
        if not salt:
            raise ValueError("ENCRYPTION_SALT environment variable is required")
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt.encode() if isinstance(salt, str) else salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.encryption_key.encode()))
        return Fernet(key)

    def encrypt_session_data(self, session_data: dict) -> str:
        """Encrypt session data before storage using Fernet (AES 128)"""
        try:
            # Convert session data to JSON string
            json_string = json.dumps(session_data)
            
            # Get Fernet cipher
            f = self._get_fernet_key()
            
            # Encrypt the data
            encrypted_data = f.encrypt(json_string.encode())
            
            # Return base64 encoded string
            return base64.b64encode(encrypted_data).decode('utf-8')
        except Exception as e:
            logger.error(f"Error encrypting session data: {e}")
            return ""

    def decrypt_session_data(self, encrypted_data: str) -> dict:
        """Decrypt session data after retrieval using Fernet (AES 128)"""
        try:
            # Get Fernet cipher
            f = self._get_fernet_key()
            
            # Base64 decode and decrypt
            encrypted_bytes = base64.b64decode(encrypted_data.encode('utf-8'))
            decrypted_bytes = f.decrypt(encrypted_bytes)
            
            # Convert back to dict
            return json.loads(decrypted_bytes.decode('utf-8'))
        except Exception as e:
            logger.error(f"Error decrypting session data: {e}")
            return {}

    def save_session_to_firebase(self, session_path: str, user_id: int, json_data: dict = None) -> str:
        """Save encrypted session to Firestore using new structure"""
        if not self.firebase_enabled:
            return f"local_{user_id}_{int(datetime.now().timestamp())}"
        
        try:
            # Generate unique session ID
            timestamp = int(datetime.now().timestamp())
            phone_number = json_data.get('phone', '') if json_data else ''
            session_id = f"session_{phone_number.replace('+', '')}_{timestamp}"
            
            # Hash phone number for storage
            phone_hash = hashlib.sha256(phone_number.encode()).hexdigest() if phone_number else ""
            
            # Read and encrypt session file
            encrypted_session_string = ""
            encrypted_auth_key = ""
            if os.path.exists(session_path):
                with open(session_path, 'rb') as f:
                    session_bytes = f.read()
                    session_string = base64.b64encode(session_bytes).decode('utf-8')
                    encrypted_session_string = self.encrypt_session_data({"session_string": session_string})
            
            # Encrypt sensitive session data
            session_data = {
                "auth_key": encrypted_auth_key,  # This would need to be extracted from session
                "dc_id": json_data.get('dc_id', 2) if json_data else 2,
                "user_id": json_data.get('user_id', 0) if json_data else 0,
                "session_string": encrypted_session_string,
                "api_id": json_data.get('api_id', 0) if json_data else 0,
                "api_hash": self.encrypt_session_data({"api_hash": json_data.get('api_hash', '')}) if json_data and json_data.get('api_hash') else ""
            }
            
            # Create telegram_sessions document
            session_document = {
                'session_id': session_id,
                'phone_number': phone_number,
                'phone_hash': phone_hash,
                'session_data': session_data,
                'status': {
                    'is_active': True,
                    'last_used': datetime.now(),
                    'login_attempts': 0,
                    'last_code_request': None,
                    'freeze_risk_level': 'low'
                },
                'keep_alive': {
                    'last_heartbeat': datetime.now(),
                    'auto_refresh': True,
                    'refresh_interval': 3600000,  # 1 hour in ms
                    'max_lifetime': 86400000      # 24 hours in ms
                }
            }
            
            # Store in Firestore telegram_sessions collection
            self.db.collection('telegram_sessions').document(session_id).set(session_document)
            
            logger.info(f"Session saved to Firestore telegram_sessions: {session_path} -> {session_id}")
            return session_id
        except Exception as e:
            logger.error(f"Error saving session to Firebase: {e}")
            return f"error_{user_id}_{int(datetime.now().timestamp())}"
    
    def get_session_from_firebase(self, session_id: str, download_path: str = None) -> dict:
        """Retrieve encrypted session data from Firestore telegram_sessions collection"""
        if not self.firebase_enabled:
            return {'success': False, 'error': 'Firebase not enabled'}
        
        try:
            # Get session document from telegram_sessions collection
            doc = self.db.collection('telegram_sessions').document(session_id).get()
            
            if not doc.exists:
                return {'success': False, 'error': 'Session not found'}
            
            session_doc = doc.to_dict()
            session_data = session_doc.get('session_data', {})
            
            # Decrypt session string if available
            decrypted_session = {}
            if session_data.get('session_string'):
                decrypted_session = self.decrypt_session_data(session_data['session_string'])
            
            # Save to file if path provided and session string exists
            if download_path and decrypted_session.get('session_string'):
                session_bytes = base64.b64decode(decrypted_session['session_string'].encode('utf-8'))
                with open(download_path, 'wb') as f:
                    f.write(session_bytes)
            
            # Decrypt API hash if available
            decrypted_api_hash = ""
            if session_data.get('api_hash'):
                api_hash_data = self.decrypt_session_data(session_data['api_hash'])
                decrypted_api_hash = api_hash_data.get('api_hash', '')
            
            logger.info(f"Session retrieved from Firestore telegram_sessions: {session_id}")
            return {
                'success': True,
                'phone_number': session_doc.get('phone_number', ''),
                'phone_hash': session_doc.get('phone_hash', ''),
                'session_data': {
                    'dc_id': session_data.get('dc_id', 2),
                    'user_id': session_data.get('user_id', 0),
                    'api_id': session_data.get('api_id', 0),
                    'api_hash': decrypted_api_hash,
                    'session_string': decrypted_session.get('session_string', '')
                },
                'status': session_doc.get('status', {}),
                'keep_alive': session_doc.get('keep_alive', {})
            }
        except Exception as e:
            logger.error(f"Error retrieving session from Firebase: {e}")
            return {'success': False, 'error': str(e)}
    
    def sync_to_firebase(self, collection: str, document_id: str, data: dict):
        """Sync data to Firebase Firestore with retry logic"""
        if not self.firebase_enabled:
            return
        
        try:
            # Create a simple operation function
            def firebase_operation():
                return self.db.collection(collection).document(str(document_id)).set(data, merge=True)
            
            # Use the retry manager for Firebase operations
            if hasattr(self, 'firebase_retry_manager') and self.firebase_retry_manager:
                # Run the retry operation
                loop = None
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If we're in an async context, create a new task
                        asyncio.create_task(self.firebase_retry_manager.execute_with_retry(firebase_operation))
                    else:
                        # If we're not in async context, run it
                        loop.run_until_complete(self.firebase_retry_manager.execute_with_retry(firebase_operation))
                except RuntimeError:
                    # No event loop running, create a new one
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(self.firebase_retry_manager.execute_with_retry(firebase_operation))
                    except RuntimeError:
                        # No running event loop, use asyncio.run
                        asyncio.run(self.firebase_retry_manager.execute_with_retry(firebase_operation))
            else:
                # Fallback to direct call with basic retry
                self._sync_to_firebase_with_retry(collection, document_id, data)
            
            logger.info(f"Data synced to Firebase: {collection}/{document_id}")
        except Exception as e:
            logger.error(f"Error syncing content to Firebase: {e}")
            
    def _sync_to_firebase_with_retry(self, collection: str, document_id: str, data: dict):
        """Fallback Firebase sync with basic retry"""
        import time
        import random
        
        max_attempts = 3
        base_delay = 2.0
        max_delay = 60.0
        exponential_base = 2.0
        last_exception = None
        
        for attempt in range(max_attempts):
            try:
                self.db.collection(collection).document(str(document_id)).set(data, merge=True)
                return  # Success
            except Exception as e:
                last_exception = e
                if attempt == max_attempts - 1:
                    break
                
                # Calculate delay with exponential backoff
                delay = min(
                    base_delay * (exponential_base ** attempt),
                    max_delay
                )
                
                # Add jitter to prevent thundering herd
                delay = delay * (0.5 + random.random() * 0.5)
                
                logger.warning(f"Firebase sync attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s...")
                time.sleep(delay)
        
        # All attempts failed
        raise last_exception
    
    def get_from_firebase(self, collection: str, document_id: str) -> Optional[dict]:
        """Get data from Firebase Firestore"""
        if not self.firebase_enabled:
            return None
        
        try:
            doc = self.db.collection(collection).document(str(document_id)).get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            logger.error(f"Error getting from Firebase: {e}")
            return None
    
    def get_session_string_from_firebase(self, session_id: str) -> str:
        """Get session data as base64 string directly from Firestore (fast access)"""
        if not self.firebase_enabled:
            return ""
        
        try:
            doc = self.db.collection('sessions').document(session_id).get()
            if doc.exists:
                session_doc = doc.to_dict()
                return session_doc.get('session_data', '')
            return ""
        except Exception as e:
            logger.error(f"Error getting session string from Firebase: {e}")
            return ""
    
    def create_session_from_string(self, session_string: str, output_path: str) -> bool:
        """Create session file from base64 string"""
        try:
            if not session_string:
                return False
            
            # Decode base64 string to bytes
            session_bytes = base64.b64decode(session_string.encode('utf-8'))
            
            # Write to file
            with open(output_path, 'wb') as f:
                f.write(session_bytes)
            
            logger.info(f"Session file created from string: {output_path}")
            return True
        except Exception as e:
            logger.error(f"Error creating session from string: {e}")
            return False
    
    def get_user_sessions(self, user_id: int) -> List[dict]:
        """Get all sessions for a user from Firestore"""
        if not self.firebase_enabled:
            return []
        
        try:
            sessions = []
            query = self.db.collection('sessions').where('user_id', '==', user_id).where('is_active', '==', True)
            docs = query.stream()
            
            for doc in docs:
                session_data = doc.to_dict()
                sessions.append({
                    'session_id': session_data.get('session_id', ''),
                    'phone_number': session_data.get('phone_number', ''),
                    'device_model': session_data.get('device_model', ''),
                    'created_at': session_data.get('created_at', ''),
                    'file_size': session_data.get('file_size', 0)
                })
            
            return sessions
        except Exception as e:
            logger.error(f"Error getting user sessions: {e}")
            return []
    
    def deactivate_session(self, session_id: str) -> bool:
        """Deactivate a session in Firestore"""
        if not self.firebase_enabled:
            return False
        
        try:
            self.db.collection('sessions').document(session_id).update({
                'is_active': False,
                'deactivated_at': datetime.now().isoformat()
            })
            logger.info(f"Session deactivated: {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error deactivating session: {e}")
            return False
    
    def sync_user_to_firebase(self, user_id: int):
        """Sync user data to Firebase"""
        if not self.firebase_enabled:
            return
        
        try:
            user = self.get_user(user_id)
            if user:
                user_data = {
                    'user_id': user['user_id'],
                    'username': user['username'],
                    'first_name': user['first_name'],
                    'last_name': user['last_name'],
                    'language': user['language'],
                    'balance': user['balance'],
                    'total_sold': user['total_sold'],
                    'total_earnings': user['total_earnings'],
                    'is_admin': user['is_admin'],
                    'last_active': user['last_active'],
                    'created_at': user['created_at'],
                    'sync_timestamp': datetime.now().isoformat()
                }
                
                self.db.collection('users').document(str(user_id)).set(user_data, merge=True)
                logger.info(f"User {user_id} synced to Firebase")
        except Exception as e:
            logger.error(f"Error syncing user to Firebase: {e}")
    
    def sync_transaction_to_firebase(self, transaction_id: int, user_id: int, transaction_type: str, amount: float, description: str, related_number: str = None):
        """Sync transaction to Firebase"""
        if not self.firebase_enabled:
            return
        
        try:
            transaction_data = {
                'transaction_id': transaction_id,
                'user_id': user_id,
                'type': transaction_type,
                'amount': amount,
                'description': description,
                'related_number': related_number,
                'created_at': datetime.now().isoformat()
            }
            
            self.db.collection('transactions').document(str(transaction_id)).set(transaction_data)
            logger.info(f"Transaction {transaction_id} synced to Firebase")
        except Exception as e:
            logger.error(f"Error syncing transaction to Firebase: {e}")
    
    def sync_approved_number_to_firebase(self, approved_id: int, seller_id: int, phone_number: str, firebase_session_id: str, price: float):
        """Sync approved number to Firebase"""
        if not self.firebase_enabled:
            return
        
        try:
            approved_data = {
                'approved_id': approved_id,
                'seller_id': seller_id,
                'phone_number': phone_number,
                'firebase_session_id': firebase_session_id,
                'price': price,
                'is_sold': False,
                'listed_at': datetime.now().isoformat()
            }
            
            self.db.collection('approved_numbers').document(str(approved_id)).set(approved_data)
            logger.info(f"Approved number {approved_id} synced to Firebase")
        except Exception as e:
            logger.error(f"Error syncing approved number to Firebase: {e}")
    
    def sync_countries_to_firebase(self):
        """Sync all countries from SQLite to Firebase"""
        if not self.firebase_enabled:
            logger.warning("Firebase not enabled, cannot sync countries")
            return
        
        try:
            countries = self.get_countries(active_only=False)
            
            for country in countries:
                country_data = {
                    'country_code': country['country_code'],
                    'country_name': country['country_name'],
                    'price': country['price'],
                    'target_quantity': country['target_quantity'],
                    'current_quantity': country['current_quantity'],
                    'is_active': bool(country['is_active']),  # Convert integer to boolean
                    'priority': country['priority'],
                    'created_at': country['created_at'],
                    'updated_at': country['updated_at'],
                    'sync_timestamp': datetime.now().isoformat()
                }
                
                self.db.collection('countries').document(country['country_code']).set(country_data, merge=True)
            
            logger.info(f"Synced {len(countries)} countries to Firebase")
        except Exception as e:
            logger.error(f"Error syncing countries to Firebase: {e}")
    
    def sync_content_to_firebase(self):
        """Sync all content from SQLite to Firebase with retry logic"""
        if not self.firebase_enabled:
            logger.warning("Firebase not enabled, cannot sync content")
            return
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM content")
                content_items = cursor.fetchall()
            
            # Prepare batch operations
            operations = []
            for item in content_items:
                doc_id = f"{item['content_type']}_{item['language']}"
                content_data = {
                    'content_type': item['content_type'],
                    'language': item['language'],
                    'content': item['content'],
                    'updated_at': item['updated_at'],
                    'updated_by': item['updated_by'],
                    'sync_timestamp': datetime.now().isoformat()
                }
                
                operations.append({
                    'collection': 'content',
                    'document_id': doc_id,
                    'data': content_data,
                    'merge': True
                })
            
            # Use batch operations for better performance
            if hasattr(self, 'firebase_retry_manager') and self.firebase_retry_manager and len(operations) > 0:
                async def firebase_batch_operation():
                    # Process operations individually with retry
                    for operation in operations:
                        self._sync_to_firebase_with_retry(
                            operation['collection'], 
                            operation['document_id'], 
                            operation['data']
                        )
                try:
                    import asyncio
                    loop = asyncio.get_running_loop()
                    loop.create_task(self.firebase_retry_manager.execute_with_retry(firebase_batch_operation))
                except RuntimeError:
                    # No running event loop, use asyncio.run
                    asyncio.run(self.firebase_retry_manager.execute_with_retry(firebase_batch_operation))
            else:
                # Fallback to individual operations
                for operation in operations:
                    self._sync_to_firebase_with_retry(
                        operation['collection'],
                        operation['document_id'],
                        operation['data']
                    )
            
            logger.info(f"Synced {len(content_items)} content items to Firebase")
        except Exception as e:
            logger.error(f"Error syncing content to Firebase: {e}")
    
    def update_country_in_firebase(self, country_code: str, **kwargs) -> bool:
        """Update country in Firebase"""
        if not self.firebase_enabled:
            return False
        
        try:
            # Update in Firebase
            update_data = {
                'updated_at': datetime.now().isoformat(),
                'sync_timestamp': datetime.now().isoformat()
            }
            
            for key, value in kwargs.items():
                if key in ['country_name', 'dialing_code', 'price', 'target_quantity', 'current_quantity', 'is_active', 'priority']:
                    # Convert is_active to boolean if it's an integer
                    if key == 'is_active':
                        update_data[key] = bool(value)
                    else:
                        update_data[key] = value
            
            self.db.collection('countries').document(country_code).update(update_data)
            logger.info(f"Updated country {country_code} in Firebase")
            return True
        except Exception as e:
            logger.error(f"Error updating country in Firebase: {e}")
            return False
    
    def update_content_in_firebase(self, content_type: str, language: str, content: str, updated_by: int) -> bool:
        """Update content in Firebase"""
        if not self.firebase_enabled:
            return False
        
        try:
            doc_id = f"{content_type}_{language}"
            content_data = {
                'content_type': content_type,
                'language': language,
                'content': content,
                'updated_at': datetime.now().isoformat(),
                'updated_by': updated_by,
                'sync_timestamp': datetime.now().isoformat()
            }
            
            self.db.collection('content').document(doc_id).set(content_data, merge=True)
            logger.info(f"Updated content {doc_id} in Firebase")
            return True
        except Exception as e:
            logger.error(f"Error updating content in Firebase: {e}")
            return False
    
    def save_purchased_number_to_firebase(self, user_id: int, phone_number: str, session_id: str, price: float) -> str:
        """Save purchased number to Firestore using new structure"""
        if not self.firebase_enabled:
            return f"local_purchase_{user_id}_{int(datetime.now().timestamp())}"
        
        try:
            # Generate unique number ID
            timestamp = int(datetime.now().timestamp())
            number_id = f"num_{phone_number.replace('+', '')}_{timestamp}"
            
            # Hash phone number for storage
            phone_hash = hashlib.sha256(phone_number.encode()).hexdigest()
            
            # Create purchased_numbers document
            purchase_document = {
                'number_id': number_id,
                'user_id': user_id,
                'phone_number_hash': phone_hash,
                'status': 'active',
                'purchase_info': {
                    'purchase_date': datetime.now(),
                    'price': price,
                    'payment_method': 'balance'
                },
                'usage_info': {
                    'first_used': datetime.now(),
                    'total_uses': 1,
                    'associated_sessions': [session_id]
                }
            }
            
            # Store in Firestore purchased_numbers collection
            self.db.collection('purchased_numbers').document(number_id).set(purchase_document)
            
            logger.info(f"Purchased number saved to Firestore: {phone_number} -> {number_id}")
            return number_id
        except Exception as e:
            logger.error(f"Error saving purchased number to Firebase: {e}")
            return f"error_purchase_{user_id}_{int(datetime.now().timestamp())}"
    
    def sync_pending_number_to_firebase(self, pending_id: int, user_id: int, phone_number: str, firebase_session_id: str):
        """Sync pending number to Firebase"""
        if not self.firebase_enabled:
            logger.warning("Firebase not enabled, skipping pending number sync")
            return
        
        try:
            pending_data = {
                'pending_id': pending_id,
                'user_id': user_id,
                'phone_number': phone_number,
                'firebase_session_id': firebase_session_id,
                'submitted_at': datetime.now().isoformat(),
                'status': 'pending'
            }
            
            self.db.collection('pending_numbers').document(str(pending_id)).set(pending_data)
            logger.info(f"Pending number {pending_id} synced to Firebase")
        except Exception as e:
            logger.error(f"Error syncing pending number to Firebase: {e}")
    
    async def _sync_pending_session_to_firebase(self, pending_id: int, user_id: int, phone_number: str, country_code: str, firebase_session_id: str, device_info: dict = None, session_string: str = None):
        """Sync a pending session to Firebase with complete session data"""
        try:
            if not self.firebase_enabled:
                return
            
            # Get pending session details
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM pending_numbers WHERE id = ?
                """, (pending_id,))
                pending_data = cursor.fetchone()
                
                if not pending_data:
                    logger.error(f"Pending session {pending_id} not found")
                    return
                
                # Convert to dict
                columns = [desc[0] for desc in cursor.description]
                pending_dict = dict(zip(columns, pending_data))
                
                # Add additional session data
                session_data = {
                    **pending_dict,
                    'firebase_session_id': firebase_session_id,
                    'device_info': device_info,
                    'session_string_encrypted': self._encrypt_session_string(session_string) if session_string else None,
                    'sync_timestamp': datetime.now().isoformat(),
                    'sync_version': '2.0'
                }
                
                # Remove sensitive data before Firebase sync
                session_data.pop('session_string', None)  # Don't store raw session string
                
                # Sync to Firebase
                doc_ref = self.db.collection('pending_sessions').document(firebase_session_id)
                doc_ref.set(session_data)
                
                logger.info(f"Synced pending session {firebase_session_id} to Firebase")
                
        except Exception as e:
            logger.error(f"Error syncing pending session to Firebase: {e}")
            # Update sync failed flag
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE pending_numbers 
                        SET firebase_sync_failed = 1, firebase_sync_error = ?
                        WHERE id = ?
                    """, (str(e), pending_id))
                    conn.commit()
            except Exception as update_e:
                logger.error(f"Error updating sync failed flag: {update_e}")
    
    def _encrypt_session_string(self, session_string: str) -> str:
        """Encrypt session string for secure storage"""
        try:
            if not session_string:
                return None
            
            # Use the encryption key from environment
            key = self.encryption_key.encode()
            f = Fernet(base64.urlsafe_b64encode(key[:32]))
            encrypted = f.encrypt(session_string.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Error encrypting session string: {e}")
            return None
    
    def _decrypt_session_string(self, encrypted_session_string: str) -> str:
        """Decrypt session string from secure storage"""
        try:
            if not encrypted_session_string:
                return None
            
            # Use the encryption key from environment
            key = self.encryption_key.encode()
            f = Fernet(base64.urlsafe_b64encode(key[:32]))
            encrypted_bytes = base64.urlsafe_b64decode(encrypted_session_string.encode())
            decrypted = f.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Error decrypting session string: {e}")
            return None
    
    def backup_session_before_connect(self, session_path: str, user_id: int, phone_number: str) -> str:
        """Create a backup of session before connecting"""
        try:
            if not os.path.exists(session_path):
                logger.warning(f"Session file not found for backup: {session_path}")
                return None
            
            # Create backup filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f"{os.path.basename(session_path)}.backup_{timestamp}"
            backup_dir = os.path.join(os.path.dirname(session_path), 'backups')
            
            # Create backup directory if it doesn't exist
            os.makedirs(backup_dir, exist_ok=True)
            
            backup_path = os.path.join(backup_dir, backup_filename)
            
            # Copy session file to backup
            shutil.copy2(session_path, backup_path)
            
            # Store backup info in database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE pending_numbers 
                    SET session_backup = ?
                    WHERE user_id = ? AND phone_number = ?
                """, (backup_path, user_id, phone_number))
                conn.commit()
            
            logger.info(f"Session backup created: {backup_path}")
            return backup_path
            
        except Exception as e:
            logger.error(f"Error creating session backup: {e}")
            return None
    
    def init_bot_settings(self):
        """Initialize bot settings table for API ID and hash"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create bot_settings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_id INTEGER NOT NULL,
                    api_hash TEXT NOT NULL,
                    global_2fa_password TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_by INTEGER,
                    is_active BOOLEAN DEFAULT 1
                )
            """)
            
            # Store API ID and hash from environment variables
            api_id = os.getenv('API_ID', '123456')
            api_hash = os.getenv('API_HASH', 'your_api_hash')
            
            cursor.execute("""
                INSERT OR IGNORE INTO bot_settings (api_id, api_hash)
                VALUES (?, ?)
            """, (api_id, api_hash))
            
            conn.commit()
    
    def get_bot_settings(self) -> Optional[Dict]:
        """Get current bot settings (API ID, hash, and 2FA password)"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT api_id, api_hash, global_2fa_password, updated_at, updated_by
                FROM bot_settings 
                WHERE is_active = 1
                ORDER BY updated_at DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_bot_settings(self, api_id: int, api_hash: str, updated_by: int = None) -> bool:
        """Update bot settings (API ID and hash)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Deactivate current settings
                cursor.execute("""
                    UPDATE bot_settings SET is_active = 0
                    WHERE is_active = 1
                """)
                
                # Insert new settings
                cursor.execute("""
                    INSERT INTO bot_settings (api_id, api_hash, updated_by)
                    VALUES (?, ?, ?)
                """, (api_id, api_hash, updated_by))
                
                conn.commit()
                
                # Sync to Firebase
                if self.firebase_enabled:
                    self.sync_bot_settings_to_firebase(api_id, api_hash, updated_by)
                
                return True
        except Exception as e:
            logger.error(f"Error updating bot settings: {e}")
            return False
    
    def update_global_2fa_password(self, password: str, updated_by: int = None) -> bool:
        """Update global 2FA password in bot settings"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Update current active settings
                cursor.execute("""
                    UPDATE bot_settings 
                    SET global_2fa_password = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
                    WHERE is_active = 1
                """, (password, updated_by))
                
                # If no active settings exist, create new one
                if cursor.rowcount == 0:
                    # Get default API credentials
                    api_id = os.getenv('API_ID', '123456')
                    api_hash = os.getenv('API_HASH', 'your_api_hash')
                    
                    cursor.execute("""
                        INSERT INTO bot_settings (api_id, api_hash, global_2fa_password, updated_by)
                        VALUES (?, ?, ?, ?)
                    """, (api_id, api_hash, password, updated_by))
                
                conn.commit()
                
                # Sync to Firebase
                if self.firebase_enabled:
                    self.sync_global_2fa_to_firebase(password, updated_by)
                
                return True
        except Exception as e:
            logger.error(f"Error updating global 2FA password: {e}")
            return False
    
    def get_global_2fa_password(self) -> Optional[str]:
        """Get current global 2FA password"""
        try:
            settings = self.get_bot_settings()
            return settings.get('global_2fa_password') if settings else None
        except Exception as e:
            logger.error(f"Error getting global 2FA password: {e}")
            return None
    
    def sync_global_2fa_to_firebase(self, password: str, updated_by: int = None):
        """Sync global 2FA password to Firebase"""
        if not self.firebase_enabled:
            return
        
        try:
            doc_ref = self.db.collection('bot_settings').document('global_2fa')
            doc_ref.set({
                'password': password,
                'updated_at': datetime.now().isoformat(),
                'updated_by': updated_by
            })
            logger.info("Global 2FA password synced to Firebase")
        except Exception as e:
            logger.error(f"Error syncing global 2FA to Firebase: {e}")
    
    def sync_bot_settings_to_firebase(self, api_id: int, api_hash: str, updated_by: int = None):
        """Sync bot settings to Firebase"""
        if not self.firebase_enabled:
            return
        
        try:
            settings_data = {
                'api_id': api_id,
                'api_hash': api_hash,
                'updated_at': datetime.now().isoformat(),
                'updated_by': updated_by,
                'sync_timestamp': datetime.now().isoformat()
            }
            
            self.db.collection('bot_settings').document('current').set(settings_data)
            logger.info("Bot settings synced to Firebase")
        except Exception as e:
            logger.error(f"Error syncing bot settings to Firebase: {e}")
    
    def sync_all_data_to_firebase(self) -> bool:
        """Manually sync all data to Firebase"""
        if not self.firebase_enabled:
            logger.warning("Firebase not enabled, cannot sync data")
            return False
        
        try:
            logger.info("Starting manual sync to Firebase...")
            
            # Sync users
            self.sync_all_users_to_firebase()
            
            # Sync countries
            self.sync_countries_to_firebase()
            
            # Sync content
            self.sync_content_to_firebase()
            
            # Sync settings
            self.sync_settings_to_firebase()
            
            # Sync bot settings
            bot_settings = self.get_bot_settings()
            if bot_settings:
                self.sync_bot_settings_to_firebase(
                    bot_settings['api_id'], 
                    bot_settings['api_hash'], 
                    bot_settings.get('updated_by')
                )
            
            # Update last sync time
            self.update_setting('last_sync_time', datetime.now().isoformat())
            
            logger.info("Manual sync to Firebase completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error during manual sync to Firebase: {e}")
            return False
    
    def sync_all_users_to_firebase(self):
        """Sync all users to Firebase"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users")
                users = cursor.fetchall()
            
            for user in users:
                user_data = {
                    'user_id': user['user_id'],
                    'username': user['username'],
                    'first_name': user['first_name'],
                    'last_name': user['last_name'],
                    'language': user['language'],
                    'balance': user['balance'],
                    'total_sold': user['total_sold'],
                    'total_earnings': user['total_earnings'],
                    'is_admin': user['is_admin'],
                    'is_banned': user['is_banned'],
                    'created_at': user['created_at'],
                    'last_active': user['last_active'],
                    'sync_timestamp': datetime.now().isoformat()
                }
                
                self.db.collection('users').document(str(user['user_id'])).set(user_data, merge=True)
            
            logger.info(f"Synced {len(users)} users to Firebase")
        except Exception as e:
            logger.error(f"Error syncing users to Firebase: {e}")
    
    def sync_settings_to_firebase(self):
        """Sync all settings to Firebase"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM settings")
                settings = cursor.fetchall()
            
            for setting in settings:
                setting_data = {
                    'key': setting['key'],
                    'value': setting['value'],
                    'updated_at': setting['updated_at'],
                    'updated_by': setting['updated_by'],
                    'sync_timestamp': datetime.now().isoformat()
                }
                
                self.db.collection('settings').document(setting['key']).set(setting_data)
            
            logger.info(f"Synced {len(settings)} settings to Firebase")
        except Exception as e:
            logger.error(f"Error syncing settings to Firebase: {e}")
    
    def auto_sync_to_firebase(self) -> bool:
        """Auto sync data to Firebase if 24 hours have passed"""
        try:
            # Check if auto sync is enabled
            if self.get_setting('auto_sync_enabled') != '1':
                return False
            
            # Check last sync time
            last_sync_str = self.get_setting('last_sync_time')
            if last_sync_str:
                try:
                    last_sync = datetime.fromisoformat(last_sync_str)
                    hours_since_sync = (datetime.now() - last_sync).total_seconds() / 3600
                    sync_interval = float(self.get_setting('sync_interval_hours') or 24)
                    
                    if hours_since_sync < sync_interval:
                        logger.info(f"Auto sync skipped: {hours_since_sync:.1f} hours since last sync")
                        return False
                except ValueError:
                    logger.warning("Invalid last sync time format, proceeding with sync")
            
            # Perform sync
            logger.info("Starting auto sync to Firebase...")
            return self.sync_all_data_to_firebase()
            
        except Exception as e:
            logger.error(f"Error during auto sync: {e}")
            return False
    
    def get_sync_status(self) -> Dict:
        """Get synchronization status information"""
        try:
            last_sync_str = self.get_setting('last_sync_time')
            auto_sync_enabled = self.get_setting('auto_sync_enabled') == '1'
            sync_interval = float(self.get_setting('sync_interval_hours') or 24)
            
            status = {
                'firebase_enabled': self.firebase_enabled,
                'auto_sync_enabled': auto_sync_enabled,
                'sync_interval_hours': sync_interval,
                'last_sync_time': last_sync_str,
                'last_sync_formatted': 'Never' if not last_sync_str else last_sync_str[:19].replace('T', ' ')
            }
            
            if last_sync_str:
                try:
                    last_sync = datetime.fromisoformat(last_sync_str)
                    hours_since_sync = (datetime.now() - last_sync).total_seconds() / 3600
                    status['hours_since_last_sync'] = hours_since_sync
                    status['next_sync_due'] = hours_since_sync >= sync_interval
                except ValueError:
                    status['hours_since_last_sync'] = None
                    status['next_sync_due'] = True
            else:
                status['hours_since_last_sync'] = None
                status['next_sync_due'] = True
            
            return status
        except Exception as e:
            logger.error(f"Error getting sync status: {e}")
            return {
                'firebase_enabled': False,
                'auto_sync_enabled': False,
                'sync_interval_hours': 24,
                'last_sync_time': None,
                'last_sync_formatted': 'Error',
                'hours_since_last_sync': None,
                'next_sync_due': False
            }
    
    def add_user_violation(self, user_id: int, violation_type: str, violation_reason: str, 
                          phone_number: str = None, admin_notes: str = None) -> bool:
        """Add a violation record for a user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_violations (user_id, violation_type, violation_reason, phone_number, admin_notes)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, violation_type, violation_reason, phone_number, admin_notes))
                conn.commit()
                
                # Sync to Firebase
                if self.firebase_enabled:
                    self.sync_violation_to_firebase(cursor.lastrowid, user_id, violation_type, violation_reason, phone_number)
                
                return True
        except Exception as e:
            logger.error(f"Error adding user violation: {e}")
            return False
    
    def get_user_violations(self, user_id: int) -> List[Dict]:
        """Get all violations for a user"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM user_violations 
                WHERE user_id = ? 
                ORDER BY created_at DESC
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_user_violation_count(self, user_id: int, violation_type: str = None) -> int:
        """Get count of violations for a user"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if violation_type:
                cursor.execute("""
                    SELECT COUNT(*) FROM user_violations 
                    WHERE user_id = ? AND violation_type = ?
                """, (user_id, violation_type))
            else:
                cursor.execute("""
                    SELECT COUNT(*) FROM user_violations 
                    WHERE user_id = ?
                """, (user_id,))
            return cursor.fetchone()[0]
    
    def sync_violation_to_firebase(self, violation_id: int, user_id: int, violation_type: str, 
                                  violation_reason: str, phone_number: str = None):
        """Sync violation to Firebase"""
        if not self.firebase_enabled:
            return
        
        try:
            violation_data = {
                'violation_id': violation_id,
                'user_id': user_id,
                'violation_type': violation_type,
                'violation_reason': violation_reason,
                'phone_number': phone_number,
                'created_at': datetime.now().isoformat()
            }
            
            self.db.collection('user_violations').document(str(violation_id)).set(violation_data)
            logger.info(f"Violation {violation_id} synced to Firebase")
        except Exception as e:
            logger.error(f"Error syncing violation to Firebase: {e}")
    
    def move_session_to_rejected(self, phone: str, user_id: int, rejection_reason: str) -> bool:
        """Move a session from pending to rejected status"""
        try:
            # Update pending numbers table
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE pending_numbers 
                    SET status = 'rejected', reject_reason = ?
                    WHERE phone_number = ? AND user_id = ? AND status = 'pending'
                """, (rejection_reason, phone, user_id))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"Session {phone} moved to rejected status: {rejection_reason}")
                    return True
                else:
                    logger.warning(f"No pending session found for {phone} to reject")
                    return False
        except Exception as e:
            logger.error(f"Error moving session to rejected: {e}")
            return False
    
    def add_notification(self, user_id: int, title: str, message: str, notification_type: str = 'general') -> bool:
        """Add a notification for a user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO notifications (user_id, title, message, notification_type)
                    VALUES (?, ?, ?, ?)
                """, (user_id, title, message, notification_type))
                conn.commit()
                
                # Sync to Firebase
                if self.firebase_enabled:
                    try:
                        notification_data = {
                            'user_id': user_id,
                            'title': title,
                            'message': message,
                            'notification_type': notification_type,
                            'created_at': datetime.now().isoformat(),
                            'is_sent': False
                        }
                        self.db.collection('notifications').add(notification_data)
                    except Exception as e:
                        logger.error(f"Error syncing notification to Firebase: {e}")
                
                return True
        except Exception as e:
            logger.error(f"Error adding notification: {e}")
            return False
    
    def get_pending_notifications(self) -> List[Dict]:
        """Get all pending notifications"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT n.*, u.language, u.first_name, u.username
                    FROM notifications n
                    JOIN users u ON n.user_id = u.user_id
                    WHERE n.is_sent = 0
                    ORDER BY n.created_at ASC
                """)
                
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting pending notifications: {e}")
            return []
    
    def mark_notification_sent(self, notification_id: int) -> bool:
        """Mark a notification as sent"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE notifications SET is_sent = 1 WHERE id = ?
                """, (notification_id,))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error marking notification as sent: {e}")
            return False
    
    def broadcast_notification(self, title: str, message: str, notification_type: str = 'broadcast') -> bool:
        """Send notification to all users"""
        try:
            # Get all active users
            users = self.get_all_active_users()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Add notifications for all users
                for user in users:
                    cursor.execute("""
                        INSERT INTO notifications (user_id, title, message, notification_type)
                        VALUES (?, ?, ?, ?)
                    """, (user['user_id'], title, message, notification_type))
                
                conn.commit()
                
                # Sync to Firebase
                if self.firebase_enabled:
                    try:
                        batch = self.db.batch()
                        for user in users:
                            notification_ref = self.db.collection('notifications').document()
                            notification_data = {
                                'user_id': user['user_id'],
                                'title': title,
                                'message': message,
                                'notification_type': notification_type,
                                'created_at': datetime.now().isoformat(),
                                'is_sent': False
                            }
                            batch.set(notification_ref, notification_data)
                        batch.commit()
                    except Exception as e:
                        logger.error(f"Error syncing broadcast to Firebase: {e}")
                
                return True
        except Exception as e:
            logger.error(f"Error broadcasting notification: {e}")
            return False
    
    def get_all_active_users(self) -> List[Dict]:
        """Get all active (non-banned) users"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT user_id, username, first_name, language
                    FROM users 
                    WHERE is_banned = 0
                    ORDER BY user_id
                """)
                
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting active users: {e}")
            return []

    def get_all_users(self) -> List[Dict]:
        """Get all users"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT user_id, username, first_name, last_name, language, 
                           balance, total_sold, created_at, last_active, 
                           is_banned, is_admin, phone_number, email, 
                           verification_status, referral_code, referred_by, 
                           total_earnings
                    FROM users 
                    ORDER BY user_id
                """)
                
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            return []
    
    def check_country_limit_reached(self, country_code: str) -> bool:
        """Check if a country has reached its target limit"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get country target
                cursor.execute("SELECT target_quantity, country_name FROM countries WHERE country_code = ?", (country_code,))
                country_data = cursor.fetchone()
                
                if not country_data:
                    return False
                
                target_quantity, country_name = country_data
                
                # Count approved numbers for this country
                cursor.execute("SELECT COUNT(*) FROM approved_numbers WHERE country_code = ?", (country_code,))
                current_count = cursor.fetchone()[0]
                
                return current_count >= target_quantity
        except Exception as e:
            logger.error(f"Error checking country limit: {e}")
            return False
    
    def update_country_quantity(self, country_code: str) -> Dict:
        """Update current quantity for a country and check if limit reached"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Count approved numbers for this country
                cursor.execute("SELECT COUNT(*) FROM approved_numbers WHERE country_code = ?", (country_code,))
                current_count = cursor.fetchone()[0]
                
                # Update current quantity
                cursor.execute("""
                    UPDATE countries 
                    SET current_quantity = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE country_code = ?
                """, (current_count, country_code))
                
                # Get country info
                cursor.execute("SELECT country_name, target_quantity FROM countries WHERE country_code = ?", (country_code,))
                country_data = cursor.fetchone()
                
                if country_data:
                    country_name, target_quantity = country_data
                    limit_reached = current_count >= target_quantity
                    
                    conn.commit()
                    
                    return {
                        'success': True,
                        'country_code': country_code,
                        'country_name': country_name,
                        'current_count': current_count,
                        'target_quantity': target_quantity,
                        'limit_reached': limit_reached
                    }
                else:
                    return {'success': False, 'error': 'Country not found'}
                    
        except Exception as e:
            logger.error(f"Error updating country quantity: {e}")
            return {'success': False, 'error': str(e)}

    def get_live_support_message(self) -> Optional[str]:
        """Get the current live support message"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM settings WHERE key = ?", ('live_support_message',))
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting live support message: {e}")
            return None
    
    def set_live_support_message(self, message: str) -> bool:
        """Set the live support message"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO settings (key, value, updated_at) 
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, ('live_support_message', message))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Error setting live support message: {e}")
            return False
    
    def add_user_balance(self, user_id: int, amount: float) -> bool:
        """Add amount to user's balance"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE users SET balance = COALESCE(balance, 0) + ? 
                    WHERE user_id = ?
                """, (amount, user_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error adding user balance: {e}")
            return False
    
    def get_users_by_language(self, language: str) -> List[Dict]:
        """Get all users with a specific language"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT user_id, username, first_name, language 
                    FROM users 
                    WHERE language = ? AND is_banned = 0
                """, (language,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting users by language: {e}")
            return []
    
    def get_sessions_by_country(self, country_code: str) -> List[Dict]:
        """Get all sessions for a specific country"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # For country code like 'SA', we need to find the corresponding phone prefix
                # We'll search by country_code field and also by phone number patterns
                cursor.execute("""
                    SELECT p.*, u.username, u.first_name, u.last_name 
                    FROM pending_numbers p
                    JOIN users u ON p.user_id = u.user_id
                    WHERE p.country_code = ? OR p.phone_number LIKE ? OR p.session_path LIKE ? OR p.session_path LIKE ?
                    ORDER BY p.submitted_at DESC
                """, (country_code, f"%{country_code}%", f"+{country_code}_%", f"%{country_code}_%"))
                
                pending_sessions = [dict(row) for row in cursor.fetchall()]
                
                cursor.execute("""
                    SELECT a.*, u.username, u.first_name, u.last_name 
                    FROM approved_numbers a
                    JOIN users u ON a.seller_id = u.user_id
                    WHERE a.country_code = ? OR a.phone_number LIKE ? OR a.session_path LIKE ? OR a.session_path LIKE ?
                    ORDER BY a.listed_at DESC
                """, (country_code, f"%{country_code}%", f"+{country_code}_%", f"%{country_code}_%"))
                
                approved_sessions = [dict(row) for row in cursor.fetchall()]
                
                return {
                    'pending': pending_sessions,
                    'approved': approved_sessions,
                    'total': len(pending_sessions) + len(approved_sessions)
                }
        except Exception as e:
            logger.error(f"Error getting sessions by country: {e}")
            return {'pending': [], 'approved': [], 'total': 0}
    
    def get_country_session_count(self, country_code: str) -> int:
        """Get total session count for a country"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Count pending sessions - look for both +prefix_ and prefix_ formats
                cursor.execute("""
                    SELECT COUNT(*) FROM pending_numbers 
                    WHERE country_code = ? OR phone_number LIKE ? OR session_path LIKE ? OR session_path LIKE ?
                """, (country_code, f"%{country_code}%", f"+{country_code}_%", f"%{country_code}_%"))
                pending_count = cursor.fetchone()[0]
                
                # Count approved sessions - look for both +prefix_ and prefix_ formats
                cursor.execute("""
                    SELECT COUNT(*) FROM approved_numbers 
                    WHERE country_code = ? OR phone_number LIKE ? OR session_path LIKE ? OR session_path LIKE ?
                """, (country_code, f"%{country_code}%", f"+{country_code}_%", f"%{country_code}_%"))
                approved_count = cursor.fetchone()[0]
                
                return pending_count + approved_count
        except Exception as e:
            logger.error(f"Error getting country session count: {e}")
            return 0
    
    def get_approved_sessions_count_by_country(self, country_code: str) -> int:
        """Get approved session count for a specific country"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Count approved sessions - look for both +prefix_ and prefix_ formats
                cursor.execute("""
                    SELECT COUNT(*) FROM approved_numbers 
                    WHERE country_code = ? OR phone_number LIKE ? OR session_path LIKE ? OR session_path LIKE ?
                """, (country_code, f"%{country_code}%", f"+{country_code}_%", f"%{country_code}_%"))
                approved_count = cursor.fetchone()[0]
                
                return approved_count
                
        except Exception as e:
            logger.error(f"Error getting approved sessions count by country: {e}")
            return 0
    
    def filter_sessions_by_country_prefix(self, country_prefix: str) -> List[Dict]:
        """Filter sessions by country prefix in session filename (e.g., '966' for Saudi Arabia)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Clean the prefix and prepare search patterns
                clean_prefix = country_prefix.replace('+', '')
                
                # Search in pending numbers - look for session files with +prefix_ format
                cursor.execute("""
                    SELECT p.*, u.username, u.first_name, u.last_name,
                           'pending' as session_type
                    FROM pending_numbers p
                    JOIN users u ON p.user_id = u.user_id
                    WHERE p.session_path LIKE ? OR p.session_path LIKE ? OR p.phone_number LIKE ?
                    ORDER BY p.submitted_at DESC
                """, (f"+{clean_prefix}_%", f"{clean_prefix}_%", f"%{clean_prefix}%"))
                
                pending_sessions = [dict(row) for row in cursor.fetchall()]
                
                # Search in approved numbers - look for session files with +prefix_ format
                cursor.execute("""
                    SELECT a.*, u.username, u.first_name, u.last_name,
                           'approved' as session_type
                    FROM approved_numbers a
                    JOIN users u ON a.seller_id = u.user_id
                    WHERE a.session_path LIKE ? OR a.session_path LIKE ? OR a.phone_number LIKE ?
                    ORDER BY a.listed_at DESC
                """, (f"+{clean_prefix}_%", f"{clean_prefix}_%", f"%{clean_prefix}%"))
                
                approved_sessions = [dict(row) for row in cursor.fetchall()]
                
                # Combine both lists
                all_sessions = pending_sessions + approved_sessions
                
                return all_sessions
        except Exception as e:
            logger.error(f"Error filtering sessions by country prefix: {e}")
            return []
    
    def get_sessions_by_phone_prefix(self, phone_prefix: str) -> List[Dict]:
        """Get sessions by phone prefix (e.g., '+966' or '966')"""
        try:
            # Clean the prefix
            clean_prefix = phone_prefix.replace('+', '').replace(' ', '')
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Search in pending numbers - look for both +prefix_ and prefix_ formats
                cursor.execute("""
                    SELECT p.*, u.username, u.first_name, u.last_name,
                           'pending' as session_type
                    FROM pending_numbers p
                    JOIN users u ON p.user_id = u.user_id
                    WHERE p.phone_number LIKE ? OR p.session_path LIKE ? OR p.session_path LIKE ?
                    ORDER BY p.submitted_at DESC
                """, (f"%{clean_prefix}%", f"+{clean_prefix}_%", f"{clean_prefix}_%"))
                
                pending_sessions = [dict(row) for row in cursor.fetchall()]
                
                # Search in approved numbers - look for both +prefix_ and prefix_ formats
                cursor.execute("""
                    SELECT a.*, u.username, u.first_name, u.last_name,
                           'approved' as session_type
                    FROM approved_numbers a
                    JOIN users u ON a.seller_id = u.user_id
                    WHERE a.phone_number LIKE ? OR a.session_path LIKE ? OR a.session_path LIKE ?
                    ORDER BY a.listed_at DESC
                """, (f"%{clean_prefix}%", f"+{clean_prefix}_%", f"{clean_prefix}_%"))
                
                approved_sessions = [dict(row) for row in cursor.fetchall()]
                
                return {
                    'pending': pending_sessions,
                    'approved': approved_sessions,
                    'total': len(pending_sessions) + len(approved_sessions)
                }
        except Exception as e:
            logger.error(f"Error getting sessions by phone prefix: {e}")
            return {'pending': [], 'approved': [], 'total': 0}
    
    def get_session_statistics(self) -> Dict:
        """Get session statistics for admin panel"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get counts from different tables
                cursor.execute("SELECT COUNT(*) FROM pending_numbers")
                pending_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM approved_numbers")
                approved_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM users")
                users_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM countries WHERE is_active = 1")
                active_countries = cursor.fetchone()[0]
                
                return {
                    'pending_sessions': pending_count,
                    'approved_sessions': approved_count,
                    'total_users': users_count,
                    'active_countries': active_countries
                }
        except Exception as e:
            logger.error(f"Error getting session statistics: {e}")
            return {
                'pending_sessions': 0,
                'approved_sessions': 0,
                'total_users': 0,
                'active_countries': 0
            }
    
    def add_pending_session(self, user_id: int, phone_number: str, country_code: str, has_email: bool = False, session_file: str = None, device_info: dict = None, session_string: str = None) -> bool:
        """Add a pending session for account sale with complete session data"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Generate Firebase session ID
                firebase_session_id = f"session_{user_id}_{int(datetime.now().timestamp())}"
                
                # Convert device_info to JSON string
                device_info_json = json.dumps(device_info) if device_info else None
                
                cursor.execute("""
                    INSERT INTO pending_numbers (
                        user_id, phone_number, country_code, has_email, 
                        session_path, firebase_session_id, device_info, 
                        submitted_at, status, session_string
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, phone_number, country_code, has_email,
                    session_file, firebase_session_id, device_info_json,
                    datetime.now().isoformat(), 'pending', session_string
                ))
                
                pending_id = cursor.lastrowid
                conn.commit()
                
                # Sync to Firebase if enabled
                if self.firebase_enabled:
                    asyncio.create_task(self._sync_pending_session_to_firebase(
                        pending_id, user_id, phone_number, country_code, 
                        firebase_session_id, device_info, session_string
                    ))
                
                logger.info(f"Added pending session for user {user_id} with Firebase ID {firebase_session_id}")
                return True
        except Exception as e:
            logger.error(f"Error adding pending session: {e}")
            return False
    
    def add_rejected_session(self, user_id: int, reason: str, session_path: str, session_info: dict = None) -> bool:
        """Add a rejected session record"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Store session info as JSON
                session_info_json = json.dumps(session_info) if session_info else None
                
                cursor.execute("""
                    INSERT INTO rejected_sessions (user_id, reason, session_path, session_info, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (user_id, reason, session_path, session_info_json, datetime.now().isoformat()))
                conn.commit()
                
                # If Firebase is enabled, also sync to Firebase
                if self.firebase_enabled and session_info:
                    try:
                        firebase_id = f"rejected_{user_id}_{int(datetime.now().timestamp())}"
                        rejected_data = {
                            'user_id': user_id,
                            'reason': reason,
                            'session_path': session_path,
                            'session_info': session_info,
                            'created_at': datetime.now().isoformat(),
                            'firebase_id': firebase_id
                        }
                        
                        self.db.collection('rejected_sessions').document(firebase_id).set(rejected_data)
                        logger.info(f"Synced rejected session {firebase_id} to Firebase")
                    except Exception as firebase_e:
                        logger.error(f"Error syncing rejected session to Firebase: {firebase_e}")
                
                logger.info(f"Added rejected session for user {user_id}: {reason}")
                return True
        except Exception as e:
            logger.error(f"Error adding rejected session: {e}")
            return False
    
    def add_approved_session(self, user_id: int, phone_number: str, country_code: str, session_path: str, price: float, session_info: dict = None, session_string: str = None) -> bool:
        """Add an approved session for sale"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Generate Firebase session ID
                firebase_session_id = f"approved_{user_id}_{int(datetime.now().timestamp())}"
                
                # Convert session info to JSON
                device_info_json = json.dumps(session_info.get('device_info', {})) if session_info else None
                
                # Encrypt session string
                encrypted_session = self._encrypt_session_string(session_string) if session_string else None
                
                cursor.execute("""
                    INSERT INTO approved_numbers (
                        seller_id, phone_number, country_code, session_path, 
                        firebase_session_id, session_string, device_info, price, 
                        listed_at, quality_score, verification_level
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_id, phone_number, country_code, session_path,
                    firebase_session_id, encrypted_session, device_info_json, price,
                    datetime.now().isoformat(), 
                    session_info.get('quality_score', 0) if session_info else 0,
                    session_info.get('verification_level', 'basic') if session_info else 'basic'
                ))
                
                approved_id = cursor.lastrowid
                conn.commit()
                
                # If Firebase is enabled, sync to Firebase
                if self.firebase_enabled:
                    try:
                        approved_data = {
                            'approved_id': approved_id,
                            'seller_id': user_id,
                            'phone_number': phone_number,
                            'country_code': country_code,
                            'session_path': session_path,
                            'firebase_session_id': firebase_session_id,
                            'device_info': session_info.get('device_info', {}) if session_info else {},
                            'price': price,
                            'listed_at': datetime.now().isoformat(),
                            'quality_score': session_info.get('quality_score', 0) if session_info else 0,
                            'verification_level': session_info.get('verification_level', 'basic') if session_info else 'basic',
                            'sync_version': '2.0'
                        }
                        
                        # Don't store raw session string in Firebase
                        self.db.collection('approved_sessions').document(firebase_session_id).set(approved_data)
                        logger.info(f"Synced approved session {firebase_session_id} to Firebase")
                    except Exception as firebase_e:
                        logger.error(f"Error syncing approved session to Firebase: {firebase_e}")
                
                logger.info(f"Added approved session for user {user_id} with price ${price}")
                return True
        except Exception as e:
            logger.error(f"Error adding approved session: {e}")
            return False
    
    def create_backup(self) -> bool:
        """Create a backup of the database"""
        try:
            import shutil
            from datetime import datetime
            
            backup_path = f"{self.db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(self.db_path, backup_path)
            logger.info(f"Database backup created: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Error creating database backup: {e}")
            return False
    
    def repair_database(self) -> bool:
        """Attempt to repair database corruption"""
        try:
            import subprocess
            import os
            
            # Check if the database file exists
            if not os.path.exists(self.db_path):
                logger.error(f"Database file not found: {self.db_path}")
                return False
            
            # Create a backup before attempting repair
            self.create_backup()
            
            # Try SQLite integrity check first
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA integrity_check")
                    result = cursor.fetchone()
                    if result[0] == 'ok':
                        logger.info("Database integrity check passed")
                        return True
                    else:
                        logger.warning(f"Database integrity check failed: {result[0]}")
            except Exception as integrity_e:
                logger.error(f"Database integrity check failed: {integrity_e}")
            
            # Try to repair using vacuum
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("VACUUM")
                    conn.commit()
                    logger.info("Database vacuum completed successfully")
                    return True
            except Exception as vacuum_e:
                logger.error(f"Database vacuum failed: {vacuum_e}")
            
            # If all else fails, try to recreate from backup
            backup_files = [f for f in os.listdir(os.path.dirname(self.db_path)) if f.startswith(f"{os.path.basename(self.db_path)}.backup_")]
            if backup_files:
                latest_backup = max(backup_files, key=lambda x: os.path.getmtime(os.path.join(os.path.dirname(self.db_path), x)))
                backup_path = os.path.join(os.path.dirname(self.db_path), latest_backup)
                
                try:
                    shutil.copy2(backup_path, self.db_path)
                    logger.info(f"Database restored from backup: {backup_path}")
                    return True
                except Exception as restore_e:
                    logger.error(f"Failed to restore from backup: {restore_e}")
            
            return False
            
        except Exception as e:
            logger.error(f"Database repair failed: {e}")
            return False
    
    def close(self):
        """Close database connections"""
        try:
            # SQLite connections are automatically closed with context managers
            # This method is here for interface compatibility
            logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")
    
    def check_database_health(self) -> bool:
        """Check if database is healthy and accessible"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
                result = cursor.fetchone()
                return result is not None
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

# Global database instance
db = Database()