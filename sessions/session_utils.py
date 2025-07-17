"""
Shared utilities for session management operations.

This module contains common session-related functions used across
multiple session management modules to avoid code duplication.
"""

import asyncio
import logging
from telethon import TelegramClient
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty
from telethon.errors import (
    AuthKeyUnregisteredError,
    UserDeactivatedError,
    UserDeactivatedBanError,
    ChatWriteForbiddenError,
    FloodWaitError,
)

logger = logging.getLogger(__name__)


async def check_account_frozen(client: TelegramClient, me) -> bool:
    """Check if the Telegram account has restrictions.

    Sends a test message to Saved Messages and fetches dialogs to detect
    frozen or limited accounts.
    
    Args:
        client: Active TelegramClient instance
        me: User information from client.get_me()
        
    Returns:
        bool: True if account is frozen/restricted, False if normal
    """
    try:
        # Attempt to write to Saved Messages
        try:
            test_msg = await client.send_message('me', 'test', silent=True)
            await client.delete_messages('me', test_msg.id)
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 5))
        except ChatWriteForbiddenError:
            logger.error(f"Account {me.id} cannot write to Saved Messages")
            return True
        except (UserDeactivatedError, UserDeactivatedBanError):
            logger.error(f"Account {me.id} is deactivated/banned")
            return True

        # Test ability to get dialogs
        try:
            await client(GetDialogsRequest(
                offset_date=None,
                offset_id=0,
                offset_peer=InputPeerEmpty(),
                limit=1,
                hash=0
            ))
        except (UserDeactivatedError, UserDeactivatedBanError) as e:
            logger.error("Account %s is deactivated/banned: %s", me.id, e)
            return True
        except Exception as e:  # pragma: no cover - just in case
            logger.warning("Error checking account status for %s: %s", me.id, e)
            return False

        return False

    except (AuthKeyUnregisteredError, UserDeactivatedError, UserDeactivatedBanError) as e:
        logger.error("Account %s is deactivated/banned: %s", me.id, e)
        return True
    except Exception as e:  # pragma: no cover - just in case
        logger.warning("Error checking account status for %s: %s", me.id, e)
        return False


# Configuration constants
SESSION_TERMINATION_DELAY_HOURS = 12
SESSION_TOTAL_WAIT_HOURS = 23
SESSION_RETRY_DELAY_HOURS = SESSION_TOTAL_WAIT_HOURS - SESSION_TERMINATION_DELAY_HOURS  # 11 hours
MAX_TERMINATION_ATTEMPTS = 2