"""
Admin System Integration

This module handles the integration of the new modular admin system
with the main bot, replacing all old admin functionality.
"""

import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext

from admin.admin_panel import AdminPanel
from database.database import Database
from admin.auth_service import AuthService

logger = logging.getLogger(__name__)


class AdminIntegration:
    """Handles integration of modular admin system with main bot"""
    
    def __init__(self, bot: Bot, database: Database, admin_ids: list, api_id: str, api_hash: str):
        self.bot = bot
        self.database = database
        self.admin_ids = admin_ids
        self.auth_service = AuthService(database, admin_ids)
        
        # Initialize the main admin panel
        self.admin_panel = AdminPanel(bot, database, admin_ids, api_id, api_hash)
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin"""
        return self.auth_service.is_admin(user_id)
    
    def get_user_language(self, user_id: int) -> str:
        """Get user's language preference from database"""
        try:
            user = self.database.get_user(user_id)
            return user.get('language', 'en') if user else 'en'
        except Exception as e:
            logger.error(f"Error getting user language: {e}")
            return 'en'
    
    async def handle_admin_panel_request(self, message: types.Message):
        """Handle admin panel button press from main menu"""
        user_id = message.from_user.id
        
        # Debug logging
        logger.info(f"Admin panel request from user {user_id}")
        logger.info(f"Admin IDs configured: {self.admin_ids}")
        logger.info(f"Is admin check result: {self.is_admin(user_id)}")
        
        if not self.is_admin(user_id):
            await message.answer("❌ Access denied")
            return
        
        # Get user data to determine language
        user = self.database.get_user(message.from_user.id)
        lang = user.get('language', 'en') if user else 'en'
        
        # Get admin stats for display
        try:
            stats = await self.admin_panel.get_admin_stats()
        except:
            stats = {
                'pending_sessions': 0,
                'total_users': 0,
                'active_countries': 0,
                'pending_withdrawals': 0
            }
        
        # Create admin panel message
        text = (
            "🔧 **Admin Panel**\n\n"
            f"📊 **Quick Stats:**\n"
            f"• Pending Sessions: {stats['pending_sessions']}\n"
            f"• Total Users: {stats['total_users']}\n"
            f"• Active Countries: {stats['active_countries']}\n"
            f"• Pending Withdrawals: {stats['pending_withdrawals']}\n\n"
            "Select an option to manage:"
        )
        
        # Send the admin panel
        await message.answer(
            text=text,
            reply_markup=self.admin_panel.get_main_keyboard(),
            parse_mode="Markdown"
        )
    
    def register_handlers(self, dp: Dispatcher):
        """Register admin integration handlers"""
        # Import languages function
        try:
            from languages.languages import get_text, get_supported_languages
            
            # Register handler for admin panel button
            @dp.message(F.text.in_([
                get_text('admin_panel', lang) for lang in get_supported_languages()
            ]))
            async def admin_panel_handler(message: types.Message):
                await self.handle_admin_panel_request(message)
        
        except ImportError:
            # Fallback if languages module not available
            @dp.message(F.text.in_(['👨‍💼 Admin Panel', 'لوحة الإدارة']))
            async def admin_panel_handler(message: types.Message):
                await self.handle_admin_panel_request(message)
        
        # Register all admin module handlers
        self.admin_panel.register_handlers(dp)
        
        logger.info("Admin system integration handlers registered successfully")