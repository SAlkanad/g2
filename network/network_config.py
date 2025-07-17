"""
Network Configuration Settings for Bot
Provides resilient network configuration with proper timeouts and retry logic
"""

import os
import logging
import asyncio
from typing import Optional
import functools # ADDED THIS IMPORT

logger = logging.getLogger(__name__)

# Global network configuration instance will be created at the end

def configure_ssl_warnings():
    """Configure SSL warnings based on settings"""
    try:
        config = get_network_config()
        if config.suppress_ssl_warnings:
            import warnings
            import urllib3
            warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)
            warnings.filterwarnings('ignore', message='.*SSL.*')
            warnings.filterwarnings('ignore', message='.*certificate.*')
            logger.info("SSL warnings suppressed")
    except Exception as e:
        logger.error(f"Error configuring SSL warnings: {e}")

def get_network_config():
    """Get the global network configuration"""
    global network_config
    if 'network_config' not in globals():
        network_config = NetworkConfig()
    return network_config


class RetryConfig:
    """Configuration for retry logic"""
    
    def __init__(self, max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = 2.0
        self.jitter = True



def retry_on_network_error(retry_config: Optional[RetryConfig] = None):
    """Decorator to retry network operations on failure"""
    if retry_config is None:
        retry_config = RetryConfig()
    
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Handle both instance methods (with self) and standalone functions
            last_exception = None
            
            for attempt in range(retry_config.max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == retry_config.max_attempts - 1:
                        break
                    
                    # Calculate delay with exponential backoff
                    delay = min(
                        retry_config.base_delay * (retry_config.exponential_base ** attempt),
                        retry_config.max_delay
                    )
                    
                    # Add jitter to prevent thundering herd
                    if retry_config.jitter:
                        import random
                        delay = delay * (0.5 + random.random() * 0.5)
                    
                    logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
            
            # All attempts failed
            raise last_exception
        return wrapper
    return decorator

class NetworkConfig:
    """Enhanced network configuration with Telegram client support"""
    
    def __init__(self):
        # Firebase settings
        self.firebase_timeout = int(os.getenv('FIREBASE_TIMEOUT', '30'))
        self.firebase_retry_attempts = int(os.getenv('FIREBASE_RETRY_ATTEMPTS', '3'))
        self.firebase_retry_delay = int(os.getenv('FIREBASE_RETRY_DELAY', '2'))
        
        # Telegram settings
        self.telegram_timeout = int(os.getenv('TELEGRAM_TIMEOUT', '30'))
        self.telegram_retry_attempts = int(os.getenv('TELEGRAM_RETRY_ATTEMPTS', '3'))
        self.telegram_retry_delay = int(os.getenv('TELEGRAM_RETRY_DELAY', '5'))
        
        # SSL settings
        self.ssl_verify = os.getenv('SSL_VERIFY', 'true').lower() == 'true'
        self.suppress_ssl_warnings = os.getenv('SUPPRESS_SSL_WARNINGS', 'false').lower() == 'true'
        
        # Connection pool settings
        self.connection_pool_size = int(os.getenv('CONNECTION_POOL_SIZE', '100'))
        self.connection_timeout = int(os.getenv('CONNECTION_TIMEOUT', '30'))
        
        logger.info(f"Network configuration loaded: Firebase timeout={self.firebase_timeout}s, "
                   f"Telegram timeout={self.telegram_timeout}s")
    
    def get_telegram_client_config(self) -> dict:
        """Get Telegram client configuration"""
        return {
            'timeout': self.telegram_timeout,
            'retry_delay': self.telegram_retry_delay,
            'flood_sleep_threshold': 60,
            'connection_retries': self.telegram_retry_attempts,
            'request_retries': self.telegram_retry_attempts,
            'connection_timeout': self.connection_timeout,
            'use_ipv6': False,  # Disable IPv6 to avoid connection issues
        }
    
    def get_firebase_config(self) -> dict:
        """Get Firebase configuration"""
        return {
            'timeout': self.firebase_timeout,
            'retry_attempts': self.firebase_retry_attempts,
            'retry_delay': self.firebase_retry_delay,
        }

    def get_aiohttp_config(self) -> dict:
        """Get aiohttp client configuration"""
        return {
            'timeout': asyncio.TimeoutError(self.connection_timeout),
            'connector_limit': self.connection_pool_size,
            'connector_limit_per_host': 30,
            'read_timeout': self.connection_timeout,
            'conn_timeout': self.connection_timeout,
        }
    
    @staticmethod
    def get_telegram_client_kwargs() -> dict:
        """Get Telegram client kwargs for Telethon"""
        config = get_network_config()
        return {
            'connection_retries': config.telegram_retry_attempts,
            'timeout': config.telegram_timeout,
            'auto_reconnect': True,
            'retry_delay': config.telegram_retry_delay,
            'flood_sleep_threshold': 60,
            'use_ipv6': False,
            'catch_up': True,
            'sequential_updates': True,
            'request_retries': config.telegram_retry_attempts,
        }
    
    @staticmethod
    def get_ssl_context():
        """Get SSL context for secure connections"""
        import ssl
        import certifi
        
        context = ssl.create_default_context(cafile=certifi.where())
        config = get_network_config()
        
        # Check if we're in development mode
        development_mode = os.getenv('DEVELOPMENT_MODE', 'false').lower() == 'true'
        
        # Configure based on environment - only disable in explicit development mode
        if development_mode and not config.ssl_verify:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            logger.warning("SSL verification disabled - DEVELOPMENT MODE ONLY")
        else:
            # Production mode: enforce SSL verification
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
            logger.info("SSL verification enabled for production")
        
        return context


class FirebaseRetryManager:
    """Manages Firebase retry logic"""
    
    def __init__(self, config: NetworkConfig):
        self.config = config
        self.retry_config = RetryConfig(
            max_attempts=config.firebase_retry_attempts,
            base_delay=config.firebase_retry_delay,
            max_delay=120.0
        )
    
    async def execute_with_retry(self, operation):
        """Execute Firebase operation with retry logic"""
        last_exception = None
        
        for attempt in range(self.retry_config.max_attempts):
            try:
                # Execute the operation directly
                if asyncio.iscoroutinefunction(operation):
                    return await operation()
                else:
                    return operation()
            except Exception as e:
                last_exception = e
                if attempt == self.retry_config.max_attempts - 1:
                    break
                
                # Calculate delay with exponential backoff
                delay = min(
                    self.retry_config.base_delay * (self.retry_config.exponential_base ** attempt),
                    self.retry_config.max_delay
                )
                
                # Add jitter to prevent thundering herd
                if self.retry_config.jitter:
                    import random
                    delay = delay * (0.5 + random.random() * 0.5)
                
                logger.warning(f"Firebase operation attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)
        
        # All attempts failed
        raise last_exception


class TelegramRetryManager:
    """Manages Telegram client retry logic"""
    
    def __init__(self, config: NetworkConfig = None):
        self.config = config or get_network_config()
        self.retry_config = RetryConfig(
            max_attempts=self.config.telegram_retry_attempts,
            base_delay=self.config.telegram_retry_delay,
            max_delay=300.0  # 5 minutes max delay
        )
    
    async def connect_client(self, client):
        """Connect Telegram client with retry logic"""
        last_exception = None
        
        for attempt in range(self.retry_config.max_attempts):
            try:
                await client.connect()
                return True
            except Exception as e:
                last_exception = e
                if attempt == self.retry_config.max_attempts - 1:
                    break
                
                # Calculate delay with exponential backoff
                delay = min(
                    self.retry_config.base_delay * (self.retry_config.exponential_base ** attempt),
                    self.retry_config.max_delay
                )
                
                # Add jitter to prevent thundering herd
                if self.retry_config.jitter:
                    import random
                    delay = delay * (0.5 + random.random() * 0.5)
                
                logger.warning(f"Telegram connection attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)
        
        # All attempts failed
        raise last_exception
    
    async def start_client(self, client):
        """Start Telegram client with retry logic - for user sessions, check if already authorized"""
        last_exception = None
        
        for attempt in range(self.retry_config.max_attempts):
            try:
                # For user sessions, we don't want to call start() if not authorized
                # as it will prompt for input. Instead, check if already authorized.
                if not await client.is_user_authorized():
                    logger.warning("Client is not authorized - cannot start without authentication")
                    return False
                
                # If authorized, we can proceed (client.start() is not needed for authorized sessions)
                return True
            except Exception as e:
                last_exception = e
                if attempt == self.retry_config.max_attempts - 1:
                    break
                
                # Calculate delay with exponential backoff
                delay = min(
                    self.retry_config.base_delay * (self.retry_config.exponential_base ** attempt),
                    self.retry_config.max_delay
                )
                
                # Add jitter to prevent thundering herd
                if self.retry_config.jitter:
                    import random
                    delay = delay * (0.5 + random.random() * 0.5)
                
                logger.warning(f"Telegram client start attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s...")
                await asyncio.sleep(delay)
        
        # All attempts failed
        raise last_exception


def initialize_network_managers(database_instance):
    """Initialize network managers for database instance"""
    try:
        database_instance.firebase_retry_manager = FirebaseRetryManager(network_config)
        logger.info("Network managers initialized")
    except Exception as e:
        logger.error(f"Failed to initialize network managers: {e}")


# Initialize the global network configuration
network_config = None

def init_network_config():
    """Initialize the global network configuration"""
    global network_config
    if network_config is None:
        network_config = NetworkConfig()
    return network_config

# Initialize immediately
init_network_config()