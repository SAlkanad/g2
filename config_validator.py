"""
Configuration validator for Account Market Bot
"""
import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

class ConfigValidator:
    """Validates bot configuration and environment"""
    
    def __init__(self, database=None):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.database = database
        
        # Initialize config service if database is provided
        if database:
            try:
                from config_service import ConfigService
                self.config_service = ConfigService(database)
            except ImportError:
                self.config_service = None
        else:
            self.config_service = None
    
    def validate_environment(self) -> bool:
        """Validate environment variables"""
        if self.config_service:
            # Use config service for validation
            is_valid, config_errors = self.config_service.validate_required_config()
            if not is_valid:
                self.errors.extend(config_errors)
            return is_valid
        else:
            # Fallback to old validation method
            required_vars = {
                'BOT_TOKEN': 'Telegram bot token from @BotFather',
                'API_ID': 'Telegram API ID from my.telegram.org',
                'API_HASH': 'Telegram API hash from my.telegram.org',
                'ADMIN_IDS': 'Comma-separated list of admin user IDs'
            }
            
            for var, description in required_vars.items():
                value = os.getenv(var)
                if not value:
                    self.errors.append(f"Missing environment variable: {var} ({description})")
                elif var == 'BOT_TOKEN' and value == 'YOUR_BOT_TOKEN':
                    self.errors.append(f"Please set a valid {var}")
                elif var == 'API_ID' and value in ['123456', '12345']:
                    self.errors.append(f"Please set a valid {var}")
                elif var == 'API_HASH' and value in ['your_api_hash', 'default_hash']:
                    self.errors.append(f"Please set a valid {var}")
            
            return len(self.errors) == 0
    
    def validate_firebase_config(self) -> bool:
        """Validate Firebase configuration"""
        service_key_path = Path('serviceAccountKey.json')
        
        if not service_key_path.exists():
            self.errors.append("Firebase service account key file not found: serviceAccountKey.json")
            return False
        
        try:
            with open(service_key_path, 'r') as f:
                key_data = json.load(f)
            
            required_fields = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
            for field in required_fields:
                if field not in key_data:
                    self.errors.append(f"Missing field in Firebase service key: {field}")
            
            if key_data.get('type') != 'service_account':
                self.errors.append("Firebase service key must be for a service account")
            
        except json.JSONDecodeError:
            self.errors.append("Invalid JSON in Firebase service account key")
        except Exception as e:
            self.errors.append(f"Error reading Firebase service key: {e}")
        
        return len(self.errors) == 0
    
    def validate_directories(self) -> bool:
        """Validate required directories exist"""
        try:
            from sessions.session_paths import get_session_paths, validate_all_session_directories
            
            # Use centralized session paths
            session_paths = get_session_paths()
            validation_results = validate_all_session_directories()
            
            # Check validation results
            for directory, is_valid in validation_results.items():
                if not is_valid:
                    self.warnings.append(f"Directory will be created/fixed: {directory}")
            
            # Create directories if needed
            if not session_paths.create_directories():
                self.errors.append("Failed to create required session directories")
                return False
            
            return True
            
        except ImportError:
            # Fallback to old validation method
            required_dirs = [
                'session_files',
                'session_files/pending'
            ]
            
            for directory in required_dirs:
                dir_path = Path(directory)
                if not dir_path.exists():
                    self.warnings.append(f"Directory will be created: {directory}")
                    dir_path.mkdir(parents=True, exist_ok=True)
            
            return True
    
    def validate_dependencies(self) -> bool:
        """Validate Python dependencies"""
        required_packages = [
            ('aiogram', 'aiogram'),
            ('python-dotenv', 'dotenv'),
            ('telethon', 'telethon'),
            ('aiofiles', 'aiofiles'),
            ('cryptography', 'cryptography'),
            ('firebase-admin', 'firebase_admin')
        ]
        
        missing_packages = []
        for package_name, import_name in required_packages:
            try:
                __import__(import_name)
            except ImportError:
                missing_packages.append(package_name)
        
        if missing_packages:
            self.errors.append(f"Missing packages: {', '.join(missing_packages)}")
            self.errors.append("Run: pip install -r requirements.txt")
        
        return len(missing_packages) == 0
    
    def validate_permissions(self) -> bool:
        """Validate file permissions"""
        current_dir = Path('.')
        
        # Check if we can write to current directory
        try:
            test_file = current_dir / 'test_write.tmp'
            test_file.write_text('test')
            test_file.unlink()
        except Exception as e:
            self.errors.append(f"Cannot write to current directory: {e}")
            return False
        
        # Check session directory permissions
        session_dir = Path('session_files')
        if session_dir.exists():
            try:
                test_file = session_dir / 'test_write.tmp'
                test_file.write_text('test')
                test_file.unlink()
            except Exception as e:
                self.errors.append(f"Cannot write to session directory: {e}")
                return False
        
        return True
    
    def validate_all(self) -> bool:
        """Run all validations"""
        self.errors.clear()
        self.warnings.clear()
        
        # Run all validations
        validations = [
            self.validate_environment(),
            self.validate_firebase_config(),
            self.validate_directories(),
            self.validate_dependencies(),
            self.validate_permissions()
        ]
        
        success = all(validations)
        return success
    
    def get_validation_results(self) -> Tuple[bool, List[str], List[str]]:
        """Get validation results"""
        success = self.validate_all()
        return success, self.errors, self.warnings
    
    def print_results(self):
        """Print validation results"""
        success, errors, warnings = self.get_validation_results()
        
        if success:
            print("✅ Configuration validation passed!")
            if warnings:
                print("\nWarnings:")
                for warning in warnings:
                    print(f"  ⚠️  {warning}")
        else:
            print("❌ Configuration validation failed!")
            print("\nErrors:")
            for error in errors:
                print(f"  ❌ {error}")
            
            if warnings:
                print("\nWarnings:")
                for warning in warnings:
                    print(f"  ⚠️  {warning}")
        
        return success

if __name__ == "__main__":
    validator = ConfigValidator()
    success = validator.print_results()
    
    if not success:
        print("\nPlease fix the errors above and try again.")
        exit(1)
    else:
        print("\n🚀 Ready to start the bot!")