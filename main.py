"""
Account Market Bot - Complete rewrite
A Telegram bot for selling and buying phone numbers/accounts
"""
import asyncio
import os
import logging
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Optional

# Load environment variables first
from dotenv import load_dotenv
os.chdir(os.path.dirname(__file__))
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from database.database import db
from languages.languages import get_text, get_language_name, get_supported_languages
from config_validator import ConfigValidator
from country_filter_service import CountryFilterService
# AdminExtractor is now handled through AdminIntegration
from auto_sync_scheduler import auto_sync_scheduler
from notification_service import init_notification_service
from admin.admin_integration import AdminIntegration
from network.network_monitor import initialize_network_monitoring, get_network_health

# Configure centralized logging
from logging_config import configure_application_logging, get_logger
configure_application_logging()
logger = get_logger(__name__)

# Configuration - Require all critical environment variables
API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

# Get API ID and hash from database first, fallback to env
def get_api_credentials():
    """Get API credentials from database or environment"""
    try:
        bot_settings = db.get_bot_settings()
        if bot_settings:
            return bot_settings['api_id'], bot_settings['api_hash']
    except:
        pass
    
    # Fallback to environment variables
    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    
    if not api_id or not api_hash:
        raise ValueError("API_ID and API_HASH environment variables are required")
    
    return int(api_id), api_hash

API_ID, API_HASH = get_api_credentials()
# Require admin IDs to be configured
admin_ids_str = os.getenv("ADMIN_IDS")
if not admin_ids_str:
    raise ValueError("ADMIN_IDS environment variable is required")
ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip().isdigit()]

# Initialize session paths
from sessions.session_paths import initialize_session_paths, get_session_directory_constants, create_all_session_directories

# Initialize session paths with environment variable or default
session_paths = initialize_session_paths()

# Create all required directories
if not create_all_session_directories():
    raise RuntimeError("Failed to create required session directories")

# Get directory constants for backward compatibility
directory_constants = get_session_directory_constants()
SESSIONS_DIR = directory_constants['SESSIONS_DIR']
PENDING_DIR = directory_constants['PENDING_DIR']
APPROVED_DIR = directory_constants['APPROVED_DIR']
REJECTED_DIR = directory_constants['REJECTED_DIR']
EXTRACTED_DIR = directory_constants['EXTRACTED_DIR']

logger.info(f"Session directories initialized under: {SESSIONS_DIR}")

# Initialize network configuration
from network.network_config import get_network_config, configure_ssl_warnings
from network.ssl_config import initialize_ssl_for_telethon, validate_ssl_configuration
from network.security_config import validate_startup_security

# Validate security configuration first
logger.info("Validating security configuration...")
security_valid, errors, warnings, security_issues = validate_startup_security()

if security_issues:
    logger.critical("SECURITY ISSUES DETECTED:")
    for issue in security_issues:
        logger.critical(f"  {issue}")
    raise RuntimeError("Critical security issues detected. Cannot start application.")

if errors:
    logger.error("Configuration errors detected:")
    for error in errors:
        logger.error(f"  {error}")
    raise RuntimeError("Configuration errors detected. Cannot start application.")

if warnings:
    logger.warning("Configuration warnings:")
    for warning in warnings:
        logger.warning(f"  {warning}")

logger.info("Security validation completed successfully")

# Configure SSL and network settings
configure_ssl_warnings()
ssl_context = initialize_ssl_for_telethon()

# Validate SSL configuration
if not validate_ssl_configuration():
    raise RuntimeError("SSL configuration validation failed")

# Get network configuration
network_config = get_network_config()

# Initialize bot (session will be created in main function)
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Initialize notification service and management
notification_service = init_notification_service(bot, db)

# Initialize new modular admin system (registration moved to after imports)
admin_integration = None

# States
class LanguageSelection(StatesGroup):
    waiting_language = State()

class WithdrawStates(StatesGroup):
    waiting_amount = State()
    waiting_details = State()

# Keyboard builders
def get_language_keyboard() -> InlineKeyboardMarkup:
    """Get language selection keyboard"""
    kb = []
    for code in get_supported_languages():
        kb.append([InlineKeyboardButton(
            text=get_language_name(code), 
            callback_data=f'lang_{code}'
        )])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_main_keyboard(lang: str, user_id: int) -> ReplyKeyboardMarkup:
    """Get main menu keyboard"""
    is_admin = db.is_admin(user_id)
    kb = [
        [KeyboardButton(text=get_text('sell_accounts', lang)), 
         KeyboardButton(text=get_text('total_accounts_sold', lang))],
        [KeyboardButton(text=get_text('cash_out', lang)), 
         KeyboardButton(text=get_text('balance', lang))],
        [KeyboardButton(text=get_text('live_support', lang)), 
         KeyboardButton(text=get_text('rules', lang))],
        [KeyboardButton(text=get_text('available_countries', lang)), 
         KeyboardButton(text=get_text('bot_updates', lang))],
        [KeyboardButton(text=get_text('language_settings', lang))]
    ]
    
    if is_admin:
        kb.append([KeyboardButton(text=get_text('admin_panel', lang))])
    
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_cancel_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Get cancel keyboard"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text('cancel', lang), callback_data='cancel')]
    ])

# Helper functions

def is_banned(user_id: int) -> bool:
    """Check if user is banned"""
    user = db.get_user(user_id)
    return user and user['is_banned']

def get_user_language(user_id: int) -> str:
    """Get user's language preference from database"""
    try:
        user = db.get_user(user_id)
        return user.get('language', 'en') if user else 'en'
    except Exception as e:
        logger.error(f"Error getting user language: {e}")
        return 'en'

def escape_markdown(text: str) -> str:
    """Escape Markdown special characters"""
    if not text:
        return ""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    escaped_text = str(text)
    for char in special_chars:
        escaped_text = escaped_text.replace(char, f'\\{char}')
    return escaped_text

async def handle_frozen_account(message: types.Message, user: dict, phone: str, account_info: dict):
    """Handle frozen account detection with proper notification"""
    try:
        lang = user['language']
        user_id = user['user_id']
        
        logger.info(f"Handling frozen account for user {user_id}, phone {phone}")
        
        # Check if session is already in rejected folder (saved by session validator)
        rejected_session = os.path.join(REJECTED_DIR, f"{phone}.session")
        rejected_json = os.path.join(REJECTED_DIR, f"{phone}.json")
        
        session_already_rejected = os.path.exists(rejected_session) or os.path.exists(rejected_json)
        
        if session_already_rejected:
            logger.info(f"Session {phone} already saved to rejected folder by validator")
            db_success = True
            file_success = True
        else:
            # Move session to rejected status in database
            db_success = db.move_session_to_rejected(phone, user_id, "Account is frozen/restricted")
            
            # Move session files to rejected folder
            file_success = await move_session_to_rejected_folder(phone, user_id, "Account is frozen/restricted")
        
        if db_success or file_success or session_already_rejected:
            # Add violation record
            violation_reason = f"Frozen/restricted Telegram account detected for {phone}"
            violation_details = f"Account info: {account_info.get('first_name', 'N/A')} (@{account_info.get('username', 'N/A')}) ID: {account_info.get('user_id', 'N/A')}"
            
            try:
                db.add_user_violation(
                    user_id=user_id,
                    violation_type='frozen_account',
                    violation_reason=violation_reason,
                    phone_number=phone,
                    admin_notes=violation_details
                )
                logger.info(f"Added violation record for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to add violation record: {e}")
        
            # Check violation count
            try:
                frozen_violations = db.get_user_violation_count(user_id, 'frozen_account')
                logger.info(f"User {user_id} has {frozen_violations} frozen account violations")
            except Exception as e:
                logger.error(f"Failed to get violation count: {e}")
                frozen_violations = 1  # Assume first violation if can't check
            
            # Send appropriate notification based on violation count
            try:
                if frozen_violations == 1:
                    # First violation - warning
                    warning_text = get_text('account_rejected_frozen', lang, phone=phone)
                    await message.answer(warning_text, parse_mode='Markdown')
                    logger.info(f"Sent first violation warning to user {user_id}")
                    
                elif frozen_violations >= 2:
                    # Second or more violation - ban user and freeze balance
                    try:
                        db.ban_user(user_id, admin_id=0)  # System ban
                        logger.info(f"Banned user {user_id} for repeated frozen accounts")
                    except Exception as e:
                        logger.error(f"Failed to ban user {user_id}: {e}")
                    
                    ban_text = get_text('account_banned_frozen', lang, 
                                      violations=frozen_violations, 
                                      balance=user['balance'])
                    await message.answer(ban_text, parse_mode='Markdown')
                    logger.info(f"Sent ban notification to user {user_id}")
                    
                    # Notify admins
                    username = user.get('first_name') or user.get('username') or 'Unknown'
                    admin_notification = get_text('admin_user_banned', 'en', 
                                                username=username, 
                                                user_id=user_id, 
                                                phone=phone, 
                                                violations=frozen_violations, 
                                                balance=user['balance'])
                    
                    # Send to all admins
                    for admin_id in ADMIN_IDS:
                        try:
                            await bot.send_message(admin_id, admin_notification, parse_mode='Markdown')
                            logger.info(f"Sent admin notification to {admin_id}")
                        except Exception as e:
                            logger.error(f"Failed to send admin notification to {admin_id}: {e}")
                    
                    # Also try to send to database admins
                    try:
                        admin_users = db.get_all_admins()
                        for admin_user in admin_users:
                            if admin_user['user_id'] not in ADMIN_IDS:
                                try:
                                    await bot.send_message(admin_user['user_id'], admin_notification, parse_mode='Markdown')
                                    logger.info(f"Sent admin notification to database admin {admin_user['user_id']}")
                                except Exception as e:
                                    logger.error(f"Failed to send admin notification to {admin_user['user_id']}: {e}")
                    except Exception as e:
                        logger.error(f"Failed to get admin users from database: {e}")
                        
            except Exception as e:
                logger.error(f"Failed to send user notification: {e}")
                # Fallback notification
                try:
                    await message.answer(
                        f"❌ **Account Rejected - Frozen Account**\n\n"
                        f"Your account ({phone}) has been rejected because it appears to be frozen or restricted.\n\n"
                        f"Please contact support for assistance.",
                        parse_mode='Markdown'
                    )
                except Exception as fallback_error:
                    logger.error(f"Even fallback notification failed: {fallback_error}")
        
            logger.info(f"Frozen account handling completed for user {user_id}, phone {phone}, violations: {frozen_violations}")
        else:
            # All operations failed
            logger.error(f"Failed to handle frozen session {phone} - all operations failed")
            try:
                await message.answer(
                    "❌ **Account Verification Failed**\n\n"
                    "Your account appears to have issues and could not be processed. "
                    "Please contact support for assistance.",
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send error notification: {e}")
        
    except Exception as e:
        logger.error(f"Critical error handling frozen account for user {user_id}, phone {phone}: {e}")
        try:
            await message.answer(
                "❌ **System Error**\n\n"
                "An unexpected error occurred while processing your account. "
                "Please contact support with this error code: FROZEN_HANDLE_ERROR",
                parse_mode='Markdown'
            )
        except Exception as final_error:
            logger.error(f"Final error notification failed: {final_error}")

async def move_session_to_rejected_folder(phone: str, user_id: int, reason: str) -> bool:
    """Move session files from pending to rejected folder"""
    try:
        import shutil
        
        # Use the properly defined directory paths instead of hardcoded ones
        pending_session = os.path.join(PENDING_DIR, f"{phone}.session")
        pending_json = os.path.join(PENDING_DIR, f"{phone}.json")
        
        rejected_session = os.path.join(REJECTED_DIR, f"{phone}.session")
        rejected_json = os.path.join(REJECTED_DIR, f"{phone}.json")
        
        # Ensure rejected directory exists
        os.makedirs(REJECTED_DIR, exist_ok=True)
        
        success = True
        
        # Move session file if it exists
        if os.path.exists(pending_session):
            try:
                # Remove target file if it exists to avoid conflicts
                if os.path.exists(rejected_session):
                    os.remove(rejected_session)
                shutil.move(pending_session, rejected_session)
                logger.info(f"Moved session file: {pending_session} -> {rejected_session}")
            except Exception as e:
                logger.error(f"Failed to move session file {pending_session}: {e}")
                success = False
        else:
            logger.warning(f"Session file not found: {pending_session}")
            success = False
        
        # Handle JSON file
        session_data = {}
        if os.path.exists(pending_json):
            # Read existing JSON and update
            try:
                with open(pending_json, 'r') as f:
                    session_data = json.load(f)
            except Exception as e:
                logger.error(f"Failed to read JSON file {pending_json}: {e}")
                session_data = {}
        
        # Update or create session data
        session_data.update({
            'phone': phone,
            'user_id': user_id,
            'status': 'rejected',
            'rejection_reason': reason,
            'rejected_at': datetime.now().isoformat(),
            'rejected_by': 'system'
        })
        
        # Ensure basic fields exist
        if 'created_by' not in session_data:
            session_data['created_by'] = user_id
        if 'created_at' not in session_data:
            session_data['created_at'] = datetime.now().isoformat()
        
        # Write to rejected folder
        try:
            with open(rejected_json, 'w') as f:
                json.dump(session_data, f, indent=2)
            logger.info(f"Created/updated JSON file in rejected folder: {rejected_json}")
            
            # Remove from pending if it exists
            if os.path.exists(pending_json):
                os.remove(pending_json)
                logger.info(f"Removed JSON from pending: {pending_json}")
                
        except Exception as e:
            logger.error(f"Failed to handle JSON file for {phone}: {e}")
            success = False
        
        return success
        
    except Exception as e:
        logger.error(f"Error moving session {phone} to rejected folder: {e}")
        return False

async def handle_2fa_rejection(message: types.Message, user: dict, phone: str):
    """Handle 2FA account rejection with improved error handling"""
    try:
        lang = user['language']
        user_id = user['user_id']
        
        logger.info(f"Handling 2FA rejection for user {user_id}, phone {phone}")
        
        # Check if session is already in rejected folder (saved by session validator)
        rejected_session = os.path.join(REJECTED_DIR, f"{phone}.session")
        rejected_json = os.path.join(REJECTED_DIR, f"{phone}.json")
        
        session_already_rejected = os.path.exists(rejected_session) or os.path.exists(rejected_json)
        
        if session_already_rejected:
            logger.info(f"2FA session {phone} already saved to rejected folder by validator")
            db_success = True
            file_success = True
        else:
            # Move session to rejected status in database
            db_success = db.move_session_to_rejected(phone, user_id, "Account has 2FA enabled")
            
            # Move session files to rejected folder
            file_success = await move_session_to_rejected_folder(phone, user_id, "Account has 2FA enabled")
        
        if db_success or file_success or session_already_rejected:
            try:
                rejection_text = get_text('account_rejected_2fa', lang, phone=phone)
                await message.answer(rejection_text, parse_mode='Markdown')
                logger.info(f"Sent 2FA rejection notification to user {user_id}")
            except Exception as e:
                logger.error(f"Failed to send 2FA rejection notification: {e}")
                # Fallback notification
                await message.answer(
                    f"❌ **Account Rejected - 2FA Enabled**\n\n"
                    f"Your account ({phone}) has 2FA enabled which prevents automatic processing.\n\n"
                    f"Please disable 2FA and try again.",
                    parse_mode='Markdown'
                )
        else:
            logger.error(f"Failed to move 2FA session {phone} to rejected")
            await message.answer(
                "❌ **Account Processing Error**\n\n"
                "Your account could not be processed due to 2FA restrictions. "
                "Please contact support for assistance.",
                parse_mode='Markdown'
            )
    
    except Exception as e:
        logger.error(f"Error handling 2FA rejection for {phone}: {e}")
        try:
            await message.answer(
                "❌ **Processing Error**\n\n"
                "An error occurred while processing your account. "
                "Please try again later or contact support.",
                parse_mode='Markdown'
            )
        except Exception as final_error:
            logger.error(f"Failed to send error message: {final_error}")

def get_user_info_text(user: dict, lang: str) -> str:
    """Get formatted user info text"""
    join_date = user['created_at'][:10] if user['created_at'] else 'Unknown'
    return get_text('user_info', lang, 
                   user_id=user['user_id'], 
                   balance=user['balance'], 
                   join_date=join_date)

def verify_session_directories():
    """Verify that all session directories exist and are accessible"""
    try:
        from sessions.session_paths import get_session_paths
        session_paths = get_session_paths()
        required_dirs = session_paths.get_required_directories()
        
        for directory in required_dirs:
            if not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                logger.info(f"Created missing directory: {directory}")
            elif not os.path.isdir(directory):
                logger.error(f"Path exists but is not a directory: {directory}")
                return False
            elif not os.access(directory, os.R_OK | os.W_OK):
                logger.error(f"Directory is not readable/writable: {directory}")
                return False
        
        logger.info("All session directories verified successfully")
        return True
    except Exception as e:
        logger.error(f"Error verifying session directories: {e}")
        return False

# Handlers
@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    """Start command - language selection for new users"""
    try:
        user_id = message.from_user.id
        logger.info(f"User {user_id} started the bot")
        
        user = db.get_user(user_id)
        
        if not user:
            # New user - show language selection
            logger.info(f"New user {user_id} - showing language selection")
            await message.answer(
                "🌍 Welcome! Please select your language:\n"
                "مرحباً! يرجى اختيار لغتك:\n"
                "خوش آمدید! لطفاً زبان خود را انتخاب کنید:\n"
                "স্বাগতম! অনুগ্রহ করে আপনার ভাষা নির্বাচন করুন:",
                reply_markup=get_language_keyboard()
            )
            await state.set_state(LanguageSelection.waiting_language)
        else:
            # Existing user - show main menu
            logger.info(f"Existing user {user_id} - showing main menu")
            await show_main_menu(message, user)
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        user_language = get_user_language(message.from_user.id)
        await message.answer(get_text("error", user_language))

async def show_main_menu(message: types.Message, user: dict):
    """Show main menu with user info"""
    lang = user['language']
    user_info = get_user_info_text(user, lang)
    
    welcome_text = get_text('welcome_back', lang) + '\n\n' + user_info + '\n\n' + get_text('main_menu', lang)
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(lang, user['user_id']),
        parse_mode='Markdown'
    )

# Language selection handler
@dp.callback_query(F.data.startswith('lang_'))
async def language_selection(callback: types.CallbackQuery, state: FSMContext):
    """Handle language selection (only for user language setting, not admin content editing)"""
    # Check if we're in admin state - if so, let the admin handler deal with it
    current_state = await state.get_state()
    
    lang_code = callback.data.split('_')[1]
    user_id = callback.from_user.id
    
    # Create or update user
    user = db.get_user(user_id)
    if not user:
        # New user
        db.create_user(
            user_id=user_id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
            language=lang_code
        )
        
        # Set admin if in ADMIN_IDS
        if user_id in ADMIN_IDS:
            db.add_admin(user_id)
    else:
        # Update language
        db.update_user_language(user_id, lang_code)
    
    # Get updated user info
    user = db.get_user(user_id)
    
    await callback.message.edit_text(get_text('language_selected', lang_code))
    await show_main_menu(callback.message, user)
    await state.clear()

# Main menu handlers
@dp.message(F.text.in_([
    get_text('sell_accounts', lang) for lang in get_supported_languages()
]))
async def sell_accounts_handler(message: types.Message, state: FSMContext):
    """Handle sell accounts request - redirect to new sell account system"""
    user = db.get_user(message.from_user.id)
    if not user:
        user_language = get_user_language(message.from_user.id)
        await message.answer(get_text("error", user_language))
        return
    
    # Check if user is banned
    if user['is_banned']:
        user_language = get_user_language(message.from_user.id)
        await message.answer(get_text("user_banned", user_language, reason="Contact support for assistance."))
        return
    
    # Create a callback query mock to use the new system
    callback_data = types.CallbackQuery(
        id="sell_accounts_redirect",
        from_user=message.from_user,
        chat_instance="sell_accounts",
        message=message,
        data="sell_accounts"
    )
    
    # Store user ID in state data for the sell account system
    await state.update_data(user_id=message.from_user.id)
    
    # Call the new sell account system
    await sell_account_system.show_available_continents(callback_data, state)

@dp.message(F.text.in_([
    get_text('total_accounts_sold', lang) for lang in get_supported_languages()
]))
async def total_accounts_sold_handler(message: types.Message):
    """Handle total accounts sold request"""
    user = db.get_user(message.from_user.id)
    if not user:
        user_language = get_user_language(message.from_user.id)
        await message.answer(get_text("error", user_language))
        return
    
    lang = user['language']
    
    # Get user's sales statistics
    text = get_text('sales_statistics', lang) + "\n\n"
    text += get_text('total_sold', lang, total_sold=user['total_sold']) + "\n"
    text += get_text('total_earnings', lang, total_earnings=f"{user['total_earnings']:.2f}") + "\n"
    text += get_text('current_balance', lang, balance=f"{user['balance']:.2f}") + "\n\n"
    
    if user['total_sold'] == 0:
        text += get_text('no_sales_yet', lang)
    
    await message.answer(text, parse_mode='Markdown')

@dp.message(F.text.in_([
    get_text('cash_out', lang) for lang in get_supported_languages()
]))
async def cash_out_handler(message: types.Message, state: FSMContext):
    """Handle cash out request"""
    user = db.get_user(message.from_user.id)
    if not user:
        user_language = get_user_language(message.from_user.id)
        await message.answer(get_text("error", user_language))
        return
    
    lang = user['language']
    min_withdraw = float(db.get_setting('min_balance_withdraw') or 10.0)
    
    if user['balance'] < min_withdraw:
        await message.answer(get_text('min_withdrawal_error', lang, min_withdraw=min_withdraw, balance=user['balance']), parse_mode='Markdown')
        return
    
    await message.answer(
        f"💸 *Cash Out*\n\nYour balance: ${user['balance']}\nMinimum: ${min_withdraw}\n\nEnter amount to withdraw:",
        parse_mode='Markdown',
        reply_markup=get_cancel_keyboard(lang)
    )
    await state.set_state(WithdrawStates.waiting_amount)

@dp.message(F.text.in_([
    get_text('balance', lang) for lang in get_supported_languages()
]))
async def balance_handler(message: types.Message):
    """Handle balance request"""
    user = db.get_user(message.from_user.id)
    if not user:
        user_language = get_user_language(message.from_user.id)
        await message.answer(get_text("error", user_language))
        return
    
    lang = user['language']
    
    text = get_text('your_balance', lang) + "\n\n"
    text += get_text('current_balance', lang, balance=f"{user['balance']:.2f}") + "\n"
    text += get_text('total_earnings', lang, total_earnings=f"{user['total_earnings']:.2f}") + "\n"
    text += get_text('accounts_sold', lang, total_sold=user['total_sold']) + "\n\n"
    
    min_withdraw = float(db.get_setting('min_balance_withdraw') or 10.0)
    if user['balance'] >= min_withdraw:
        text += get_text('withdrawal_available', lang, min_withdraw=min_withdraw)
    else:
        text += get_text('withdrawal_not_available', lang, min_withdraw=min_withdraw)
    
    await message.answer(text, parse_mode='Markdown')

@dp.message(F.text.in_([
    get_text('live_support', lang) for lang in get_supported_languages()
]))
async def live_support_handler(message: types.Message):
    """Handle live support request"""
    user = db.get_user(message.from_user.id)
    if not user:
        user_language = get_user_language(message.from_user.id)
        await message.answer(get_text("error", user_language))
        return
    
    lang = user['language']
    support_content = db.get_content('support', lang)
    
    await message.answer(
        support_content.format(user_id=user['user_id']),
        parse_mode='Markdown'
    )

@dp.message(F.text.in_([
    get_text('rules', lang) for lang in get_supported_languages()
]))
async def rules_handler(message: types.Message):
    """Handle rules request"""
    user = db.get_user(message.from_user.id)
    if not user:
        user_language = get_user_language(message.from_user.id)
        await message.answer(get_text("error", user_language))
        return
    
    lang = user['language']
    
    # Try to get rules from Firebase first
    try:
        rules_content = db.get_content_from_firebase('rules', lang)
        logger.info(f"Retrieved rules content from Firebase for user {user['user_id']} in language {lang}")
    except Exception as e:
        logger.error(f"Error fetching rules from Firebase: {e}")
        # Fallback to local database
        rules_content = db.get_content('rules', lang)
        logger.info(f"Retrieved rules content from local database as fallback")
    
    await message.answer(rules_content, parse_mode='Markdown')

def get_country_continent_mapping():
    """Get mapping of countries to continents"""
    return {
        # Africa
        'DZ': 'Africa', 'AO': 'Africa', 'BJ': 'Africa', 'BW': 'Africa', 'BF': 'Africa',
        'BI': 'Africa', 'CV': 'Africa', 'CM': 'Africa', 'CF': 'Africa', 'TD': 'Africa',
        'KM': 'Africa', 'CG': 'Africa', 'CD': 'Africa', 'DJ': 'Africa', 'EG': 'Africa',
        'GQ': 'Africa', 'ER': 'Africa', 'SZ': 'Africa', 'ET': 'Africa', 'GA': 'Africa',
        'GM': 'Africa', 'GH': 'Africa', 'GN': 'Africa', 'GW': 'Africa', 'CI': 'Africa',
        'KE': 'Africa', 'LS': 'Africa', 'LR': 'Africa', 'LY': 'Africa', 'MG': 'Africa',
        'MW': 'Africa', 'ML': 'Africa', 'MR': 'Africa', 'MU': 'Africa', 'MA': 'Africa',
        'MZ': 'Africa', 'NA': 'Africa', 'NE': 'Africa', 'NG': 'Africa', 'RW': 'Africa',
        'ST': 'Africa', 'SN': 'Africa', 'SC': 'Africa', 'SL': 'Africa', 'SO': 'Africa',
        'ZA': 'Africa', 'SS': 'Africa', 'SD': 'Africa', 'TZ': 'Africa', 'TG': 'Africa',
        'TN': 'Africa', 'UG': 'Africa', 'ZM': 'Africa', 'ZW': 'Africa',
        
        # Asia
        'AF': 'Asia', 'AM': 'Asia', 'AZ': 'Asia', 'BH': 'Asia', 'BD': 'Asia',
        'BT': 'Asia', 'BN': 'Asia', 'KH': 'Asia', 'CN': 'Asia', 'CY': 'Asia',
        'GE': 'Asia', 'IN': 'Asia', 'ID': 'Asia', 'IR': 'Asia', 'IQ': 'Asia',
        'IL': 'Asia', 'JP': 'Asia', 'JO': 'Asia', 'KZ': 'Asia', 'KW': 'Asia',
        'KG': 'Asia', 'LA': 'Asia', 'LB': 'Asia', 'MY': 'Asia', 'MV': 'Asia',
        'MN': 'Asia', 'MM': 'Asia', 'NP': 'Asia', 'KP': 'Asia', 'OM': 'Asia',
        'PK': 'Asia', 'PS': 'Asia', 'PH': 'Asia', 'QA': 'Asia', 'SA': 'Asia',
        'SG': 'Asia', 'KR': 'Asia', 'LK': 'Asia', 'SY': 'Asia', 'TW': 'Asia',
        'TJ': 'Asia', 'TH': 'Asia', 'TL': 'Asia', 'TR': 'Asia', 'TM': 'Asia',
        'AE': 'Asia', 'UZ': 'Asia', 'VN': 'Asia', 'YE': 'Asia',
        
        # Europe
        'AL': 'Europe', 'AD': 'Europe', 'AT': 'Europe', 'BY': 'Europe', 'BE': 'Europe',
        'BA': 'Europe', 'BG': 'Europe', 'HR': 'Europe', 'CZ': 'Europe', 'DK': 'Europe',
        'EE': 'Europe', 'FI': 'Europe', 'FR': 'Europe', 'DE': 'Europe', 'GR': 'Europe',
        'HU': 'Europe', 'IS': 'Europe', 'IE': 'Europe', 'IT': 'Europe', 'XK': 'Europe',
        'LV': 'Europe', 'LI': 'Europe', 'LT': 'Europe', 'LU': 'Europe', 'MT': 'Europe',
        'MD': 'Europe', 'MC': 'Europe', 'ME': 'Europe', 'NL': 'Europe', 'MK': 'Europe',
        'NO': 'Europe', 'PL': 'Europe', 'PT': 'Europe', 'RO': 'Europe', 'RU': 'Europe',
        'SM': 'Europe', 'RS': 'Europe', 'SK': 'Europe', 'SI': 'Europe', 'ES': 'Europe',
        'SE': 'Europe', 'CH': 'Europe', 'UA': 'Europe', 'GB': 'Europe', 'VA': 'Europe',
        
        # North America
        'AG': 'North America', 'BS': 'North America', 'BB': 'North America', 'BZ': 'North America',
        'CA': 'North America', 'CR': 'North America', 'CU': 'North America', 'DM': 'North America',
        'DO': 'North America', 'SV': 'North America', 'GD': 'North America', 'GT': 'North America',
        'HT': 'North America', 'HN': 'North America', 'JM': 'North America', 'MX': 'North America',
        'NI': 'North America', 'PA': 'North America', 'KN': 'North America', 'LC': 'North America',
        'VC': 'North America', 'TT': 'North America', 'US': 'North America',
        
        # South America
        'AR': 'South America', 'BO': 'South America', 'BR': 'South America', 'CL': 'South America',
        'CO': 'South America', 'EC': 'South America', 'GY': 'South America', 'PY': 'South America',
        'PE': 'South America', 'SR': 'South America', 'UY': 'South America', 'VE': 'South America',
        
        # Oceania
        'AU': 'Oceania', 'FJ': 'Oceania', 'KI': 'Oceania', 'MH': 'Oceania',
        'FM': 'Oceania', 'NR': 'Oceania', 'NZ': 'Oceania', 'PW': 'Oceania',
        'PG': 'Oceania', 'WS': 'Oceania', 'SB': 'Oceania', 'TO': 'Oceania',
        'TV': 'Oceania', 'VU': 'Oceania'
    }

@dp.message(F.text.in_([
    get_text('available_countries', lang) for lang in get_supported_languages()
]))
async def available_countries_handler(message: types.Message):
    """Handle available countries request with enhanced filtering"""
    user = db.get_user(message.from_user.id)
    if not user:
        user_language = get_user_language(message.from_user.id)
        await message.answer(get_text("error", user_language))
        return
    
    lang = user['language']
    
    # Use country filter service for enhanced filtering
    country_filter = CountryFilterService(db)
    countries = country_filter.get_available_countries()
    
    if not countries:
        await message.answer(f"{get_text('no_countries_available', lang)}\n\n{get_text('countries_empty_message', lang)}", parse_mode='Markdown')
        return
    
    # Countries are already filtered by the service, so format for display
    available_countries = []
    
    for country in countries:
        country_info = {
            'name': country['country_name'],
            'code': country['country_code'],
            'price': country['price'],
            'remaining': country['available_quantity'],
            'target': country['target_quantity'],
            'current': country['approved_count']
        }
        available_countries.append(country_info)
    
    # Sort by remaining slots (descending) then by price (ascending)
    available_countries.sort(key=lambda x: (-x['remaining'], x['price']))
    
    # Check if we should show continents first (if more than 20 countries)
    if len(available_countries) > 20:
        await show_continents_for_countries(message, available_countries, [], lang)
    else:
        await show_all_countries_list(message, available_countries, [], lang)

async def show_continents_for_countries(message: types.Message, available_countries: list, full_countries: list, lang: str):
    """Show continents when there are more than 20 countries"""
    continent_mapping = get_country_continent_mapping()
    continent_counts = {}
    
    # Count countries per continent
    all_countries = available_countries + full_countries
    for country in all_countries:
        continent = continent_mapping.get(country['code'], 'Other')
        if continent not in continent_counts:
            continent_counts[continent] = {'available': 0, 'full': 0}
        
        if country in available_countries:
            continent_counts[continent]['available'] += 1
        else:
            continent_counts[continent]['full'] += 1
    
    # Create continent keyboard
    keyboard = []
    continent_emojis = {
        'Africa': '🌍',
        'Asia': '🌏', 
        'Europe': '🌍',
        'North America': '🌎',
        'South America': '🌎',
        'Oceania': '🌏'
    }
    
    text = "🌍 **Select a Continent to View Available Countries**\n\n"
    
    for continent, counts in sorted(continent_counts.items()):
        emoji = continent_emojis.get(continent, '🌐')
        total = counts['available'] + counts['full']
        available = counts['available']
        
        status = ""
        if available > 0:
            status = f"({available} available)"
        else:
            status = "(all full)"
        
        text += f"{emoji} **{continent}**: {total} countries {status}\n"
        
        keyboard.append([
            InlineKeyboardButton(
                text=f"{emoji} {continent} ({available} available)",
                callback_data=f"continent_countries:{continent}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="📊 View All (Compact)", callback_data="show_all_countries_compact")
    ])
    
    text += f"\n📊 **Total**: {len(all_countries)} countries ({len(available_countries)} accepting accounts)"
    
    await message.answer(
        text, 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode='Markdown'
    )

async def show_all_countries_list(message: types.Message, available_countries: list, full_countries: list, lang: str):
    """Show complete countries list when there are 20 or fewer countries"""
    text = "🌍 **Available Countries for Account Sales**\n\n"
    
    if available_countries:
        text += "✅ **ACCEPTING ACCOUNTS:**\n"
        for country in available_countries:
            status = "🟢 OPEN" if country['remaining'] > 10 else "🟡 LIMITED"
            text += f"• **{country['name']}** ({country['code']})\n"
            text += f"  💰 Price: ${country['price']:.2f} | 📊 Available: {country['remaining']} slots | {status}\n\n"
    
    if full_countries:
        text += "❌ **CURRENTLY FULL:**\n"
        for country in full_countries[:10]:  # Show max 10 full countries
            text += f"• **{country['name']}** ({country['code']}) - ${country['price']:.2f} | FULL\n"
        
        if len(full_countries) > 10:
            text += f"... and {len(full_countries) - 10} more countries are full\n"
    
    text += f"\n📊 **Summary:** {len(available_countries)} countries accepting accounts, {len(full_countries)} countries full"
    text += f"\n\n💡 **Tip:** Countries with higher remaining slots have better acceptance chances!"
    
    await message.answer(text, parse_mode='Markdown')

@dp.message(F.text.in_([
    get_text('bot_updates', lang) for lang in get_supported_languages()
]))
async def bot_updates_handler(message: types.Message):
    """Handle bot updates request"""
    user = db.get_user(message.from_user.id)
    if not user:
        user_language = get_user_language(message.from_user.id)
        await message.answer(get_text("error", user_language))
        return
    
    lang = user['language']
    
    # Try to get updates from Firebase first
    try:
        updates_content = db.get_content_from_firebase('updates', lang)
        logger.info(f"Retrieved updates content from Firebase for user {user['user_id']} in language {lang}")
    except Exception as e:
        logger.error(f"Error fetching updates from Firebase: {e}")
        # Fallback to local database
        updates_content = db.get_content('updates', lang)
        logger.info(f"Retrieved updates content from local database as fallback")
    
    await message.answer(updates_content, parse_mode='Markdown')

@dp.message(F.text.in_([
    get_text('language_settings', lang) for lang in get_supported_languages()
]))
async def language_settings_handler(message: types.Message, state: FSMContext):
    """Handle language settings request"""
    user = db.get_user(message.from_user.id)
    if not user:
        user_language = get_user_language(message.from_user.id)
        await message.answer(get_text("error", user_language))
        return
    
    lang = user['language']
    
    await message.answer(
        get_text('select_language', lang),
        reply_markup=get_language_keyboard()
    )

# Withdrawal handlers
@dp.message(WithdrawStates.waiting_amount)
async def withdraw_amount_received(message: types.Message, state: FSMContext):
    """Handle withdrawal amount"""
    user = db.get_user(message.from_user.id)
    lang = user['language']
    
    try:
        amount = float(message.text.strip())
        min_withdraw = float(db.get_setting('min_balance_withdraw') or 10.0)
        
        if amount < min_withdraw:
            await message.answer(get_text('min_withdrawal_error', lang, min_withdraw=min_withdraw, balance=user['balance']))
            return
        
        if amount > user['balance']:
            user_language = get_user_language(message.from_user.id)
            await message.answer(get_text("min_withdrawal_error", user_language, min_withdraw=3, balance=user['balance']))
            return
        
        await state.update_data(amount=amount)
        await message.answer(
            f"💸 Withdraw ${amount}\n\nSend your payment details (PayPal, bank account, etc.):",
            parse_mode='Markdown',
            reply_markup=get_cancel_keyboard(lang)
        )
        await state.set_state(WithdrawStates.waiting_details)
        
    except ValueError:
        user_language = get_user_language(message.from_user.id)
        await message.answer(get_text("error", user_language))

@dp.message(WithdrawStates.waiting_details)
async def withdraw_details_received(message: types.Message, state: FSMContext):
    """Handle withdrawal details"""
    user = db.get_user(message.from_user.id)
    lang = user['language']
    
    data = await state.get_data()
    amount = data['amount']
    
    # Create withdrawal request in database
    with sqlite3.connect(db.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO withdrawal_requests (user_id, amount, payment_details)
            VALUES (?, ?, ?)
        """, (user['user_id'], amount, message.text))
        conn.commit()
    
    await message.answer(
        f"✅ Withdrawal request submitted!\n\nAmount: ${amount}\nProcessing time: 1-3 business days",
        parse_mode='Markdown'
    )
    
    # Notify admins
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💸 *New Withdrawal Request*\n\nUser: {user['username'] or user['first_name']} ({user['user_id']})\nAmount: ${amount}\nDetails: {message.text}",
                parse_mode='Markdown'
            )
        except:
            pass
    
    await state.clear()

# Cancel handler
@dp.callback_query(F.data == 'cancel')
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    """Handle cancel action"""
    await state.clear()
    user = db.get_user(callback.from_user.id)
    if user:
        user_language = get_user_language(callback.from_user.id)
        await callback.message.edit_text(get_text("cancel", user_language))
        await show_main_menu(callback.message, user)
    else:
        user_language = get_user_language(callback.from_user.id)
        await callback.message.edit_text(get_text("cancel", user_language))

@dp.callback_query(F.data == 'back_main')
async def back_main_callback(callback: types.CallbackQuery, state: FSMContext):
    """Go back to main menu"""
    await state.clear()
    user = db.get_user(callback.from_user.id)
    if user:
        await callback.message.edit_text("🏠 Main Menu")
        await show_main_menu(callback.message, user)
    else:
        await callback.message.edit_text("Please use /start")

# Initialize and register admin system handlers before catch-all handler
admin_integration = AdminIntegration(bot, db, ADMIN_IDS, API_ID, API_HASH)
admin_integration.register_handlers(dp)
logger.info("Admin system handlers registered")

# Initialize sell account system
from sellaccount import SellAccountSystem
sell_account_system = SellAccountSystem(
    bot=bot,
    database=db,
    api_id=API_ID,
    api_hash=API_HASH,
    admin_chat_id=os.getenv('ADMIN_CHAT_ID', ''),
    reporting_system=None
)
sell_account_system.register_handlers(dp)
logger.info("Sell account system handlers registered")

# Error handler
@dp.message()
async def unknown_message(message: types.Message):
    """Handle unknown messages"""
    user = db.get_user(message.from_user.id)
    if not user:
        user_language = get_user_language(message.from_user.id)
        await message.answer(get_text("error", user_language))
        return
    
    lang = user['language']
    user_language = get_user_language(message.from_user.id)
    await message.answer(get_text("error", user_language))

@dp.callback_query(F.data == 'admin_back')
async def admin_back_callback(callback: types.CallbackQuery, state: FSMContext):
    """Handle back to admin panel"""
    user = db.get_user(callback.from_user.id)
    if not user or not user['is_admin']:
        user_language = get_user_language(callback.from_user.id)
        await callback.answer(get_text("access_denied", user_language), show_alert=True)
        return
    
    await state.clear()
    lang = user['language']
    await callback.message.edit_text(
        "🔧 Admin Panel",
        reply_markup=get_admin_keyboard(lang)
    )

@dp.callback_query(F.data.startswith('continent_countries:'))
async def continent_countries_callback(callback: types.CallbackQuery):
    """Handle continent selection to show countries"""
    continent = callback.data.split(':', 1)[1]
    
    user = db.get_user(callback.from_user.id)
    if not user:
        user_language = get_user_language(callback.from_user.id)
        await callback.answer(get_text("error", user_language), show_alert=True)
        return
    
    # Get countries data
    countries = []
    try:
        countries = db.get_countries_from_firebase(active_only=False)
    except Exception as e:
        logger.error(f"Error fetching countries from Firebase: {e}")
        countries = db.get_countries(active_only=False)
    
    if not countries:
        user_language = get_user_language(callback.from_user.id)
        await callback.answer(get_text("no_countries_available", user_language), show_alert=True)
        return
    
    # Process countries data
    available_countries = []
    full_countries = []
    
    for country in countries:
        current_qty = country.get('current_quantity', 0)
        target_qty = country['target_quantity']
        remaining = target_qty - current_qty
        
        country_info = {
            'name': country['country_name'],
            'code': country['country_code'],
            'price': country['price'],
            'remaining': remaining
        }
        
        if remaining > 0:
            available_countries.append(country_info)
        else:
            full_countries.append(country_info)
    
    # Filter by continent
    continent_mapping = get_country_continent_mapping()
    continent_available = []
    continent_full = []
    
    for country in available_countries:
        if continent_mapping.get(country['code'], 'Other') == continent:
            continent_available.append(country)
    
    for country in full_countries:
        if continent_mapping.get(country['code'], 'Other') == continent:
            continent_full.append(country)
    
    # Sort countries
    continent_available.sort(key=lambda x: (-x['remaining'], x['price']))
    continent_full.sort(key=lambda x: x['name'])
    
    # Create message
    continent_emojis = {
        'Africa': '🌍', 'Asia': '🌏', 'Europe': '🌍',
        'North America': '🌎', 'South America': '🌎', 'Oceania': '🌏'
    }
    
    emoji = continent_emojis.get(continent, '🌐')
    text = f"{emoji} **{continent} - Available Countries**\n\n"
    
    if continent_available:
        text += "✅ **ACCEPTING ACCOUNTS:**\n"
        for country in continent_available:
            status = "🟢 OPEN" if country['remaining'] > 10 else "🟡 LIMITED"
            text += f"• **{country['name']}** ({country['code']})\n"
            text += f"  💰 Price: ${country['price']:.2f} | 📊 Available: {country['remaining']} slots | {status}\n\n"
    
    if continent_full:
        text += "❌ **CURRENTLY FULL:**\n"
        for country in continent_full:
            text += f"• **{country['name']}** ({country['code']}) - ${country['price']:.2f} | FULL\n"
    
    if not continent_available and not continent_full:
        text += "❌ No countries available in this continent at the moment."
    
    text += f"\n📊 **{continent} Summary:** {len(continent_available)} accepting, {len(continent_full)} full"
    
    keyboard = [[InlineKeyboardButton(text="🔙 Back to Continents", callback_data="back_to_continents")]]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='Markdown')

@dp.callback_query(F.data == 'show_all_countries_compact')
async def show_all_countries_compact_callback(callback: types.CallbackQuery):
    """Handle compact view of all countries"""
    user = db.get_user(callback.from_user.id)
    if not user:
        user_language = get_user_language(callback.from_user.id)
        await callback.answer(get_text("error", user_language), show_alert=True)
        return
    
    # Get countries data
    countries = []
    try:
        countries = db.get_countries_from_firebase(active_only=False)
    except Exception as e:
        countries = db.get_countries(active_only=False)
    
    if not countries:
        user_language = get_user_language(callback.from_user.id)
        await callback.answer(get_text("no_countries_available", user_language), show_alert=True)
        return
    
    # Process countries data
    available_countries = []
    full_countries = []
    
    for country in countries:
        current_qty = country.get('current_quantity', 0)
        target_qty = country['target_quantity']
        remaining = target_qty - current_qty
        
        country_info = {
            'name': country['country_name'],
            'code': country['country_code'],
            'price': country['price'],
            'remaining': remaining
        }
        
        if remaining > 0:
            available_countries.append(country_info)
        else:
            full_countries.append(country_info)
    
    # Sort countries
    available_countries.sort(key=lambda x: (-x['remaining'], x['price']))
    full_countries.sort(key=lambda x: x['name'])
    
    # Create compact message
    text = "🌍 **All Countries (Compact View)**\n\n"
    
    if available_countries:
        text += "✅ **ACCEPTING ACCOUNTS:**\n"
        for country in available_countries:
            status = "🟢" if country['remaining'] > 10 else "🟡"
            text += f"{status} {country['name']} ({country['code']}) - ${country['price']:.2f} | {country['remaining']} slots\n"
    
    if full_countries:
        text += "\n❌ **CURRENTLY FULL:**\n"
        for country in full_countries[:15]:  # Limit to avoid long message
            text += f"🔴 {country['name']} ({country['code']}) - ${country['price']:.2f}\n"
        
        if len(full_countries) > 15:
            text += f"... and {len(full_countries) - 15} more countries are full\n"
    
    text += f"\n📊 **Summary:** {len(available_countries)} accepting, {len(full_countries)} full"
    
    keyboard = [[InlineKeyboardButton(text="🔙 Back to Continents", callback_data="back_to_continents")]]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='Markdown')

@dp.callback_query(F.data == 'back_to_continents')
async def back_to_continents_callback(callback: types.CallbackQuery):
    """Handle back to continents view"""
    user = db.get_user(callback.from_user.id)
    if not user:
        user_language = get_user_language(callback.from_user.id)
        await callback.answer(get_text("error", user_language), show_alert=True)
        return
    
    # Get countries data and show continents
    countries = []
    try:
        countries = db.get_countries_from_firebase(active_only=False)
    except Exception as e:
        countries = db.get_countries(active_only=False)
    
    if not countries:
        user_language = get_user_language(callback.from_user.id)
        await callback.answer(get_text("no_countries_available", user_language), show_alert=True)
        return
    
    # Process countries data
    available_countries = []
    full_countries = []
    
    for country in countries:
        current_qty = country.get('current_quantity', 0)
        target_qty = country['target_quantity']
        remaining = target_qty - current_qty
        
        country_info = {
            'name': country['country_name'],
            'code': country['country_code'],
            'price': country['price'],
            'remaining': remaining
        }
        
        if remaining > 0:
            available_countries.append(country_info)
        else:
            full_countries.append(country_info)
    
    # Show continents view
    continent_mapping = get_country_continent_mapping()
    continent_counts = {}
    
    all_countries = available_countries + full_countries
    for country in all_countries:
        continent = continent_mapping.get(country['code'], 'Other')
        if continent not in continent_counts:
            continent_counts[continent] = {'available': 0, 'full': 0}
        
        if country in available_countries:
            continent_counts[continent]['available'] += 1
        else:
            continent_counts[continent]['full'] += 1
    
    # Create continent keyboard
    keyboard = []
    continent_emojis = {
        'Africa': '🌍', 'Asia': '🌏', 'Europe': '🌍',
        'North America': '🌎', 'South America': '🌎', 'Oceania': '🌏'
    }
    
    text = "🌍 **Select a Continent to View Available Countries**\n\n"
    
    for continent, counts in sorted(continent_counts.items()):
        emoji = continent_emojis.get(continent, '🌐')
        total = counts['available'] + counts['full']
        available = counts['available']
        
        status = f"({available} available)" if available > 0 else "(all full)"
        text += f"{emoji} **{continent}**: {total} countries {status}\n"
        
        keyboard.append([InlineKeyboardButton(
            text=f"{emoji} {continent} ({available} available)",
            callback_data=f"continent_countries:{continent}"
        )])
    
    keyboard.append([InlineKeyboardButton(text="📊 View All (Compact)", callback_data="show_all_countries_compact")])
    
    text += f"\n📊 **Total**: {len(all_countries)} countries ({len(available_countries)} accepting accounts)"
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode='Markdown')

async def main():
    """Main function"""
    try:
        logger.info("🚀 Account Market Bot starting...")
        
        # Validate configuration
        validator = ConfigValidator(db)
        success, errors, warnings = validator.get_validation_results()
        
        if not success:
            logger.error("Configuration validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
            return
        
        if warnings:
            for warning in warnings:
                logger.warning(f"  - {warning}")
        
        # Check global 2FA password configuration
        logger.info("Checking global 2FA password configuration...")
        try:
            from config_service import ConfigService
            config_service = ConfigService(db)
            global_2fa_password = config_service.get_global_2fa_password()
            
            if not global_2fa_password:
                logger.warning("⚠️  GLOBAL 2FA PASSWORD NOT CONFIGURED")
                logger.warning("Users with 2FA-enabled accounts will NOT be able to sell their accounts.")
                logger.warning("To fix this, run: python3 setup_global_2fa.py")
                logger.warning("Or configure it via Admin Panel → Bot Settings → Global 2FA Settings")
                
                # Try to notify admins if bot token is available
                try:
                    temp_bot = Bot(token=API_TOKEN)
                    admin_ids = config_service.get_admin_ids()
                    
                    for admin_id in admin_ids:
                        try:
                            await temp_bot.send_message(
                                admin_id,
                                "⚠️ **Bot Startup Warning**\n\n"
                                "The bot started successfully but the global 2FA password is not configured.\n\n"
                                "**Impact:** Users with 2FA-enabled accounts cannot sell their accounts.\n\n"
                                "**To fix:**\n"
                                "• Run: `python3 setup_global_2fa.py`\n"
                                "• Or go to Admin Panel → Bot Settings → Global 2FA Settings\n\n"
                                "⏱️ Please configure this as soon as possible.",
                                parse_mode="Markdown"
                            )
                        except Exception as e:
                            logger.error(f"Failed to notify admin {admin_id} about 2FA config: {e}")
                    
                    await temp_bot.session.close()
                    
                except Exception as e:
                    logger.error(f"Failed to send 2FA configuration warnings to admins: {e}")
            else:
                logger.info("✅ Global 2FA password is configured")
                
        except Exception as e:
            logger.error(f"Error checking global 2FA password: {e}")
        
        # Verify session directories
        logger.info("Verifying session directories...")
        if not verify_session_directories():
            logger.error("Session directory verification failed")
            return
        logger.info("Session directories verified successfully")
        
        # Test database connection
        try:
            test_user = db.get_user(1)
            logger.info("Database connection successful")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return
        
        # Session scheduling functionality moved to sellaccount.py
        logger.info("Session scheduling functionality consolidated in sellaccount.py")
        
        # Check for auto-sync on startup
        try:
            logger.info("Checking for auto-sync requirement...")
            sync_result = db.auto_sync_to_firebase()
            if sync_result:
                logger.info("Auto-sync completed successfully")
            else:
                logger.info("Auto-sync not required or failed")
        except Exception as e:
            logger.error(f"Error during auto-sync check: {e}")
        
        # Start auto-sync scheduler
        try:
            await auto_sync_scheduler.start()
            logger.info("Auto-sync scheduler started")
        except Exception as e:
            logger.error(f"Error starting auto-sync scheduler: {e}")
        
        # Use the existing bot instance for polling (aiogram will handle session internally)
        polling_bot = bot
        
        # Start bot with retry logic
        logger.info("Starting bot polling...")
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                await dp.start_polling(polling_bot, skip_updates=True)
                break
            except Exception as e:
                logger.error(f"Polling failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error("Max retries exceeded. Bot stopped.")
                    raise
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error in main: {e}")
        raise
    finally:
        # Cleanup bot session (aiogram handles this automatically)
        logger.info("Bot polling stopped")
        
        # Cleanup auto-sync scheduler
        try:
            await auto_sync_scheduler.stop()
            logger.info("Auto-sync scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping auto-sync scheduler: {e}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown completed")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        exit(1)