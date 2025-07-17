"""
Comprehensive Reporting System Module

Handles all reporting functionality including:
- Error notifications to groups
- User interaction tracking
- Account purchase notifications
- Daily reports with statistics
- Control room commands for admin management
- Automated backup system
"""

import asyncio
import os
import json
import zipfile
import logging
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
import schedule
import threading
import time

from database.database import Database
from admin.admin_extractor import AdminExtractor

logger = logging.getLogger(__name__)


class ReportingStates(StatesGroup):
    """FSM states for reporting system configuration"""
    waiting_group_id = State()
    waiting_errors_chat_id = State()
    waiting_users_chat_id = State()
    waiting_bought_accounts_chat_id = State()
    waiting_reports_chat_id = State()
    waiting_control_room_chat_id = State()
    waiting_backup_chat_id = State()
    waiting_backup_interval = State()


class ReportingSystem:
    """Comprehensive reporting system for the bot"""
    
    def __init__(self, bot: Bot, database: Database, session_manager, admin_extractor: AdminExtractor, admin_ids: List[int]):
        self.bot = bot
        self.database = database
        self.session_manager = session_manager
        self.admin_extractor = admin_extractor
        self.admin_ids = admin_ids
        
        # Initialize settings with default values
        self.settings = self.load_settings()
        
        # Statistics tracking
        self.daily_stats = {
            'users_interacted': set(),
            'new_users': set(),
            'accounts_bought': [],
            'errors_occurred': [],
            'approved_sessions': 0,
            'pending_sessions': 0,
            'rejected_sessions': 0,
            'balance_added': 0.0,
            'countries_stats': {}
        }
        
        # Start background tasks
        self.start_scheduler()
        
        # Control room command handlers
        self.control_commands = {
            '/u': self.handle_user_command,
            '/s': self.handle_session_command,
            '/xa': self.handle_extract_approved,
            '/xp': self.handle_extract_pending,
            '/xr': self.handle_extract_rejected,
            '/x': self.handle_extract_command
        }
    
    def load_settings(self) -> Dict:
        """Load reporting system settings from database"""
        try:
            settings = self.database.get_setting('reporting_system')
            if settings:
                return json.loads(settings) if isinstance(settings, str) else settings
            else:
                # Default settings
                default_settings = {
                    'group_id': None,
                    'errors_chat_id': None,
                    'users_chat_id': None,
                    'bought_accounts_chat_id': None,
                    'reports_chat_id': None,
                    'control_room_chat_id': None,
                    'backup_chat_id': None,
                    'backup_interval_minutes': 60,
                    'daily_report_time': '00:00',
                    'enabled': True
                }
                self.save_settings(default_settings)
                return default_settings
        except Exception as e:
            logger.error(f"Error loading reporting settings: {e}")
            return {
                'group_id': None,
                'errors_chat_id': None,
                'users_chat_id': None,
                'bought_accounts_chat_id': None,
                'reports_chat_id': None,
                'control_room_chat_id': None,
                'backup_chat_id': None,
                'backup_interval_minutes': 60,
                'daily_report_time': '00:00',
                'enabled': True
            }
    
    def save_settings(self, settings: Dict):
        """Save reporting system settings to database"""
        try:
            self.settings = settings
            self.database.set_setting('reporting_system', json.dumps(settings))
            logger.info("Reporting system settings saved successfully")
        except Exception as e:
            logger.error(f"Error saving reporting settings: {e}")
    
    async def report_error(self, error: Exception, context: str = "", user_id: Optional[int] = None):
        """Report errors to the designated error chat"""
        try:
            if not self.settings.get('enabled') or not self.settings.get('errors_chat_id'):
                return
            
            error_text = (
                f"🚨 **Bot Error Report**\n\n"
                f"**Context:** {context}\n"
                f"**Error:** {str(error)}\n"
                f"**Type:** {type(error).__name__}\n"
                f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            
            if user_id:
                user_info = self.database.get_user(user_id)
                error_text += f"**User ID:** {user_id}\n"
                if user_info:
                    error_text += f"**Username:** @{user_info.get('username', 'N/A')}\n"
            
            # Add traceback for debugging
            tb = traceback.format_exc()
            if len(tb) > 500:
                tb = tb[:500] + "..."
            error_text += f"\n**Traceback:**\n```\n{tb}\n```"
            
            await self.bot.send_message(
                chat_id=self.settings['errors_chat_id'],
                text=error_text,
                parse_mode="Markdown"
            )
            
            # Track error in daily stats
            self.daily_stats['errors_occurred'].append({
                'error': str(error),
                'context': context,
                'time': datetime.now().isoformat(),
                'user_id': user_id
            })
            
        except Exception as e:
            logger.error(f"Error reporting error: {e}")
    
    async def report_new_user(self, user: types.User):
        """Report new user interactions to the designated users chat"""
        try:
            if not self.settings.get('enabled') or not self.settings.get('users_chat_id'):
                return
            
            user_text = (
                f"👤 **New User Interaction**\n\n"
                f"**User ID:** {user.id}\n"
                f"**Username:** @{user.username if user.username else 'N/A'}\n"
                f"**First Name:** {user.first_name if user.first_name else 'N/A'}\n"
                f"**Last Name:** {user.last_name if user.last_name else 'N/A'}\n"
                f"**Language:** {user.language_code if user.language_code else 'N/A'}\n"
                f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            
            # Check if user is premium
            if hasattr(user, 'is_premium') and user.is_premium:
                user_text += f"**Premium:** ✅\n"
            
            await self.bot.send_message(
                chat_id=self.settings['users_chat_id'],
                text=user_text,
                parse_mode="Markdown"
            )
            
            # Track in daily stats
            self.daily_stats['users_interacted'].add(user.id)
            self.daily_stats['new_users'].add(user.id)
            
        except Exception as e:
            logger.error(f"Error reporting new user: {e}")
    
    async def report_user_interaction(self, user_id: int):
        """Track user interaction for daily stats"""
        try:
            self.daily_stats['users_interacted'].add(user_id)
        except Exception as e:
            logger.error(f"Error tracking user interaction: {e}")
    
    async def report_bought_account(self, user_id: int, phone_number: str, country_code: str, price: float, status: str = "pending"):
        """Report account purchases to the designated bought accounts chat"""
        try:
            if not self.settings.get('enabled') or not self.settings.get('bought_accounts_chat_id'):
                return
            
            user_info = self.database.get_user(user_id)
            
            account_text = (
                f"💰 **Account Purchase Report**\n\n"
                f"**Phone:** {phone_number}\n"
                f"**Country:** {country_code}\n"
                f"**Price:** ${price:.2f}\n"
                f"**Status:** {status.title()}\n"
                f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"**Seller Info:**\n"
                f"• User ID: {user_id}\n"
            )
            
            if user_info:
                account_text += (
                    f"• Username: @{user_info.get('username', 'N/A')}\n"
                    f"• Balance: ${user_info.get('balance', 0):.2f}\n"
                    f"• Total Sold: {user_info.get('accounts_sold', 0)}\n"
                )
            
            await self.bot.send_message(
                chat_id=self.settings['bought_accounts_chat_id'],
                text=account_text,
                parse_mode="Markdown"
            )
            
            # Track in daily stats
            self.daily_stats['accounts_bought'].append({
                'user_id': user_id,
                'phone': phone_number,
                'country': country_code,
                'price': price,
                'status': status,
                'time': datetime.now().isoformat()
            })
            
            if status == 'approved':
                self.daily_stats['balance_added'] += price
            
        except Exception as e:
            logger.error(f"Error reporting bought account: {e}")
    
    async def report_manual_approval_needed(self, phone_number: str, country_code: str, user_id: int, reason: str):
        """Report accounts that need manual approval to control room"""
        try:
            if not self.settings.get('enabled') or not self.settings.get('control_room_chat_id'):
                return
            
            user_info = self.database.get_user(user_id)
            
            approval_text = (
                f"⚠️ **Manual Approval Required**\n\n"
                f"**Phone:** {phone_number}\n"
                f"**Country:** {country_code}\n"
                f"**Reason:** {reason}\n"
                f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"**User Info:**\n"
                f"• ID: {user_id}\n"
            )
            
            if user_info:
                approval_text += (
                    f"• Username: @{user_info.get('username', 'N/A')}\n"
                    f"• Balance: ${user_info.get('balance', 0):.2f}\n"
                )
            
            approval_text += (
                f"\n**Commands:**\n"
                f"• `/s {phone_number}` - View session details\n"
                f"• `/u {user_id}` - View user details\n"
            )
            
            await self.bot.send_message(
                chat_id=self.settings['control_room_chat_id'],
                text=approval_text,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"Error reporting manual approval needed: {e}")
    
    async def send_daily_report(self):
        """Send comprehensive daily report"""
        try:
            if not self.settings.get('enabled') or not self.settings.get('reports_chat_id'):
                return
            
            # Get session statistics
            session_stats = self.session_manager.get_session_statistics()
            
            # Get country statistics
            countries_stats = {}
            countries = self.database.get_countries()
            
            for country in countries:
                code = country.get('country_code', country.get('code', ''))
                approved = len([s for s in self.session_manager.get_sessions_by_status('approved') 
                              if s.get('data', {}).get('country_code') == code])
                pending = len([s for s in self.session_manager.get_sessions_by_status('pending') 
                             if s.get('data', {}).get('country_code') == code])
                rejected = len([s for s in self.session_manager.get_sessions_by_status('rejected') 
                              if s.get('data', {}).get('country_code') == code])
                
                if approved > 0 or pending > 0 or rejected > 0:
                    countries_stats[code] = {
                        'name': country.get('country_name', country.get('name', code)),
                        'approved': approved,
                        'pending': pending,
                        'rejected': rejected
                    }
            
            # Generate report
            report_text = (
                f"📊 **Daily Report - {datetime.now().strftime('%Y-%m-%d')}**\n\n"
                f"👥 **User Statistics:**\n"
                f"• Users Interacted: {len(self.daily_stats['users_interacted'])}\n"
                f"• New Users: {len(self.daily_stats['new_users'])}\n\n"
                f"💰 **Financial:**\n"
                f"• Balance Added: ${self.daily_stats['balance_added']:.2f}\n"
                f"• Accounts Bought: {len(self.daily_stats['accounts_bought'])}\n\n"
                f"📱 **Session Statistics:**\n"
                f"• Total Sessions: {session_stats.get('total', 0)}\n"
                f"• Approved: {session_stats.get('approved', 0)}\n"
                f"• Pending: {session_stats.get('pending', 0)}\n"
                f"• Rejected: {session_stats.get('rejected', 0)}\n"
                f"• Extracted: {session_stats.get('extracted', {}).get('total', 0)}\n\n"
            )
            
            if countries_stats:
                report_text += f"🌍 **Countries Breakdown:**\n"
                for code, stats in sorted(countries_stats.items(), key=lambda x: x[1]['approved'], reverse=True)[:10]:
                    report_text += (
                        f"• **{stats['name']} ({code})**\n"
                        f"  ✅ {stats['approved']} | ⏳ {stats['pending']} | ❌ {stats['rejected']}\n"
                    )
                
                if len(countries_stats) > 10:
                    report_text += f"  ... and {len(countries_stats) - 10} more countries\n"
            
            if self.daily_stats['errors_occurred']:
                report_text += f"\n🚨 **Errors Today:** {len(self.daily_stats['errors_occurred'])}\n"
            
            report_text += f"\n🕐 **Report Generated:** {datetime.now().strftime('%H:%M:%S')}"
            
            await self.bot.send_message(
                chat_id=self.settings['reports_chat_id'],
                text=report_text,
                parse_mode="Markdown"
            )
            
            # Reset daily stats
            self.reset_daily_stats()
            
        except Exception as e:
            logger.error(f"Error sending daily report: {e}")
    
    def reset_daily_stats(self):
        """Reset daily statistics"""
        self.daily_stats = {
            'users_interacted': set(),
            'new_users': set(),
            'accounts_bought': [],
            'errors_occurred': [],
            'approved_sessions': 0,
            'pending_sessions': 0,
            'rejected_sessions': 0,
            'balance_added': 0.0,
            'countries_stats': {}
        }
    
    async def create_backup_zip(self) -> Optional[str]:
        """Create backup ZIP file containing all session folders"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"backup_{timestamp}.zip"
            backup_path = Path("temp") / backup_filename
            
            # Ensure temp directory exists
            backup_path.parent.mkdir(exist_ok=True)
            
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add session files folders
                # Use centralized session paths
                from sessions.session_paths import get_session_paths
                session_paths = get_session_paths()
                
                folders_to_backup = [
                    (session_paths.pending_dir, "pending"),
                    (session_paths.approved_dir, "approved"),
                    (session_paths.rejected_dir, "rejected"),
                    (session_paths.extracted_pending_dir, "extracted_pending"),
                    (session_paths.extracted_approved_dir, "extracted_approved"),
                    (session_paths.extracted_rejected_dir, "extracted_rejected")
                ]
                
                session_count = 0
                
                for folder_path, archive_name in folders_to_backup:
                    if os.path.exists(folder_path):
                        for root, dirs, files in os.walk(folder_path):
                            for file in files:
                                file_path = os.path.join(root, file)
                                arcname = os.path.join(archive_name, os.path.relpath(file_path, folder_path))
                                zipf.write(file_path, arcname)
                                if file.endswith('.session'):
                                    session_count += 1
                
                # Add metadata
                metadata = {
                    'backup_info': {
                        'timestamp': datetime.now().isoformat(),
                        'session_count': session_count,
                        'backup_type': 'automated_hourly'
                    },
                    'statistics': self.session_manager.get_session_statistics()
                }
                
                zipf.writestr("backup_metadata.json", json.dumps(metadata, indent=2))
                
                # Add README
                readme_content = f"""
Automated Backup - {timestamp}
==============================

This backup contains all session files and account data.

Contents:
- pending/: Pending session files
- approved/: Approved session files  
- rejected/: Rejected session files
- extracted_pending/: Extracted pending sessions
- extracted_approved/: Extracted approved sessions
- extracted_rejected/: Extracted rejected sessions

Total Sessions: {session_count}
Backup Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

IMPORTANT: Keep this backup secure and encrypted.
"""
                zipf.writestr("README.txt", readme_content.strip())
            
            return str(backup_path) if session_count > 0 else None
            
        except Exception as e:
            logger.error(f"Error creating backup ZIP: {e}")
            return None
    
    async def send_backup(self):
        """Send backup to designated backup chat"""
        try:
            if not self.settings.get('enabled') or not self.settings.get('backup_chat_id'):
                return
            
            backup_path = await self.create_backup_zip()
            if not backup_path:
                await self.bot.send_message(
                    chat_id=self.settings['backup_chat_id'],
                    text="⚠️ Backup creation failed - no sessions to backup"
                )
                return
            
            # Get file size
            file_size = os.path.getsize(backup_path)
            file_size_mb = file_size / (1024 * 1024)
            
            # Send backup file
            with open(backup_path, 'rb') as backup_file:
                backup_data = backup_file.read()
            
            caption = (
                f"💾 **Automated Backup**\n\n"
                f"📅 **Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"📁 **Size:** {file_size_mb:.2f} MB\n"
                f"📊 **Statistics:** Check backup_metadata.json inside\n\n"
                f"🔐 **Security:** Keep this backup secure!"
            )
            
            await self.bot.send_document(
                chat_id=self.settings['backup_chat_id'],
                document=BufferedInputFile(
                    file=backup_data,
                    filename=os.path.basename(backup_path)
                ),
                caption=caption,
                parse_mode="Markdown"
            )
            
            # Clean up temporary file
            os.remove(backup_path)
            
            logger.info(f"Backup sent successfully: {file_size_mb:.2f} MB")
            
        except Exception as e:
            logger.error(f"Error sending backup: {e}")
            await self.report_error(e, "Backup system")
    
    def start_scheduler(self):
        """Start background scheduler for reports and backups"""
        def run_scheduler():
            # Schedule daily report
            schedule.every().day.at(self.settings.get('daily_report_time', '00:00')).do(
                lambda: asyncio.create_task(self.send_daily_report())
            )
            
            # Schedule backups
            backup_interval = self.settings.get('backup_interval_minutes', 60)
            schedule.every(backup_interval).minutes.do(
                lambda: asyncio.create_task(self.send_backup())
            )
            
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        
        # Start scheduler in background thread
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        
        logger.info("Reporting system scheduler started")
    
    # Control Room Command Handlers
    async def handle_control_room_message(self, message: types.Message):
        """Handle messages in control room chat"""
        try:
            if message.chat.id != self.settings.get('control_room_chat_id'):
                return
            
            if not message.text or not message.text.startswith('/'):
                return
            
            # Extract command and parameters
            parts = message.text.split()
            command = parts[0]
            params = parts[1:] if len(parts) > 1 else []
            
            # Find and execute command handler
            for cmd_prefix, handler in self.control_commands.items():
                if command.startswith(cmd_prefix):
                    await handler(message, command, params)
                    return
                    
        except Exception as e:
            await self.report_error(e, f"Control room command: {message.text}", message.from_user.id)
    
    async def handle_user_command(self, message: types.Message, command: str, params: List[str]):
        """Handle /u command for user information"""
        try:
            if command == '/u' and not params:
                # Show all users summary
                users = self.database.get_all_users()
                if not users:
                    await message.reply("📭 No users found in database")
                    return
                
                response = f"👥 **Users Summary** ({len(users)} total)\n\n"
                
                # Sort by balance or recent activity
                sorted_users = sorted(users, key=lambda x: x.get('balance', 0), reverse=True)[:20]
                
                for user in sorted_users:
                    response += (
                        f"• **{user.get('user_id')}** @{user.get('username', 'N/A')}\n"
                        f"  💰 ${user.get('balance', 0):.2f} | 📱 {user.get('accounts_sold', 0)} sold\n"
                    )
                
                if len(users) > 20:
                    response += f"\n... and {len(users) - 20} more users"
                
                await message.reply(response, parse_mode="Markdown")
                
            elif len(params) >= 1:
                # Show specific user details
                user_identifier = params[0]
                
                # Remove @ if present
                if user_identifier.startswith('@'):
                    user_identifier = user_identifier[1:]
                
                # Try to get user by ID or username
                user = None
                if user_identifier.isdigit():
                    user = self.database.get_user(int(user_identifier))
                else:
                    # Search by username
                    users = self.database.get_all_users()
                    user = next((u for u in users if u.get('username') == user_identifier), None)
                
                if not user:
                    await message.reply(f"❌ User not found: {user_identifier}")
                    return
                
                # Get user's sessions
                user_sessions = []
                for status in ['approved', 'pending', 'rejected']:
                    sessions = self.session_manager.get_sessions_by_status(status)
                    user_sessions.extend([
                        s for s in sessions 
                        if s.get('data', {}).get('user_id') == user['user_id']
                    ])
                
                response = (
                    f"👤 **User Report: {user['user_id']}**\n\n"
                    f"**Profile:**\n"
                    f"• Username: @{user.get('username', 'N/A')}\n"
                    f"• Balance: ${user.get('balance', 0):.2f}\n"
                    f"• Accounts Sold: {user.get('accounts_sold', 0)}\n"
                    f"• Join Date: {user.get('created_at', 'N/A')}\n\n"
                    f"**Sessions ({len(user_sessions)}):**\n"
                )
                
                if user_sessions:
                    for session in user_sessions[:10]:  # Limit to 10 recent
                        session_data = session.get('data', {})
                        phone = session_data.get('phone_number', session_data.get('phone', 'N/A'))
                        country = session_data.get('country_code', 'N/A')
                        status = session_data.get('status', 'unknown')
                        response += f"• {phone} ({country}) - {status.title()}\n"
                    
                    if len(user_sessions) > 10:
                        response += f"... and {len(user_sessions) - 10} more sessions\n"
                else:
                    response += "• No sessions found\n"
                
                await message.reply(response, parse_mode="Markdown")
                
        except Exception as e:
            await self.report_error(e, f"User command: {command} {params}")
            await message.reply(f"❌ Error processing user command: {str(e)}")
    
    async def handle_session_command(self, message: types.Message, command: str, params: List[str]):
        """Handle /s command for session information"""
        try:
            if command == '/sa':
                # Show approved sessions summary
                sessions = self.session_manager.get_sessions_by_status('approved')
                await self.send_sessions_summary(message, sessions, "Approved")
                
            elif command == '/sp':
                # Show pending sessions summary
                sessions = self.session_manager.get_sessions_by_status('pending')
                await self.send_sessions_summary(message, sessions, "Pending")
                
            elif command == '/sr':
                # Show rejected sessions summary
                sessions = self.session_manager.get_sessions_by_status('rejected')
                await self.send_sessions_summary(message, sessions, "Rejected")
                
            elif command == '/s' and not params:
                # Show all sessions summary
                all_sessions = []
                for status in ['approved', 'pending', 'rejected']:
                    sessions = self.session_manager.get_sessions_by_status(status)
                    all_sessions.extend(sessions)
                await self.send_sessions_summary(message, all_sessions, "All")
                
            elif len(params) >= 1:
                param = params[0]
                
                if param.startswith('+') and len(param) > 5:
                    if len(param) > 8:  # Full phone number
                        # Show specific session details
                        await self.send_session_details(message, param)
                    else:  # Country code
                        # Show sessions for country
                        await self.send_country_sessions(message, param)
                        
        except Exception as e:
            await self.report_error(e, f"Session command: {command} {params}")
            await message.reply(f"❌ Error processing session command: {str(e)}")
    
    async def send_sessions_summary(self, message: types.Message, sessions: List[Dict], session_type: str):
        """Send summary of sessions"""
        try:
            if not sessions:
                await message.reply(f"📭 No {session_type.lower()} sessions found")
                return
            
            # Group by country
            country_stats = {}
            for session in sessions:
                session_data = session.get('data', {})
                country = session_data.get('country_code', 'Unknown')
                country_stats[country] = country_stats.get(country, 0) + 1
            
            response = f"📱 **{session_type} Sessions** ({len(sessions)} total)\n\n"
            
            # Show top countries
            sorted_countries = sorted(country_stats.items(), key=lambda x: x[1], reverse=True)
            for country, count in sorted_countries[:15]:
                response += f"• **{country}:** {count} sessions\n"
            
            if len(sorted_countries) > 15:
                response += f"... and {len(sorted_countries) - 15} more countries\n"
            
            await message.reply(response, parse_mode="Markdown")
            
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def send_session_details(self, message: types.Message, phone_number: str):
        """Send detailed information about a specific session"""
        try:
            # Find session across all statuses
            session_found = None
            session_status = None
            
            for status in ['approved', 'pending', 'rejected']:
                sessions = self.session_manager.get_sessions_by_status(status)
                for session in sessions:
                    session_data = session.get('data', {})
                    session_phone = session_data.get('phone_number', session_data.get('phone', ''))
                    if session_phone == phone_number:
                        session_found = session_data
                        session_status = status
                        break
                if session_found:
                    break
            
            if not session_found:
                await message.reply(f"❌ Session not found: {phone_number}")
                return
            
            # Get user info
            user_id = session_found.get('user_id')
            user_info = self.database.get_user(user_id) if user_id else None
            
            response = (
                f"📱 **Session Details: {phone_number}**\n\n"
                f"**Status:** {session_status.title()}\n"
                f"**Country:** {session_found.get('country_code', 'N/A')}\n"
                f"**Created:** {session_found.get('created_at', session_found.get('timestamp', 'N/A'))}\n"
            )
            
            if user_info:
                response += (
                    f"\n**Seller:**\n"
                    f"• User ID: {user_id}\n"
                    f"• Username: @{user_info.get('username', 'N/A')}\n"
                    f"• Balance: ${user_info.get('balance', 0):.2f}\n"
                )
            
            # Add action buttons based on status
            if session_status == 'pending':
                response += f"\n**Actions:**\n• Approve: Send `/approve {phone_number}`\n• Reject: Send `/reject {phone_number}`"
            elif session_status in ['approved', 'rejected']:
                response += f"\n**Actions:**\n• Extract: Send `/extract {phone_number}`"
            
            await message.reply(response, parse_mode="Markdown")
            
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def send_country_sessions(self, message: types.Message, country_code: str):
        """Send sessions for a specific country"""
        try:
            # Get all sessions for country
            country_sessions = []
            for status in ['approved', 'pending', 'rejected']:
                sessions = self.session_manager.get_sessions_by_status(status)
                country_sessions.extend([
                    s for s in sessions 
                    if s.get('data', {}).get('country_code') == country_code
                ])
            
            if not country_sessions:
                await message.reply(f"📭 No sessions found for {country_code}")
                return
            
            response = f"📱 **{country_code} Sessions** ({len(country_sessions)} total)\n\n"
            
            # Group by status
            status_counts = {}
            for session in country_sessions:
                status = session.get('data', {}).get('status', 'unknown')
                status_counts[status] = status_counts.get(status, 0) + 1
            
            for status, count in status_counts.items():
                response += f"• **{status.title()}:** {count} sessions\n"
            
            # Show recent sessions
            response += f"\n**Recent Sessions:**\n"
            for session in country_sessions[:10]:
                session_data = session.get('data', {})
                phone = session_data.get('phone_number', session_data.get('phone', 'N/A'))
                status = session_data.get('status', 'unknown')
                response += f"• {phone} - {status.title()}\n"
            
            if len(country_sessions) > 10:
                response += f"... and {len(country_sessions) - 10} more\n"
            
            await message.reply(response, parse_mode="Markdown")
            
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def handle_extract_approved(self, message: types.Message, command: str, params: List[str]):
        """Handle /xa command - extract approved sessions"""
        try:
            if not params:
                # Extract all approved sessions
                sessions = self.session_manager.get_sessions_by_status('approved')
                if not sessions:
                    await message.reply("📭 No approved sessions to extract")
                    return
                
                # Create extraction
                extraction_name = f"Control_Room_All_Approved_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                zip_path = await self.admin_extractor.create_extraction_zip(sessions, extraction_name)
                
                if zip_path:
                    # Send ZIP file
                    with open(zip_path, 'rb') as zip_file:
                        zip_data = zip_file.read()
                    
                    await message.reply_document(
                        document=BufferedInputFile(
                            file=zip_data,
                            filename=f"{extraction_name}.zip"
                        ),
                        caption=f"📦 **Approved Sessions Extraction**\n\n✅ {len(sessions)} sessions extracted"
                    )
                    
                    # Clean up
                    os.remove(zip_path)
                    
                    # Move sessions to extracted
                    for session in sessions:
                        phone = session.get('data', {}).get('phone_number', session.get('data', {}).get('phone'))
                        if phone:
                            self.session_manager.move_session_to_extracted(phone)
                else:
                    await message.reply("❌ Failed to create extraction ZIP")
                    
            else:
                # Extract by country or phone
                param = params[0]
                if param.startswith('+') and len(param) > 8:
                    # Extract specific phone
                    await self.extract_specific_phone(message, param, 'approved')
                elif param.startswith('+'):
                    # Extract country approved sessions
                    await self.extract_country_sessions(message, param, 'approved')
                    
        except Exception as e:
            await self.report_error(e, f"Extract approved command: {command} {params}")
            await message.reply(f"❌ Error: {str(e)}")
    
    async def handle_extract_pending(self, message: types.Message, command: str, params: List[str]):
        """Handle /xp command - extract pending sessions"""
        try:
            sessions = self.session_manager.get_sessions_by_status('pending')
            if not sessions:
                await message.reply("📭 No pending sessions to extract")
                return
            
            extraction_name = f"Control_Room_All_Pending_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            zip_path = await self.admin_extractor.create_extraction_zip(sessions, extraction_name)
            
            if zip_path:
                with open(zip_path, 'rb') as zip_file:
                    zip_data = zip_file.read()
                
                await message.reply_document(
                    document=BufferedInputFile(
                        file=zip_data,
                        filename=f"{extraction_name}.zip"
                    ),
                    caption=f"📦 **Pending Sessions Extraction**\n\n⏳ {len(sessions)} sessions extracted"
                )
                
                os.remove(zip_path)
            else:
                await message.reply("❌ Failed to create extraction ZIP")
                
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def handle_extract_rejected(self, message: types.Message, command: str, params: List[str]):
        """Handle /xr command - extract rejected sessions"""
        try:
            sessions = self.session_manager.get_sessions_by_status('rejected')
            if not sessions:
                await message.reply("📭 No rejected sessions to extract")
                return
            
            extraction_name = f"Control_Room_All_Rejected_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            zip_path = await self.admin_extractor.create_extraction_zip(sessions, extraction_name)
            
            if zip_path:
                with open(zip_path, 'rb') as zip_file:
                    zip_data = zip_file.read()
                
                await message.reply_document(
                    document=BufferedInputFile(
                        file=zip_data,
                        filename=f"{extraction_name}.zip"
                    ),
                    caption=f"📦 **Rejected Sessions Extraction**\n\n❌ {len(sessions)} sessions extracted"
                )
                
                os.remove(zip_path)
            else:
                await message.reply("❌ Failed to create extraction ZIP")
                
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def handle_extract_command(self, message: types.Message, command: str, params: List[str]):
        """Handle /x command with country code"""
        try:
            if command.startswith('/xa ') and len(params) >= 1:
                # Extract approved sessions for country
                await self.extract_country_sessions(message, params[0], 'approved')
            elif command.startswith('/xp ') and len(params) >= 1:
                # Extract pending sessions for country  
                await self.extract_country_sessions(message, params[0], 'pending')
            elif command.startswith('/xr ') and len(params) >= 1:
                # Extract rejected sessions for country
                await self.extract_country_sessions(message, params[0], 'rejected')
                
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def extract_country_sessions(self, message: types.Message, country_code: str, status: str):
        """Extract sessions for specific country and status"""
        try:
            sessions = self.session_manager.get_sessions_by_status(status)
            country_sessions = [
                s for s in sessions 
                if s.get('data', {}).get('country_code') == country_code
            ]
            
            if not country_sessions:
                await message.reply(f"📭 No {status} sessions found for {country_code}")
                return
            
            extraction_name = f"Control_Room_{country_code}_{status.title()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            zip_path = await self.admin_extractor.create_extraction_zip(country_sessions, extraction_name)
            
            if zip_path:
                with open(zip_path, 'rb') as zip_file:
                    zip_data = zip_file.read()
                
                status_emoji = "✅" if status == "approved" else "⏳" if status == "pending" else "❌"
                
                await message.reply_document(
                    document=BufferedInputFile(
                        file=zip_data,
                        filename=f"{extraction_name}.zip"
                    ),
                    caption=f"📦 **{country_code} {status.title()} Sessions**\n\n{status_emoji} {len(country_sessions)} sessions extracted"
                )
                
                os.remove(zip_path)
                
                # Move approved sessions to extracted
                if status == 'approved':
                    for session in country_sessions:
                        phone = session.get('data', {}).get('phone_number', session.get('data', {}).get('phone'))
                        if phone:
                            self.session_manager.move_session_to_extracted(phone)
            else:
                await message.reply("❌ Failed to create extraction ZIP")
                
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    async def extract_specific_phone(self, message: types.Message, phone_number: str, status: str):
        """Extract specific phone session"""
        try:
            sessions = self.session_manager.get_sessions_by_status(status)
            session = next((
                s for s in sessions 
                if s.get('data', {}).get('phone_number') == phone_number or s.get('data', {}).get('phone') == phone_number
            ), None)
            
            if not session:
                await message.reply(f"❌ {status.title()} session not found: {phone_number}")
                return
            
            extraction_name = f"Control_Room_{phone_number.replace('+', '')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            zip_path = await self.admin_extractor.create_extraction_zip([session], extraction_name)
            
            if zip_path:
                with open(zip_path, 'rb') as zip_file:
                    zip_data = zip_file.read()
                
                await message.reply_document(
                    document=BufferedInputFile(
                        file=zip_data,
                        filename=f"{extraction_name}.zip"
                    ),
                    caption=f"📦 **Session Extraction**\n\n📱 {phone_number} extracted"
                )
                
                os.remove(zip_path)
                
                # Move to extracted if approved
                if status == 'approved':
                    self.session_manager.move_session_to_extracted(phone_number)
            else:
                await message.reply("❌ Failed to create extraction ZIP")
                
        except Exception as e:
            await message.reply(f"❌ Error: {str(e)}")
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin"""
        return user_id in self.admin_ids or (
            self.database.get_user(user_id) and 
            self.database.get_user(user_id).get('is_admin', False)
        )
    
    def register_handlers(self, dp: Dispatcher):
        """Register reporting system handlers"""
        # Control room message handler
        dp.message.register(
            self.handle_control_room_message,
            lambda message: message.chat.id == self.settings.get('control_room_chat_id') and message.text and message.text.startswith('/')
        )