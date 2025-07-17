"""
Admin Reporting Settings Module

Handles the configuration interface for the reporting system in the admin panel.
Allows admins to configure all reporting channels and settings.
"""

import logging
from typing import List, Dict, Optional
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.database import Database
from reporting_system import ReportingSystem, ReportingStates
from admin.auth_service import AuthService

logger = logging.getLogger(__name__)


class AdminReportingSettings:
    """Admin module for reporting system configuration"""
    
    def __init__(self, bot: Bot, database: Database, reporting_system: ReportingSystem, admin_ids: List[int]):
        self.bot = bot
        self.database = database
        self.reporting_system = reporting_system
        self.admin_ids = admin_ids
        self.auth_service = AuthService(database, admin_ids)
    
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
    
    async def show_reporting_settings(self, callback_query: types.CallbackQuery):
        """Show main reporting system settings menu"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        settings = self.reporting_system.settings
        
        keyboard = [
            [
                InlineKeyboardButton(text="📊 Group Settings", callback_data="reporting_group_settings"),
                InlineKeyboardButton(text="⚙️ System Settings", callback_data="reporting_system_settings")
            ],
            [
                InlineKeyboardButton(text="💾 Backup Settings", callback_data="reporting_backup_settings"),
                InlineKeyboardButton(text="📈 Test Reporting", callback_data="reporting_test")
            ],
            [
                InlineKeyboardButton(
                    text=f"{'🟢 Enabled' if settings.get('enabled') else '🔴 Disabled'}",
                    callback_data="reporting_toggle_enabled"
                )
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Bot Settings", callback_data="admin_bot_settings")
            ]
        ]
        
        text = (
            "📊 **Reporting System Configuration**\n\n"
            f"**Status:** {'🟢 Enabled' if settings.get('enabled') else '🔴 Disabled'}\n\n"
            f"**Configured Channels:**\n"
            f"• Errors Chat: {'✅' if settings.get('errors_chat_id') else '❌'}\n"
            f"• Users Chat: {'✅' if settings.get('users_chat_id') else '❌'}\n"
            f"• Bought Accounts: {'✅' if settings.get('bought_accounts_chat_id') else '❌'}\n"
            f"• Reports Chat: {'✅' if settings.get('reports_chat_id') else '❌'}\n"
            f"• Control Room: {'✅' if settings.get('control_room_chat_id') else '❌'}\n"
            f"• Backup Chat: {'✅' if settings.get('backup_chat_id') else '❌'}\n\n"
            f"**Settings:**\n"
            f"• Backup Interval: {settings.get('backup_interval_minutes', 60)} minutes\n"
            f"• Daily Report Time: {settings.get('daily_report_time', '00:00')}\n\n"
            "Select an option to configure:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def show_group_settings(self, callback_query: types.CallbackQuery):
        """Show group/chat configuration settings"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        settings = self.reporting_system.settings
        
        keyboard = [
            [
                InlineKeyboardButton(text="🚨 Edit Errors Chat ID", callback_data="reporting_edit_errors_chat"),
                InlineKeyboardButton(text="👥 Edit Users Chat ID", callback_data="reporting_edit_users_chat")
            ],
            [
                InlineKeyboardButton(text="💰 Edit Bought Accounts Chat", callback_data="reporting_edit_bought_chat"),
                InlineKeyboardButton(text="📈 Edit Reports Chat ID", callback_data="reporting_edit_reports_chat")
            ],
            [
                InlineKeyboardButton(text="🎛️ Edit Control Room Chat", callback_data="reporting_edit_control_chat"),
                InlineKeyboardButton(text="💾 Edit Backup Chat ID", callback_data="reporting_edit_backup_chat")
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Reporting Settings", callback_data="reporting_settings")
            ]
        ]
        
        text = (
            "📊 **Group/Chat Configuration**\n\n"
            f"**Current Settings:**\n\n"
            f"🚨 **Errors Chat ID:**\n"
            f"`{settings.get('errors_chat_id', 'Not set')}`\n"
            f"_Bot errors and exceptions_\n\n"
            f"👥 **Users Chat ID:**\n"
            f"`{settings.get('users_chat_id', 'Not set')}`\n"
            f"_New user interactions_\n\n"
            f"💰 **Bought Accounts Chat ID:**\n"
            f"`{settings.get('bought_accounts_chat_id', 'Not set')}`\n"
            f"_Account purchase notifications_\n\n"
            f"📈 **Reports Chat ID:**\n"
            f"`{settings.get('reports_chat_id', 'Not set')}`\n"
            f"_Daily reports and statistics_\n\n"
            f"🎛️ **Control Room Chat ID:**\n"
            f"`{settings.get('control_room_chat_id', 'Not set')}`\n"
            f"_Admin commands and manual approvals_\n\n"
            f"💾 **Backup Chat ID:**\n"
            f"`{settings.get('backup_chat_id', 'Not set')}`\n"
            f"_Automated backups_\n\n"
            "Click a button to edit the corresponding chat ID."
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def show_system_settings(self, callback_query: types.CallbackQuery):
        """Show system configuration settings"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        settings = self.reporting_system.settings
        
        keyboard = [
            [
                InlineKeyboardButton(text="⏰ Edit Daily Report Time", callback_data="reporting_edit_report_time"),
                InlineKeyboardButton(text="📊 View Current Stats", callback_data="reporting_view_stats")
            ],
            [
                InlineKeyboardButton(text="🔄 Reset Statistics", callback_data="reporting_reset_stats"),
                InlineKeyboardButton(text="🧹 Clear All Settings", callback_data="reporting_clear_settings")
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Reporting Settings", callback_data="reporting_settings")
            ]
        ]
        
        text = (
            "⚙️ **System Configuration**\n\n"
            f"**Current Settings:**\n\n"
            f"⏰ **Daily Report Time:** {settings.get('daily_report_time', '00:00')}\n"
            f"📊 **System Status:** {'🟢 Active' if settings.get('enabled') else '🔴 Inactive'}\n\n"
            f"**Statistics Today:**\n"
            f"• Users Interacted: {len(self.reporting_system.daily_stats['users_interacted'])}\n"
            f"• New Users: {len(self.reporting_system.daily_stats['new_users'])}\n"
            f"• Accounts Bought: {len(self.reporting_system.daily_stats['accounts_bought'])}\n"
            f"• Errors Occurred: {len(self.reporting_system.daily_stats['errors_occurred'])}\n"
            f"• Balance Added: ${self.reporting_system.daily_stats['balance_added']:.2f}\n\n"
            "Select an option to configure:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def show_backup_settings(self, callback_query: types.CallbackQuery):
        """Show backup configuration settings"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        settings = self.reporting_system.settings
        
        keyboard = [
            [
                InlineKeyboardButton(text="⏱️ Edit Backup Interval", callback_data="reporting_edit_backup_interval"),
                InlineKeyboardButton(text="💾 Test Backup Now", callback_data="reporting_test_backup")
            ],
            [
                InlineKeyboardButton(text="📁 Backup Statistics", callback_data="reporting_backup_stats"),
                InlineKeyboardButton(text="🗑️ Disable Backups", callback_data="reporting_disable_backups")
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Reporting Settings", callback_data="reporting_settings")
            ]
        ]
        
        backup_interval = settings.get('backup_interval_minutes', 60)
        hours = backup_interval // 60
        minutes = backup_interval % 60
        
        interval_text = ""
        if hours > 0:
            interval_text += f"{hours} hour{'s' if hours != 1 else ''}"
        if minutes > 0:
            if interval_text:
                interval_text += f" {minutes} minute{'s' if minutes != 1 else ''}"
            else:
                interval_text = f"{minutes} minute{'s' if minutes != 1 else ''}"
        
        text = (
            "💾 **Backup Configuration**\n\n"
            f"**Current Settings:**\n\n"
            f"⏱️ **Backup Interval:** {interval_text}\n"
            f"💾 **Backup Chat:** {'✅ Configured' if settings.get('backup_chat_id') else '❌ Not set'}\n"
            f"📁 **Auto Backup:** {'🟢 Enabled' if settings.get('backup_chat_id') else '🔴 Disabled'}\n\n"
            f"**Backup Contents:**\n"
            f"• Session files (pending, approved, rejected)\n"
            f"• Account folders with metadata\n"
            f"• System statistics\n"
            f"• Backup metadata and README\n\n"
            f"**Backup Schedule:**\n"
            f"• Interval: Every {interval_text}\n"
            f"• Format: ZIP archive\n"
            f"• Encryption: File-level security\n\n"
            "Select an option to configure:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def toggle_reporting_enabled(self, callback_query: types.CallbackQuery):
        """Toggle reporting system enabled/disabled"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        current_enabled = self.reporting_system.settings.get('enabled', True)
        new_enabled = not current_enabled
        
        self.reporting_system.settings['enabled'] = new_enabled
        self.reporting_system.save_settings(self.reporting_system.settings)
        
        status = "enabled" if new_enabled else "disabled"
        await callback_query.answer(f"✅ Reporting system {status}", show_alert=True)
        
        # Refresh the main settings menu
        await self.show_reporting_settings(callback_query)
    
    async def edit_chat_id_prompt(self, callback_query: types.CallbackQuery, state: FSMContext, chat_type: str):
        """Prompt for editing a chat ID"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        chat_names = {
            'errors': 'Errors Chat',
            'users': 'Users Chat',
            'bought': 'Bought Accounts Chat',
            'reports': 'Reports Chat',
            'control': 'Control Room Chat',
            'backup': 'Backup Chat'
        }
        
        chat_name = chat_names.get(chat_type, 'Chat')
        current_id = self.reporting_system.settings.get(f'{chat_type}_chat_id')
        
        text = (
            f"✏️ **Edit {chat_name} ID**\n\n"
            f"**Current ID:** `{current_id or 'Not set'}`\n\n"
            f"**Instructions:**\n"
            f"1. Add your bot to the target group/channel\n"
            f"2. Make sure the bot has admin permissions\n"
            f"3. Send the chat ID (can be negative for groups)\n"
            f"4. Use @userinfobot to get chat ID if needed\n\n"
            f"**Examples:**\n"
            f"• Group: `-1001234567890`\n"
            f"• Channel: `-1001234567890`\n"
            f"• Private chat: `123456789`\n\n"
            f"Send the new chat ID or /cancel to abort:"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="reporting_group_settings")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        # Set appropriate state
        state_mapping = {
            'errors': ReportingStates.waiting_errors_chat_id,
            'users': ReportingStates.waiting_users_chat_id,
            'bought': ReportingStates.waiting_bought_accounts_chat_id,
            'reports': ReportingStates.waiting_reports_chat_id,
            'control': ReportingStates.waiting_control_room_chat_id,
            'backup': ReportingStates.waiting_backup_chat_id
        }
        
        await state.set_state(state_mapping[chat_type])
        await state.update_data(chat_type=chat_type)
    
    async def process_chat_id_input(self, message: types.Message, state: FSMContext):
        """Process chat ID input"""
        if not self.is_admin(message.from_user.id):
            await message.reply("❌ Access denied")
            return
        
        if message.text == '/cancel':
            await state.clear()
            await message.reply("❌ Operation cancelled")
            return
        
        try:
            chat_id = int(message.text.strip())
            data = await state.get_data()
            chat_type = data.get('chat_type')
            
            if not chat_type:
                await message.reply("❌ Error: Chat type not found")
                await state.clear()
                return
            
            # Test the chat ID by trying to send a test message
            try:
                test_message = await self.bot.send_message(
                    chat_id=chat_id,
                    text="✅ **Bot Configuration Test**\n\nThis is a test message to verify the bot can send messages to this chat.\n\nThe reporting system is now configured for this chat.",
                    parse_mode="Markdown"
                )
                
                # If successful, save the chat ID
                self.reporting_system.settings[f'{chat_type}_chat_id'] = chat_id
                self.reporting_system.save_settings(self.reporting_system.settings)
                
                chat_names = {
                    'errors': 'Errors Chat',
                    'users': 'Users Chat', 
                    'bought': 'Bought Accounts Chat',
                    'reports': 'Reports Chat',
                    'control': 'Control Room Chat',
                    'backup': 'Backup Chat'
                }
                
                await message.reply(
                    f"✅ **{chat_names[chat_type]} Configured**\n\n"
                    f"Chat ID `{chat_id}` has been saved successfully.\n"
                    f"Test message sent to verify connectivity.",
                    parse_mode="Markdown"
                )
                
                logger.info(f"Admin {message.from_user.id} configured {chat_type} chat ID: {chat_id}")
                
            except Exception as e:
                await message.reply(
                    f"❌ **Configuration Failed**\n\n"
                    f"Unable to send message to chat ID `{chat_id}`.\n\n"
                    f"**Possible issues:**\n"
                    f"• Bot is not added to the chat\n"
                    f"• Bot lacks admin permissions\n"
                    f"• Invalid chat ID\n"
                    f"• Chat doesn't exist\n\n"
                    f"**Error:** {str(e)}"
                )
                
        except ValueError:
            await message.reply("❌ Invalid chat ID format. Please enter a valid number.")
            return
        
        await state.clear()
    
    async def edit_backup_interval_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for editing backup interval"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        current_interval = self.reporting_system.settings.get('backup_interval_minutes', 60)
        
        text = (
            f"⏱️ **Edit Backup Interval**\n\n"
            f"**Current Interval:** {current_interval} minutes\n\n"
            f"**Instructions:**\n"
            f"Enter the backup interval in minutes.\n\n"
            f"**Examples:**\n"
            f"• `60` - Every hour\n"
            f"• `120` - Every 2 hours\n"
            f"• `360` - Every 6 hours\n"
            f"• `1440` - Every 24 hours\n\n"
            f"**Recommended:** 60-360 minutes\n"
            f"**Minimum:** 30 minutes\n"
            f"**Maximum:** 1440 minutes (24 hours)\n\n"
            f"Send the new interval in minutes:"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="reporting_backup_settings")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(ReportingStates.waiting_backup_interval)
    
    async def process_backup_interval_input(self, message: types.Message, state: FSMContext):
        """Process backup interval input"""
        if not self.is_admin(message.from_user.id):
            await message.reply("❌ Access denied")
            return
        
        if message.text == '/cancel':
            await state.clear()
            await message.reply("❌ Operation cancelled")
            return
        
        try:
            interval = int(message.text.strip())
            
            if interval < 30:
                await message.reply("❌ Minimum interval is 30 minutes")
                return
            
            if interval > 1440:
                await message.reply("❌ Maximum interval is 1440 minutes (24 hours)")
                return
            
            self.reporting_system.settings['backup_interval_minutes'] = interval
            self.reporting_system.save_settings(self.reporting_system.settings)
            
            hours = interval // 60
            minutes = interval % 60
            
            interval_text = ""
            if hours > 0:
                interval_text += f"{hours} hour{'s' if hours != 1 else ''}"
            if minutes > 0:
                if interval_text:
                    interval_text += f" {minutes} minute{'s' if minutes != 1 else ''}"
                else:
                    interval_text = f"{minutes} minute{'s' if minutes != 1 else ''}"
            
            await message.reply(
                f"✅ **Backup Interval Updated**\n\n"
                f"New interval: {interval_text}\n"
                f"Backups will be sent every {interval_text}.",
                parse_mode="Markdown"
            )
            
            logger.info(f"Admin {message.from_user.id} updated backup interval to {interval} minutes")
            
        except ValueError:
            await message.reply("❌ Invalid interval format. Please enter a number.")
            return
        
        await state.clear()
    
    async def test_backup_now(self, callback_query: types.CallbackQuery):
        """Send a test backup immediately"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        await callback_query.answer("🔄 Creating test backup...", show_alert=True)
        
        try:
            await self.reporting_system.send_backup()
            await callback_query.message.reply("✅ Test backup sent successfully!")
        except Exception as e:
            await callback_query.message.reply(f"❌ Test backup failed: {str(e)}")
            await self.reporting_system.report_error(e, "Test backup", callback_query.from_user.id)
    
    async def test_reporting_system(self, callback_query: types.CallbackQuery):
        """Test all reporting functions"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        await callback_query.answer("🧪 Running reporting tests...", show_alert=True)
        
        results = []
        
        # Test error reporting
        try:
            test_error = Exception("Test error for reporting system")
            await self.reporting_system.report_error(test_error, "Test context", callback_query.from_user.id)
            results.append("✅ Error reporting")
        except Exception as e:
            results.append(f"❌ Error reporting: {str(e)}")
        
        # Test user reporting
        try:
            await self.reporting_system.report_new_user(callback_query.from_user)
            results.append("✅ User reporting")
        except Exception as e:
            results.append(f"❌ User reporting: {str(e)}")
        
        # Test manual approval needed
        try:
            await self.reporting_system.report_manual_approval_needed(
                "+1234567890", "US", callback_query.from_user.id, "Test approval needed"
            )
            results.append("✅ Manual approval reporting")
        except Exception as e:
            results.append(f"❌ Manual approval reporting: {str(e)}")
        
        # Test daily report
        try:
            await self.reporting_system.send_daily_report()
            results.append("✅ Daily report")
        except Exception as e:
            results.append(f"❌ Daily report: {str(e)}")
        
        test_results = "\n".join(results)
        
        await callback_query.message.reply(
            f"🧪 **Reporting System Test Results**\n\n{test_results}",
            parse_mode="Markdown"
        )
    
    def register_handlers(self, dp: Dispatcher):
        """Register reporting settings handlers"""
        # Main reporting settings
        dp.callback_query.register(
            self.show_reporting_settings,
            F.data == "reporting_settings"
        )
        
        # Toggle enabled
        dp.callback_query.register(
            self.toggle_reporting_enabled,
            F.data == "reporting_toggle_enabled"
        )
        
        # Group settings
        dp.callback_query.register(
            self.show_group_settings,
            F.data == "reporting_group_settings"
        )
        
        # System settings
        dp.callback_query.register(
            self.show_system_settings,
            F.data == "reporting_system_settings"
        )
        
        # Backup settings
        dp.callback_query.register(
            self.show_backup_settings,
            F.data == "reporting_backup_settings"
        )
        
        # Edit chat IDs
        dp.callback_query.register(
            lambda cq, state: self.edit_chat_id_prompt(cq, state, 'errors'),
            F.data == "reporting_edit_errors_chat"
        )
        
        dp.callback_query.register(
            lambda cq, state: self.edit_chat_id_prompt(cq, state, 'users'),
            F.data == "reporting_edit_users_chat"
        )
        
        dp.callback_query.register(
            lambda cq, state: self.edit_chat_id_prompt(cq, state, 'bought'),
            F.data == "reporting_edit_bought_chat"
        )
        
        dp.callback_query.register(
            lambda cq, state: self.edit_chat_id_prompt(cq, state, 'reports'),
            F.data == "reporting_edit_reports_chat"
        )
        
        dp.callback_query.register(
            lambda cq, state: self.edit_chat_id_prompt(cq, state, 'control'),
            F.data == "reporting_edit_control_chat"
        )
        
        dp.callback_query.register(
            lambda cq, state: self.edit_chat_id_prompt(cq, state, 'backup'),
            F.data == "reporting_edit_backup_chat"
        )
        
        # Edit backup interval
        dp.callback_query.register(
            self.edit_backup_interval_prompt,
            F.data == "reporting_edit_backup_interval"
        )
        
        # Test functions
        dp.callback_query.register(
            self.test_backup_now,
            F.data == "reporting_test_backup"
        )
        
        dp.callback_query.register(
            self.test_reporting_system,
            F.data == "reporting_test"
        )
        
        # Process input handlers
        dp.message.register(
            self.process_chat_id_input,
            ReportingStates.waiting_errors_chat_id
        )
        
        dp.message.register(
            self.process_chat_id_input,
            ReportingStates.waiting_users_chat_id
        )
        
        dp.message.register(
            self.process_chat_id_input,
            ReportingStates.waiting_bought_accounts_chat_id
        )
        
        dp.message.register(
            self.process_chat_id_input,
            ReportingStates.waiting_reports_chat_id
        )
        
        dp.message.register(
            self.process_chat_id_input,
            ReportingStates.waiting_control_room_chat_id
        )
        
        dp.message.register(
            self.process_chat_id_input,
            ReportingStates.waiting_backup_chat_id
        )
        
        dp.message.register(
            self.process_backup_interval_input,
            ReportingStates.waiting_backup_interval
        )