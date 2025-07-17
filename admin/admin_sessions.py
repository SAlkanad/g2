"""
Admin Sessions Management Module

Handles all session-related administrative functions including:
- Session approval/rejection
- Session status management
- Session statistics and reporting
- Bulk session operations
- Session details and inspection
"""

import logging
import os
from typing import List, Dict, Optional
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.database import Database
from notification_service import NotificationService
from admin.auth_service import AuthService
from config_service import ConfigService
from languages.languages import get_text

logger = logging.getLogger(__name__)


class SessionStates(StatesGroup):
    """FSM states for session management"""
    waiting_rejection_reason = State()
    waiting_bulk_action_confirm = State()
    waiting_search_term = State()


class AdminSessions:
    """Admin module for session management"""
    
    def __init__(self, bot: Bot, database: Database, admin_ids: List[int], config_service: ConfigService = None):
        self.bot = bot
        self.database = database
        self.admin_ids = admin_ids
        self.auth_service = AuthService(database, admin_ids)
        self.config_service = config_service or ConfigService(database)
        
        # Import SellAccountSystem for session management
        from sellaccount import SellAccountSystem
        self.session_manager = SellAccountSystem(
            bot=bot,
            database=database,
            api_id=self.config_service.get_api_id(),
            api_hash=self.config_service.get_api_hash(),
            admin_chat_id=self.config_service.get_admin_chat_id() or '',
            reporting_system=None
        )
        self.notification_service = NotificationService(bot, database)
        
        # Pagination settings
        self.sessions_per_page = 10
    
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
    
    async def show_sessions_menu(self, callback_query: types.CallbackQuery):
        """Show main sessions management menu"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        # Get session statistics
        stats = self.session_manager.get_session_statistics()
        
        keyboard = [
            [
                InlineKeyboardButton(text="⏳ Pending Sessions", callback_data="view_sessions_pending"),
                InlineKeyboardButton(text="✅ Approved Sessions", callback_data="view_sessions_approved")
            ],
            [
                InlineKeyboardButton(text="❌ Rejected Sessions", callback_data="view_sessions_rejected"),
                InlineKeyboardButton(text="📦 Extracted Sessions", callback_data="view_sessions_extracted")
            ],
            [
                InlineKeyboardButton(text="🌍 Sessions by Country", callback_data="sessions_by_country"),
                InlineKeyboardButton(text="🔍 Search Session", callback_data="search_session")
            ],
            [
                InlineKeyboardButton(text="📊 Session Statistics", callback_data="session_detailed_stats"),
                InlineKeyboardButton(text="📋 Bulk Operations", callback_data="bulk_session_operations")
            ],
            [
                InlineKeyboardButton(text="🔄 Refresh Stats", callback_data="admin_sessions"),
                InlineKeyboardButton(text="🔙 Back to Admin Panel", callback_data="admin_panel")
            ]
        ]
        
        text = (
            "📋 **Sessions Management**\n\n"
            f"📊 **Quick Overview:**\n"
            f"• Pending: {stats.get('pending', 0)} sessions\n"
            f"• Approved: {stats.get('approved', 0)} sessions\n"
            f"• Rejected: {stats.get('rejected', 0)} sessions\n"
            f"• Extracted: {stats.get('extracted', {}).get('total', 0) if isinstance(stats.get('extracted'), dict) else 0} sessions\n"
            f"• Total: {stats.get('total', 0)} sessions\n\n"
            "Select an action:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def view_sessions_by_status(self, callback_query: types.CallbackQuery, page: int = 1):
        """View sessions filtered by status with pagination"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        # Extract status from callback data
        status = callback_query.data.split('_')[-1]
        if status.startswith('page'):
            # Handle pagination
            parts = callback_query.data.split('_')
            status = parts[-2]
            page = int(parts[-1].replace('page', ''))
        
        sessions = self.session_manager.get_sessions_by_status(status)
        
        if not sessions:
            text = f"📭 **No {status.title()} Sessions Found**\n\nNo sessions in {status} status."
            keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="admin_sessions")]]
        else:
            # Calculate pagination
            total_sessions = len(sessions)
            total_pages = (total_sessions + self.sessions_per_page - 1) // self.sessions_per_page
            start_idx = (page - 1) * self.sessions_per_page
            end_idx = start_idx + self.sessions_per_page
            page_sessions = sessions[start_idx:end_idx]
            
            # Build session list
            text = f"📋 **{status.title()} Sessions** (Page {page}/{total_pages})\n\n"
            
            for i, session in enumerate(page_sessions, start_idx + 1):
                phone = session.get('phone', 'Unknown')
                country = session.get('country', 'Unknown')
                created_at = session.get('created_at', 'Unknown')
                user_id = session.get('user_id', 'Unknown')
                
                # Get additional info based on status
                if status == 'pending':
                    extra_info = "⏳ Awaiting approval"
                elif status == 'approved':
                    extra_info = f"✅ User: {user_id}"
                elif status == 'rejected':
                    reason = session.get('rejection_reason', 'No reason provided')
                    extra_info = f"❌ Reason: {reason[:30]}..."
                else:
                    extra_info = f"📦 Extracted"
                
                text += (
                    f"**{i}.** `{phone}` ({country})\n"
                    f"   {extra_info}\n"
                    f"   📅 {created_at}\n\n"
                )
            
            # Build keyboard
            keyboard = []
            
            # Session action buttons for pending sessions
            if status == 'pending' and page_sessions:
                session_buttons = []
                for session in page_sessions[:5]:  # Limit to 5 sessions per row
                    phone = session.get('phone', 'Unknown')
                    session_buttons.append([
                        InlineKeyboardButton(text=f"✅ {phone}", callback_data=f"approve_session_{phone}"),
                        InlineKeyboardButton(text=f"❌ {phone}", callback_data=f"reject_session_{phone}")
                    ])
                keyboard.extend(session_buttons)
            
            # Pagination buttons
            nav_buttons = []
            if page > 1:
                nav_buttons.append(
                    InlineKeyboardButton(text="⬅️ Previous", callback_data=f"view_sessions_{status}_page{page-1}")
                )
            if page < total_pages:
                nav_buttons.append(
                    InlineKeyboardButton(text="➡️ Next", callback_data=f"view_sessions_{status}_page{page+1}")
                )
            
            if nav_buttons:
                keyboard.append(nav_buttons)
            
            # Status-specific actions
            if status == 'pending':
                keyboard.append([
                    InlineKeyboardButton(text="✅ Approve All", callback_data=f"bulk_approve_{status}"),
                    InlineKeyboardButton(text="❌ Reject All", callback_data=f"bulk_reject_{status}")
                ])
            
            keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_sessions")])
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def approve_session(self, callback_query: types.CallbackQuery):
        """Approve a specific session"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        phone = callback_query.data.split('_')[-1]
        user_language = self.get_user_language(callback_query.from_user.id)
        
        try:
            # Get session info
            session_info = self.session_manager.get_session_info(phone, 'pending')
            if not session_info:
                await callback_query.answer(get_text("session_not_found", user_language), show_alert=True)
                return
            
            # Approve session
            success = self.session_manager.approve_session(phone)
            
            if success:
                # Update database
                self.database.update_session_status(phone, 'approved')
                
                # Notify user
                user_id = session_info.get('user_id')
                if user_id:
                    await self.notification_service.notify_session_approved(user_id, phone)
                
                await callback_query.answer(get_text("session_approved", user_language, phone=phone), show_alert=True)
                
                # Log the action
                logger.info(f"Admin {callback_query.from_user.id} approved session {phone}")
                
                # Refresh the view
                await self.view_sessions_by_status(callback_query)
            else:
                await callback_query.answer(get_text("failed_approve_session", user_language), show_alert=True)
        
        except Exception as e:
            logger.error(f"Error approving session {phone}: {e}")
            await callback_query.answer(get_text("error_occurred", user_language), show_alert=True)
    
    async def reject_session_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for rejection reason"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        phone = callback_query.data.split('_')[-1]
        
        text = (
            f"❌ **Reject Session: {phone}**\n\n"
            "Please provide a reason for rejection:\n\n"
            "Common reasons:\n"
            "• Account frozen/restricted\n"
            "• Invalid phone number\n"
            "• 2FA enabled\n"
            "• Low quality session\n"
            "• Duplicate submission\n\n"
            "Enter your custom reason:"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="view_sessions_pending")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(SessionStates.waiting_rejection_reason)
        await state.update_data(phone=phone)
    
    async def process_rejection(self, message: types.Message, state: FSMContext):
        """Process session rejection with reason"""
        if not self.is_admin(message.from_user.id):
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("access_denied", user_language))
            return
        
        try:
            data = await state.get_data()
            phone = data.get('phone')
            reason = message.text.strip()
            user_language = self.get_user_language(message.from_user.id)
            
            if not phone:
                await message.reply(get_text("phone_not_found", user_language))
                await state.clear()
                return
            
            if not reason:
                await message.reply(get_text("provide_rejection_reason", user_language))
                return
            
            # Get session info
            session_info = self.session_manager.get_session_info(phone, 'pending')
            if not session_info:
                await message.reply(get_text("session_not_found", user_language))
                await state.clear()
                return
            
            # Reject session
            success = self.session_manager.reject_session(phone, reason)
            
            if success:
                # Update database
                self.database.update_session_status(phone, 'rejected', rejection_reason=reason)
                
                # Notify user
                user_id = session_info.get('user_id')
                if user_id:
                    await self.notification_service.notify_session_rejected(user_id, phone, reason)
                
                await message.reply(
                    f"✅ **Session Rejected**\n\n"
                    f"📱 Phone: `{phone}`\n"
                    f"❌ Reason: {reason}",
                    parse_mode="Markdown"
                )
                
                # Log the action
                logger.info(f"Admin {message.from_user.id} rejected session {phone}: {reason}")
                
            else:
                await message.reply(get_text("failed_reject_session", user_language))
        
        except Exception as e:
            logger.error(f"Error rejecting session: {e}")
            await message.reply(get_text("error_rejecting_session", user_language, error=str(e)))
        
        await state.clear()
    
    async def show_detailed_statistics(self, callback_query: types.CallbackQuery):
        """Show detailed session statistics"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        try:
            # Get comprehensive stats
            stats = self.session_manager.get_detailed_statistics()
            
            text = "📊 **Detailed Session Statistics**\n\n"
            
            # Overall stats
            text += f"📈 **Overall Statistics:**\n"
            text += f"• Total Sessions: {stats.get('total', 0)}\n"
            text += f"• Pending: {stats.get('pending', 0)}\n"
            text += f"• Approved: {stats.get('approved', 0)}\n"
            text += f"• Rejected: {stats.get('rejected', 0)}\n"
            extracted_total = stats.get('extracted', {}).get('total', 0) if isinstance(stats.get('extracted'), dict) else 0
            text += f"• Extracted: {extracted_total}\n\n"
            
            # Country breakdown
            if 'countries' in stats:
                text += f"🌍 **By Country:**\n"
                for country, count in stats['countries'].items():
                    text += f"• {country}: {count} sessions\n"
                text += "\n"
            
            # Daily stats
            if 'daily' in stats:
                text += f"📅 **Recent Activity:**\n"
                for date, count in list(stats['daily'].items())[-7:]:
                    text += f"• {date}: {count} sessions\n"
                text += "\n"
            
            # User stats
            if 'users' in stats:
                text += f"👥 **User Statistics:**\n"
                text += f"• Active Users: {stats['users'].get('active', 0)}\n"
                text += f"• Total Submissions: {stats['users'].get('total_submissions', 0)}\n"
                text += f"• Average per User: {stats['users'].get('average', 0):.1f}\n\n"
            
            # Performance metrics
            if 'performance' in stats:
                perf = stats['performance']
                text += f"⚡ **Performance Metrics:**\n"
                text += f"• Approval Rate: {perf.get('approval_rate', 0):.1f}%\n"
                text += f"• Rejection Rate: {perf.get('rejection_rate', 0):.1f}%\n"
                text += f"• Avg Processing Time: {perf.get('avg_processing_time', 'N/A')}\n"
        
        except Exception as e:
            logger.error(f"Error getting detailed statistics: {e}")
            user_language = self.get_user_language(callback_query.from_user.id)
            text = get_text("error_loading_sessions", user_language)
        
        keyboard = [
            [
                InlineKeyboardButton(text="🔄 Refresh", callback_data="session_detailed_stats"),
                InlineKeyboardButton(text="📊 Export Stats", callback_data="export_session_stats")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin_sessions")
            ]
        ]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def search_session(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Search for specific session"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        text = (
            "🔍 **Search Sessions**\n\n"
            "Enter search criteria:\n\n"
            "**Search Options:**\n"
            "• Phone number (e.g., +1234567890)\n"
            "• User ID (e.g., 123456789)\n"
            "• Country code (e.g., US)\n\n"
            "Enter your search term:"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="admin_sessions")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(SessionStates.waiting_search_term)
    
    async def process_search(self, message: types.Message, state: FSMContext):
        """Process session search"""
        if not self.is_admin(message.from_user.id):
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("access_denied", user_language))
            return
        
        try:
            search_term = message.text.strip()
            
            if not search_term:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                return
            
            # Search sessions
            results = self.session_manager.search_sessions(search_term)
            
            if not results:
                text = f"🔍 **Search Results**\n\nNo sessions found for: `{search_term}`"
            else:
                text = f"🔍 **Search Results** ({len(results)} found)\n\n"
                
                for i, session in enumerate(results[:20], 1):  # Limit to 20 results
                    phone = session.get('phone', 'Unknown')
                    status = session.get('status', 'Unknown')
                    country = session.get('country', 'Unknown')
                    user_id = session.get('user_id', 'Unknown')
                    created_at = session.get('created_at', 'Unknown')
                    
                    status_emoji = {
                        'pending': '⏳',
                        'approved': '✅',
                        'rejected': '❌',
                        'extracted': '📦'
                    }.get(status, '❓')
                    
                    text += (
                        f"**{i}.** `{phone}` {status_emoji}\n"
                        f"   🌍 {country} | 👤 {user_id}\n"
                        f"   📅 {created_at}\n\n"
                    )
                
                if len(results) > 20:
                    text += f"... and {len(results) - 20} more results"
            
            await message.reply(text, parse_mode="Markdown")
        
        except Exception as e:
            logger.error(f"Error searching sessions: {e}")
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("error", user_language))
        
        await state.clear()
    
    async def sessions_by_country(self, callback_query: types.CallbackQuery):
        """Show sessions grouped by country"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        try:
            # Get all active countries
            countries = self.database.get_countries(active_only=True)
            
            if not countries:
                text = "❌ No active countries found"
                keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="admin_sessions")]]
            else:
                text = "🌍 **Sessions by Country**\n\n"
                text += "Select a country to view its sessions:\n\n"
                
                keyboard = []
                for country in countries:
                    country_code = country.get('country_code', 'XX')
                    country_name = country.get('country_name', 'Unknown')
                    session_count = self.database.get_country_session_count(country_code)
                    
                    if session_count > 0:
                        btn_text = f"🏳️ {country_name} ({session_count} sessions)"
                        keyboard.append([
                            InlineKeyboardButton(
                                text=btn_text,
                                callback_data=f"view_country_sessions_{country_code}"
                            )
                        ])
                
                if not keyboard:
                    text += "No sessions found for any country."
                    keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="admin_sessions")]]
                else:
                    keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_sessions")])
            
            await callback_query.message.edit_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="Markdown"
            )
        
        except Exception as e:
            logger.error(f"Error showing sessions by country: {e}")
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("error", user_language), show_alert=True)
    
    async def view_country_sessions(self, callback_query: types.CallbackQuery):
        """View sessions for a specific country"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        try:
            country_code = callback_query.data.split('_')[-1]
            
            # Get country info
            countries = self.database.get_countries()
            country = next((c for c in countries if c.get('country_code') == country_code), None)
            
            if not country:
                user_language = self.get_user_language(callback_query.from_user.id)
                await callback_query.answer(get_text("error", user_language), show_alert=True)
                return
            
            # Get sessions for this country
            country_sessions = self.database.get_sessions_by_country(country_code)
            
            country_name = country.get('country_name', 'Unknown')
            text = f"📊 **Sessions for {country_name} ({country_code})**\n\n"
            
            if country_sessions['total'] == 0:
                text += "No sessions found for this country."
            else:
                text += f"**Total Sessions:** {country_sessions['total']}\n"
                text += f"**Pending:** {len(country_sessions['pending'])}\n"
                text += f"**Approved:** {len(country_sessions['approved'])}\n\n"
                
                # Show recent sessions
                if country_sessions['pending']:
                    text += "**Recent Pending Sessions:**\n"
                    for session in country_sessions['pending'][:5]:  # Show first 5
                        user_name = session.get('username', session.get('first_name', 'Unknown'))
                        phone = session.get('phone_number', 'Unknown')
                        text += f"• {phone} - {user_name}\n"
                
                if country_sessions['approved']:
                    text += "\n**Recent Approved Sessions:**\n"
                    for session in country_sessions['approved'][:5]:  # Show first 5
                        user_name = session.get('username', session.get('first_name', 'Unknown'))
                        phone = session.get('phone_number', 'Unknown')
                        text += f"• {phone} - {user_name}\n"
            
            keyboard = [[
                InlineKeyboardButton(text="🔙 Back to Countries", callback_data="sessions_by_country")
            ]]
            
            await callback_query.message.edit_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="Markdown"
            )
        
        except Exception as e:
            logger.error(f"Error viewing country sessions: {e}")
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("error", user_language), show_alert=True)
    
    async def bulk_operations_menu(self, callback_query: types.CallbackQuery):
        """Show bulk operations menu"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        stats = self.session_manager.get_session_statistics()
        
        keyboard = [
            [
                InlineKeyboardButton(text=f"✅ Approve All Pending ({stats.get('pending', 0)})", 
                                   callback_data="bulk_approve_all"),
                InlineKeyboardButton(text=f"❌ Reject All Pending ({stats.get('pending', 0)})", 
                                   callback_data="bulk_reject_all")
            ],
            [
                InlineKeyboardButton(text="🧹 Clean Old Sessions", callback_data="bulk_clean_old"),
                InlineKeyboardButton(text="🔄 Refresh All Stats", callback_data="bulk_refresh_stats")
            ],
            [
                InlineKeyboardButton(text="📊 Export All Data", callback_data="bulk_export_data"),
                InlineKeyboardButton(text="🔄 Sync Firebase", callback_data="bulk_sync_firebase")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin_sessions")
            ]
        ]
        
        text = (
            "📋 **Bulk Operations**\n\n"
            "⚠️ **Warning**: Bulk operations affect multiple sessions.\n"
            "Please use with caution.\n\n"
            f"📊 **Current Status:**\n"
            f"• Pending: {stats.get('pending', 0)} sessions\n"
            f"• Total: {sum(stats.values())} sessions\n\n"
            "Select an operation:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def bulk_approve_all(self, callback_query: types.CallbackQuery):
        """Bulk approve all pending sessions"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        try:
            pending_sessions = self.session_manager.get_sessions_by_status('pending')
            
            if not pending_sessions:
                user_language = self.get_user_language(callback_query.from_user.id)
                await callback_query.answer(get_text("no_sessions_found", user_language), show_alert=True)
                return
            
            success_count = 0
            for session in pending_sessions:
                phone = session.get('phone')
                if phone and self.session_manager.approve_session(phone):
                    self.database.update_session_status(phone, 'approved')
                    success_count += 1
                    
                    # Notify user
                    user_id = session.get('user_id')
                    if user_id:
                        await self.notification_service.notify_session_approved(user_id, phone)
            
            await callback_query.answer(
                f"✅ Approved {success_count} sessions successfully", 
                show_alert=True
            )
            
            # Log the action
            logger.info(f"Admin {callback_query.from_user.id} bulk approved {success_count} sessions")
            
            # Refresh menu
            await self.show_sessions_menu(callback_query)
        
        except Exception as e:
            logger.error(f"Error in bulk approve: {e}")
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("error", user_language), show_alert=True)
    
    def register_handlers(self, dp: Dispatcher):
        """Register session management handlers"""
        # Main menu
        dp.callback_query.register(
            self.show_sessions_menu,
            F.data == "admin_sessions"
        )
        
        # View sessions by status
        dp.callback_query.register(
            self.view_sessions_by_status,
            F.data.startswith("view_sessions_")
        )
        
        # Session approval/rejection
        dp.callback_query.register(
            self.approve_session,
            F.data.startswith("approve_session_")
        )
        
        dp.callback_query.register(
            self.reject_session_prompt,
            F.data.startswith("reject_session_")
        )
        
        dp.message.register(
            self.process_rejection,
            SessionStates.waiting_rejection_reason
        )
        
        # Statistics
        dp.callback_query.register(
            self.show_detailed_statistics,
            F.data == "session_detailed_stats"
        )
        
        # Search
        dp.callback_query.register(
            self.search_session,
            F.data == "search_session"
        )
        
        dp.message.register(
            self.process_search,
            SessionStates.waiting_search_term
        )
        
        # Sessions by country
        dp.callback_query.register(
            self.sessions_by_country,
            F.data == "sessions_by_country"
        )
        
        dp.callback_query.register(
            self.view_country_sessions,
            F.data.startswith("view_country_sessions_")
        )
        
        # Bulk operations
        dp.callback_query.register(
            self.bulk_operations_menu,
            F.data == "bulk_session_operations"
        )
        
        dp.callback_query.register(
            self.bulk_approve_all,
            F.data == "bulk_approve_all"
        )