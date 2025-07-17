"""
Security Configuration and Validation
Centralizes security settings and provides validation for production deployment
"""

import os
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class SecurityValidator:
    """Validates security configuration for production deployment"""
    
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.security_issues: List[str] = []
    
    def validate_ssl_configuration(self) -> bool:
        """Validate SSL configuration for security"""
        development_mode = os.getenv('DEVELOPMENT_MODE', 'false').lower() == 'true'
        ssl_verify = os.getenv('SSL_VERIFY', 'true').lower() == 'true'
        suppress_ssl_warnings = os.getenv('SUPPRESS_SSL_WARNINGS', 'false').lower() == 'true'
        
        # Critical security check
        if not development_mode and not ssl_verify:
            self.security_issues.append(
                "CRITICAL: SSL verification is disabled in production mode! "
                "This makes the application vulnerable to MITM attacks."
            )
            return False
        
        # Warning checks
        if development_mode:
            self.warnings.append("Running in development mode - SSL verification may be disabled")
        
        if suppress_ssl_warnings and not development_mode:
            self.warnings.append("SSL warnings are suppressed in production mode")
        
        return True
    
    def validate_api_credentials(self) -> bool:
        """Validate API credentials are not using defaults"""
        api_id = os.getenv('API_ID', '')
        api_hash = os.getenv('API_HASH', '')
        bot_token = os.getenv('BOT_TOKEN', '')
        
        # Check for hardcoded/default values
        if api_id in ['123456', '12345', 'Not set', '']:
            self.security_issues.append("API_ID is not properly configured or using default value")
            return False
        
        if api_hash in ['your_api_hash', 'default_hash', 'Not set', '']:
            self.security_issues.append("API_HASH is not properly configured or using default value")
            return False
        
        if bot_token in ['YOUR_BOT_TOKEN', 'Not set', '']:
            self.security_issues.append("BOT_TOKEN is not properly configured or using default value")
            return False
        
        return True
    
    def validate_admin_configuration(self) -> bool:
        """Validate admin configuration security"""
        admin_ids = os.getenv('ADMIN_IDS', '')
        
        if not admin_ids or admin_ids in ['123456789', 'YOUR_ADMIN_ID']:
            self.security_issues.append("ADMIN_IDS is not properly configured or using default value")
            return False
        
        # Check for reasonable admin ID format
        try:
            admin_list = [int(x.strip()) for x in admin_ids.split(',') if x.strip()]
            for admin_id in admin_list:
                if admin_id < 1000000:  # Telegram user IDs are typically larger
                    self.warnings.append(f"Admin ID {admin_id} seems unusually small for a Telegram user ID")
        except ValueError:
            self.errors.append("ADMIN_IDS contains invalid numeric values")
            return False
        
        return True
    
    def validate_database_security(self) -> bool:
        """Validate database security configuration"""
        # Check if Firebase service account key exists and is not default
        firebase_key_path = 'serviceAccountKey.json'
        
        if not os.path.exists(firebase_key_path):
            self.errors.append("Firebase service account key file not found")
            return False
        
        try:
            import json
            with open(firebase_key_path, 'r') as f:
                key_data = json.load(f)
            
            # Check for placeholder values
            if key_data.get('project_id') in ['your-project-id', 'test-project', '']:
                self.security_issues.append("Firebase project_id appears to be a placeholder value")
                return False
            
            if key_data.get('private_key', '').startswith('-----BEGIN PRIVATE KEY-----'):
                # This is good - has a real private key
                pass
            else:
                self.security_issues.append("Firebase private key appears to be invalid or placeholder")
                return False
                
        except (json.JSONDecodeError, Exception) as e:
            self.errors.append(f"Error validating Firebase configuration: {e}")
            return False
        
        return True
    
    def validate_production_readiness(self) -> bool:
        """Validate if the application is ready for production deployment"""
        development_mode = os.getenv('DEVELOPMENT_MODE', 'false').lower() == 'true'
        
        if development_mode:
            self.warnings.append("Application is running in development mode")
            return True  # Development mode is not a security issue
        
        # Production-specific checks
        debug_mode = os.getenv('DEBUG', 'false').lower() == 'true'
        if debug_mode:
            self.warnings.append("Debug mode is enabled in production")
        
        return True
    
    def validate_all(self) -> Tuple[bool, List[str], List[str], List[str]]:
        """Run all security validations"""
        self.errors.clear()
        self.warnings.clear()
        self.security_issues.clear()
        
        validations = [
            self.validate_ssl_configuration(),
            self.validate_api_credentials(),
            self.validate_admin_configuration(),
            self.validate_database_security(),
            self.validate_production_readiness()
        ]
        
        success = all(validations) and len(self.security_issues) == 0
        return success, self.errors, self.warnings, self.security_issues
    
    def print_security_report(self) -> bool:
        """Print comprehensive security validation report"""
        success, errors, warnings, security_issues = self.validate_all()
        
        print("🔒 Security Configuration Report")
        print("=" * 50)
        
        if success and not security_issues:
            print("✅ Security validation passed!")
        else:
            print("❌ Security validation failed!")
        
        if security_issues:
            print("\n🚨 CRITICAL SECURITY ISSUES:")
            for issue in security_issues:
                print(f"  🚨 {issue}")
        
        if errors:
            print("\n❌ ERRORS:")
            for error in errors:
                print(f"  ❌ {error}")
        
        if warnings:
            print("\n⚠️  WARNINGS:")
            for warning in warnings:
                print(f"  ⚠️  {warning}")
        
        if success and not security_issues:
            print("\n🚀 Application is secure and ready for deployment!")
        else:
            print("\n🛑 Please fix the security issues above before deploying to production!")
        
        return success and len(security_issues) == 0


def validate_startup_security():
    """Validate security configuration at application startup"""
    validator = SecurityValidator()
    return validator.validate_all()


if __name__ == "__main__":
    validator = SecurityValidator()
    success = validator.print_security_report()
    
    if not success:
        print("\nPlease fix the security issues above before running the application.")
        exit(1)
    else:
        print("\n✅ Security validation completed successfully!")