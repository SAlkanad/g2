"""
Callback Utility Functions

Provides helper functions for handling callback queries properly 
with aiogram bot instances.
"""

from aiogram import Bot
from aiogram.types import CallbackQuery
import logging

logger = logging.getLogger(__name__)

async def answer_callback_query(bot: Bot, callback_query: CallbackQuery, text: str, show_alert: bool = False):
    """
    Safely answer a callback query with proper bot instance handling
    
    Args:
        bot: The bot instance
        callback_query: The callback query to answer
        text: Text to show in the callback answer
        show_alert: Whether to show as an alert popup
    """
    try:
        await bot.answer_callback_query(
            callback_query.id,
            text=text,
            show_alert=show_alert
        )
    except Exception as e:
        # Common errors like "query too old" or "query ID invalid" are not critical
        if "too old" in str(e).lower() or "invalid" in str(e).lower():
            logger.warning(f"Callback query expired or invalid: {e}")
        else:
            logger.error(f"Error answering callback query: {e}")
        
        # Don't attempt fallback for expired queries as it will also fail