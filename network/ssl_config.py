"""
SSL Configuration for Telethon
Addresses SSL library warnings and ensures proper certificate validation
"""

import os
import ssl
import logging
import certifi
from telethon.crypto import rsa

logger = logging.getLogger(__name__)

def configure_telethon_ssl():
    """Configure SSL settings for Telethon with proper security"""
    try:
        # Set environment variables for SSL
        os.environ['SSL_CERT_FILE'] = certifi.where()
        os.environ['SSL_CERT_DIR'] = os.path.dirname(certifi.where())
        
        # Configure OpenSSL settings
        os.environ['OPENSSL_CONF'] = ''
        
        # Set proper SSL context with security based on environment
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        
        # Check if we're in development mode
        development_mode = os.getenv('DEVELOPMENT_MODE', 'false').lower() == 'true'
        ssl_verify = os.getenv('SSL_VERIFY', 'true').lower() == 'true'
        
        if development_mode and not ssl_verify:
            # Only disable SSL verification in explicit development mode
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            logger.warning("SSL certificate verification disabled - DEVELOPMENT MODE ONLY")
        else:
            # Production mode: enforce SSL verification
            ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            logger.info("SSL certificate verification enabled for production")
        
        logger.info("SSL configuration applied for Telethon")
        return ssl_context
        
    except Exception as e:
        logger.error(f"Failed to configure SSL for Telethon: {e}")
        return None

def suppress_ssl_warnings():
    """Suppress SSL warnings only when explicitly configured"""
    suppress_warnings = os.getenv('SUPPRESS_SSL_WARNINGS', 'false').lower() == 'true'
    development_mode = os.getenv('DEVELOPMENT_MODE', 'false').lower() == 'true'
    
    if suppress_warnings or development_mode:
        import warnings
        import urllib3
        
        # Suppress urllib3 warnings
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Suppress SSL warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        warnings.filterwarnings("ignore", message=".*SSL.*")
        
        logger.info("SSL warnings suppressed (development mode or explicitly configured)")
    else:
        logger.info("SSL warnings enabled for production security")

def check_ssl_libraries():
    """Check if SSL libraries are properly loaded"""
    try:
        import ssl
        import cryptography
        
        logger.info(f"SSL library version: {ssl.OPENSSL_VERSION}")
        logger.info(f"Cryptography version: {cryptography.__version__}")
        
        # Check for pyOpenSSL (optional)
        try:
            import OpenSSL
            logger.info(f"OpenSSL version: {OpenSSL.version.__version__}")
        except ImportError:
            logger.warning("pyOpenSSL not available (optional dependency)")
        
        return True
    except ImportError as e:
        logger.error(f"Critical SSL library missing: {e}")
        return False

def initialize_ssl_for_telethon():
    """Initialize SSL configuration for Telethon"""
    logger.info("Initializing SSL configuration for Telethon...")
    
    # Configure SSL settings and get the context
    ssl_context = configure_telethon_ssl()
    
    # Suppress warnings if configured
    suppress_ssl_warnings()
    
    # Check library availability
    check_ssl_libraries()
    
    logger.info("SSL configuration completed for Telethon")
    return ssl_context

def get_secure_ssl_context():
    """Get a secure SSL context for production use"""
    try:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        ssl_context.check_hostname = True
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        logger.info("Secure SSL context created")
        return ssl_context
    except Exception as e:
        logger.error(f"Failed to create secure SSL context: {e}")
        return None

def validate_ssl_configuration():
    """Validate the current SSL configuration for security"""
    development_mode = os.getenv('DEVELOPMENT_MODE', 'false').lower() == 'true'
    ssl_verify = os.getenv('SSL_VERIFY', 'true').lower() == 'true'
    
    if not development_mode and not ssl_verify:
        logger.critical("SECURITY WARNING: SSL verification is disabled in production mode!")
        return False
    
    if development_mode:
        logger.warning("Running in development mode - SSL verification may be disabled")
    
    logger.info("SSL configuration validation passed")
    return True