"""
Main Integration File - Example of how to integrate the reporting system with the main bot

This file demonstrates how to properly initialize and integrate all components
including the new reporting system.
"""

import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage

# Import all modules
from database.database import Database
from admin.admin_extractor import AdminExtractor
from reporting_system import ReportingSystem
from admin.admin_reporting_settings import AdminReportingSettings
from sellaccount import SellAccountSystem
from admin.admin_panel import AdminPanel
from admin.admin_countries import AdminCountries
from admin.admin_sessions import AdminSessions
from admin.admin_users import AdminUsers
from languages.languages import get_text

# Use centralized logging
from logging_config import get_logger
logger = get_logger(__name__)


class TelegramBot:
    """Main bot class with integrated reporting system"""
    
    def __init__(self):
        # Bot configuration
        self.bot_token = os.getenv('BOT_TOKEN')
        self.api_id = os.getenv('API_ID')
        self.api_hash = os.getenv('API_HASH')
        self.admin_ids = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
        self.admin_chat_id = os.getenv('ADMIN_CHAT_ID')
        
        # Initialize bot and dispatcher
        self.bot = Bot(token=self.bot_token)
        self.dp = Dispatcher(storage=MemoryStorage())
        
        # Initialize database
        self.database = Database()
        
        # Initialize session manager using SellAccountSystem
        self.session_manager = SellAccountSystem(
            bot=self.bot,
            database=self.database,
            api_id=self.api_id,
            api_hash=self.api_hash,
            admin_chat_id=self.admin_chat_id,
            reporting_system=None
        )
        
        # Initialize admin extractor
        self.admin_extractor = AdminExtractor(
            bot=self.bot,
            database=self.database,
            admin_ids=self.admin_ids,
            api_id=self.api_id,
            api_hash=self.api_hash
        )
        
        # Initialize reporting system (IMPORTANT: Initialize before other components that need it)
        self.reporting_system = ReportingSystem(
            bot=self.bot,
            database=self.database,
            session_manager=self.session_manager,
            admin_extractor=self.admin_extractor,
            admin_ids=self.admin_ids
        )
        
        # Initialize reporting settings admin module
        self.admin_reporting_settings = AdminReportingSettings(
            bot=self.bot,
            database=self.database,
            reporting_system=self.reporting_system,
            admin_ids=self.admin_ids
        )
        
        # Initialize sell account system with reporting
        self.sell_account_system = SellAccountSystem(
            bot=self.bot,
            database=self.database,
            api_id=self.api_id,
            api_hash=self.api_hash,
            admin_chat_id=self.admin_chat_id,
            reporting_system=self.reporting_system  # Pass reporting system
        )
        
        # Initialize admin modules
        self.admin_panel = AdminPanel(self.bot, self.database, self.admin_ids)
        self.admin_countries = AdminCountries(self.bot, self.database, self.admin_ids)
        self.admin_sessions = AdminSessions(self.bot, self.database, self.admin_ids)
        self.admin_users = AdminUsers(self.bot, self.database, self.admin_ids)
        
        # Register all handlers
        self.register_handlers()
        
        # Register error handler for the reporting system
        self.register_error_handler()
    
    def register_handlers(self):
        """Register all bot handlers"""
        
        # Register reporting system handlers
        self.reporting_system.register_handlers(self.dp)
        self.admin_reporting_settings.register_handlers(self.dp)
        
        # Register sell account handlers
        self.sell_account_system.register_handlers(self.dp)
        
        # Register admin handlers
        self.admin_countries.register_handlers(self.dp)
        self.admin_sessions.register_handlers(self.dp)
        self.admin_users.register_handlers(self.dp)
        self.admin_extractor.register_handlers(self.dp)
        
        # Register main menu and start handlers
        self.dp.message.register(self.start_command, commands=['start'])
        self.dp.callback_query.register(self.admin_panel.show_main_panel, lambda c: c.data == "admin_panel")
        
        # Add middleware for user interaction tracking
        self.dp.message.middleware(self.user_interaction_middleware)
        self.dp.callback_query.middleware(self.user_interaction_middleware)
    
    def register_error_handler(self):
        """Register global error handler for reporting"""
        
        @self.dp.error()
        async def error_handler(event, exception):
            """Global error handler that reports to the reporting system"""
            try:
                # Get user ID if available
                user_id = None
                context = "Unknown"
                
                if hasattr(event, 'message') and event.message:
                    user_id = event.message.from_user.id if event.message.from_user else None
                    context = f"Message: {event.message.text[:100] if event.message.text else 'N/A'}"
                elif hasattr(event, 'callback_query') and event.callback_query:
                    user_id = event.callback_query.from_user.id if event.callback_query.from_user else None
                    context = f"Callback: {event.callback_query.data}"
                
                # Report the error
                await self.reporting_system.report_error(exception, context, user_id)
                
                logger.error(f"Error in bot: {exception}", exc_info=True)
                
            except Exception as e:
                logger.error(f"Error in error handler: {e}")
    
    async def user_interaction_middleware(self, handler, event, data):
        """Middleware to track user interactions"""
        try:
            # Track user interaction for reporting
            user_id = None
            
            if hasattr(event, 'from_user') and event.from_user:
                user_id = event.from_user.id
                
                # Check if this is a new user
                user = self.database.get_user(user_id)
                if not user:
                    # New user - report it
                    await self.reporting_system.report_new_user(event.from_user)
                    
                    # Add user to database if not exists
                    self.database.add_user(
                        user_id=user_id,
                        username=event.from_user.username,
                        first_name=event.from_user.first_name,
                        last_name=event.from_user.last_name
                    )
                else:
                    # Existing user - track interaction
                    await self.reporting_system.report_user_interaction(user_id)
            
        except Exception as e:
            logger.error(f"Error in user interaction middleware: {e}")
        
        # Continue with the handler
        return await handler(event, data)
    
    async def start_command(self, message: types.Message):
        """Handle /start command"""
        # Get user's language preference (default to English)
        user_language = self.database.get_user_language(message.from_user.id) or 'en'
        
        keyboard = [
            [
                types.InlineKeyboardButton(text=get_text("sell_accounts", user_language), callback_data="sell_accounts"),
                types.InlineKeyboardButton(text="👤 My Profile", callback_data="user_profile")
            ],
            [
                types.InlineKeyboardButton(text=get_text("rules", user_language), callback_data="show_rules"),
                types.InlineKeyboardButton(text=get_text("bot_updates", user_language), callback_data="show_updates")
            ],
            [
                types.InlineKeyboardButton(text=get_text("live_support", user_language), callback_data="support")
            ]
        ]
        
        # Add admin panel button for admins
        if message.from_user.id in self.admin_ids:
            keyboard.append([
                types.InlineKeyboardButton(text=get_text("admin_panel", user_language), callback_data="admin_panel")
            ])
        
        await message.answer(
            get_text("welcome", user_language),
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def start_bot(self):
        """Start the bot"""
        try:
            logger.info("Starting Telegram Account Market Bot with Reporting System...")
            
            # Start the bot
            await self.dp.start_polling(self.bot)
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            await self.reporting_system.report_error(e, "Bot startup")
        finally:
            await self.bot.session.close()


async def main():
    """Main function to run the bot"""
    bot = TelegramBot()
    await bot.start_bot()


if __name__ == "__main__":
    asyncio.run(main())