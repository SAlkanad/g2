"""
Session Processor - Handles automatic session testing and approval workflow
"""

import asyncio
import logging
from typing import Dict, List
from datetime import datetime
from aiogram import Bot

from network.telegram_security import TelegramSecurityManager
from languages.languages import get_text
from database.database import Database

logger = logging.getLogger(__name__)

class SessionProcessor:
    """Handles automatic session testing and approval"""
    
    def __init__(self, bot: Bot, session_manager: SessionManager, database: Database, admin_ids: List[int], pending_dir: str, approved_dir: str, rejected_dir: str, extracted_dir: str):
        self.bot = bot
        self.session_manager = SessionManager(
            sessions_dir=os.path.dirname(pending_dir),  # Assuming sessions_dir is parent of pending_dir
            api_id=0,  # Placeholder, will be set by main bot
            api_hash="",  # Placeholder
            pending_dir=pending_dir,
            approved_dir=approved_dir,
            rejected_dir=rejected_dir,
            extracted_dir=extracted_dir
        )
        self.admin_ids = admin_ids
        self.db = database
    
    def _get_user_language(self, user_id: int) -> str:
        """Get user's language preference"""
        try:
            user = self.db.get_user(user_id)
            return user['language'] if user else 'en'
        except:
            return 'en'
    
    async def process_pending_session(self, phone: str, user_id: int, created_at: str) -> Dict:
        """Process a pending session through the approval workflow"""
        try:
            logger.info(f"Initial processing for pending session {phone}")
            
            # Test session validity
            test_result = await self.session_manager.test_session(phone, 'pending')
            
            if not test_result['valid']:
                # Session is invalid, reject it
                await self._reject_session(phone, user_id, f"Session invalid: {test_result['error']}")
                return {'status': 'rejected', 'reason': test_result['error']}
            
            # Check for 2FA
            if test_result.get('has_2fa', False):
                await self._reject_session(phone, user_id, "Account has 2FA enabled")
                return {'status': 'rejected', 'reason': 'has_2fa'}
            
            # Check for email
            if test_result.get('has_email', False):
                # Session has email, need manual approval
                await self._notify_admin_email_change(phone, user_id, test_result)
                return {'status': 'pending_email', 'reason': 'has_email'}
            
            # Session passed initial tests, but we need to wait 12 hours for termination
            # Schedule the session for delayed processing
            from sessions.session_scheduler import SessionScheduler
            scheduler = SessionScheduler(self.bot, self.session_manager, self.admin_ids)
            scheduler.schedule_session_processing(phone, user_id, created_at)
            
            # Notify user about the delay
            try:
                lang = self._get_user_language(user_id)
                message_text = get_text('session_processing', lang, phone=phone)
                await self.bot.send_message(user_id, message_text)
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
            
            return {'status': 'scheduled', 'reason': 'waiting_for_termination_window'}
            
        except Exception as e:
            logger.error(f"Error processing session {phone}: {e}")
            await self._notify_admin_manual_review(phone, user_id, f"Processing error: {str(e)}")
            return {'status': 'error', 'reason': str(e)}
    
    async def _approve_session(self, phone: str, user_id: int):
        """Approve a session"""
        success = self.session_manager.move_session(phone, 'pending', 'approved', 
                                                   f"Automatically approved on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if success:
            logger.info(f"Session {phone} approved automatically")
            
            # Notify user
            try:
                lang = self._get_user_language(user_id)
                message_text = get_text('session_approved', lang, phone=phone)
                await self.bot.send_message(user_id, message_text)
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
            
            # Notify admins
            admin_message = get_text('admin_session_approved', 'en', phone=phone, user_id=user_id)
            await self._notify_admins(admin_message)
        else:
            logger.error(f"Failed to approve session {phone}")
    
    async def _reject_session(self, phone: str, user_id: int, reason: str):
        """Reject a session"""
        success = self.session_manager.move_session(phone, 'pending', 'rejected', reason)
        
        if success:
            logger.info(f"Session {phone} rejected: {reason}")
            
            # Notify user
            try:
                lang = self._get_user_language(user_id)
                message_text = get_text('session_rejected_validation', lang, phone=phone, reason=reason)
                await self.bot.send_message(user_id, message_text)
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
            
            # Notify admins
            admin_message = get_text('admin_session_rejected', 'en', phone=phone, user_id=user_id, reason=reason)
            await self._notify_admins(admin_message)
        else:
            logger.error(f"Failed to reject session {phone}")
    
    async def _notify_admin_email_change(self, phone: str, user_id: int, test_result: Dict):
        """Notify admin about session with email that needs manual handling"""
        message = (
            f"📧 Session Requires Email Change\n\n"
            f"Phone: {phone}\n"
            f"User ID: {user_id}\n"
            f"Username: {test_result.get('username', 'N/A')}\n"
            f"First Name: {test_result.get('first_name', 'N/A')}\n"
            f"Last Name: {test_result.get('last_name', 'N/A')}\n\n"
            f"⚠️ This account has a recovery email linked.\n"
            f"Please manually change the email before approving.\n\n"
            f"Actions available:"
        )
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Approve (Email Changed)", callback_data=f"approve_email_{phone}"),
                InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_email_{phone}")
            ],
            [InlineKeyboardButton(text="🔄 Change Email via Bot", callback_data=f"change_email_{phone}")]
        ])
        
        await self._notify_admins(message, keyboard)
    
    async def _notify_admin_manual_review(self, phone: str, user_id: int, reason: str):
        """Notify admin about session that needs manual review"""
        message = (
            f"⚠️ Session Requires Manual Review\n\n"
            f"Phone: {phone}\n"
            f"User ID: {user_id}\n"
            f"Reason: {reason}\n\n"
            f"Please review this session manually."
        )
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Approve", callback_data=f"manual_approve_{phone}"),
                InlineKeyboardButton(text="❌ Reject", callback_data=f"manual_reject_{phone}")
            ],
            [InlineKeyboardButton(text="🔍 View Details", callback_data=f"view_session_{phone}")]
        ])
        
        await self._notify_admins(message, keyboard)
    
    async def _notify_admins(self, message: str, keyboard=None):
        """Notify all admins"""
        for admin_id in self.admin_ids:
            try:
                await self.bot.send_message(admin_id, message, reply_markup=keyboard)
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
    
    async def handle_admin_approval(self, callback_data: str, admin_id: int) -> bool:
        """Handle admin approval actions"""
        try:
            if callback_data.startswith('approve_email_'):
                phone = callback_data.replace('approve_email_', '')
                return await self._admin_approve_session(phone, admin_id, "Email changed manually")
            
            elif callback_data.startswith('reject_email_'):
                phone = callback_data.replace('reject_email_', '')
                return await self._admin_reject_session(phone, admin_id, "Rejected due to email")
            
            elif callback_data.startswith('manual_approve_'):
                phone = callback_data.replace('manual_approve_', '')
                return await self._admin_approve_session(phone, admin_id, "Manually approved")
            
            elif callback_data.startswith('manual_reject_'):
                phone = callback_data.replace('manual_reject_', '')
                return await self._admin_reject_session(phone, admin_id, "Manually rejected")
            
            elif callback_data.startswith('change_email_'):
                phone = callback_data.replace('change_email_', '')
                return await self._start_email_change(phone, admin_id)
            
            elif callback_data.startswith('view_session_'):
                phone = callback_data.replace('view_session_', '')
                return await self._show_session_details(phone, admin_id)
            
            return False
            
        except Exception as e:
            logger.error(f"Error handling admin approval: {e}")
            return False
    
    async def _admin_approve_session(self, phone: str, admin_id: int, reason: str) -> bool:
        """Admin manually approves a session"""
        success = self.session_manager.move_session(phone, 'pending', 'approved', reason)
        
        if success:
            # Get session info to notify user
            session_info = self.session_manager.get_session_info(phone, 'approved')
            if session_info:
                user_id = session_info.get('created_by')
                if user_id:
                    try:
                        await self.bot.send_message(
                            user_id,
                            f"✅ Your session {phone} has been approved!\n"
                            f"The session has been manually reviewed and approved.\n"
                            f"Reason: {reason}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify user {user_id}: {e}")
            
            # Notify admin
            try:
                await self.bot.send_message(
                    admin_id,
                    f"✅ Session {phone} approved successfully!\n"
                    f"Reason: {reason}"
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
        
        return success
    
    async def _admin_reject_session(self, phone: str, admin_id: int, reason: str) -> bool:
        """Admin manually rejects a session"""
        success = self.session_manager.move_session(phone, 'pending', 'rejected', reason)
        
        if success:
            # Get session info to notify user
            session_info = self.session_manager.get_session_info(phone, 'rejected')
            if session_info:
                user_id = session_info.get('created_by')
                if user_id:
                    try:
                        await self.bot.send_message(
                            user_id,
                            f"❌ Your session {phone} has been rejected.\n\n"
                            f"Reason: {reason}\n\n"
                            f"Please contact support if you need assistance."
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify user {user_id}: {e}")
            
            # Notify admin
            try:
                await self.bot.send_message(
                    admin_id,
                    f"❌ Session {phone} rejected successfully!\n"
                    f"Reason: {reason}"
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
        
        return success
    
    async def _start_email_change(self, phone: str, admin_id: int) -> bool:
        """Start email change process"""
        try:
            await self.bot.send_message(
                admin_id,
                f"🔄 Email Change Process for {phone}\n\n"
                f"This feature is under development.\n"
                f"For now, please change the email manually and then approve the session."
            )
            return True
        except Exception as e:
            logger.error(f"Failed to start email change: {e}")
            return False
    
    async def _show_session_details(self, phone: str, admin_id: int) -> bool:
        """Show detailed session information"""
        try:
            session_info = self.session_manager.get_session_info(phone, 'pending')
            if not session_info:
                await self.bot.send_message(admin_id, f"❌ Session {phone} not found")
                return False
            
            text = f"🔍 Session Details: {phone}\n\n"
            text += f"Status: {session_info.get('status', 'unknown')}\n"
            text += f"Created by: {session_info.get('created_by', 'unknown')}\n"
            text += f"Created at: {session_info.get('created_at', 'unknown')}\n"
            text += f"Telegram User ID: {session_info.get('telegram_user_id', 'unknown')}\n"
            text += f"Username: {session_info.get('username', 'N/A')}\n"
            text += f"First Name: {session_info.get('first_name', 'N/A')}\n"
            text += f"Last Name: {session_info.get('last_name', 'N/A')}\n"
            text += f"Has 2FA: {session_info.get('has_2fa', 'unknown')}\n"
            text += f"Has Email: {session_info.get('has_email', 'unknown')}\n"
            text += f"Last Tested: {session_info.get('last_tested', 'never')}\n"
            
            await self.bot.send_message(admin_id, text)
            return True
            
        except Exception as e:
            logger.error(f"Failed to show session details: {e}")
            return False