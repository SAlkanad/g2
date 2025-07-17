"""
Admin Users Management Module

Handles all user-related administrative functions including:
- User search and management
- Ban/unban users
- User statistics and reporting
- Balance management
- Admin promotion/demotion
- User activity monitoring
"""

import logging
from typing import List, Dict, Optional
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.database import Database
from notification_service import NotificationService
from admin.auth_service import AuthService
from languages.languages import get_text

logger = logging.getLogger(__name__)


class UserStates(StatesGroup):
    """FSM states for user management"""
    waiting_user_search = State()
    waiting_ban_user_id = State()
    waiting_ban_reason = State()
    waiting_unban_user_id = State()
    waiting_balance_adjustment = State()
    waiting_admin_promotion = State()


class AdminUsers:
    """Admin module for user management"""
    
    def __init__(self, bot: Bot, database: Database, admin_ids: List[int]):
        self.bot = bot
        self.database = database
        self.admin_ids = admin_ids
        self.auth_service = AuthService(database, admin_ids)
        self.notification_service = NotificationService(bot, database)
        
        # Pagination settings
        self.users_per_page = 15
    
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
    
    async def show_users_menu(self, callback_query: types.CallbackQuery):
        """Show main users management menu"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        # Get user statistics
        all_users = self.database.get_all_users()
        total_users = len(all_users) if all_users else 0
        banned_users = sum(1 for user in all_users if user.get('banned', False)) if all_users else 0
        admin_users = sum(1 for user in all_users if user.get('is_admin', False)) if all_users else 0
        active_users = total_users - banned_users
        
        # Calculate total balance
        total_balance = sum(user.get('balance', 0) for user in all_users) if all_users else 0
        
        keyboard = [
            [
                InlineKeyboardButton(text="👥 View All Users", callback_data="view_all_users"),
                InlineKeyboardButton(text="🔍 Search User", callback_data="search_user")
            ],
            [
                InlineKeyboardButton(text="🚫 Ban User", callback_data="ban_user"),
                InlineKeyboardButton(text="✅ Unban User", callback_data="unban_user")
            ],
            [
                InlineKeyboardButton(text="💰 Balance Management", callback_data="balance_management"),
                InlineKeyboardButton(text="👑 Admin Management", callback_data="admin_management")
            ],
            [
                InlineKeyboardButton(text="📊 User Statistics", callback_data="user_statistics"),
                InlineKeyboardButton(text="📈 Activity Report", callback_data="user_activity_report")
            ],
            [
                InlineKeyboardButton(text="🚫 Banned Users", callback_data="view_banned_users"),
                InlineKeyboardButton(text="👑 Admin Users", callback_data="view_admin_users")
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Admin Panel", callback_data="admin_panel")
            ]
        ]
        
        text = (
            "👥 **Users Management**\n\n"
            f"📊 **Overview:**\n"
            f"• Total Users: {total_users}\n"
            f"• Active Users: {active_users}\n"
            f"• Banned Users: {banned_users}\n"
            f"• Admin Users: {admin_users}\n"
            f"• Total Balance: ${total_balance:.2f}\n\n"
            "Select an action:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def view_all_users(self, callback_query: types.CallbackQuery, page: int = 1):
        """View all users with pagination"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        # Handle pagination
        if callback_query.data.startswith('users_page'):
            page = int(callback_query.data.split('_')[-1])
        
        all_users = self.database.get_all_users()
        
        if not all_users:
            text = "📭 **No Users Found**\n\nNo users are registered in the system."
            keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="admin_users")]]
        else:
            # Calculate pagination
            total_users = len(all_users)
            total_pages = (total_users + self.users_per_page - 1) // self.users_per_page
            start_idx = (page - 1) * self.users_per_page
            end_idx = start_idx + self.users_per_page
            page_users = all_users[start_idx:end_idx]
            
            text = f"👥 **All Users** (Page {page}/{total_pages})\n\n"
            
            for i, user in enumerate(page_users, start_idx + 1):
                user_id = user.get('user_id', 'Unknown')
                username = user.get('username', 'No username')
                first_name = user.get('first_name', 'Unknown')
                balance = user.get('balance', 0)
                is_admin = user.get('is_admin', False)
                banned = user.get('banned', False)
                
                # Status indicators
                status_indicators = []
                if is_admin:
                    status_indicators.append("👑")
                if banned:
                    status_indicators.append("🚫")
                
                status_text = " ".join(status_indicators) if status_indicators else "👤"
                
                text += (
                    f"**{i}.** {status_text} `{user_id}`\n"
                    f"   📝 {first_name} (@{username})\n"
                    f"   💰 ${balance:.2f}\n\n"
                )
            
            # Build pagination keyboard
            keyboard = []
            nav_buttons = []
            
            if page > 1:
                nav_buttons.append(
                    InlineKeyboardButton(text="⬅️ Previous", callback_data=f"users_page_{page-1}")
                )
            if page < total_pages:
                nav_buttons.append(
                    InlineKeyboardButton(text="➡️ Next", callback_data=f"users_page_{page+1}")
                )
            
            if nav_buttons:
                keyboard.append(nav_buttons)
            
            keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_users")])
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def search_user_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for user search"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        text = (
            "🔍 **Search User**\n\n"
            "Enter search criteria:\n\n"
            "**Search Options:**\n"
            "• User ID (e.g., 123456789)\n"
            "• Username (e.g., @username or username)\n"
            "• First name (e.g., John)\n\n"
            "Enter your search term:"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="admin_users")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(UserStates.waiting_user_search)
    
    async def process_user_search(self, message: types.Message, state: FSMContext):
        """Process user search"""
        if not self.is_admin(message.from_user.id):
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("access_denied", user_language))
            return
        
        try:
            search_term = message.text.strip().lower()
            
            if not search_term:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                return
            
            # Search users
            all_users = self.database.get_all_users()
            results = []
            
            for user in all_users:
                user_id = str(user.get('user_id', ''))
                username = user.get('username', '').lower()
                first_name = user.get('first_name', '').lower()
                
                if (search_term in user_id or 
                    search_term in username or 
                    search_term in first_name or
                    search_term.replace('@', '') in username):
                    results.append(user)
            
            if not results:
                text = f"🔍 **Search Results**\n\nNo users found for: `{search_term}`"
            else:
                text = f"🔍 **Search Results** ({len(results)} found)\n\n"
                
                for i, user in enumerate(results[:10], 1):  # Limit to 10 results
                    user_id = user.get('user_id', 'Unknown')
                    username = user.get('username', 'No username')
                    first_name = user.get('first_name', 'Unknown')
                    balance = user.get('balance', 0)
                    is_admin = user.get('is_admin', False)
                    banned = user.get('banned', False)
                    
                    # Status indicators
                    status_indicators = []
                    if is_admin:
                        status_indicators.append("👑 Admin")
                    if banned:
                        status_indicators.append("🚫 Banned")
                    
                    status_text = " | ".join(status_indicators) if status_indicators else "👤 User"
                    
                    text += (
                        f"**{i}.** `{user_id}`\n"
                        f"   📝 {first_name} (@{username})\n"
                        f"   💰 ${balance:.2f} | {status_text}\n\n"
                    )
                
                if len(results) > 10:
                    text += f"... and {len(results) - 10} more results"
            
            # Add action buttons for found users
            keyboard = []
            if results:
                for user in results[:3]:  # Limit action buttons
                    user_id = user.get('user_id')
                    if user_id:
                        keyboard.append([
                            InlineKeyboardButton(
                                text=f"👤 Manage {user_id}", 
                                callback_data=f"manage_user_{user_id}"
                            )
                        ])
            
            keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_users")])
            
            await message.reply(
                text, 
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
        
        except Exception as e:
            logger.error(f"Error searching users: {e}")
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("error", user_language))
        
        await state.clear()
    
    async def manage_specific_user(self, callback_query: types.CallbackQuery):
        """Show management options for specific user"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        user_id = int(callback_query.data.split('_')[-1])
        user_data = self.database.get_user(user_id)
        
        if not user_data:
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("user_not_found", user_language), show_alert=True)
            return
        
        username = user_data.get('username', 'No username')
        first_name = user_data.get('first_name', 'Unknown')
        balance = user_data.get('balance', 0)
        is_admin = user_data.get('is_admin', False)
        banned = user_data.get('banned', False)
        sessions_count = self.database.get_user_sessions_count(user_id)
        
        keyboard = [
            [
                InlineKeyboardButton(text="💰 Adjust Balance", callback_data=f"adjust_balance_{user_id}"),
                InlineKeyboardButton(text="📊 View Sessions", callback_data=f"user_sessions_{user_id}")
            ]
        ]
        
        if banned:
            keyboard.append([
                InlineKeyboardButton(text="✅ Unban User", callback_data=f"unban_specific_{user_id}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(text="🚫 Ban User", callback_data=f"ban_specific_{user_id}")
            ])
        
        if is_admin:
            keyboard.append([
                InlineKeyboardButton(text="👤 Demote Admin", callback_data=f"demote_admin_{user_id}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(text="👑 Promote to Admin", callback_data=f"promote_admin_{user_id}")
            ])
        
        keyboard.extend([
            [
                InlineKeyboardButton(text="📩 Send Message", callback_data=f"message_user_{user_id}"),
                InlineKeyboardButton(text="📈 User Stats", callback_data=f"user_stats_{user_id}")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin_users")
            ]
        ])
        
        status_text = []
        if is_admin:
            status_text.append("👑 Admin")
        if banned:
            status_text.append("🚫 Banned")
        if not status_text:
            status_text.append("👤 Regular User")
        
        text = (
            f"👤 **User Management**\n\n"
            f"**User Details:**\n"
            f"• ID: `{user_id}`\n"
            f"• Name: {first_name}\n"
            f"• Username: @{username}\n"
            f"• Balance: ${balance:.2f}\n"
            f"• Status: {' | '.join(status_text)}\n"
            f"• Sessions: {sessions_count}\n\n"
            "Select an action:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def ban_user_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for user ID to ban"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        text = (
            "🚫 **Ban User**\n\n"
            "Enter the User ID to ban:\n\n"
            "⚠️ **Warning**: Banned users will:\n"
            "• Lose access to the bot\n"
            "• Cannot submit new sessions\n"
            "• Cannot withdraw funds\n\n"
            "Enter User ID:"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="admin_users")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(UserStates.waiting_ban_user_id)
    
    async def process_ban_user_id(self, message: types.Message, state: FSMContext):
        """Process ban user ID input"""
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
            
            # Check if user is already banned
            if user_data.get('banned', False):
                await message.reply(get_text("user_already_banned", user_language))
                return
            
            # Check if trying to ban another admin
            if user_data.get('is_admin', False):
                await message.reply(get_text("cannot_ban_admin", user_language))
                return
            
            # Prompt for ban reason
            text = (
                f"🚫 **Ban User: {user_id}**\n\n"
                f"**User Details:**\n"
                f"• Name: {user_data.get('first_name', 'Unknown')}\n"
                f"• Username: @{user_data.get('username', 'No username')}\n"
                f"• Balance: ${user_data.get('balance', 0):.2f}\n\n"
                "Please provide a reason for banning this user:"
            )
            
            keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="admin_users")]]
            
            await message.reply(
                text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
            )
            
            await state.update_data(ban_user_id=user_id)
            await state.set_state(UserStates.waiting_ban_reason)
        
        except ValueError:
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("invalid_user_id", user_language))
        except Exception as e:
            logger.error(f"Error processing ban user ID: {e}")
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("error_occurred", user_language, error=str(e)))
    
    async def process_ban_reason(self, message: types.Message, state: FSMContext):
        """Process ban reason and execute ban"""
        if not self.is_admin(message.from_user.id):
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("access_denied", user_language))
            return
        
        try:
            data = await state.get_data()
            user_id = data.get('ban_user_id')
            reason = message.text.strip()
            user_language = self.get_user_language(message.from_user.id)
            
            if not user_id:
                await message.reply(get_text("user_id_not_found", user_language))
                await state.clear()
                return
            
            if not reason:
                await message.reply(get_text("provide_ban_reason", user_language))
                return
            
            # Execute ban
            success = self.database.ban_user(user_id, reason)
            
            if success:
                # Notify user about ban
                try:
                    await self.bot.send_message(
                        user_id,
                        f"🚫 **Account Banned**\n\n"
                        f"Your account has been banned.\n"
                        f"Reason: {reason}\n\n"
                        f"If you believe this is a mistake, please contact support.",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass  # User might have blocked the bot
                
                await message.reply(
                    f"✅ **User Banned Successfully**\n\n"
                    f"👤 User ID: `{user_id}`\n"
                    f"🚫 Reason: {reason}",
                    parse_mode="Markdown"
                )
                
                # Log the action
                logger.info(f"Admin {message.from_user.id} banned user {user_id}: {reason}")
                
            else:
                await message.reply(get_text("failed_ban_user", user_language))
        
        except Exception as e:
            logger.error(f"Error banning user: {e}")
            await message.reply(get_text("error_occurred", user_language, error=str(e)))
        
        await state.clear()
    
    async def unban_user_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for user ID to unban"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        text = (
            "✅ **Unban User**\n\n"
            "Enter the User ID to unban:\n\n"
            "🔓 **Note**: Unbanned users will:\n"
            "• Regain full access to the bot\n"
            "• Be able to submit sessions again\n"
            "• Have access to their balance\n\n"
            "Enter User ID:"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="admin_users")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(UserStates.waiting_unban_user_id)
    
    async def process_unban_user(self, message: types.Message, state: FSMContext):
        """Process user unban"""
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
            
            # Check if user is actually banned
            if not user_data.get('banned', False):
                await message.reply(get_text("user_not_banned", user_language))
                return
            
            # Execute unban
            success = self.database.unban_user(user_id)
            
            if success:
                # Notify user about unban
                try:
                    await self.bot.send_message(
                        user_id,
                        f"✅ **Account Unbanned**\n\n"
                        f"Your account has been unbanned.\n"
                        f"You now have full access to the bot again.\n\n"
                        f"Welcome back!",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass  # User might have blocked the bot
                
                await message.reply(
                    f"✅ **User Unbanned Successfully**\n\n"
                    f"👤 User ID: `{user_id}`\n"
                    f"📝 Name: {user_data.get('first_name', 'Unknown')}",
                    parse_mode="Markdown"
                )
                
                # Log the action
                logger.info(f"Admin {message.from_user.id} unbanned user {user_id}")
                
            else:
                await message.reply(get_text("failed_unban_user", user_language))
        
        except ValueError:
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("invalid_user_id", user_language))
        except Exception as e:
            logger.error(f"Error unbanning user: {e}")
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("error_occurred", user_language, error=str(e)))
        
        await state.clear()
    
    async def view_banned_users(self, callback_query: types.CallbackQuery):
        """View all banned users"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        all_users = self.database.get_all_users()
        banned_users = [user for user in all_users if user.get('banned', False)] if all_users else []
        
        if not banned_users:
            text = "✅ **No Banned Users**\n\nNo users are currently banned."
        else:
            text = f"🚫 **Banned Users** ({len(banned_users)} total)\n\n"
            
            for i, user in enumerate(banned_users[:20], 1):  # Limit to 20
                user_id = user.get('user_id', 'Unknown')
                username = user.get('username', 'No username')
                first_name = user.get('first_name', 'Unknown')
                ban_reason = user.get('ban_reason', 'No reason provided')
                
                text += (
                    f"**{i}.** `{user_id}`\n"
                    f"   📝 {first_name} (@{username})\n"
                    f"   🚫 Reason: {ban_reason[:50]}...\n\n"
                )
            
            if len(banned_users) > 20:
                text += f"... and {len(banned_users) - 20} more banned users"
        
        keyboard = [
            [
                InlineKeyboardButton(text="✅ Unban User", callback_data="unban_user"),
                InlineKeyboardButton(text="🔄 Refresh", callback_data="view_banned_users")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin_users")
            ]
        ]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def view_admin_users(self, callback_query: types.CallbackQuery):
        """View all admin users"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        all_users = self.database.get_all_users()
        admin_users = [user for user in all_users if user.get('is_admin', False)] if all_users else []
        
        # Also include admin IDs from config
        config_admins = []
        for admin_id in self.admin_ids:
            if not any(user.get('user_id') == admin_id for user in admin_users):
                # Try to get user data for config admin
                user_data = self.database.get_user(admin_id)
                if user_data:
                    config_admins.append(user_data)
                else:
                    config_admins.append({
                        'user_id': admin_id,
                        'first_name': 'Config Admin',
                        'username': 'unknown',
                        'is_admin': True,
                        'from_config': True
                    })
        
        all_admins = admin_users + config_admins
        
        if not all_admins:
            text = "👑 **No Admin Users**\n\nNo admin users found."
        else:
            text = f"👑 **Admin Users** ({len(all_admins)} total)\n\n"
            
            for i, user in enumerate(all_admins, 1):
                user_id = user.get('user_id', 'Unknown')
                username = user.get('username', 'No username')
                first_name = user.get('first_name', 'Unknown')
                from_config = user.get('from_config', False)
                
                source = "📋 Config" if from_config else "💾 Database"
                
                text += (
                    f"**{i}.** 👑 `{user_id}`\n"
                    f"   📝 {first_name} (@{username})\n"
                    f"   🔧 Source: {source}\n\n"
                )
        
        keyboard = [
            [
                InlineKeyboardButton(text="➕ Add Admin", callback_data="promote_admin_prompt"),
                InlineKeyboardButton(text="🔄 Refresh", callback_data="view_admin_users")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin_users")
            ]
        ]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def show_user_statistics(self, callback_query: types.CallbackQuery):
        """Show detailed user statistics"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        try:
            all_users = self.database.get_all_users()
            
            if not all_users:
                text = "📭 **No User Data**\n\nNo users found in the database."
            else:
                total_users = len(all_users)
                banned_users = sum(1 for user in all_users if user.get('banned', False))
                admin_users = sum(1 for user in all_users if user.get('is_admin', False))
                active_users = total_users - banned_users
                
                # Calculate balance statistics
                balances = [user.get('balance', 0) for user in all_users]
                total_balance = sum(balances)
                avg_balance = total_balance / total_users if total_users > 0 else 0
                max_balance = max(balances) if balances else 0
                
                # Calculate session statistics
                total_sessions = 0
                users_with_sessions = 0
                for user in all_users:
                    user_sessions = self.database.get_user_sessions_count(user.get('user_id', 0))
                    total_sessions += user_sessions
                    if user_sessions > 0:
                        users_with_sessions += 1
                
                avg_sessions = total_sessions / total_users if total_users > 0 else 0
                
                text = (
                    "📊 **User Statistics**\n\n"
                    
                    f"👥 **User Counts:**\n"
                    f"• Total Users: {total_users}\n"
                    f"• Active Users: {active_users}\n"
                    f"• Banned Users: {banned_users}\n"
                    f"• Admin Users: {admin_users}\n\n"
                    
                    f"💰 **Balance Statistics:**\n"
                    f"• Total Balance: ${total_balance:.2f}\n"
                    f"• Average Balance: ${avg_balance:.2f}\n"
                    f"• Highest Balance: ${max_balance:.2f}\n\n"
                    
                    f"📱 **Session Statistics:**\n"
                    f"• Total Sessions: {total_sessions}\n"
                    f"• Users with Sessions: {users_with_sessions}\n"
                    f"• Avg Sessions per User: {avg_sessions:.1f}\n\n"
                    
                    f"📈 **Activity:**\n"
                    f"• Users with Balance: {sum(1 for b in balances if b > 0)}\n"
                    f"• Participation Rate: {(users_with_sessions/total_users*100):.1f}%\n"
                    f"• Admin Ratio: {(admin_users/total_users*100):.1f}%"
                )
        
        except Exception as e:
            logger.error(f"Error generating user statistics: {e}")
            text = "❌ **Error Loading Statistics**\n\nUnable to load user statistics. Please try again."
        
        keyboard = [
            [
                InlineKeyboardButton(text="🔄 Refresh", callback_data="user_statistics"),
                InlineKeyboardButton(text="📊 Export Data", callback_data="export_user_data")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin_users")
            ]
        ]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    def register_handlers(self, dp: Dispatcher):
        """Register user management handlers"""
        # Main menu
        dp.callback_query.register(
            self.show_users_menu,
            F.data == "admin_users"
        )
        
        # View users
        dp.callback_query.register(
            self.view_all_users,
            F.data.startswith("view_all_users") | F.data.startswith("users_page_")
        )
        
        # Search users
        dp.callback_query.register(
            self.search_user_prompt,
            F.data == "search_user"
        )
        
        dp.message.register(
            self.process_user_search,
            UserStates.waiting_user_search
        )
        
        # Manage specific user
        dp.callback_query.register(
            self.manage_specific_user,
            F.data.startswith("manage_user_")
        )
        
        # Ban/unban users
        dp.callback_query.register(
            self.ban_user_prompt,
            F.data == "ban_user"
        )
        
        dp.message.register(
            self.process_ban_user_id,
            UserStates.waiting_ban_user_id
        )
        
        dp.message.register(
            self.process_ban_reason,
            UserStates.waiting_ban_reason
        )
        
        dp.callback_query.register(
            self.unban_user_prompt,
            F.data == "unban_user"
        )
        
        dp.message.register(
            self.process_unban_user,
            UserStates.waiting_unban_user_id
        )
        
        # View banned/admin users
        dp.callback_query.register(
            self.view_banned_users,
            F.data == "view_banned_users"
        )
        
        dp.callback_query.register(
            self.view_admin_users,
            F.data == "view_admin_users"
        )
        
        # Statistics
        dp.callback_query.register(
            self.show_user_statistics,
            F.data == "user_statistics"
        )