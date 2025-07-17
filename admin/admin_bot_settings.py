"""
Admin Bot Settings Module

Handles all bot configuration and settings including:
- API ID and API Hash management
- Admin user management (add/remove)
- Bot configuration settings
- Environment variables management
- Withdrawal settings
- Notification settings
- Bot maintenance modes
"""

import logging
import os
from typing import List, Dict, Optional
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.database import Database
from admin.auth_service import AuthService
from languages.languages import get_text

logger = logging.getLogger(__name__)


class BotSettingsStates(StatesGroup):
    """FSM states for bot settings management"""
    waiting_api_id = State()
    waiting_api_hash = State()
    waiting_new_admin_id = State()
    waiting_remove_admin_id = State()
    waiting_min_withdrawal = State()
    waiting_bot_token = State()
    waiting_maintenance_message = State()
    waiting_setting_value = State()
    waiting_global_2fa_password = State()


class AdminBotSettings:
    """Admin module for bot settings management"""
    
    def __init__(self, bot: Bot, database: Database, admin_ids: List[int]):
        self.bot = bot
        self.database = database
        self.admin_ids = admin_ids
        self.auth_service = AuthService(database, admin_ids)
        
        # Load current settings
        self.current_settings = self.load_current_settings()
    
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
    
    def load_current_settings(self) -> dict:
        """Load current bot settings from environment and database"""
        settings = {
            'api_id': os.getenv('API_ID', 'Not set'),
            'api_hash': os.getenv('API_HASH', 'Not set'),
            'bot_token': os.getenv('BOT_TOKEN', 'Not set'),
            'admin_ids': os.getenv('ADMIN_IDS', 'Not set'),
            'min_withdrawal': 0,
            'max_withdrawal': 0,
            'maintenance_mode': False,
            'maintenance_message': '',
            'database_path': os.getenv('DATABASE_PATH', 'bot_database_v2.db'),
            'firebase_config': os.path.exists('serviceAccountKey.json'),
            'sessions_directory': 'session_files',
        }
        
        # Load database-specific settings
        try:
            db_settings = self.database.get_bot_settings()
            if db_settings:
                settings.update(db_settings)
        except Exception as e:
            logger.error(f"Error loading database settings: {e}")
        
        return settings
    
    async def show_settings_menu(self, callback_query: types.CallbackQuery):
        """Show main bot settings menu"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        # Refresh settings
        self.current_settings = self.load_current_settings()
        
        # Mask sensitive information
        api_id = self.current_settings.get('api_id', 'Not set')
        api_hash = self.current_settings.get('api_hash', 'Not set')
        bot_token = self.current_settings.get('bot_token', 'Not set')
        global_2fa = self.current_settings.get('global_2fa_password', 'Not set')
        if global_2fa is None:
            global_2fa = 'Not set'
        
        # Mask values for display
        api_id_display = api_id if api_id == 'Not set' else f"{str(api_id)[:4]}..."
        api_hash_display = api_hash if api_hash == 'Not set' else f"{api_hash[:8]}..."
        bot_token_display = bot_token if bot_token == 'Not set' else f"{bot_token[:10]}..."
        global_2fa_display = global_2fa if global_2fa == 'Not set' or global_2fa is None else f"{global_2fa[:4]}****"
        
        keyboard = [
            [
                InlineKeyboardButton(text="🔑 API Credentials", callback_data="api_credentials"),
                InlineKeyboardButton(text="👑 Admin Management", callback_data="admin_management")
            ],
            [
                InlineKeyboardButton(text="🔐 Global 2FA Password", callback_data="global_2fa_settings"),
                InlineKeyboardButton(text="💰 Withdrawal Settings", callback_data="withdrawal_settings")
            ],
            [
                InlineKeyboardButton(text="🔔 Notification Settings", callback_data="notification_settings"),
                InlineKeyboardButton(text="🛠️ Maintenance Mode", callback_data="maintenance_mode")
            ],
            [
                InlineKeyboardButton(text="📁 File Paths", callback_data="file_paths"),
                InlineKeyboardButton(text="🔄 Environment Variables", callback_data="env_variables")
            ],
            [
                InlineKeyboardButton(text="💾 Database Settings", callback_data="database_settings"),
                InlineKeyboardButton(text="🧪 Test Configuration", callback_data="test_config")
            ],
            [
                InlineKeyboardButton(text="📊 System Status", callback_data="system_status"),
                InlineKeyboardButton(text="🔙 Back to Admin Panel", callback_data="admin_panel")
            ]
        ]
        
        text = (
            "⚙️ **Bot Settings**\n\n"
            f"🔧 **Current Configuration:**\n"
            f"• API ID: `{api_id_display}`\n"
            f"• API Hash: `{api_hash_display}`\n"
            f"• Bot Token: `{bot_token_display}`\n"
            f"• Global 2FA: `{global_2fa_display}`\n"
            f"• Admin Count: {len(self.admin_ids)}\n"
            f"• Min Withdrawal: ${self.current_settings.get('min_withdrawal', 0):.2f}\n"
            f"• Maintenance: {'🟢 Active' if self.current_settings.get('maintenance_mode') else '🔴 Inactive'}\n"
            f"• Firebase: {'✅ Connected' if self.current_settings.get('firebase_config') else '❌ Not configured'}\n\n"
            "Select a category to configure:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def show_global_2fa_settings(self, callback_query: types.CallbackQuery):
        """Show global 2FA password settings"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        # Get current 2FA password
        current_2fa = self.database.get_global_2fa_password()
        current_2fa_display = current_2fa if current_2fa else "Not set"
        if current_2fa and current_2fa != "Not set":
            current_2fa_display = f"{current_2fa[:4]}****"
        
        keyboard = [
            [
                InlineKeyboardButton(text="✏️ Change 2FA Password", callback_data="change_global_2fa"),
                InlineKeyboardButton(text="🗑️ Remove 2FA Password", callback_data="remove_global_2fa")
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Settings", callback_data="admin_bot_settings")
            ]
        ]
        
        text = (
            "🔐 **Global 2FA Password Settings**\n\n"
            f"**Current Password:** `{current_2fa_display}`\n\n"
            "**About Global 2FA:**\n"
            "• This password is used to change 2FA on all sold accounts\n"
            "• When users sell accounts with 2FA enabled, their current password is changed to this global password\n"
            "• This ensures all sold accounts use the same 2FA password for management\n\n"
            "**Security Notice:**\n"
            "⚠️ Keep this password secure and change it regularly\n"
            "⚠️ All pending sessions will use the new password for 2FA changes\n\n"
            "Choose an action:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def prompt_change_global_2fa(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt admin to enter new global 2FA password"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        keyboard = [
            [InlineKeyboardButton(text="❌ Cancel", callback_data="global_2fa_settings")]
        ]
        
        text = (
            "🔐 **Change Global 2FA Password**\n\n"
            "Please enter the new global 2FA password:\n\n"
            "**Requirements:**\n"
            "• Minimum 8 characters\n"
            "• Mix of letters, numbers, and symbols recommended\n"
            "• Should be memorable but secure\n\n"
            "**Note:** This will be used for all future account 2FA changes."
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(BotSettingsStates.waiting_global_2fa_password)
    
    async def process_global_2fa_password(self, message: types.Message, state: FSMContext):
        """Process new global 2FA password"""
        if not self.is_admin(message.from_user.id):
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("access_denied", user_language))
            return
        
        new_password = message.text.strip()
        user_language = self.get_user_language(message.from_user.id)
        
        # Validate password
        if len(new_password) < 8:
            await message.reply(get_text("password_too_short", user_language))
            return
        
        if len(new_password) > 100:
            await message.reply(get_text("password_too_long", user_language))
            return
        
        try:
            # Update the password in database
            success = self.database.update_global_2fa_password(new_password, message.from_user.id)
            
            if success:
                await message.reply(
                    "✅ **Global 2FA password updated successfully!**\n\n"
                    "The new password will be used for all future account 2FA changes.\n"
                    "Make sure to keep this password secure.",
                    parse_mode="Markdown"
                )
                
                # Log the change
                logger.info(f"Admin {message.from_user.id} updated global 2FA password")
                
            else:
                await message.reply(
                    "❌ **Failed to update global 2FA password**\n\n"
                    "Please try again or contact system administrator.",
                    parse_mode="Markdown"
                )
                
        except Exception as e:
            logger.error(f"Error updating global 2FA password: {e}")
            await message.reply(
                "❌ **Error updating password**\n\n"
                "An error occurred while updating the password. Please try again.",
                parse_mode="Markdown"
            )
        
        await state.clear()
    
    async def remove_global_2fa(self, callback_query: types.CallbackQuery):
        """Remove global 2FA password"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        keyboard = [
            [
                InlineKeyboardButton(text="✅ Confirm Remove", callback_data="confirm_remove_global_2fa"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="global_2fa_settings")
            ]
        ]
        
        text = (
            "🗑️ **Remove Global 2FA Password**\n\n"
            "⚠️ **WARNING:** This will remove the global 2FA password!\n\n"
            "**Consequences:**\n"
            "• New account sales with 2FA will be rejected\n"
            "• Existing pending sessions may fail 2FA changes\n"
            "• You'll need to set a new password before accepting 2FA accounts\n\n"
            "Are you sure you want to remove the global 2FA password?"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def confirm_remove_global_2fa(self, callback_query: types.CallbackQuery):
        """Confirm removal of global 2FA password"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        try:
            # Remove the password by setting it to None
            success = self.database.update_global_2fa_password(None, callback_query.from_user.id)
            
            if success:
                await callback_query.answer("✅ Global 2FA password removed successfully", show_alert=True)
                logger.info(f"Admin {callback_query.from_user.id} removed global 2FA password")
                
                # Return to settings
                await self.show_global_2fa_settings(callback_query)
            else:
                await callback_query.answer("❌ Failed to remove global 2FA password", show_alert=True)
                
        except Exception as e:
            logger.error(f"Error removing global 2FA password: {e}")
            await callback_query.answer("❌ Error removing password", show_alert=True)
    
    async def show_api_credentials(self, callback_query: types.CallbackQuery):
        """Show API credentials management"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        api_id = self.current_settings.get('api_id', 'Not set')
        api_hash = self.current_settings.get('api_hash', 'Not set')
        
        # Mask for display
        api_id_display = api_id if api_id == 'Not set' else f"{str(api_id)[:4]}..."
        api_hash_display = api_hash if api_hash == 'Not set' else f"{api_hash[:8]}..."
        
        keyboard = [
            [
                InlineKeyboardButton(text="🔑 Set API ID", callback_data="set_api_id"),
                InlineKeyboardButton(text="🔐 Set API Hash", callback_data="set_api_hash")
            ],
            [
                InlineKeyboardButton(text="🤖 Set Bot Token", callback_data="set_bot_token"),
                InlineKeyboardButton(text="✅ Test API Connection", callback_data="test_api")
            ],
            [
                InlineKeyboardButton(text="📋 View Full Config", callback_data="view_full_config"),
                InlineKeyboardButton(text="🔄 Reload from Env", callback_data="reload_env")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin_bot_settings")
            ]
        ]
        
        text = (
            "🔑 **API Credentials Management**\n\n"
            f"📊 **Current Status:**\n"
            f"• API ID: `{api_id_display}`\n"
            f"• API Hash: `{api_hash_display}`\n"
            f"• Bot Token: {'✅ Set' if self.current_settings.get('bot_token') != 'Not set' else '❌ Not set'}\n\n"
            "⚠️ **Important Notes:**\n"
            "• API credentials are required for Telegram operations\n"
            "• Changes require bot restart to take effect\n"
            "• Keep credentials secure and private\n\n"
            "Select an action:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def set_api_id_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for API ID"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        text = (
            "🔑 **Set API ID**\n\n"
            "Enter your Telegram API ID:\n\n"
            "📝 **How to get API ID:**\n"
            "1. Go to https://my.telegram.org\n"
            "2. Log in with your phone number\n"
            "3. Go to 'API development tools'\n"
            "4. Create an app and get your API ID\n\n"
            "Enter the API ID (numbers only):"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="api_credentials")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(BotSettingsStates.waiting_api_id)
    
    async def process_api_id(self, message: types.Message, state: FSMContext):
        """Process API ID input"""
        if not self.is_admin(message.from_user.id):
            await message.reply("❌ Access denied")
            return
        
        try:
            api_id = int(message.text.strip())
            
            if api_id <= 0:
                await message.reply("❌ API ID must be a positive number")
                return
            
            # Update environment variable (for current session)
            os.environ['API_ID'] = str(api_id)
            
            # Update database settings
            self.database.update_bot_setting('api_id', str(api_id))
            
            # Refresh settings
            self.current_settings = self.load_current_settings()
            
            await message.reply(
                f"✅ **API ID Updated**\n\n"
                f"🔑 New API ID: `{api_id}`\n\n"
                f"⚠️ **Note**: Restart the bot for changes to take full effect.",
                parse_mode="Markdown"
            )
            
            # Log the action
            logger.info(f"Admin {message.from_user.id} updated API ID")
            
        except ValueError:
            await message.reply("❌ Invalid API ID. Please enter a valid number.")
        except Exception as e:
            logger.error(f"Error setting API ID: {e}")
            await message.reply(f"❌ Error setting API ID: {str(e)}")
        
        await state.clear()
    
    async def set_api_hash_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for API Hash"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        text = (
            "🔐 **Set API Hash**\n\n"
            "Enter your Telegram API Hash:\n\n"
            "📝 **How to get API Hash:**\n"
            "1. Go to https://my.telegram.org\n"
            "2. Log in with your phone number\n"
            "3. Go to 'API development tools'\n"
            "4. Create an app and get your API Hash\n\n"
            "Enter the API Hash (32 character string):"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="api_credentials")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(BotSettingsStates.waiting_api_hash)
    
    async def process_api_hash(self, message: types.Message, state: FSMContext):
        """Process API Hash input"""
        if not self.is_admin(message.from_user.id):
            await message.reply("❌ Access denied")
            return
        
        try:
            api_hash = message.text.strip()
            
            if len(api_hash) != 32:
                await message.reply("❌ API Hash must be exactly 32 characters long")
                return
            
            if not api_hash.isalnum():
                await message.reply("❌ API Hash must contain only letters and numbers")
                return
            
            # Update environment variable (for current session)
            os.environ['API_HASH'] = api_hash
            
            # Update database settings
            self.database.update_bot_setting('api_hash', api_hash)
            
            # Refresh settings
            self.current_settings = self.load_current_settings()
            
            await message.reply(
                f"✅ **API Hash Updated**\n\n"
                f"🔐 New API Hash: `{api_hash[:8]}...`\n\n"
                f"⚠️ **Note**: Restart the bot for changes to take full effect.",
                parse_mode="Markdown"
            )
            
            # Log the action
            logger.info(f"Admin {message.from_user.id} updated API Hash")
            
        except Exception as e:
            logger.error(f"Error setting API Hash: {e}")
            await message.reply(f"❌ Error setting API Hash: {str(e)}")
        
        await state.clear()
    
    async def show_admin_management(self, callback_query: types.CallbackQuery):
        """Show admin management interface"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        # Get all admins
        db_admins = self.database.get_all_admins()
        config_admins = self.admin_ids
        
        keyboard = [
            [
                InlineKeyboardButton(text="➕ Add Admin", callback_data="add_admin_prompt"),
                InlineKeyboardButton(text="➖ Remove Admin", callback_data="remove_admin_prompt")
            ],
            [
                InlineKeyboardButton(text="📋 View All Admins", callback_data="view_all_admins"),
                InlineKeyboardButton(text="🔄 Sync Admin Lists", callback_data="sync_admin_lists")
            ],
            [
                InlineKeyboardButton(text="🧪 Test Admin Permissions", callback_data="test_admin_perms"),
                InlineKeyboardButton(text="📊 Admin Activity Log", callback_data="admin_activity_log")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin_bot_settings")
            ]
        ]
        
        text = (
            "👑 **Admin Management**\n\n"
            f"📊 **Current Status:**\n"
            f"• Config Admins: {len(config_admins)}\n"
            f"• Database Admins: {len(db_admins) if db_admins else 0}\n"
            f"• Total Unique: {len(set(config_admins + [a.get('user_id') for a in db_admins if db_admins]))}\n\n"
            "⚠️ **Note**: Changes to config admins require bot restart.\n"
            "Database admins take effect immediately.\n\n"
            "Select an action:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def add_admin_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for new admin ID"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        text = (
            "➕ **Add New Admin**\n\n"
            "Enter the User ID to promote to admin:\n\n"
            "📝 **How to get User ID:**\n"
            "1. Have the user send any message to the bot\n"
            "2. Check the user database for their ID\n"
            "3. Or use @userinfobot to get the ID\n\n"
            "⚠️ **Important**: Only promote trusted users!\n\n"
            "Enter User ID:"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="admin_management")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(BotSettingsStates.waiting_new_admin_id)
    
    async def process_add_admin(self, message: types.Message, state: FSMContext):
        """Process new admin addition"""
        if not self.is_admin(message.from_user.id):
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("access_denied", user_language))
            return
        
        try:
            user_id = int(message.text.strip())
            user_language = self.get_user_language(message.from_user.id)
            
            # Check if user exists
            user_data = self.database.get_user(user_id)
            if not user_data:
                await message.reply(get_text("user_not_found", user_language))
                return
            
            # Check if already admin
            if user_data.get('is_admin', False) or user_id in self.admin_ids:
                await message.reply(get_text("user_already_admin", user_language))
                return
            
            # Add to database admins
            success = self.database.add_admin(user_id)
            
            if success:
                # Notify the new admin
                try:
                    await self.bot.send_message(
                        user_id,
                        "🎉 **Congratulations!**\n\n"
                        "You have been promoted to admin.\n"
                        "You now have access to the admin panel.\n\n"
                        "Use /admin to access admin functions.",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass  # User might have blocked the bot
                
                await message.reply(
                    f"✅ **Admin Added Successfully**\n\n"
                    f"👤 User ID: `{user_id}`\n"
                    f"📝 Name: {user_data.get('first_name', 'Unknown')}\n"
                    f"👑 Added to database admins\n\n"
                    f"⚡ **Effect**: Immediate",
                    parse_mode="Markdown"
                )
                
                # Log the action
                logger.info(f"Admin {message.from_user.id} promoted user {user_id} to admin")
                
            else:
                await message.reply("❌ Failed to add admin. Please try again.")
        
        except ValueError:
            await message.reply("❌ Invalid User ID. Please enter a valid number.")
        except Exception as e:
            logger.error(f"Error adding admin: {e}")
            await message.reply(f"❌ Error adding admin: {str(e)}")
        
        await state.clear()
    
    async def show_withdrawal_settings(self, callback_query: types.CallbackQuery):
        """Show withdrawal settings management"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        min_withdrawal = self.current_settings.get('min_withdrawal', 0)
        max_withdrawal = self.current_settings.get('max_withdrawal', 0)
        
        keyboard = [
            [
                InlineKeyboardButton(text="💰 Set Min Withdrawal", callback_data="set_min_withdrawal"),
                InlineKeyboardButton(text="💎 Set Max Withdrawal", callback_data="set_max_withdrawal")
            ],
            [
                InlineKeyboardButton(text="🔄 Reset to Defaults", callback_data="reset_withdrawal_defaults"),
                InlineKeyboardButton(text="📊 Withdrawal Statistics", callback_data="withdrawal_statistics")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin_bot_settings")
            ]
        ]
        
        text = (
            "💰 **Withdrawal Settings**\n\n"
            f"📊 **Current Settings:**\n"
            f"• Minimum Withdrawal: ${min_withdrawal:.2f}\n"
            f"• Maximum Withdrawal: ${max_withdrawal:.2f}\n\n"
            "⚙️ **Configuration Options:**\n"
            "• Set minimum amount users can withdraw\n"
            "• Set maximum amount per withdrawal\n"
            "• Reset to recommended defaults\n\n"
            "Select an action:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def set_min_withdrawal_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for minimum withdrawal amount"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        current_min = self.current_settings.get('min_withdrawal', 0)
        
        text = (
            "💰 **Set Minimum Withdrawal**\n\n"
            f"Current minimum: ${current_min:.2f}\n\n"
            "Enter the new minimum withdrawal amount:\n\n"
            "💡 **Recommendations:**\n"
            "• $1.00 - Very accessible\n"
            "• $5.00 - Balanced approach\n"
            "• $10.00 - Reduce transaction costs\n\n"
            "Enter amount (e.g., 5.00):"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="withdrawal_settings")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(BotSettingsStates.waiting_min_withdrawal)
    
    async def process_min_withdrawal(self, message: types.Message, state: FSMContext):
        """Process minimum withdrawal amount"""
        if not self.is_admin(message.from_user.id):
            await message.reply("❌ Access denied")
            return
        
        try:
            amount = float(message.text.strip())
            
            if amount < 0:
                await message.reply("❌ Amount must be positive")
                return
            
            if amount > 1000:
                await message.reply("❌ Amount seems too high. Please enter a reasonable minimum.")
                return
            
            # Update database setting
            self.database.update_bot_setting('min_withdrawal', amount)
            
            # Refresh settings
            self.current_settings = self.load_current_settings()
            
            await message.reply(
                f"✅ **Minimum Withdrawal Updated**\n\n"
                f"💰 New minimum: ${amount:.2f}\n\n"
                f"⚡ **Effect**: Immediate for new withdrawals",
                parse_mode="Markdown"
            )
            
            # Log the action
            logger.info(f"Admin {message.from_user.id} set minimum withdrawal to ${amount:.2f}")
            
        except ValueError:
            await message.reply("❌ Invalid amount. Please enter a valid number (e.g., 5.00)")
        except Exception as e:
            logger.error(f"Error setting minimum withdrawal: {e}")
            await message.reply(f"❌ Error setting minimum withdrawal: {str(e)}")
        
        await state.clear()
    
    async def show_system_status(self, callback_query: types.CallbackQuery):
        """Show system status and health"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        try:
            # Check various system components
            status_checks = {
                'database': self.check_database_connection(),
                'firebase': self.check_firebase_connection(),
                'sessions_dir': self.check_sessions_directory(),
                'env_vars': self.check_environment_variables(),
                'permissions': self.check_file_permissions(),
            }
            
            # Overall system health
            healthy_components = sum(1 for status in status_checks.values() if status)
            total_components = len(status_checks)
            health_percentage = (healthy_components / total_components) * 100
            
            if health_percentage >= 80:
                health_status = "🟢 Healthy"
            elif health_percentage >= 60:
                health_status = "🟡 Warning"
            else:
                health_status = "🔴 Critical"
            
            text = (
                f"📊 **System Status** - {health_status}\n\n"
                f"🏥 **Health**: {health_percentage:.0f}% ({healthy_components}/{total_components})\n\n"
                f"📋 **Component Status:**\n"
                f"• Database: {'✅' if status_checks['database'] else '❌'}\n"
                f"• Firebase: {'✅' if status_checks['firebase'] else '❌'}\n"
                f"• Sessions Dir: {'✅' if status_checks['sessions_dir'] else '❌'}\n"
                f"• Environment: {'✅' if status_checks['env_vars'] else '❌'}\n"
                f"• Permissions: {'✅' if status_checks['permissions'] else '❌'}\n\n"
                f"⚙️ **Configuration:**\n"
                f"• API Configured: {'✅' if self.current_settings.get('api_id') != 'Not set' else '❌'}\n"
                f"• Admin Count: {len(self.admin_ids)}\n"
                f"• Maintenance Mode: {'🟡 Active' if self.current_settings.get('maintenance_mode') else '🟢 Inactive'}"
            )
        
        except Exception as e:
            logger.error(f"Error checking system status: {e}")
            text = "❌ **Error checking system status**\n\nUnable to retrieve system information."
        
        keyboard = [
            [
                InlineKeyboardButton(text="🔄 Refresh Status", callback_data="system_status"),
                InlineKeyboardButton(text="🛠️ Auto Fix Issues", callback_data="auto_fix_issues")
            ],
            [
                InlineKeyboardButton(text="📊 Detailed Report", callback_data="detailed_system_report"),
                InlineKeyboardButton(text="🚨 Emergency Reset", callback_data="emergency_reset")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin_bot_settings")
            ]
        ]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    def check_database_connection(self) -> bool:
        """Check if database is accessible"""
        try:
            self.database.get_all_users()
            return True
        except Exception:
            return False
    
    def check_firebase_connection(self) -> bool:
        """Check if Firebase is configured"""
        try:
            return os.path.exists('serviceAccountKey.json')
        except Exception:
            return False
    
    def check_sessions_directory(self) -> bool:
        """Check if sessions directory exists and is writable"""
        try:
            from sessions.session_paths import get_session_paths
            session_paths = get_session_paths()
            sessions_dir = session_paths.sessions_dir
            return os.path.exists(sessions_dir) and os.access(sessions_dir, os.W_OK)
        except ImportError as e:
            logger.error(f"Could not import session_paths: {e}")
            return False
        except OSError as e:
            logger.error(f"File system error checking sessions directory: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking sessions directory: {e}")
            return False
    
    def check_environment_variables(self) -> bool:
        """Check if critical environment variables are set"""
        try:
            required_vars = ['API_ID', 'API_HASH', 'BOT_TOKEN']
            return all(os.getenv(var) for var in required_vars)
        except Exception as e:
            logger.error(f"Error checking environment variables: {e}")
            return False
    
    def check_file_permissions(self) -> bool:
        """Check if bot has necessary file permissions"""
        try:
            # Check if we can create/write files
            test_file = 'test_permissions.tmp'
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            return True
        except PermissionError as e:
            logger.error(f"Permission error checking file permissions: {e}")
            return False
        except OSError as e:
            logger.error(f"File system error checking permissions: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error checking file permissions: {e}")
            return False
    
    async def handle_add_admin(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Handle add admin from main admin panel"""
        await self.add_admin_prompt(callback_query, state)
    
    def register_handlers(self, dp: Dispatcher):
        """Register bot settings handlers"""
        # Main menu
        dp.callback_query.register(
            self.show_settings_menu,
            F.data == "admin_bot_settings"
        )
        
        # API credentials
        dp.callback_query.register(
            self.show_api_credentials,
            F.data == "api_credentials"
        )
        
        dp.callback_query.register(
            self.set_api_id_prompt,
            F.data == "set_api_id"
        )
        
        dp.message.register(
            self.process_api_id,
            BotSettingsStates.waiting_api_id
        )
        
        dp.callback_query.register(
            self.set_api_hash_prompt,
            F.data == "set_api_hash"
        )
        
        dp.message.register(
            self.process_api_hash,
            BotSettingsStates.waiting_api_hash
        )
        
        # Global 2FA management
        dp.callback_query.register(
            self.show_global_2fa_settings,
            F.data == "global_2fa_settings"
        )
        
        dp.callback_query.register(
            self.prompt_change_global_2fa,
            F.data == "change_global_2fa"
        )
        
        dp.message.register(
            self.process_global_2fa_password,
            BotSettingsStates.waiting_global_2fa_password
        )
        
        dp.callback_query.register(
            self.remove_global_2fa,
            F.data == "remove_global_2fa"
        )
        
        dp.callback_query.register(
            self.confirm_remove_global_2fa,
            F.data == "confirm_remove_global_2fa"
        )
        
        # Admin management
        dp.callback_query.register(
            self.show_admin_management,
            F.data == "admin_management"
        )
        
        dp.callback_query.register(
            self.add_admin_prompt,
            F.data.in_(["add_admin_prompt", "admin_add_admin"])
        )
        
        dp.message.register(
            self.process_add_admin,
            BotSettingsStates.waiting_new_admin_id
        )
        
        # Withdrawal settings
        dp.callback_query.register(
            self.show_withdrawal_settings,
            F.data == "withdrawal_settings"
        )
        
        dp.callback_query.register(
            self.set_min_withdrawal_prompt,
            F.data == "set_min_withdrawal"
        )
        
        dp.message.register(
            self.process_min_withdrawal,
            BotSettingsStates.waiting_min_withdrawal
        )
        
        # System status
        dp.callback_query.register(
            self.show_system_status,
            F.data == "system_status"
        )