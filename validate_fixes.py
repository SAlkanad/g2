#!/usr/bin/env python3
"""
Validation script to test the implemented fixes
"""

import os
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_security_config():
    """Test security configuration validation"""
    print("🔒 Testing security configuration...")
    try:
        from network.security_config import SecurityValidator
        validator = SecurityValidator()
        success, errors, warnings, security_issues = validator.validate_all()
        
        print(f"  Security validation: {'✅ PASSED' if success and not security_issues else '❌ FAILED'}")
        if security_issues:
            print(f"  Security issues: {len(security_issues)}")
        if errors:
            print(f"  Errors: {len(errors)}")
        if warnings:
            print(f"  Warnings: {len(warnings)}")
        
        return success and not security_issues
    except Exception as e:
        print(f"  ❌ Error testing security config: {e}")
        return False

def test_session_paths():
    """Test session paths centralization"""
    print("📁 Testing session paths...")
    try:
        from sessions.session_paths import SessionPaths, get_session_paths
        
        # Test instance creation
        paths = SessionPaths()
        all_paths = paths.get_all_paths()
        
        print(f"  Session paths created: ✅")
        print(f"  Paths count: {len(all_paths)}")
        
        # Test global instance
        global_paths = get_session_paths()
        print(f"  Global instance: ✅")
        
        # Test directory creation
        success = paths.create_directories()
        print(f"  Directory creation: {'✅' if success else '❌'}")
        
        return success
    except Exception as e:
        print(f"  ❌ Error testing session paths: {e}")
        return False

def test_config_service():
    """Test config service centralization"""
    print("⚙️ Testing config service...")
    try:
        # Try to import without database (should fail gracefully)
        from config_service import ConfigService
        print(f"  Config service import: ✅")
        
        # Note: We can't fully test without a database instance
        return True
    except Exception as e:
        print(f"  ❌ Error testing config service: {e}")
        return False

def test_auth_service():
    """Test auth service centralization"""
    print("🔐 Testing auth service...")
    try:
        from admin.auth_service import AuthService
        print(f"  Auth service import: ✅")
        
        # Note: We can't fully test without a database instance
        return True
    except Exception as e:
        print(f"  ❌ Error testing auth service: {e}")
        return False

def test_telegram_security():
    """Test telegram security manager"""
    print("📡 Testing telegram security...")
    try:
        from network.telegram_security import TelegramSecurityManager
        
        # Test static method
        device_info = TelegramSecurityManager.generate_device_info_static()
        print(f"  Device info generation: ✅")
        print(f"  Device info keys: {list(device_info.keys())}")
        
        return True
    except Exception as e:
        print(f"  ❌ Error testing telegram security: {e}")
        return False

def test_ssl_config():
    """Test SSL configuration"""
    print("🔒 Testing SSL configuration...")
    try:
        from network.ssl_config import validate_ssl_configuration, get_secure_ssl_context
        
        # Test validation
        is_valid = validate_ssl_configuration()
        print(f"  SSL validation: {'✅' if is_valid else '⚠️'}")
        
        # Test secure context creation
        ssl_context = get_secure_ssl_context()
        print(f"  Secure SSL context: {'✅' if ssl_context else '❌'}")
        
        return is_valid and ssl_context is not None
    except Exception as e:
        print(f"  ❌ Error testing SSL config: {e}")
        return False

def main():
    """Run all validation tests"""
    print("🧪 Running validation tests for implemented fixes...")
    print("=" * 60)
    
    tests = [
        test_security_config,
        test_session_paths,
        test_config_service,
        test_auth_service,
        test_telegram_security,
        test_ssl_config,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            logger.error(f"Test {test.__name__} failed with error: {e}")
            results.append(False)
        print()  # Add spacing between tests
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print("=" * 60)
    print(f"📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed! Fixes are working correctly.")
        return 0
    else:
        print("⚠️ Some tests failed. Please review the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())