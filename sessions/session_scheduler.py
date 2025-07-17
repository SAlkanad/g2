"""
Session Scheduler - Handles delayed session termination and approval workflow
"""

import asyncio
import logging
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from aiogram import Bot

from sessions.session_manager import SessionManager
from sessions.session_utils import SESSION_TERMINATION_DELAY_HOURS, SESSION_RETRY_DELAY_HOURS, MAX_TERMINATION_ATTEMPTS, SESSION_TOTAL_WAIT_HOURS

logger = logging.getLogger(__name__)

class SessionScheduler:
    """Handles scheduled session processing with proper timing"""
    
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
        self.database = database
        self.scheduled_tasks = {}
        self.schedule_file = "session_schedule.json"
        self.load_schedule()
    
    def load_schedule(self):
        """Load scheduled tasks from file"""
        try:
            if os.path.exists(self.schedule_file):
                with open(self.schedule_file, 'r') as f:
                    data = json.load(f)
                    self.scheduled_tasks = data
                logger.info(f"Loaded {len(self.scheduled_tasks)} scheduled tasks")
            else:
                self.scheduled_tasks = {}
        except Exception as e:
            logger.error(f"Error loading schedule: {e}")
            self.scheduled_tasks = {}
    
    def save_schedule(self):
        """Save scheduled tasks to file"""
        try:
            with open(self.schedule_file, 'w') as f:
                json.dump(self.scheduled_tasks, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving schedule: {e}")
    
    def schedule_session_processing(self, phone: str, user_id: int, created_at: str):
        """Schedule session for processing after 12 hours"""
        try:
            # Parse creation time
            created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00').replace('+00:00', ''))
            
            # Schedule first attempt after configured delay
            first_attempt = created_time + timedelta(hours=SESSION_TERMINATION_DELAY_HOURS)
            
            # Store in schedule
            self.scheduled_tasks[phone] = {
                'user_id': user_id,
                'created_at': created_at,
                'first_attempt': first_attempt.isoformat(),
                'second_attempt': None,
                'attempts': 0,
                'status': 'scheduled'
            }
            
            self.save_schedule()
            
            # Calculate delay until first attempt
            now = datetime.now()
            delay_seconds = (first_attempt - now).total_seconds()
            
            if delay_seconds > 0:
                logger.info(f"Scheduled session {phone} for processing in {delay_seconds/3600:.1f} hours")
                # Schedule the task
                asyncio.create_task(self._delayed_process_session(phone, delay_seconds))
            else:
                # Session is already old enough, process immediately
                logger.info(f"Session {phone} is old enough, processing immediately")
                asyncio.create_task(self._process_session_attempt(phone, 1))
                
        except Exception as e:
            logger.error(f"Error scheduling session {phone}: {e}")
    
    async def _delayed_process_session(self, phone: str, delay_seconds: float):
        """Process session after delay"""
        try:
            await asyncio.sleep(delay_seconds)
            await self._process_session_attempt(phone, 1)
        except Exception as e:
            logger.error(f"Error in delayed processing for {phone}: {e}")
    
    async def _process_session_attempt(self, phone: str, attempt: int):
        """Process a session termination attempt"""
        try:
            if phone not in self.scheduled_tasks:
                logger.warning(f"Session {phone} not found in schedule")
                return
            
            schedule_info = self.scheduled_tasks[phone]
            schedule_info['attempts'] = attempt
            
            logger.info(f"Processing session {phone} - attempt {attempt}")
            
            # Check if session still exists in pending
            session_info = self.session_manager.get_session_info(phone, 'pending')
            if not session_info:
                logger.info(f"Session {phone} no longer in pending status")
                del self.scheduled_tasks[phone]
                self.save_schedule()
                return
            
            # Test session validity first
            test_result = await self.session_manager.test_session(phone, 'pending')
            
            if not test_result['valid']:
                logger.warning(f"Session {phone} is no longer valid: {test_result['error']}")
                await self._reject_session(phone, schedule_info['user_id'], f"Session invalid: {test_result['error']}")
                del self.scheduled_tasks[phone]
                self.save_schedule()
                return
            
            # Check for 2FA (should have been caught earlier, but double-check)
            if test_result.get('has_2fa', False):
                logger.warning(f"Session {phone} has 2FA enabled")
                await self._reject_session(phone, schedule_info['user_id'], "Account has 2FA enabled")
                del self.scheduled_tasks[phone]
                self.save_schedule()
                return
            
            # Attempt to terminate other sessions
            termination_result = await self._terminate_sessions_safely(phone)
            
            if termination_result:
                # Success! Approve the session
                logger.info(f"Successfully terminated sessions for {phone}")
                await self._approve_session(phone, schedule_info['user_id'])
                del self.scheduled_tasks[phone]
                self.save_schedule()
                
            elif attempt == 1:
                # First attempt failed, schedule second attempt after configured retry delay
                logger.info(f"First termination attempt failed for {phone}, scheduling retry")
                second_attempt = datetime.now() + timedelta(hours=SESSION_RETRY_DELAY_HOURS)
                schedule_info['second_attempt'] = second_attempt.isoformat()
                schedule_info['status'] = 'retry_scheduled'
                self.save_schedule()
                
                # Schedule second attempt
                asyncio.create_task(self._delayed_retry_session(phone, SESSION_RETRY_DELAY_HOURS * 3600))
                
            else:
                # Second attempt failed, notify admin
                logger.warning(f"Second termination attempt failed for {phone}, notifying admin")
                await self._notify_admin_termination_failed(phone, schedule_info['user_id'])
                schedule_info['status'] = 'admin_required'
                self.save_schedule()
                
        except Exception as e:
            logger.error(f"Error processing session attempt for {phone}: {e}")
    
    async def _delayed_retry_session(self, phone: str, delay_seconds: float):
        """Retry session processing after delay"""
        try:
            await asyncio.sleep(delay_seconds)
            await self._process_session_attempt(phone, 2)
        except Exception as e:
            logger.error(f"Error in delayed retry for {phone}: {e}")
    
    async def _terminate_sessions_safely(self, phone: str) -> bool:
        """Safely attempt to terminate other sessions"""
        try:
            # Import here to avoid circular imports
            from telethon import TelegramClient
            from telethon.tl.functions.auth import ResetAuthorizationsRequest
            
            status_dir = self.session_manager.pending_dir
            session_file = os.path.join(status_dir, f"{phone}.session")
            
            if not os.path.exists(session_file):
                logger.error(f"Session file not found: {session_file}")
                return False
            
            # Create a copy of the session file to avoid conflicts
            temp_session = session_file + ".temp"
            import shutil
            shutil.copy2(session_file, temp_session)
            
            try:
                client = TelegramClient(temp_session, 
                                      self.session_manager.api_id, 
                                      self.session_manager.api_hash)
                await client.connect()
                
                if not await client.is_user_authorized():
                    await client.disconnect()
                    return False
                
                # Attempt to reset other authorizations
                await client(ResetAuthorizationsRequest())
                await client.disconnect()
                
                # Clean up temp file
                if os.path.exists(temp_session + ".session"):
                    os.remove(temp_session + ".session")
                
                logger.info(f"Successfully terminated other sessions for {phone}")
                return True
                
            except Exception as e:
                logger.error(f"Error terminating sessions for {phone}: {e}")
                try:
                    await client.disconnect()
                except:
                    pass
                # Clean up temp file
                if os.path.exists(temp_session + ".session"):
                    try:
                        os.remove(temp_session + ".session")
                    except:
                        pass
                return False
                
        except Exception as e:
            logger.error(f"Error in safe termination for {phone}: {e}")
            return False
    
    async def _approve_session(self, phone: str, user_id: int):
        """Approve a session after successful termination"""
        success = self.session_manager.move_session(phone, 'pending', 'approved', 
                                                   f"Approved after termination on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if success:
            logger.info(f"Session {phone} approved after termination")
            
            # Notify user
            try:
                await self.bot.send_message(
                    user_id,
                    f"✅ Your session {phone} has been approved!\n\n"
                    f"✓ Session tested and validated\n"
                    f"✓ Other sessions terminated successfully\n"
                    f"✓ Account is ready for use\n\n"
                    f"Your session is now available in the approved folder."
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
            
            # Notify admins
            await self._notify_admins(
                f"✅ Session Approved Successfully\n\n"
                f"Phone: {phone}\n"
                f"User ID: {user_id}\n"
                f"Status: Approved after termination\n"
                f"Processing time: ~12+ hours\n"
                f"Other sessions: Terminated"
            )
        else:
            logger.error(f"Failed to approve session {phone}")
    
    async def _reject_session(self, phone: str, user_id: int, reason: str):
        """Reject a session"""
        success = self.session_manager.move_session(phone, 'pending', 'rejected', reason)
        
        if success:
            logger.info(f"Session {phone} rejected: {reason}")
            
            # Notify user
            try:
                await self.bot.send_message(
                    user_id,
                    f"❌ Your session {phone} has been rejected.\n\n"
                    f"Reason: {reason}\n\n"
                    f"Please contact support if you need assistance."
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
            
            # Notify admins
            await self._notify_admins(
                f"❌ Session Rejected\n\n"
                f"Phone: {phone}\n"
                f"User ID: {user_id}\n"
                f"Reason: {reason}"
            )
        else:
            logger.error(f"Failed to reject session {phone}")
    
    async def _notify_admin_termination_failed(self, phone: str, user_id: int):
        """Notify admin when termination fails after 2 attempts"""
        session_info = self.session_manager.get_session_info(phone, 'pending')
        
        message = (
            f"⚠️ Session Termination Failed (2 attempts)\n\n"
            f"Phone: {phone}\n"
            f"User ID: {user_id}\n"
            f"Username: {session_info.get('username', 'N/A') if session_info else 'N/A'}\n"
            f"First Name: {session_info.get('first_name', 'N/A') if session_info else 'N/A'}\n\n"
            f"🔄 Attempted termination after 12 hours: Failed\n"
            f"🔄 Attempted termination after 23 hours: Failed\n\n"
            f"❓ Possible reasons:\n"
            f"• Session too new (Telegram restriction)\n"
            f"• Network connectivity issues\n"
            f"• Account limitations\n\n"
            f"⚡ Manual action required:"
        )
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Approve Anyway", callback_data=f"force_approve_{phone}"),
                InlineKeyboardButton(text="❌ Reject Session", callback_data=f"force_reject_{phone}")
            ],
            [InlineKeyboardButton(text="🔄 Try Termination Again", callback_data=f"retry_termination_{phone}")],
            [InlineKeyboardButton(text="🔍 View Session Details", callback_data=f"view_session_{phone}")]
        ])
        
        await self._notify_admins(message, keyboard)
    
    async def _notify_admins(self, message: str, keyboard=None):
        """Notify all admins"""
        for admin_id in self.admin_ids:
            try:
                await self.bot.send_message(admin_id, message, reply_markup=keyboard)
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
    
    async def handle_admin_termination_action(self, callback_data: str, admin_id: int) -> bool:
        """Handle admin actions for termination failures"""
        try:
            if callback_data.startswith('force_approve_'):
                phone = callback_data.replace('force_approve_', '')
                return await self._force_approve_session(phone, admin_id)
            
            elif callback_data.startswith('force_reject_'):
                phone = callback_data.replace('force_reject_', '')
                return await self._force_reject_session(phone, admin_id)
            
            elif callback_data.startswith('retry_termination_'):
                phone = callback_data.replace('retry_termination_', '')
                return await self._retry_termination_now(phone, admin_id)
            
            return False
            
        except Exception as e:
            logger.error(f"Error handling admin termination action: {e}")
            return False
    
    async def _force_approve_session(self, phone: str, admin_id: int) -> bool:
        """Force approve a session without termination"""
        if phone in self.scheduled_tasks:
            user_id = self.scheduled_tasks[phone]['user_id']
            del self.scheduled_tasks[phone]
            self.save_schedule()
        else:
            session_info = self.session_manager.get_session_info(phone, 'pending')
            user_id = session_info.get('created_by') if session_info else None
        
        success = self.session_manager.move_session(phone, 'pending', 'approved', 
                                                   f"Force approved by admin (termination failed)")
        
        if success and user_id:
            # Notify user
            try:
                await self.bot.send_message(
                    user_id,
                    f"✅ Your session {phone} has been approved!\n\n"
                    f"✓ Session manually approved by admin\n"
                    f"⚠️ Note: Other sessions may still be active\n\n"
                    f"Your session is now available."
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
            
            # Notify admin
            try:
                await self.bot.send_message(
                    admin_id,
                    f"✅ Session {phone} force approved!\n"
                    f"Note: Other sessions were not terminated."
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
        
        return success
    
    async def _force_reject_session(self, phone: str, admin_id: int) -> bool:
        """Force reject a session"""
        if phone in self.scheduled_tasks:
            user_id = self.scheduled_tasks[phone]['user_id']
            del self.scheduled_tasks[phone]
            self.save_schedule()
        else:
            session_info = self.session_manager.get_session_info(phone, 'pending')
            user_id = session_info.get('created_by') if session_info else None
        
        success = self.session_manager.move_session(phone, 'pending', 'rejected', 
                                                   f"Rejected by admin (termination failed)")
        
        if success and user_id:
            # Notify user
            try:
                await self.bot.send_message(
                    user_id,
                    f"❌ Your session {phone} has been rejected.\n\n"
                    f"Reason: Session termination failed\n\n"
                    f"Please contact support for assistance."
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
            
            # Notify admin
            try:
                await self.bot.send_message(
                    admin_id,
                    f"❌ Session {phone} rejected successfully!"
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
        
        return success
    
    async def _retry_termination_now(self, phone: str, admin_id: int) -> bool:
        """Retry termination immediately"""
        try:
            termination_result = await self._terminate_sessions_safely(phone)
            
            if termination_result:
                # Success! Approve the session
                if phone in self.scheduled_tasks:
                    user_id = self.scheduled_tasks[phone]['user_id']
                    del self.scheduled_tasks[phone]
                    self.save_schedule()
                else:
                    session_info = self.session_manager.get_session_info(phone, 'pending')
                    user_id = session_info.get('created_by') if session_info else None
                
                await self._approve_session(phone, user_id)
                
                try:
                    await self.bot.send_message(
                        admin_id,
                        f"✅ Termination retry successful for {phone}!\n"
                        f"Session has been approved."
                    )
                except:
                    pass
                
                return True
            else:
                try:
                    await self.bot.send_message(
                        admin_id,
                        f"❌ Termination retry failed for {phone}.\n"
                        f"Please choose another action."
                    )
                except:
                    pass
                
                return False
                
        except Exception as e:
            logger.error(f"Error retrying termination for {phone}: {e}")
            return False
    
    async def check_pending_schedules(self):
        """Check for scheduled tasks that need processing (recovery function)"""
        try:
            now = datetime.now()
            
            for phone, schedule_info in list(self.scheduled_tasks.items()):
                try:
                    # Check if first attempt is due
                    if schedule_info['attempts'] == 0:
                        first_attempt = datetime.fromisoformat(schedule_info['first_attempt'])
                        if now >= first_attempt:
                            logger.info(f"Processing overdue first attempt for {phone}")
                            asyncio.create_task(self._process_session_attempt(phone, 1))
                    
                    # Check if second attempt is due
                    elif schedule_info['attempts'] == 1 and schedule_info.get('second_attempt'):
                        second_attempt = datetime.fromisoformat(schedule_info['second_attempt'])
                        if now >= second_attempt:
                            logger.info(f"Processing overdue second attempt for {phone}")
                            asyncio.create_task(self._process_session_attempt(phone, 2))
                            
                except Exception as e:
                    logger.error(f"Error checking schedule for {phone}: {e}")
                    
        except Exception as e:
            logger.error(f"Error checking pending schedules: {e}")