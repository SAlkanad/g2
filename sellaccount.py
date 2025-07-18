"""
Sell Account System - Complete workflow for users selling Telegram accounts

This module handles the entire process from country selection to final account approval/rejection.
Includes phone verification, 2FA checking, frozen account detection, and automated session management.
"""

import os
import json
import asyncio
import logging
import random
import string
import shutil
import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from telethon import TelegramClient, errors, functions
from telethon.errors import AuthRestartError, FloodWaitError, PhoneCodeInvalidError, PhoneCodeExpiredError, SessionPasswordNeededError
from telethon.tl.functions.account import (
    GetPasswordRequest, 
    UpdatePasswordSettingsRequest,
    GetAuthorizationsRequest,
    ResetAuthorizationRequest
)
from telethon.tl.types.account import PasswordInputSettings
from telethon.sessions import StringSession
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from languages.languages import get_text

from database.database import Database
from config_service import ConfigService
from network.telegram_security import TelegramSecurityManager
from country_filter_service import CountryFilterService, get_continent_emoji

logger = logging.getLogger(__name__)


class SellAccountStates(StatesGroup):
    """FSM states for selling account process"""
    selecting_continent = State()
    selecting_country = State()
    waiting_phone_number = State()
    waiting_verification_code = State()
    waiting_2fa_password = State()
    processing_account = State()



class SellAccountSystem:
    """Complete system for handling account selling process"""
    
    def __init__(self, bot: Bot, database: Database, api_id: str, api_hash: str, admin_chat_id: str, reporting_system=None, config_service: ConfigService = None):
        self.bot = bot
        self.database = database
        self.api_id = api_id
        self.api_hash = api_hash
        self.admin_chat_id = admin_chat_id
        self.reporting_system = reporting_system
        self.config_service = config_service or ConfigService(database)
        self.country_filter = CountryFilterService(database)
        
        # Get admin IDs from config service for notifications
        try:
            self.admin_ids = self.config_service.get_admin_ids()
        except Exception as e:
            logger.error(f"Error getting admin IDs: {e}")
            self.admin_ids = []
        
        # Import session paths for centralized directory management
        from sessions.session_paths import get_session_paths
        session_paths = get_session_paths()
        
        # Folders for different account statuses (using centralized paths)
        self.folders = session_paths.get_folders_dict()
        
        # Create necessary directories
        for folder in self.folders.values():
            os.makedirs(folder, exist_ok=True)
        
        # Track active sessions for cleanup
        self.active_sessions = {}
        
        # Track verification attempts
        self.verification_attempts = {}
        
        # Phone to country code mapping for session naming
        self.phone_country_mapping = {
            '+1': 'US', '+44': 'GB', '+49': 'DE', '+33': 'FR', '+7': 'RU', '+86': 'CN',
            '+98': 'IR', '+966': 'SA', '+971': 'AE', '+91': 'IN', '+880': 'BD', '+93': 'AF',
            '+92': 'PK', '+90': 'TR', '+81': 'JP', '+82': 'KR', '+84': 'VN', '+62': 'ID',
            '+60': 'MY', '+65': 'SG', '+66': 'TH', '+55': 'BR', '+54': 'AR', '+52': 'MX',
            '+39': 'IT', '+34': 'ES', '+31': 'NL', '+46': 'SE', '+47': 'NO', '+358': 'FI',
            '+20': 'EG', '+234': 'NG', '+27': 'ZA', '+212': 'MA', '+213': 'DZ', '+216': 'TN',
            '+218': 'LY', '+963': 'SY', '+964': 'IQ', '+961': 'LB', '+962': 'JO', '+965': 'KW',
            '+974': 'QA', '+968': 'OM', '+973': 'BH', '+967': 'YE', '+994': 'AZ', '+995': 'GE',
            '+996': 'KG', '+998': 'UZ', '+992': 'TJ', '+993': 'TM'
        }
    
    def get_user_language(self, user_id: int) -> str:
        """Get user's language preference from database"""
        try:
            user = self.database.get_user(user_id)
            return user.get('language', 'en') if user else 'en'
        except Exception as e:
            logger.error(f"Error getting user language: {e}")
            return 'en'
    
    
    def extract_country_code_from_phone(self, phone_number: str) -> str:
        """Extract country code from phone number for session naming"""
        # Remove + and spaces
        clean_phone = phone_number.replace('+', '').replace(' ', '').replace('-', '')
        
        # Try to match country codes by length (longer codes first to avoid conflicts)
        # Sort by length descending to match longer codes first
        sorted_codes = sorted(self.phone_country_mapping.keys(), key=len, reverse=True)
        
        for country_prefix in sorted_codes:
            prefix_digits = country_prefix.replace('+', '')
            if clean_phone.startswith(prefix_digits):
                return self.phone_country_mapping[country_prefix]
        
        # If no match found, return 'XX' as unknown
        return 'XX'

    async def get_available_countries(self) -> List[Dict]:
        """Get list of available countries using the country filter service"""
        return self.country_filter.get_available_countries()
    
    async def show_available_continents(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Show available countries or continents based on count"""
        user_id = callback_query.from_user.id
        
        # Track user interaction
        if self.reporting_system:
            await self.reporting_system.report_user_interaction(user_id)
        
        # Get available countries with enhanced filtering
        countries = await self.get_available_countries()
        
        if not countries:
            # Answer callback query silently first
            try:
                await self.bot.answer_callback_query(callback_query.id)
            except Exception as e:
                logger.warning(f"Failed to answer callback query: {e}")
            
            # Get user language and send localized message
            user_language = self.get_user_language(user_id)
            text = get_text("countries_inactive_message", user_language)
            
            try:
                await callback_query.message.edit_text(
                    text=text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_main")]
                    ]),
                    parse_mode="Markdown"
                )
            except Exception:
                await callback_query.message.answer(
                    text=text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_main")]
                    ]),
                    parse_mode="Markdown"
                )
            return
        
        # If 20 or fewer countries, show them directly
        if len(countries) <= 20:
            await self.show_countries_directly(callback_query, state, countries)
        else:
            # More than 20 countries - show continents first
            await self.show_continents_menu(callback_query, state, countries)
    
    async def show_countries_directly(self, callback_query: types.CallbackQuery, state: FSMContext, countries: List[Dict]):
        """Show countries directly when 20 or fewer available"""
        # Get user language
        user_id = callback_query.from_user.id
        user_language = self.get_user_language(user_id)
        
        # Create keyboard with countries (2 per row)
        keyboard = []
        for i in range(0, len(countries), 2):
            row = []
            for j in range(2):
                if i + j < len(countries):
                    country = countries[i + j]
                    price = country.get('price', 0)
                    btn_text = f"🏳️ {country['country_name']} (${price:.2f})"
                    row.append(
                        InlineKeyboardButton(
                            text=btn_text,
                            callback_data=f"sell_country_{country['country_code']}"
                        )
                    )
            keyboard.append(row)
        
        keyboard.append([
            InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_main")
        ])
        
        # Use translation system
        text = get_text("select_country_for_sale", user_language, count=len(countries))
        
        try:
            await callback_query.message.edit_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="Markdown"
            )
        except Exception:
            await callback_query.message.answer(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="Markdown"
            )
        
        await state.set_state(SellAccountStates.selecting_country)
    
    async def show_continents_menu(self, callback_query: types.CallbackQuery, state: FSMContext, countries: List[Dict]):
        """Show continents menu when more than 20 countries available"""
        # Get user language
        user_id = callback_query.from_user.id
        user_language = self.get_user_language(user_id)
        
        # Group countries by continent using the filter service
        continent_countries = self.country_filter.get_countries_by_continent(countries)
        
        # Create keyboard with continents
        keyboard = []
        for continent in sorted(continent_countries.keys()):
            count = len(continent_countries[continent])
            emoji = get_continent_emoji(continent)
            btn_text = f"{emoji} {continent} ({count} countries)"
            keyboard.append([
                InlineKeyboardButton(
                    text=btn_text,
                    callback_data=f"sell_continent_{continent.replace(' ', '_')}"
                )
            ])
        
        keyboard.append([
            InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="back_main")
        ])
        
        # Use translation system
        text = get_text("select_continent_for_sale", user_language, 
                       total_countries=len(countries), 
                       total_continents=len(continent_countries))
        
        try:
            await callback_query.message.edit_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="Markdown"
            )
        except Exception:
            await callback_query.message.answer(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="Markdown"
            )
        
        await state.set_state(SellAccountStates.selecting_continent)

    async def show_continent_countries(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Show countries for selected continent"""
        user_id = callback_query.from_user.id
        continent = callback_query.data.replace('sell_continent_', '').replace('_', ' ')
        
        # Get available countries with enhanced filtering
        countries = await self.get_available_countries()
        
        # Get countries grouped by continent and filter for selected continent
        continent_countries_map = self.country_filter.get_countries_by_continent(countries)
        continent_countries = continent_countries_map.get(continent, [])
        
        if not continent_countries:
            # Answer callback query silently
            try:
                await self.bot.answer_callback_query(callback_query.id)
            except Exception as e:
                logger.warning(f"Failed to answer callback query: {e}")
            
            # Send localized message
            user_language = self.get_user_language(user_id)
            continent_emoji = get_continent_emoji(continent)
            text = get_text("continent_no_countries", user_language, 
                          emoji=continent_emoji, continent=continent)
            
            try:
                await callback_query.message.edit_text(
                    text=text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 Back to Continents", callback_data="sell_accounts")],
                        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_main")]
                    ]),
                    parse_mode="Markdown"
                )
            except Exception:
                await callback_query.message.answer(
                    text=text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 Back to Continents", callback_data="sell_accounts")],
                        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_main")]
                    ]),
                    parse_mode="Markdown"
                )
            return
        
        # Create keyboard with countries (2 per row)
        keyboard = []
        for i in range(0, len(continent_countries), 2):
            row = []
            for j in range(2):
                if i + j < len(continent_countries):
                    country = continent_countries[i + j]
                    price = country.get('price', 0)
                    btn_text = f"🏳️ {country['country_name']} (${price:.2f})"
                    row.append(
                        InlineKeyboardButton(
                            text=btn_text,
                            callback_data=f"sell_country_{country['country_code']}"
                        )
                    )
            keyboard.append(row)
        
        keyboard.extend([
            [InlineKeyboardButton(text="🔙 Back to Continents", callback_data="sell_accounts")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_main")]
        ])
        
        continent_emoji = get_continent_emoji(continent)
        text = (
            f"{continent_emoji} **{continent} Countries**\n\n"
            f"Available countries in {continent}:\n"
            f"Select a country to sell your account.\n\n"
            f"💰 Prices shown are earnings per approved account.\n\n"
            f"📊 **{len(continent_countries)} countries available**"
        )
        
        try:
            await callback_query.message.edit_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="Markdown"
            )
        except Exception:
            await callback_query.message.answer(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="Markdown"
            )
        
        await state.set_state(SellAccountStates.selecting_country)
    
    async def validate_country_availability(self, country_code: str) -> Tuple[Optional[Dict], str]:
        """Validate if a country is available using the country filter service"""
        return self.country_filter.validate_country_selection(country_code)
    
    async def country_selected(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Handle country selection with enhanced validation"""
        user_id = callback_query.from_user.id
        country_code = callback_query.data.split('_')[-1]
        
        # Validate country availability
        country, error_message = await self.validate_country_availability(country_code)
        
        if not country:
            # Answer callback query silently
            try:
                await self.bot.answer_callback_query(callback_query.id)
            except Exception as e:
                logger.warning(f"Failed to answer callback query: {e}")
            
            # Send localized error message
            user_language = self.get_user_language(user_id)
            text = get_text("country_not_available", user_language, 
                          error_message=error_message)
            
            try:
                await callback_query.message.edit_text(
                    text=text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 Back to Countries", callback_data="sell_accounts")],
                        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_main")]
                    ]),
                    parse_mode="Markdown"
                )
            except Exception:
                await callback_query.message.answer(
                    text=text,
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="🔙 Back to Countries", callback_data="sell_accounts")],
                        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_main")]
                    ]),
                    parse_mode="Markdown"
                )
            return
        
        # Store selected country
        await state.update_data(
            country_code=country_code, 
            country_name=country['country_name'], 
            price=country['price'],
            available_quantity=country['available_quantity']
        )
        
        text = (
            f"🌍 **Country Selected: {country['country_name']}**\n\n"
            f"💰 **Price per approved account:** ${country['price']:.2f}\n"
            f"📊 **Available slots:** {country['available_quantity']}\n"
            f"📈 **Target quantity:** {country.get('target_quantity', 0)}\n\n"
            "📱 **Next Step: Phone Number**\n\n"
            f"Please send your phone number from {country['country_name']} in international format.\n\n"
            "**Example formats:**\n"
            f"• +1234567890\n\n"
            "⚠️ **Important:** Use the phone number registered to your Telegram account."
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="sell_accounts")]]
        
        try:
            await callback_query.message.edit_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="Markdown"
            )
        except Exception:
            # If edit fails, send new message
            await callback_query.message.answer(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="Markdown"
            )
        
        await state.set_state(SellAccountStates.waiting_phone_number)
    
    async def phone_number_received(self, message: types.Message, state: FSMContext):
        """Process received phone number"""
        user_id = message.from_user.id
        user_language = self.get_user_language(user_id)
        phone = message.text.strip()
        
        # Clean phone number
        phone = re.sub(r'[^\d+]', '', phone)
        if not phone.startswith('+'):
            phone = '+' + phone
        
        # Validate phone number format
        if not re.match(r'^\+\d{10,15}$', phone):
            await message.reply(
                "❌ **Invalid phone number format**\n\n"
                "Please send a valid phone number in international format:\n"
                "• +1234567890\n"
                "• 1234567890\n\n"
                "Try again:",
                parse_mode="Markdown"
            )
            return
        
        # Store phone number
        await state.update_data(phone_number=phone)
        
        # Create Telegram client for verification with retry logic
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                # Format session name as +966_533077429 (prefix_number format)
                clean_phone = phone.replace('+', '').replace(' ', '').replace('-', '')
                
                # Extract country code prefix
                country_prefix = ""
                for prefix in sorted(self.phone_country_mapping.keys(), key=len, reverse=True):
                    prefix_digits = prefix.replace('+', '')
                    if clean_phone.startswith(prefix_digits):
                        country_prefix = prefix_digits
                        break
                
                if country_prefix:
                    remaining_number = clean_phone[len(country_prefix):]
                    session_name = f"+{country_prefix}_{remaining_number}"
                else:
                    session_name = f"+{clean_phone}"
                    
                # Create session files with proper naming in session_files directory
                session_file = f"{session_name}.session"
                json_file = f"{session_name}.json"
                
                # Get the session paths manager
                from sessions.session_paths import get_session_paths
                session_paths = get_session_paths()
                
                # Create session file path in the pending directory
                session_path = os.path.join(session_paths.pending_dir, session_file)
                
                # Generate unique device info for this session
                device_info = TelegramSecurityManager.generate_device_info_static()
                
                # Create backup before connecting
                backup_path = self.database.backup_session_before_connect(
                    session_path, user_id, phone
                )
                
                # Create client with session in the pending directory
                client = TelegramClient(
                    session_path.replace('.session', ''),  # Remove .session extension
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
                
                # Connect with timeout
                await asyncio.wait_for(client.connect(), timeout=30)
                
                # Verify connection
                if not client.is_connected():
                    await client.disconnect()
                    raise ConnectionError("Failed to establish connection")
                
                # Send verification code with retry
                try:
                    result = await asyncio.wait_for(client.send_code_request(phone), timeout=30)
                    phone_code_hash = result.phone_code_hash
                except errors.AuthRestartError:
                    logger.warning(f"Auth restart required, retrying... (attempt {attempt + 1})")
                    await client.disconnect()
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        raise
                except errors.FloodWaitError as e:
                    logger.warning(f"Flood wait error: {e.seconds} seconds")
                    await client.disconnect()
                    if attempt < max_retries - 1:
                        await asyncio.sleep(min(e.seconds, 60))
                        continue
                    else:
                        raise
                
                # Store verification data
                await state.update_data(
                    phone_code_hash=phone_code_hash,
                    session_name=session_name,
                    session_path=session_path,
                    session_file=session_file,
                    json_file=json_file,
                    device_info=device_info
                )
                
                # Track attempts
                self.verification_attempts[user_id] = {'attempts': 0, 'max_attempts': 3, 'resend_count': 0}
                
                # Use translation system for verification code sent message
                title = get_text("verification_code_sent_title", user_language)
                message_text = get_text("verification_code_sent_message", user_language, phone=phone)
                
                await message.reply(
                    f"{title}\n\n{message_text}",
                    parse_mode="Markdown"
                )
                
                # Safely disconnect client with error handling
                await self.safe_client_cleanup(client, "verification_code_send")
                    
                await state.set_state(SellAccountStates.waiting_verification_code)
                return
                
            except (errors.AuthRestartError, ConnectionError, asyncio.TimeoutError, OSError) as e:
                logger.warning(f"Connection error on attempt {attempt + 1}: {e}")
                if 'client' in locals():
                    await client.disconnect()
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error(f"Failed to send verification code after {max_retries} attempts")
                    if self.reporting_system:
                        await self.reporting_system.report_error(e, "Sending verification code after retries", message.from_user.id)
                    await message.reply(
                        "⚠️ **Connection Error**\n\n"
                        "We're experiencing connection issues with Telegram servers.\n"
                        "Please wait a few minutes and try again.",
                        parse_mode="Markdown"
                    )
                    return
                    
            except Exception as e:
                logger.error(f"Error sending verification code: {e}")
                if 'client' in locals():
                    await client.disconnect()
                
                if self.reporting_system:
                    await self.reporting_system.report_error(e, "Sending verification code", message.from_user.id)
                await message.reply(
                    "❌ **Error sending verification code**\n\n"
                    "Please make sure the phone number is correct and try again.",
                    parse_mode="Markdown"
                )
                return
    
    async def verification_code_received(self, message: types.Message, state: FSMContext):
        """Process verification code"""
        user_id = message.from_user.id
        user_language = self.get_user_language(user_id)
        code = message.text.strip()
        
        # Validate code format
        if not re.match(r'^\d{5,6}$', code):
            await message.reply(
                "❌ **Invalid verification code format**\n\n"
                "Please enter the 5-6 digit code you received:\n"
                "Example: 12345"
            )
            return
        
        # Get stored data
        data = await state.get_data()
        phone_number = data.get('phone_number')
        phone_code_hash = data.get('phone_code_hash')
        session_name = data.get('session_name')
        session_path = data.get('session_path')
        country_code = data.get('country_code')
        
        # Create backup before verification attempt
        backup_path = self.database.backup_session_before_connect(
            session_path, user_id, phone_number
        )
        
        # Check attempts
        if user_id in self.verification_attempts:
            self.verification_attempts[user_id]['attempts'] += 1
            if self.verification_attempts[user_id]['attempts'] > self.verification_attempts[user_id]['max_attempts']:
                await message.reply(
                    "❌ **Too many failed attempts**\n\n"
                    "Please start over by selecting your country again.",
                    parse_mode="Markdown"
                )
                await state.clear()
                return
        else:
            # Initialize if not exists
            self.verification_attempts[user_id] = {'attempts': 1, 'max_attempts': 3, 'resend_count': 0}
        
        # Verify code with connection handling
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                # Use stored device info or generate new one
                device_info = data.get('device_info', TelegramSecurityManager.generate_device_info_static())
                
                # Create client and verify code (use session path for verification)
                client = TelegramClient(
                    session_path.replace('.session', ''),  # Remove .session extension
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
                
                # Connect with timeout
                await asyncio.wait_for(client.connect(), timeout=30)
                
                # Verify connection
                if not client.is_connected():
                    await client.disconnect()
                    raise ConnectionError("Failed to establish connection")
                
                # Sign in with verification code
                try:
                    await asyncio.wait_for(
                        client.sign_in(phone_number, code, phone_code_hash=phone_code_hash),
                        timeout=30
                    )
                    
                    # Extract and store session string securely
                    session_string = await self.extract_and_store_session_string(
                        client, user_id, phone_number, state
                    )
                    
                    # Verification successful - proceed to security check
                    success_msg = get_text("phone_verification_successful", user_language)
                    checking_msg = get_text("checking_account_security", user_language)
                    
                    await message.reply(
                        f"{success_msg}\n\n{checking_msg}",
                        parse_mode="Markdown"
                    )
                    
                    # Initialize security manager
                    security_manager = TelegramSecurityManager(self.api_id, self.api_hash, session_path)
                    await security_manager.connect()
                    
                    # Check account status
                    account_status = await security_manager.check_account_status()
                    
                    await state.update_data(
                        account_status=account_status,
                        security_manager=security_manager
                    )
                    
                    # Process based on account status
                    await self.process_account_security(message, state, account_status)
                    
                    # Cleanup security manager with error handling
                    await self.safe_client_cleanup(security_manager, "security_manager_verification")
                    
                except errors.SessionPasswordNeededError:
                    # Account has 2FA - need password
                    await message.reply(
                        "🔐 **2FA Detected**\n\n"
                        "Your account has Two-Factor Authentication enabled.\n"
                        "Please enter your current 2FA password:",
                        parse_mode="Markdown"
                    )
                    await client.disconnect()
                    await state.set_state(SellAccountStates.waiting_2fa_password)
                    return
                    
                except errors.PhoneCodeInvalidError:
                    attempts_remaining = self.verification_attempts[user_id]['max_attempts'] - self.verification_attempts[user_id]['attempts']
                    if attempts_remaining > 0:
                        await message.reply(
                            "❌ **Invalid verification code**\n\n"
                            "Please check the code and try again.\n"
                            f"Attempts remaining: {attempts_remaining}\n\n"
                            "Make sure to enter the exact code received from Telegram."
                        )
                    else:
                        await message.reply(
                            "❌ **Too many failed attempts**\n\n"
                            "Please start over by selecting your country again.",
                            parse_mode="Markdown"
                        )
                        await state.clear()
                    return
                    
                except errors.PhoneCodeExpiredError:
                    await message.reply(
                        "⏰ **Verification code expired**\n\n"
                        "The verification code has expired. I'll send you a new one.\n"
                        "Please wait a moment...",
                        parse_mode="Markdown"
                    )
                    # Resend code automatically
                    await self.resend_verification_code(message, state)
                    return
                    
                except errors.AuthRestartError:
                    logger.warning(f"Auth restart required during verification, retrying... (attempt {attempt + 1})")
                    await client.disconnect()
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        raise
                        
                await client.disconnect()
                return
                
            except (errors.AuthRestartError, ConnectionError, asyncio.TimeoutError, OSError) as e:
                logger.warning(f"Connection error during verification on attempt {attempt + 1}: {e}")
                if 'client' in locals():
                    await client.disconnect()
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error(f"Failed to verify code after {max_retries} attempts")
                    await message.reply(
                        "⚠️ **Connection Error**\n\n"
                        "We're experiencing connection issues with Telegram servers.\n"
                        "Please wait a few minutes and try again.",
                        parse_mode="Markdown"
                    )
                    return
                    
            except Exception as e:
                logger.error(f"Error verifying code: {e}")
                
                # Handle database corruption specifically
                if "database disk image is malformed" in str(e):
                    logger.error("Database corruption detected - attempting recovery")
                    
                    # Try to recover database
                    recovery_success = await self._attempt_database_recovery()
                    
                    if recovery_success:
                        logger.info("Database recovery successful, continuing with verification")
                        await message.reply(
                            "⚠️ **System Issue Resolved**\n\n"
                            "We've resolved a temporary system issue. Your verification is continuing.\n"
                            "Please wait a moment...",
                            parse_mode="Markdown"
                        )
                        # Try verification again after recovery
                        continue
                    else:
                        logger.error("Database recovery failed")
                        await message.reply(
                            "⚠️ **System Maintenance Required**\n\n"
                            "We're experiencing a system issue that requires maintenance.\n"
                            "Please try again in a few minutes or contact support.",
                            parse_mode="Markdown"
                        )
                else:
                    await message.reply(
                        "❌ **Verification failed**\n\n"
                        "Please try again or contact support if the problem persists.",
                        parse_mode="Markdown"
                    )
                
                # Clean up any clients that might be open
                if 'client' in locals():
                    await self.safe_client_cleanup(client, "verification_code_processing")
                
                return
    
    async def resend_verification_code(self, message: types.Message, state: FSMContext):
        """Resend verification code with improved error handling"""
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                data = await state.get_data()
                phone_number = data.get('phone_number')
                session_name = data.get('session_name')
                session_path = data.get('session_path')
                resend_count = data.get('resend_count', 0)
                
                if not phone_number or not session_name or not session_path:
                    await message.reply(
                        "❌ **Session data lost**\n\n"
                        "Please start over by selecting your country again.",
                        parse_mode="Markdown"
                    )
                    await state.clear()
                    return
                
                # Check resend limit
                if resend_count >= 3:
                    await message.reply(
                        "⚠️ **Resend limit reached**\n\n"
                        "Please start over by selecting your country again.",
                        parse_mode="Markdown"
                    )
                    await state.clear()
                    return
                
                # Generate device info for this session
                device_info = TelegramSecurityManager.generate_device_info_static()
                
                # Create backup before connecting
                user_id = message.from_user.id
                backup_path = self.database.backup_session_before_connect(
                    session_path, user_id, phone_number
                )
                
                # Create client and resend code (use proper session path)
                client = TelegramClient(
                    session_path.replace('.session', ''),
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
                
                # Connect with timeout
                await asyncio.wait_for(client.connect(), timeout=30)
                
                # Verify connection
                if not client.is_connected():
                    await client.disconnect()
                    raise ConnectionError("Failed to establish connection")
                
                # Send code with retry
                try:
                    result = await asyncio.wait_for(client.send_code_request(phone_number), timeout=30)
                except errors.AuthRestartError:
                    logger.warning(f"Auth restart required during resend, retrying... (attempt {attempt + 1})")
                    await client.disconnect()
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        raise
                except errors.FloodWaitError as e:
                    logger.warning(f"Flood wait error during resend: {e.seconds} seconds")
                    await client.disconnect()
                    if attempt < max_retries - 1:
                        await asyncio.sleep(min(e.seconds, 60))
                        continue
                    else:
                        raise
                
                await state.update_data(
                    phone_code_hash=result.phone_code_hash,
                    resend_count=resend_count + 1
                )
                
                await message.reply(
                    "📨 **New verification code sent!**\n\n"
                    "Please check your Telegram messages and enter the new verification code."
                )
                
                await client.disconnect()
                return
                
            except (errors.AuthRestartError, ConnectionError, asyncio.TimeoutError, OSError) as e:
                logger.warning(f"Connection error during resend on attempt {attempt + 1}: {e}")
                if 'client' in locals():
                    await client.disconnect()
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error(f"Failed to resend verification code after {max_retries} attempts")
                    await message.reply(
                        "⚠️ **Connection Error**\n\n"
                        "We're experiencing connection issues with Telegram servers.\n"
                        "Please wait a few minutes and try again.",
                        parse_mode="Markdown"
                    )
                    return
                    
            except Exception as e:
                logger.error(f"Error resending verification code: {e}")
                if 'client' in locals():
                    await client.disconnect()
                
                await message.reply(
                    "❌ **Failed to resend code**\n\n"
                    "Please start over by selecting your country again.",
                    parse_mode="Markdown"
                )
                await state.clear()
                return
    
    async def handle_2fa_password(self, message: types.Message, state: FSMContext):
        """Handle 2FA password input"""
        user_id = message.from_user.id
        current_password = message.text.strip()
        
        data = await state.get_data()
        session_name = data.get('session_name')
        session_path = data.get('session_path')
        phone_number = data.get('phone_number')
        
        # Create backup before 2FA attempt
        backup_path = self.database.backup_session_before_connect(
            session_path, user_id, phone_number
        )
        
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(max_retries):
            try:
                # Get global 2FA password from config service
                global_2fa = self.config_service.get_global_2fa_password()
                
                if not global_2fa:
                    # Notify admin about missing 2FA configuration
                    if self.reporting_system:
                        await self.reporting_system.report_error(
                            Exception("Global 2FA password not configured"),
                            "2FA Configuration Error",
                            user_id,
                            additional_info={
                                "phone": data.get('phone_number', ''),
                                "country": data.get('country_code', ''),
                                "message": "Admin needs to configure global 2FA password in Bot Settings"
                            }
                        )
                    
                    # Also notify admins directly if possible
                    try:
                        for admin_id in self.admin_ids:
                            await self.bot.send_message(
                                admin_id,
                                "⚠️ **Configuration Required**\n\n"
                                "A user attempted to sell an account with 2FA enabled, but the global 2FA password is not configured.\n\n"
                                "Please go to Admin Panel → Bot Settings → Global 2FA Settings to configure the global 2FA password.\n\n"
                                f"User: {user_id}\n"
                                f"Phone: {data.get('phone_number', 'Unknown')}\n"
                                f"Country: {data.get('country_code', 'Unknown')}",
                                parse_mode="Markdown"
                            )
                    except Exception as e:
                        logger.error(f"Error notifying admins about missing 2FA config: {e}")
                    
                    await message.reply(
                        "❌ **2FA Configuration Error**\n\n"
                        "Your account has 2FA enabled, but our system needs additional configuration to process it.\n\n"
                        "We've notified the administrators. Please try again in a few hours, or contact support.\n\n"
                        "**Alternative:** You can disable 2FA on your account and try again immediately.",
                        parse_mode="Markdown"
                    )
                    await self.move_to_rejected(session_path, user_id, "Global 2FA password not configured - admin notified")
                    await state.clear()
                    return
                
                # Initialize security manager
                security_manager = TelegramSecurityManager(self.api_id, self.api_hash, session_path)
                
                # Connect with timeout
                if not await asyncio.wait_for(security_manager.connect(), timeout=30):
                    await message.reply(
                        "❌ **Connection failed**\n\n"
                        "Failed to connect to your Telegram account.\n"
                        "Please try again later.",
                        parse_mode="Markdown"
                    )
                    # Cleanup security manager even on failure
                    await security_manager.disconnect()
                    await state.clear()
                    return
                
                # Try to change 2FA password
                success = await security_manager.change_2fa_password(current_password, global_2fa)
                
                if success:
                    await message.reply(
                        "✅ **2FA password changed successfully!**\n\n"
                        "🔄 Continuing with security checks...",
                        parse_mode="Markdown"
                    )
                    
                    # Extract and store session string after 2FA change
                    session_string = await self.extract_and_store_session_string(
                        security_manager.client, user_id, phone_number, state
                    )
                    
                    # Check account status after 2FA change
                    account_status = await security_manager.check_account_status()
                    account_status['2fa_changed'] = True
                    
                    await state.update_data(
                        account_status=account_status,
                        security_manager=security_manager
                    )
                    
                    # Process account
                    await self.process_account_security(message, state, account_status)
                    
                    # Cleanup security manager
                    await security_manager.disconnect()
                    return
                    
                else:
                    # Wrong password - ask again
                    attempts = data.get('twofa_attempts', 0) + 1
                    await state.update_data(twofa_attempts=attempts)
                    
                    if attempts >= 3:
                        await message.reply(
                            "❌ **Account selling rejected**\n\n"
                            "Too many failed 2FA password attempts.\n"
                            "Please disable 2FA on your account and try again.",
                            parse_mode="Markdown"
                        )
                        
                        # Move to rejected folder
                        await self.move_to_rejected(session_path, user_id, "2FA enabled - wrong password provided 3 times")
                        await state.clear()
                    else:
                        await message.reply(
                            "❌ **Incorrect 2FA password**\n\n"
                            f"Please try again. Attempts remaining: {3 - attempts}\n"
                            "Enter your current 2FA password:",
                            parse_mode="Markdown"
                        )
                    return
                    
            except (errors.AuthRestartError, ConnectionError, asyncio.TimeoutError, OSError) as e:
                logger.warning(f"Connection error during 2FA handling on attempt {attempt + 1}: {e}")
                if 'security_manager' in locals():
                    await security_manager.disconnect()
                
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                else:
                    logger.error(f"Failed to handle 2FA after {max_retries} attempts")
                    await message.reply(
                        "⚠️ **Connection Error**\n\n"
                        "We're experiencing connection issues with Telegram servers.\n"
                        "Please wait a few minutes and try again.",
                        parse_mode="Markdown"
                    )
                    return
                    
            except Exception as e:
                logger.error(f"Error handling 2FA: {e}")
                if 'security_manager' in locals():
                    await security_manager.disconnect()
                
                await message.reply(
                    "❌ **2FA Processing Error**\n\n"
                    "Account selling rejected due to 2FA issues.",
                    parse_mode="Markdown"
                )
                await self.move_to_rejected(session_path, user_id, "2FA processing error")
                await state.clear()
                return
    
    async def process_account_security(self, message: types.Message, state: FSMContext, account_status: Dict):
        """Process account based on security status"""
        user_id = message.from_user.id
        user_language = self.get_user_language(user_id)
        data = await state.get_data()
        session_path = data.get('session_path')
        country_code = data.get('country_code')
        price = data.get('price')
        phone_number = data.get('phone_number')
        
        # Check if account is frozen FIRST - highest priority check
        if account_status.get('frozen', False):
            frozen_msg = get_text("account_frozen_rejected", user_language)
            await message.reply(
                frozen_msg,
                parse_mode="Markdown"
            )
            await self.move_to_rejected(session_path, user_id, "Account frozen")
            await state.clear()
            return
        
        # Check 2FA status
        has_2fa = account_status.get('has_2fa', False)
        if has_2fa and not account_status.get('2fa_changed', False):
            await message.reply(
                "❌ **Account selling rejected**\n\n"
                "Your account has 2FA enabled. Please disable it and try again.",
                parse_mode="Markdown"
            )
            await self.move_to_rejected(session_path, user_id, "2FA enabled")
            await state.clear()
            return
        
        # Check email status
        has_email = account_status.get('has_email', False)
        
        # Determine processing path
        if has_email and not has_2fa:
            # Email linked but no 2FA - manual review
            await self.move_to_pending_with_email(session_path, user_id, account_status, data)
            
            # Report manual approval needed
            if self.reporting_system:
                await self.reporting_system.report_manual_approval_needed(
                    data.get('phone_number', ''),
                    data.get('country_code', ''),
                    user_id,
                    "Account has email linked - requires manual review"
                )
            
            # Use translation system for manual review message
            submitted_msg = get_text("account_submitted_review", user_language)
            email_review_msg = get_text("account_email_linked_review", user_language)
            notify_msg = get_text("notify_within_24_hours", user_language)
            
            await message.reply(
                f"{submitted_msg}\n\n{email_review_msg}\n{notify_msg}",
                parse_mode="Markdown"
            )
        elif not has_email and not has_2fa:
            # Clean account - automatic processing
            await self.move_to_pending_auto(session_path, user_id, account_status, data)
            # Use translation system for successful submission message
            success_msg = get_text("account_submitted_successfully", user_language)
            auto_process_msg = get_text("account_processed_automatically", user_language)
            payment_msg = get_text("payment_if_approved", user_language, price=f"{price:.2f}")
            
            await message.reply(
                f"{success_msg}\n\n{auto_process_msg}\n{payment_msg}",
                parse_mode="Markdown"
            )
        elif has_2fa and account_status.get('2fa_changed', False):
            # 2FA changed successfully
            if has_email:
                await self.move_to_pending_with_email(session_path, user_id, account_status, data)
                # Use translation system for 2FA updated with email review message
                submitted_msg = get_text("account_submitted_review", user_language)
                fa_email_msg = get_text("account_2fa_updated_email_review", user_language)
                notify_msg = get_text("notify_within_24_hours", user_language)
                
                await message.reply(
                    f"{submitted_msg}\n\n{fa_email_msg}\n{notify_msg}",
                    parse_mode="Markdown"
                )
            else:
                await self.move_to_pending_auto(session_path, user_id, account_status, data)
                # Use translation system for 2FA updated auto process message
                success_msg = get_text("account_submitted_successfully", user_language)
                fa_auto_msg = get_text("account_2fa_updated_auto_process", user_language)
                payment_msg = get_text("payment_if_approved", user_language, price=f"{price:.2f}")
                
                await message.reply(
                    f"{success_msg}\n\n{fa_auto_msg}\n{payment_msg}",
                    parse_mode="Markdown"
                )
        
        await state.clear()
    
    async def move_to_rejected(self, session_path: str, user_id: int, reason: str):
        """Move session to rejected folder"""
        try:
            # Save rejection info first (before moving files)
            rejection_info = {
                'user_id': user_id,
                'reason': reason,
                'timestamp': datetime.now().isoformat(),
                'session_file': os.path.basename(session_path),
                'original_path': session_path
            }
            
            info_path = os.path.join(
                self.folders['rejected'], 
                f"{os.path.basename(session_path)}.json"
            )
            
            with open(info_path, 'w') as f:
                json.dump(rejection_info, f, indent=2)
            
            # Save to database with session info
            self.database.add_rejected_session(
                user_id, 
                reason, 
                session_path,
                session_info=rejection_info
            )
            
            # Move session file using retry logic
            if os.path.exists(session_path):
                file_moved = await self._move_session_file_with_retry(session_path, self.folders['rejected'])
                if not file_moved:
                    logger.warning(f"Could not move session file {session_path} to rejected folder")
                    # Update rejection info to indicate file wasn't moved
                    rejection_info['file_move_failed'] = True
                    rejection_info['file_still_in_pending'] = True
                    
                    with open(info_path, 'w') as f:
                        json.dump(rejection_info, f, indent=2)
                    
                    # Schedule delayed cleanup
                    asyncio.create_task(self._delayed_rejection_cleanup(session_path, user_id, reason))
                else:
                    logger.info(f"Successfully moved session file {session_path} to rejected folder")
            
        except Exception as e:
            logger.error(f"Error moving to rejected: {e}")
            
            # If there's an error, still try to clean up the pending file
            if os.path.exists(session_path):
                try:
                    # Try to remove from pending even if move to rejected failed
                    pending_json_path = session_path.replace('.session', '.json')
                    if os.path.exists(pending_json_path):
                        os.remove(pending_json_path)
                        logger.info(f"Removed pending JSON file: {pending_json_path}")
                except Exception as cleanup_e:
                    logger.error(f"Error cleaning up pending files: {cleanup_e}")
    
    async def move_to_pending_with_email(self, session_path: str, user_id: int, account_status: Dict, data: Dict):
        """Move session to pending folder with email flag for manual review"""
        try:
            # Move session file
            if os.path.exists(session_path):
                pending_path = os.path.join(self.folders['pending'], os.path.basename(session_path))
                shutil.move(session_path, pending_path)
            
            # Save pending info
            pending_info = {
                'user_id': user_id,
                'account_status': account_status,
                'country_code': data.get('country_code'),
                'price': data.get('price'),
                'phone_number': data.get('phone_number'),
                'has_email': True,
                'manual_review': True,
                'timestamp': datetime.now().isoformat(),
                'scheduled_check': (datetime.now() + timedelta(hours=24)).isoformat(),
                'session_file': os.path.basename(session_path),
                'retry_count': 0,
                'device_info': data.get('device_info', {})
            }
            
            info_path = os.path.join(
                self.folders['pending'], 
                f"{os.path.basename(session_path)}.json"
            )
            
            with open(info_path, 'w') as f:
                json.dump(pending_info, f, indent=2)
            
            # Save to database with session info
            self.database.add_pending_session(
                user_id, 
                data.get('phone_number'), 
                data.get('country_code'),
                has_email=True,
                session_file=os.path.basename(session_path),
                device_info=data.get('device_info', {}),
                session_string=data.get('session_string')
            )
            
        except Exception as e:
            logger.error(f"Error moving to pending with email: {e}")
    
    async def move_to_pending_auto(self, session_path: str, user_id: int, account_status: Dict, data: Dict):
        """Move session to pending folder for automatic processing after 24 hours"""
        try:
            # Save pending info first (before moving files)
            pending_info = {
                'user_id': user_id,
                'account_status': account_status,
                'country_code': data.get('country_code'),
                'price': data.get('price'),
                'phone_number': data.get('phone_number'),
                'has_email': False,
                'manual_review': False,
                'timestamp': datetime.now().isoformat(),
                'scheduled_check': (datetime.now() + timedelta(hours=24)).isoformat(),
                'session_file': os.path.basename(session_path),
                'retry_count': 0,
                'device_info': data.get('device_info', {})
            }
            
            info_path = os.path.join(
                self.folders['pending'], 
                f"{os.path.basename(session_path)}.json"
            )
            
            with open(info_path, 'w') as f:
                json.dump(pending_info, f, indent=2)
            
            # Save to database with session info
            self.database.add_pending_session(
                user_id, 
                data.get('phone_number'), 
                data.get('country_code'),
                has_email=False,
                session_file=os.path.basename(session_path),
                device_info=data.get('device_info', {}),
                session_string=data.get('session_string')
            )
            
            # Move session file with retry logic
            if os.path.exists(session_path):
                file_moved = await self._move_session_file_with_retry(session_path, self.folders['pending'])
                if not file_moved:
                    logger.warning(f"Could not move session file {session_path}, but data saved to database")
                    # Update pending info to indicate file wasn't moved
                    pending_info['file_move_failed'] = True
                    pending_info['original_path'] = session_path
                    with open(info_path, 'w') as f:
                        json.dump(pending_info, f, indent=2)
            
            # Schedule automatic processing
            await self.schedule_automatic_processing(pending_info)
            
        except Exception as e:
            logger.error(f"Error in move_to_pending_auto: {e}")
            
            # Handle file access errors specifically
            if "being used by another process" in str(e):
                logger.warning("File is locked by another process - attempting delayed retry")
                # Schedule a delayed retry for file operations
                asyncio.create_task(self._delayed_file_move_retry(session_path, user_id, data))
            else:
                # For other errors, log and continue
                logger.error(f"Unexpected error in move_to_pending_auto: {e}")
                pass
    
    async def _move_session_file_with_retry(self, source_path: str, dest_folder: str, max_retries: int = 5):
        """Move session file with retry logic for file access errors"""
        import time
        import fcntl
        import platform
        
        for attempt in range(max_retries):
            try:
                # Extract filename from source path
                filename = os.path.basename(source_path)
                dest_path = os.path.join(dest_folder, filename)
                
                # Ensure destination directory exists
                os.makedirs(dest_folder, exist_ok=True)
                
                # Check if file exists and is accessible
                if not os.path.exists(source_path):
                    logger.warning(f"Source file does not exist: {source_path}")
                    return False
                
                # Try to acquire exclusive lock on file before moving (Unix/Linux only)
                if platform.system() != 'Windows':
                    try:
                        with open(source_path, 'r+b') as f:
                            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            f.flush()
                            os.fsync(f.fileno())
                    except (IOError, OSError) as lock_e:
                        if attempt < max_retries - 1:
                            logger.warning(f"File is locked, retrying in {2 * (attempt + 1)} seconds: {lock_e}")
                            await asyncio.sleep(2 * (attempt + 1))
                            continue
                        else:
                            logger.error(f"Cannot acquire lock on file: {lock_e}")
                            raise
                
                # Additional wait for Windows systems
                if platform.system() == 'Windows':
                    await asyncio.sleep(1)
                
                # Copy first, then remove original (safer than move)
                shutil.copy2(source_path, dest_path)
                
                # Verify copy was successful
                if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                    # Remove original file
                    os.remove(source_path)
                    logger.info(f"Successfully moved session file to {dest_path}")
                    return True
                else:
                    logger.error(f"Copy verification failed for {dest_path}")
                    if os.path.exists(dest_path):
                        os.remove(dest_path)
                    raise Exception("Copy verification failed")
                
            except PermissionError as e:
                if "being used by another process" in str(e):
                    if attempt < max_retries - 1:
                        logger.warning(f"File in use, retrying in {3 * (attempt + 1)} seconds: {e}")
                        await asyncio.sleep(3 * (attempt + 1))
                        continue
                    else:
                        logger.error(f"File remains in use after {max_retries} attempts: {e}")
                        # Try to continue without the file move
                        return False
                else:
                    raise
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Retry {attempt + 1}/{max_retries} failed to move file: {e}")
                    await asyncio.sleep(2 * (attempt + 1))  # Exponential backoff
                else:
                    logger.error(f"Failed to move file after {max_retries} attempts: {e}")
                    return False
        
        return False
    
    async def _delayed_file_move_retry(self, session_path: str, user_id: int, data: Dict):
        """Delayed retry for file move operations"""
        try:
            # Wait 30 seconds before retry
            await asyncio.sleep(30)
            
            # Try to move the file again
            if os.path.exists(session_path):
                file_moved = await self._move_session_file_with_retry(session_path, self.folders['pending'])
                if file_moved:
                    logger.info(f"Successfully moved session file on delayed retry: {session_path}")
                    
                    # Update the pending info to remove the file_move_failed flag
                    info_path = os.path.join(
                        self.folders['pending'], 
                        f"{os.path.basename(session_path)}.json"
                    )
                    
                    if os.path.exists(info_path):
                        with open(info_path, 'r') as f:
                            pending_info = json.load(f)
                        
                        pending_info.pop('file_move_failed', None)
                        pending_info.pop('original_path', None)
                        pending_info['delayed_move_successful'] = True
                        
                        with open(info_path, 'w') as f:
                            json.dump(pending_info, f, indent=2)
                else:
                    logger.error(f"Delayed retry also failed for session file: {session_path}")
            else:
                logger.warning(f"Session file no longer exists for delayed retry: {session_path}")
                
        except Exception as e:
            logger.error(f"Error in delayed file move retry: {e}")
    
    async def _delayed_rejection_cleanup(self, session_path: str, user_id: int, reason: str):
        """Delayed cleanup for rejected sessions that couldn't be moved immediately"""
        try:
            # Wait 60 seconds before retry
            await asyncio.sleep(60)
            
            logger.info(f"Attempting delayed rejection cleanup for {session_path}")
            
            # Try to move the file again
            if os.path.exists(session_path):
                file_moved = await self._move_session_file_with_retry(session_path, self.folders['rejected'])
                if file_moved:
                    logger.info(f"Successfully moved session file to rejected on delayed retry: {session_path}")
                    
                    # Update the rejection info to remove the file_move_failed flag
                    info_path = os.path.join(
                        self.folders['rejected'], 
                        f"{os.path.basename(session_path)}.json"
                    )
                    
                    if os.path.exists(info_path):
                        with open(info_path, 'r') as f:
                            rejection_info = json.load(f)
                        
                        rejection_info.pop('file_move_failed', None)
                        rejection_info.pop('file_still_in_pending', None)
                        rejection_info['delayed_move_successful'] = True
                        rejection_info['delayed_move_timestamp'] = datetime.now().isoformat()
                        
                        with open(info_path, 'w') as f:
                            json.dump(rejection_info, f, indent=2)
                else:
                    logger.error(f"Delayed rejection cleanup also failed for session file: {session_path}")
                    
                    # If still can't move, try to at least remove from pending
                    try:
                        pending_json_path = session_path.replace('.session', '.json')
                        if os.path.exists(pending_json_path):
                            os.remove(pending_json_path)
                            logger.info(f"Removed pending JSON file as fallback: {pending_json_path}")
                    except Exception as fallback_e:
                        logger.error(f"Error removing pending JSON file: {fallback_e}")
            else:
                logger.warning(f"Session file no longer exists for delayed rejection cleanup: {session_path}")
                
        except Exception as e:
            logger.error(f"Error in delayed rejection cleanup: {e}")
    
    async def extract_and_store_session_string(self, client, user_id: int, phone_number: str, state: FSMContext):
        """Extract session string from client and store it securely"""
        try:
            # Extract session string
            session_string = client.session.save()
            
            # Store in state data
            await state.update_data(session_string=session_string)
            
            # Also store directly in database if needed
            encrypted_session = self.database._encrypt_session_string(session_string)
            
            # Update database with session string
            import sqlite3
            with sqlite3.connect(self.database.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE pending_numbers 
                    SET session_string = ?
                    WHERE user_id = ? AND phone_number = ?
                """, (encrypted_session, user_id, phone_number))
                conn.commit()
            
            logger.info(f"Session string extracted and stored for user {user_id}")
            return session_string
            
        except Exception as e:
            logger.error(f"Error extracting session string: {e}")
            return None
    
    async def validate_and_backup_session(self, session_path: str, user_id: int, phone_number: str) -> bool:
        """Validate session file and create backup"""
        try:
            # Check if session file exists
            if not os.path.exists(session_path):
                logger.warning(f"Session file not found: {session_path}")
                return False
            
            # Check if session file is valid
            if os.path.getsize(session_path) == 0:
                logger.warning(f"Session file is empty: {session_path}")
                return False
            
            # Create backup
            backup_path = self.database.backup_session_before_connect(
                session_path, user_id, phone_number
            )
            
            if backup_path:
                logger.info(f"Session validated and backed up: {backup_path}")
                return True
            else:
                logger.warning(f"Failed to create backup for session: {session_path}")
                return False
                
        except Exception as e:
            logger.error(f"Error validating session: {e}")
            return False
    
    async def cleanup_orphaned_pending_files(self):
        """Clean up orphaned files in pending directory"""
        try:
            logger.info("Cleaning up orphaned pending files...")
            
            pending_dir = self.folders['pending']
            if not os.path.exists(pending_dir):
                return
            
            # Get all session files in pending
            session_files = [f for f in os.listdir(pending_dir) if f.endswith('.session')]
            
            for session_file in session_files:
                session_path = os.path.join(pending_dir, session_file)
                json_path = os.path.join(pending_dir, f"{session_file}.json")
                
                try:
                    # Check if this file is being used by another process
                    if not os.path.exists(json_path):
                        # Session file exists but no JSON info - likely orphaned
                        logger.warning(f"Found orphaned session file: {session_file}")
                        
                        # Try to remove it
                        file_removed = await self._remove_file_with_retry(session_path)
                        if file_removed:
                            logger.info(f"Removed orphaned session file: {session_file}")
                        else:
                            logger.warning(f"Could not remove orphaned session file: {session_file}")
                    else:
                        # Check if the session has been marked as rejected but file still in pending
                        with open(json_path, 'r') as f:
                            session_info = json.load(f)
                        
                        if session_info.get('status') == 'rejected' and session_info.get('file_still_in_pending'):
                            logger.info(f"Found rejected session still in pending: {session_file}")
                            
                            # Try to move it to rejected
                            file_moved = await self._move_session_file_with_retry(session_path, self.folders['rejected'])
                            if file_moved:
                                logger.info(f"Successfully moved rejected session to rejected folder: {session_file}")
                                # Remove the pending JSON file
                                os.remove(json_path)
                            
                except Exception as file_e:
                    logger.error(f"Error processing pending file {session_file}: {file_e}")
                    
        except Exception as e:
            logger.error(f"Error cleaning up orphaned pending files: {e}")
    
    async def _remove_file_with_retry(self, file_path: str, max_retries: int = 3) -> bool:
        """Remove file with retry logic"""
        for attempt in range(max_retries):
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    return True
                else:
                    return True  # File doesn't exist, consider it removed
            except PermissionError as e:
                if "being used by another process" in str(e):
                    if attempt < max_retries - 1:
                        logger.warning(f"File in use, retrying removal in {2 * (attempt + 1)} seconds: {file_path}")
                        await asyncio.sleep(2 * (attempt + 1))
                        continue
                    else:
                        logger.error(f"Could not remove file after {max_retries} attempts: {file_path}")
                        return False
                else:
                    raise
            except Exception as e:
                logger.error(f"Error removing file {file_path}: {e}")
                return False
        
        return False
    
    async def _attempt_database_recovery(self) -> bool:
        """Attempt to recover from database corruption"""
        try:
            logger.info("Attempting database recovery from corruption")
            
            # Check if database has a backup method
            if hasattr(self.database, 'create_backup'):
                # Try to create a backup first
                backup_success = self.database.create_backup()
                if backup_success:
                    logger.info("Database backup created successfully")
            
            # Try to repair the database
            if hasattr(self.database, 'repair_database'):
                repair_success = self.database.repair_database()
                if repair_success:
                    logger.info("Database repair completed successfully")
                    return True
            
            # If no repair method, try to recreate connection
            try:
                # Close existing connection
                if hasattr(self.database, 'close'):
                    self.database.close()
                
                # Wait a moment
                await asyncio.sleep(2)
                
                # Try to reinitialize database
                if hasattr(self.database, 'init_database'):
                    self.database.init_database()
                    logger.info("Database reinitialized successfully")
                    return True
                
            except Exception as reinit_e:
                logger.error(f"Database reinitialization failed: {reinit_e}")
            
            return False
            
        except Exception as e:
            logger.error(f"Database recovery attempt failed: {e}")
            return False
    
    async def safe_client_cleanup(self, client, operation_name: str = "unknown"):
        """Safely cleanup Telegram client with error handling"""
        try:
            if client:
                await client.disconnect()
                logger.debug(f"Client cleanup successful for {operation_name}")
        except Exception as e:
            if "database disk image is malformed" in str(e):
                logger.warning(f"Database corruption during {operation_name} cleanup: {e}")
                # Attempt database recovery
                await self._attempt_database_recovery()
            else:
                logger.warning(f"Error cleaning up client for {operation_name}: {e}")
            # Don't let cleanup errors stop the process
            pass
    
    async def safe_database_operation(self, operation_func, *args, **kwargs):
        """Safely perform database operations with corruption handling"""
        try:
            return await operation_func(*args, **kwargs)
        except Exception as e:
            if "database disk image is malformed" in str(e):
                logger.error(f"Database corruption during operation: {e}")
                # Attempt database recovery
                recovery_success = await self._attempt_database_recovery()
                if recovery_success:
                    logger.info("Database recovered, retrying operation")
                    try:
                        return await operation_func(*args, **kwargs)
                    except Exception as retry_e:
                        logger.error(f"Operation failed even after database recovery: {retry_e}")
                        raise
                else:
                    logger.error("Database recovery failed")
                    raise
            else:
                raise
    
    async def schedule_automatic_processing(self, pending_info: Dict):
        """Schedule automatic processing after 24 hours"""
        try:
            # This would typically be handled by a scheduler service
            # For now, we'll just log it
            logger.info(f"Scheduled automatic processing for session: {pending_info['session_file']}")
            
        except Exception as e:
            logger.error(f"Error scheduling processing: {e}")
    
    async def process_pending_sessions(self):
        """Process pending sessions (called by scheduler)"""
        try:
            pending_dir = self.folders['pending']
            
            for filename in os.listdir(pending_dir):
                if not filename.endswith('.json'):
                    continue
                
                info_path = os.path.join(pending_dir, filename)
                with open(info_path, 'r') as f:
                    session_info = json.load(f)
                
                # Check if it's time to process
                scheduled_time = datetime.fromisoformat(session_info['scheduled_check'])
                if datetime.now() >= scheduled_time:
                    await self.process_scheduled_session(session_info)
                    
        except Exception as e:
            logger.error(f"Error processing pending sessions: {e}")
    
    async def process_scheduled_session(self, session_info: Dict):
        """Process a scheduled session after 24-hour wait"""
        try:
            session_file = session_info['session_file']
            session_path = os.path.join(self.folders['pending'], session_file)
            user_id = session_info.get('user_id', 0)
            
            if not os.path.exists(session_path):
                logger.warning(f"Session file not found: {session_path}")
                return
            
            # Connect to check account status
            security_manager = TelegramSecurityManager(
                self.api_id, 
                self.api_hash, 
                session_path
            )
            
            if not await security_manager.connect():
                await self.move_session_to_rejected(session_info, "Connection failed during scheduled check")
                return
            
            # Check account status again
            current_status = await security_manager.check_account_status()
            
            # Check if account is frozen
            if current_status.get('frozen', False):
                await self.move_session_to_rejected(session_info, "Account frozen during scheduled check")
                await security_manager.disconnect()
                return
            
            # Check if 2FA is still our password (if account had 2FA)
            if session_info.get('account_status', {}).get('has_2fa', False):
                global_2fa = self.config_service.get_global_2fa_password()
                
                if not global_2fa:
                    # Notify admin about missing 2FA configuration during processing
                    if self.reporting_system:
                        await self.reporting_system.report_error(
                            Exception("Global 2FA password not configured during session processing"),
                            "2FA Configuration Error - Scheduled Processing",
                            user_id,
                            additional_info={
                                "session_file": session_info.get('session_file', ''),
                                "phone": session_info.get('phone_number', ''),
                                "country": session_info.get('country_code', ''),
                                "message": "Admin needs to configure global 2FA password in Bot Settings"
                            }
                        )
                    
                    await self.move_session_to_rejected(session_info, "Global 2FA password not configured - admin notified")
                    await security_manager.disconnect()
                    return
                
                # Verify 2FA password is still valid
                try:
                    current_password_info = await security_manager.client(GetPasswordRequest())
                    if not current_password_info.has_password:
                        # 2FA was disabled - this is suspicious
                        await self.move_session_to_rejected(session_info, "2FA was disabled during processing")
                        await security_manager.disconnect()
                        return
                except Exception as e:
                    logger.error(f"Error checking 2FA status: {e}")
                    await self.move_session_to_rejected(session_info, "Unable to verify 2FA status")
                    await security_manager.disconnect()
                    return
            
            # Terminate other sessions
            terminated = await security_manager.terminate_other_sessions()
            
            await security_manager.disconnect()
            
            # Determine next action based on results
            if terminated or not session_info.get('account_status', {}).get('has_2fa', False):
                # All checks passed - approve the session
                await self.approve_session(session_info)
            else:
                # Session termination failed - retry in 12 hours
                retry_count = session_info.get('retry_count', 0)
                if retry_count < 1:
                    session_info['retry_count'] = retry_count + 1
                    session_info['scheduled_check'] = (datetime.now() + timedelta(hours=12)).isoformat()
                    session_info['last_check'] = datetime.now().isoformat()
                    
                    info_path = os.path.join(
                        self.folders['pending'], 
                        f"{session_file}.json"
                    )
                    with open(info_path, 'w') as f:
                        json.dump(session_info, f, indent=2)
                    
                    logger.info(f"Session {session_file} scheduled for retry in 12 hours - termination incomplete")
                else:
                    # Final attempt failed - reject
                    await self.move_session_to_rejected(session_info, "Failed to terminate other sessions after retry")
                    
        except Exception as e:
            logger.error(f"Error processing scheduled session: {e}")
            await self.move_session_to_rejected(session_info, f"Processing error: {str(e)}")
    
    async def approve_session(self, session_info: Dict):
        """Approve session and move to approved folder"""
        try:
            session_file = session_info['session_file']
            user_id = session_info['user_id']
            price = session_info['price']
            phone_number = session_info.get('phone_number', session_file.replace('.session', ''))
            country_code = session_info.get('country_code', 'Unknown')
            
            # Move to approved folder
            pending_path = os.path.join(self.folders['pending'], session_file)
            approved_path = os.path.join(self.folders['approved'], session_file)
            
            if os.path.exists(pending_path):
                file_moved = await self._move_session_file_with_retry(pending_path, self.folders['approved'])
                if not file_moved:
                    logger.error(f"Failed to move session file to approved folder: {pending_path}")
                    return
            
            # Update session info
            session_info['status'] = 'approved'
            session_info['approved_at'] = datetime.now().isoformat()
            
            info_path = os.path.join(
                self.folders['approved'], 
                f"{session_file}.json"
            )
            
            with open(info_path, 'w') as f:
                json.dump(session_info, f, indent=2)
            
            # Add to approved_numbers table with complete session data
            session_string = session_info.get('session_string')
            self.database.add_approved_session(
                user_id=user_id,
                phone_number=phone_number,
                country_code=country_code,
                session_path=approved_path,
                price=price,
                session_info=session_info,
                session_string=session_string
            )
            
            # Add balance to user
            self.database.add_user_balance(user_id, price)
            
            # Report bought account
            if self.reporting_system:
                await self.reporting_system.report_bought_account(
                    user_id, 
                    phone_number,
                    country_code,
                    price,
                    'approved'
                )
            
            # Notify user
            try:
                await self.bot.send_message(
                    user_id,
                    f"✅ **Account Approved!**\n\n"
                    f"Your account has been approved and added to our system.\n"
                    f"💰 **Earned:** ${price:.2f}\n\n"
                    f"The amount has been added to your balance.",
                    parse_mode="Markdown"
                )
            except:
                pass
            
            # Remove from pending
            pending_info_path = os.path.join(
                self.folders['pending'], 
                f"{session_file}.json"
            )
            if os.path.exists(pending_info_path):
                os.remove(pending_info_path)
                
        except Exception as e:
            logger.error(f"Error approving session: {e}")
    
    async def move_session_to_rejected(self, session_info: Dict, reason: str):
        """Move session from pending to rejected"""
        try:
            session_file = session_info['session_file']
            user_id = session_info['user_id']
            
            # Update session info first
            session_info['status'] = 'rejected'
            session_info['rejection_reason'] = reason
            session_info['rejected_at'] = datetime.now().isoformat()
            
            info_path = os.path.join(
                self.folders['rejected'], 
                f"{session_file}.json"
            )
            
            with open(info_path, 'w') as f:
                json.dump(session_info, f, indent=2)
            
            # Move session file using retry logic
            pending_path = os.path.join(self.folders['pending'], session_file)
            if os.path.exists(pending_path):
                file_moved = await self._move_session_file_with_retry(pending_path, self.folders['rejected'])
                if not file_moved:
                    logger.warning(f"Could not move session file {pending_path} from pending to rejected")
                    # Update session info to indicate file wasn't moved
                    session_info['file_move_failed'] = True
                    session_info['file_still_in_pending'] = True
                    
                    with open(info_path, 'w') as f:
                        json.dump(session_info, f, indent=2)
                    
                    # Schedule delayed cleanup
                    asyncio.create_task(self._delayed_rejection_cleanup(pending_path, user_id, reason))
                else:
                    logger.info(f"Successfully moved session file {pending_path} from pending to rejected")
            
            # Notify user
            try:
                phone_number = session_info.get('phone_number', 'Unknown')
                await self.bot.send_message(
                    user_id,
                    f"❌ **Account Rejected**\n\n"
                    f"Your account submission has been rejected.\n"
                    f"**Reason:** {reason}\n\n"
                    f"Please resolve the issues and try again.",
                    parse_mode="Markdown"
                )
            except:
                pass
            
            # Remove from pending (only if file was moved successfully)
            pending_info_path = os.path.join(
                self.folders['pending'], 
                f"{session_file}.json"
            )
            if os.path.exists(pending_info_path):
                try:
                    os.remove(pending_info_path)
                    logger.info(f"Removed pending info file: {pending_info_path}")
                except Exception as remove_e:
                    logger.error(f"Error removing pending info file: {remove_e}")
                
        except Exception as e:
            logger.error(f"Error moving session to rejected: {e}")
    
    # Session management methods (moved from session_manager.py)
    
    def get_sessions_by_status(self, status: str) -> List[Dict]:
        """Get sessions by status (pending, approved, rejected)"""
        status_dir = self.folders[status]
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
    
    def get_session_info(self, phone: str, status: str) -> Optional[Dict]:
        """Get detailed session information"""
        try:
            status_dir = self.folders[status]
            json_file = os.path.join(status_dir, f"{phone}.json")
            
            if not os.path.exists(json_file):
                return None
            
            with open(json_file, 'r') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"Error getting session info for {phone}: {e}")
            return None
    
    def get_session_statistics(self) -> Dict:
        """Get basic session statistics"""
        stats = {
            'pending': 0,
            'approved': 0,
            'rejected': 0,
            'total': 0
        }
        
        try:
            for status in ['pending', 'approved', 'rejected']:
                status_dir = self.folders[status]
                if os.path.exists(status_dir):
                    count = len([f for f in os.listdir(status_dir) if f.endswith('.json')])
                    stats[status] = count
            
            stats['total'] = stats['pending'] + stats['approved'] + stats['rejected']
            
        except Exception as e:
            logger.error(f"Error calculating session statistics: {e}")
        
        return stats
    
    def get_detailed_statistics(self) -> Dict:
        """Get detailed session statistics with additional metrics"""
        basic_stats = self.get_session_statistics()
        
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
    
    def reject_session(self, phone: str, reason: str = None) -> bool:
        """Reject a session and move it to rejected folder"""
        try:
            # Find session in pending folder
            pending_json = os.path.join(self.folders['pending'], f"{phone}.json")
            pending_session = os.path.join(self.folders['pending'], f"{phone}.session")
            
            if not os.path.exists(pending_json):
                logger.error(f"Session {phone} not found in pending")
                return False
            
            # Load session data
            with open(pending_json, 'r') as f:
                session_data = json.load(f)
            
            # Update status
            session_data['status'] = 'rejected'
            session_data['status_changed_at'] = datetime.now().isoformat()
            if reason:
                session_data['rejection_reason'] = reason
            
            # Move files to rejected folder
            rejected_json = os.path.join(self.folders['rejected'], f"{phone}.json")
            rejected_session = os.path.join(self.folders['rejected'], f"{phone}.session")
            
            # Write updated JSON to rejected folder
            with open(rejected_json, 'w') as f:
                json.dump(session_data, f, indent=2)
            
            # Move session file if it exists
            if os.path.exists(pending_session):
                shutil.move(pending_session, rejected_session)
            
            # Remove from pending
            os.remove(pending_json)
            
            logger.info(f"Rejected session {phone} - reason: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Error rejecting session {phone}: {e}")
            return False
    
    def cleanup_session_files(self, session_name: str):
        """Clean up temporary session files from all possible locations"""
        try:
            # Get the session paths manager
            from sessions.session_paths import get_session_paths
            session_paths = get_session_paths()
            
            # Check all possible directories where session files might exist
            directories_to_check = [
                ".",  # Current directory (main folder)
                session_paths.pending_dir,
                session_paths.approved_dir,
                session_paths.rejected_dir,
                session_paths.extracted_dir
            ]
            
            file_extensions = [".session", ".session-journal", ".json"]
            
            for directory in directories_to_check:
                for ext in file_extensions:
                    temp_file = os.path.join(directory, f"{session_name}{ext}")
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                        logger.info(f"Cleaned up temporary file: {temp_file}")
                        
            # Also check for unique session files (with UUID suffix)
            for directory in directories_to_check:
                if os.path.exists(directory):
                    for file in os.listdir(directory):
                        if file.startswith(session_name) and any(file.endswith(ext) for ext in file_extensions):
                            temp_file = os.path.join(directory, file)
                            try:
                                os.remove(temp_file)
                                logger.info(f"Cleaned up temporary file: {temp_file}")
                            except Exception as e:
                                logger.warning(f"Could not remove file {temp_file}: {e}")
                    
        except Exception as e:
            logger.error(f"Error cleaning up session files: {e}")
    
    def register_handlers(self, dp: Dispatcher):
        """Register sell account handlers"""
        # Main sell accounts handler - show continents
        dp.callback_query.register(
            self.show_available_continents,
            F.data == "sell_accounts"
        )
        
        # Continent selection
        dp.callback_query.register(
            self.show_continent_countries,
            F.data.startswith("sell_continent_")
        )
        
        # Country selection
        dp.callback_query.register(
            self.country_selected,
            F.data.startswith("sell_country_")
        )
        
        # Phone number input
        dp.message.register(
            self.phone_number_received,
            SellAccountStates.waiting_phone_number
        )
        
        # Verification code input
        dp.message.register(
            self.verification_code_received,
            SellAccountStates.waiting_verification_code
        )
        
        # 2FA password input
        dp.message.register(
            self.handle_2fa_password,
            SellAccountStates.waiting_2fa_password
        )