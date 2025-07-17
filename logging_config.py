"""
Centralized Logging Configuration
Provides consistent logging setup across all modules
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class LoggingConfig:
    """Centralized logging configuration manager"""
    
    def __init__(self):
        self.log_level = self._get_log_level()
        self.log_format = self._get_log_format()
        self.log_dir = self._get_log_directory()
        self.console_enabled = self._get_console_enabled()
        self.file_logging_enabled = self._get_file_logging_enabled()
    
    def _get_log_level(self) -> int:
        """Get logging level from environment or default"""
        level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
        return getattr(logging, level_str, logging.INFO)
    
    def _get_log_format(self) -> str:
        """Get logging format from environment or default"""
        return os.getenv(
            'LOG_FORMAT',
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    def _get_log_directory(self) -> str:
        """Get log directory from environment or default"""
        return os.getenv('LOG_DIR', 'logs')
    
    def _get_console_enabled(self) -> bool:
        """Check if console logging is enabled"""
        return os.getenv('LOG_CONSOLE', 'true').lower() == 'true'
    
    def _get_file_logging_enabled(self) -> bool:
        """Check if file logging is enabled"""
        return os.getenv('LOG_FILE', 'true').lower() == 'true'
    
    def setup_logging(self, 
                     module_name: Optional[str] = None,
                     log_file: Optional[str] = None) -> logging.Logger:
        """Setup logging configuration for a module"""
        
        # Create log directory if file logging is enabled
        if self.file_logging_enabled:
            Path(self.log_dir).mkdir(exist_ok=True)
        
        # Configure root logger if not already configured
        root_logger = logging.getLogger()
        if not root_logger.handlers:
            self._configure_root_logger()
        
        # Return logger for specific module
        if module_name:
            return logging.getLogger(module_name)
        else:
            return root_logger
    
    def _configure_root_logger(self):
        """Configure the root logger with handlers"""
        root_logger = logging.getLogger()
        root_logger.setLevel(self.log_level)
        
        # Clear any existing handlers
        root_logger.handlers.clear()
        
        # Create formatter
        formatter = logging.Formatter(self.log_format)
        
        # Add console handler if enabled
        if self.console_enabled:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.log_level)
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)
        
        # Add file handler if enabled
        if self.file_logging_enabled:
            file_handler = self._create_file_handler()
            file_handler.setLevel(self.log_level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        
        # Add error file handler for ERROR and CRITICAL messages
        if self.file_logging_enabled:
            error_handler = self._create_error_file_handler()
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(formatter)
            root_logger.addHandler(error_handler)
    
    def _create_file_handler(self) -> logging.Handler:
        """Create rotating file handler for general logs"""
        from logging.handlers import RotatingFileHandler
        
        log_file = os.path.join(self.log_dir, 'bot.log')
        handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        return handler
    
    def _create_error_file_handler(self) -> logging.Handler:
        """Create rotating file handler for error logs"""
        from logging.handlers import RotatingFileHandler
        
        error_file = os.path.join(self.log_dir, 'errors.log')
        handler = RotatingFileHandler(
            error_file,
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3
        )
        return handler
    
    def get_module_logger(self, module_name: str) -> logging.Logger:
        """Get a logger for a specific module"""
        return logging.getLogger(module_name)
    
    def set_log_level(self, level: int):
        """Change log level for all handlers"""
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        for handler in root_logger.handlers:
            handler.setLevel(level)
    
    def add_telegram_logging(self, chat_id: str, bot_token: str):
        """Add Telegram handler for critical errors (optional)"""
        try:
            from logging_handlers import TelegramHandler
            telegram_handler = TelegramHandler(bot_token, chat_id)
            telegram_handler.setLevel(logging.CRITICAL)
            
            formatter = logging.Formatter(
                '🚨 CRITICAL ERROR\n'
                'Time: %(asctime)s\n'
                'Module: %(name)s\n'
                'Message: %(message)s'
            )
            telegram_handler.setFormatter(formatter)
            
            logging.getLogger().addHandler(telegram_handler)
        except ImportError:
            # TelegramHandler not available, skip
            pass
    
    def configure_specific_loggers(self):
        """Configure specific loggers for third-party libraries"""
        # Reduce noise from some libraries
        logging.getLogger('telethon').setLevel(logging.WARNING)
        logging.getLogger('aiohttp').setLevel(logging.WARNING)
        logging.getLogger('aiogram').setLevel(logging.INFO)
        logging.getLogger('firebase_admin').setLevel(logging.WARNING)
        
        # Enable debug for our modules in development
        development_mode = os.getenv('DEVELOPMENT_MODE', 'false').lower() == 'true'
        if development_mode:
            our_modules = [
                'auth_service', 'config_service', 'session_manager', 
                'telegram_security', 'admin_panel', 'security_config'
            ]
            for module in our_modules:
                logging.getLogger(module).setLevel(logging.DEBUG)


# Global logging configuration instance
_logging_config = None


def get_logging_config() -> LoggingConfig:
    """Get the global logging configuration instance"""
    global _logging_config
    if _logging_config is None:
        _logging_config = LoggingConfig()
    return _logging_config


def setup_logging(module_name: Optional[str] = None) -> logging.Logger:
    """Setup logging for a module (convenience function)"""
    config = get_logging_config()
    return config.setup_logging(module_name)


def get_logger(name: str) -> logging.Logger:
    """Get a logger for a specific module (convenience function)"""
    # Ensure logging is configured
    get_logging_config().setup_logging()
    return logging.getLogger(name)


def configure_application_logging():
    """Configure logging for the entire application"""
    config = get_logging_config()
    config.setup_logging()
    config.configure_specific_loggers()
    
    # Log configuration details
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured - Level: {logging.getLevelName(config.log_level)}")
    logger.info(f"Console logging: {'enabled' if config.console_enabled else 'disabled'}")
    logger.info(f"File logging: {'enabled' if config.file_logging_enabled else 'disabled'}")
    if config.file_logging_enabled:
        logger.info(f"Log directory: {config.log_dir}")


if __name__ == "__main__":
    # Test the logging configuration
    configure_application_logging()
    
    logger = get_logger(__name__)
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message") 
    logger.error("Error message")
    logger.critical("Critical message")
    
    print("Logging configuration test completed!")