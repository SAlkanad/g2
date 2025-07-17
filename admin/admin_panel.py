"""
Main Admin Panel - Coordinates all admin functionality modules

This module serves as the main entry point for all admin panel operations,
delegating specific functionality to specialized modules.
"""

import logging
from typing import List, Optional
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.database import Database
from notification_service import NotificationService
from admin.auth_service import AuthService
from languages.languages import get_text

logger = logging.getLogger(__name__)


class AdminStates(StatesGroup):
    """Admin FSM states for various operations"""
    # Content management
    waiting_rules_content = State()
    waiting_updates_content = State()
    selecting_language = State()
    waiting_live_support_message = State()
    
    # Withdrawal management  
    waiting_withdrawal_action = State()
    waiting_withdrawal_notes = State()
    
    # Session management
    waiting_rejection_reason = State()


class AdminPanel:
    """Main admin panel coordinator"""
    
    def __init__(self, bot: Bot, database: Database, admin_ids: List[int], api_id: str, api_hash: str):
        self.bot = bot
        self.database = database
        self.admin_ids = admin_ids
        self.auth_service = AuthService(database, admin_ids)
        self.notification_service = NotificationService(bot, database)
        
        # Import admin modules (lazy loading to avoid circular imports)
        self._countries_module = None
        self._sessions_module = None
        self._users_module = None
        self._bot_settings_module = None
        self._extractor_module = None
        self._rules_module = None
        self._updates_module = None
    
    @property
    def countries_module(self):
        """Lazy load countries module"""
        if self._countries_module is None:
            from admin.admin_countries import AdminCountries
            self._countries_module = AdminCountries(self.bot, self.database, self.admin_ids)
        return self._countries_module
    
    @property
    def sessions_module(self):
        """Lazy load sessions module"""
        if self._sessions_module is None:
            from admin.admin_sessions import AdminSessions
            from config_service import ConfigService
            config_service = ConfigService(self.database)
            self._sessions_module = AdminSessions(self.bot, self.database, self.admin_ids, config_service)
        return self._sessions_module
    
    @property
    def users_module(self):
        """Lazy load users module"""
        if self._users_module is None:
            from admin.admin_users import AdminUsers
            self._users_module = AdminUsers(self.bot, self.database, self.admin_ids)
        return self._users_module
    
    @property
    def bot_settings_module(self):
        """Lazy load bot settings module"""
        if self._bot_settings_module is None:
            from admin.admin_bot_settings import AdminBotSettings
            self._bot_settings_module = AdminBotSettings(self.bot, self.database, self.admin_ids)
        return self._bot_settings_module
    
    @property
    def extractor_module(self):
        """Lazy load extractor module"""
        if self._extractor_module is None:
            from admin.admin_extractor import AdminExtractor
            from config_service import ConfigService
            config_service = ConfigService(self.database)
            self._extractor_module = AdminExtractor(self.bot, self.database, self.admin_ids, config_service)
        return self._extractor_module
    
    @property
    def rules_module(self):
        """Lazy load rules module"""
        if self._rules_module is None:
            from rules import RulesManager
            self._rules_module = RulesManager(self.bot, self.database, self.admin_ids)
        return self._rules_module
    
    @property
    def updates_module(self):
        """Lazy load updates module"""
        if self._updates_module is None:
            from updates import UpdatesManager
            self._updates_module = UpdatesManager(self.bot, self.database, self.admin_ids)
        return self._updates_module
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin"""
        return self.auth_service.is_admin(user_id)
    
    def get_user_language(self, user_id: int) -> str:
        """Get user's language preference"""
        try:
            user = self.database.get_user(user_id)
            return user.get('language', 'en') if user else 'en'
        except Exception as e:
            logger.error(f"Error getting user language: {e}")
            return 'en'
    
    def get_main_keyboard(self) -> InlineKeyboardMarkup:
        """Get main admin panel keyboard"""
        keyboard = [
            [
                InlineKeyboardButton(text="📋 Sessions Management", callback_data="admin_sessions"),
                InlineKeyboardButton(text="🌍 Countries Management", callback_data="admin_countries")
            ],
            [
                InlineKeyboardButton(text="👥 Users Management", callback_data="admin_users"),
                InlineKeyboardButton(text="💰 Withdrawals", callback_data="admin_withdrawals")
            ],
            [
                InlineKeyboardButton(text="📜 Rules Management", callback_data="admin_rules"),
                InlineKeyboardButton(text="📢 Updates Management", callback_data="admin_updates")
            ],
            [
                InlineKeyboardButton(text="💬 Live Support Message", callback_data="admin_live_support"),
                InlineKeyboardButton(text="📦 Session Extractor", callback_data="admin_extractor")
            ],
            [
                InlineKeyboardButton(text="📊 Reporting System", callback_data="reporting_settings"),
                InlineKeyboardButton(text="⚙️ Bot Settings", callback_data="admin_bot_settings")
            ],
            [
                InlineKeyboardButton(text="🔄 Database Sync", callback_data="admin_database_sync"),
                InlineKeyboardButton(text="👤 Add Admin", callback_data="admin_add_admin")
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_to_main")
            ]
        ]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    async def show_main_panel(self, callback_query: types.CallbackQuery):
        """Show main admin panel"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        stats = await self.get_admin_stats()
        
        text = (
            "🔧 **Admin Panel**\n\n"
            f"📊 **Quick Stats:**\n"
            f"• Pending Sessions: {stats['pending_sessions']}\n"
            f"• Total Users: {stats['total_users']}\n"
            f"• Active Countries: {stats['active_countries']}\n"
            f"• Pending Withdrawals: {stats['pending_withdrawals']}\n\n"
            "Select an option to manage:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=self.get_main_keyboard(),
            parse_mode="Markdown"
        )
    
    async def get_admin_stats(self) -> dict:
        """Get quick admin statistics"""
        try:
            stats = {
                'pending_sessions': 0,
                'total_users': 0,
                'active_countries': 0,
                'pending_withdrawals': 0
            }
            
            # Get session stats
            session_stats = self.database.get_session_statistics()
            if session_stats:
                stats['pending_sessions'] = session_stats.get('pending', 0)
            
            # Get user count
            users = self.database.get_all_users()
            stats['total_users'] = len(users) if users else 0
            
            # Get active countries count
            countries = self.database.get_countries()
            stats['active_countries'] = sum(1 for c in countries if c.get('is_active', False)) if countries else 0
            
            # Get pending withdrawals
            withdrawals = self.database.get_withdrawal_requests()
            stats['pending_withdrawals'] = sum(1 for w in withdrawals if w.get('status') == 'pending') if withdrawals else 0
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting admin stats: {e}")
            return {
                'pending_sessions': 0,
                'total_users': 0,
                'active_countries': 0,
                'pending_withdrawals': 0
            }
    
    # Rules and updates management now handled by dedicated modules
    
    async def handle_database_sync(self, callback_query: types.CallbackQuery):
        """Handle database synchronization"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        user_language = self.get_user_language(callback_query.from_user.id)
        await callback_query.answer(get_text("starting_database_sync", user_language), show_alert=True)
        
        try:
            # Import and run sync
            from database.firebase_sync import FirebaseSync
            sync = FirebaseSync()
            
            sync_results = await sync.full_sync()
            
            text = (
                "✅ **Database Sync Completed**\n\n"
                f"📊 **Sync Results:**\n"
                f"• Countries synced: {sync_results.get('countries', 0)}\n"
                f"• Sessions synced: {sync_results.get('sessions', 0)}\n"
                f"• Users synced: {sync_results.get('users', 0)}\n"
                f"• Content synced: {sync_results.get('content', 0)}\n\n"
                f"🕐 **Sync Time:** {sync_results.get('timestamp', 'Unknown')}"
            )
            
        except Exception as e:
            logger.error(f"Database sync error: {e}")
            text = (
                "❌ **Database Sync Failed**\n\n"
                f"Error: {str(e)}\n\n"
                "Please check the logs for more details."
            )
        
        keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="admin_panel")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def handle_add_admin(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Handle add admin functionality"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        # This functionality will be handled by bot settings module
        await self.bot_settings_module.handle_add_admin(callback_query, state)
    
    async def show_live_support_management(self, callback_query: types.CallbackQuery):
        """Show live support message management"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        # Get current live support message from database
        current_message = self.database.get_live_support_message()
        if not current_message:
            current_message = "Live support is currently unavailable. Please contact an administrator."
        
        keyboard = [
            [
                InlineKeyboardButton(text="✏️ Edit Message", callback_data="edit_live_support_message")
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Admin Panel", callback_data="admin_panel")
            ]
        ]
        
        text = (
            "💬 **Live Support Message Management**\n\n"
            f"**Current Message:**\n"
            f"```\n{current_message}\n```\n\n"
            "Select an action:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def edit_live_support_message_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt admin to edit live support message"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        current_message = self.database.get_live_support_message()
        if not current_message:
            current_message = "Live support is currently unavailable. Please contact an administrator."
        
        text = (
            "✏️ **Edit Live Support Message**\n\n"
            f"**Current Message:**\n"
            f"```\n{current_message}\n```\n\n"
            "Please send the new live support message:"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="admin_live_support")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(AdminStates.waiting_live_support_message)
    
    async def process_live_support_message(self, message: types.Message, state: FSMContext):
        """Process new live support message"""
        if not self.is_admin(message.from_user.id):
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("access_denied", user_language))
            return
        
        new_message = message.text.strip()
        user_language = self.get_user_language(message.from_user.id)
        
        if len(new_message) > 1000:
            await message.reply(get_text("message_too_long", user_language))
            return
        
        try:
            # Save to database
            success = self.database.set_live_support_message(new_message)
            
            if success:
                await message.reply(
                    f"✅ **Live Support Message Updated**\n\n"
                    f"**New Message:**\n"
                    f"```\n{new_message}\n```",
                    parse_mode="Markdown"
                )
                
                # Send notifications to all users about live support message change
                await self.notification_service.notify_live_support_change()
                
                logger.info(f"Admin {message.from_user.id} updated live support message")
            else:
                await message.reply(get_text("failed_update_live_support", user_language))
                
        except Exception as e:
            logger.error(f"Error updating live support message: {e}")
            await message.reply(get_text("error_updating_message", user_language, error=str(e)))
        
        await state.clear()
    
    def register_handlers(self, dp: Dispatcher):
        """Register all admin panel handlers"""
        # Main panel handler
        dp.callback_query.register(
            self.show_main_panel,
            lambda c: c.data == "admin_panel"
        )
        
        # Database sync handler
        dp.callback_query.register(
            self.handle_database_sync,
            lambda c: c.data == "admin_database_sync"
        )
        
        # Live support handlers
        dp.callback_query.register(
            self.show_live_support_management,
            lambda c: c.data == "admin_live_support"
        )
        
        dp.callback_query.register(
            self.edit_live_support_message_prompt,
            lambda c: c.data == "edit_live_support_message"
        )
        
        dp.message.register(
            self.process_live_support_message,
            AdminStates.waiting_live_support_message
        )
        
        # Delegate module registrations
        self.countries_module.register_handlers(dp)
        self.sessions_module.register_handlers(dp)
        self.users_module.register_handlers(dp)
        self.bot_settings_module.register_handlers(dp)
        self.extractor_module.register_handlers(dp)
        self.rules_module.register_handlers(dp)
        self.updates_module.register_handlers(dp)