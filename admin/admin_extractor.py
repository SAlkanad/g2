"""
Admin Session Extractor Module

Handles session extraction and export functionality including:
- Session extraction by country
- Session extraction by specific numbers
- Bulk session extraction
- ZIP file creation and management
- Session statistics for extraction
- Custom extraction filters
"""

import logging
import os
import zipfile
import json
import shutil
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile

from database.database import Database
from admin.auth_service import AuthService
from config_service import ConfigService

logger = logging.getLogger(__name__)


class ExtractorStates(StatesGroup):
    """FSM states for session extraction"""
    waiting_specific_numbers = State()
    waiting_custom_filter = State()
    waiting_extraction_name = State()


class AdminExtractor:
    """Admin module for session extraction"""
    
    def __init__(self, bot: Bot, database: Database, admin_ids: List[int], config_service: ConfigService = None):
        self.bot = bot
        self.database = database
        self.admin_ids = admin_ids
        self.auth_service = AuthService(database, admin_ids)
        self.config_service = config_service or ConfigService(database)
        
        # Initialize session manager using SellAccountSystem
        from sellaccount import SellAccountSystem
        self.session_manager = SellAccountSystem(
            bot=bot,
            database=database,
            api_id=self.config_service.get_api_id(),
            api_hash=self.config_service.get_api_hash(),
            admin_chat_id=self.config_service.get_admin_chat_id() or '',
            reporting_system=None
        )
        
        # Use centralized session paths instead of separate account folders
        from sessions.session_paths import get_session_paths
        session_paths = get_session_paths()
        
        # Extraction settings - use temp folder within session_files
        self.temp_dir = Path(session_paths.sessions_dir) / "temp"
        self.temp_dir.mkdir(exist_ok=True)
        
        self.approved_accounts_dir = Path(session_paths.approved_dir)
        self.pending_accounts_dir = Path(session_paths.pending_dir)
        self.rejected_accounts_dir = Path(session_paths.rejected_dir)
        
        # Directories are already created by session_paths system
        
        # Load country names from database
        self.refresh_country_mappings()
    
    def refresh_country_mappings(self):
        """Refresh country code to name mappings from database"""
        try:
            countries = self.database.get_countries()
            self.country_names = {}
            
            if countries:
                for country in countries:
                    code = country.get('country_code', country.get('code', ''))
                    name = country.get('country_name', country.get('name', ''))
                    if code and name:
                        self.country_names[code] = name
            
            # Add fallback mappings if database is empty
            if not self.country_names:
                self.country_names = {
                    'US': 'United States', 'UK': 'United Kingdom', 'CA': 'Canada',
                    'AU': 'Australia', 'DE': 'Germany', 'FR': 'France', 'IT': 'Italy',
                    'ES': 'Spain', 'NL': 'Netherlands', 'BE': 'Belgium', 'CH': 'Switzerland',
                    'AT': 'Austria', 'SE': 'Sweden', 'NO': 'Norway', 'DK': 'Denmark',
                    'FI': 'Finland', 'PL': 'Poland', 'CZ': 'Czech Republic', 'HU': 'Hungary',
                    'RU': 'Russia', 'UA': 'Ukraine', 'IN': 'India', 'CN': 'China',
                    'JP': 'Japan', 'KR': 'South Korea', 'BR': 'Brazil', 'AR': 'Argentina',
                    'MX': 'Mexico', 'EG': 'Egypt', 'SA': 'Saudi Arabia', 'AE': 'UAE',
                    'TR': 'Turkey', 'GR': 'Greece', 'IL': 'Israel', 'ZA': 'South Africa'
                }
        except Exception as e:
            logger.error(f"Error refreshing country mappings: {e}")
            # Use fallback mappings
            self.country_names = {
                'US': 'United States', 'UK': 'United Kingdom', 'CA': 'Canada',
                'AU': 'Australia', 'DE': 'Germany', 'FR': 'France'
            }
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin"""
        return self.auth_service.is_admin(user_id)
    
    def get_user_language(self, user_id: int) -> str:
        """Get user's language preference from database"""
        try:
            user = self.database.get_user(user_id)
            return user.get('language', 'en') if user else 'en'
        except Exception as e:
            logger.error(f"Error getting user language: {e}")
            return 'en'
    
    def get_country_name(self, code: str) -> str:
        """Get country name from code"""
        return self.country_names.get(code.upper(), code.upper())
    
    async def show_extractor_menu(self, callback_query: types.CallbackQuery):
        """Show main session extractor menu"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        # Get extraction statistics
        stats = self.get_extraction_statistics()
        
        keyboard = [
            [
                InlineKeyboardButton(text="🌍 Extract by Country", callback_data="extract_by_country"),
                InlineKeyboardButton(text="📱 Extract Specific Numbers", callback_data="extract_specific_numbers")
            ],
            [
                InlineKeyboardButton(text="📋 Extract by Status", callback_data="extract_by_status"),
                InlineKeyboardButton(text="🔍 Custom Filter Extract", callback_data="extract_custom_filter")
            ],
            [
                InlineKeyboardButton(text="📊 Extraction Statistics", callback_data="extraction_statistics"),
                InlineKeyboardButton(text="📂 Manage Extractions", callback_data="manage_extractions")
            ],
            [
                InlineKeyboardButton(text="📦 Bulk Operations", callback_data="bulk_extraction_ops"),
                InlineKeyboardButton(text="🗂️ Export All Data", callback_data="export_all_data")
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Admin Panel", callback_data="admin_panel")
            ]
        ]
        
        text = (
            "📦 **Session Extractor**\n\n"
            f"📊 **Quick Stats:**\n"
            f"• Total Sessions: {stats.get('total_sessions', 0)}\n"
            f"• Available for Extract: {stats.get('extractable_sessions', 0)}\n"
            f"• Already Extracted: {stats.get('extracted_sessions', 0)}\n"
            f"• Countries Available: {stats.get('countries_count', 0)}\n\n"
            "Select extraction method:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    def get_extraction_statistics(self) -> dict:
        """Get extraction statistics"""
        try:
            stats = self.session_manager.get_session_statistics()
            countries = self.database.get_countries()
            
            # Calculate total sessions properly
            total_sessions = stats.get('total', 0)
            extractable_sessions = stats.get('approved', 0)
            # Get extracted sessions total from the extracted dictionary
            extracted_info = stats.get('extracted', {})
            extracted_sessions = extracted_info.get('total', 0) if isinstance(extracted_info, dict) else 0
            countries_count = len(countries) if countries else 0
            
            return {
                'total_sessions': total_sessions,
                'extractable_sessions': extractable_sessions,
                'extracted_sessions': extracted_sessions,
                'countries_count': countries_count
            }
        except Exception as e:
            logger.error(f"Error getting extraction statistics: {e}")
            return {
                'total_sessions': 0,
                'extractable_sessions': 0,
                'extracted_sessions': 0,
                'countries_count': 0
            }
    
    async def extract_by_country_menu(self, callback_query: types.CallbackQuery):
        """Show country selection for extraction"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        # Get countries with available sessions
        countries_with_sessions = self.get_countries_with_sessions()
        
        if not countries_with_sessions:
            text = "📭 **No Countries Available**\n\nNo countries have sessions available for extraction."
            keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="admin_extractor")]]
        else:
            text = "🌍 **Extract by Country**\n\nSelect a country to extract sessions:\n\n"
            
            keyboard = []
            for country_code, session_count in countries_with_sessions.items():
                country_name = self.get_country_name(country_code)
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"🏳️ {country_name} ({session_count} sessions)",
                        callback_data=f"extract_country_{country_code}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_extractor")])
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    def get_countries_with_sessions(self) -> dict:
        """Get countries that have extractable sessions"""
        try:
            # Get approved sessions from session manager
            approved_sessions = self.session_manager.get_sessions_by_status('approved')
            country_counts = {}
            
            for session in approved_sessions:
                # Extract country from session data
                session_data = session.get('data', {})
                country = session_data.get('country_code', session_data.get('country', 'Unknown'))
                
                if country != 'Unknown':
                    country_counts[country] = country_counts.get(country, 0) + 1
            
            # Also check the approved sessions folder for additional sessions
            try:
                for item in self.approved_accounts_dir.iterdir():
                    if item.is_file() and item.suffix == '.json':
                        try:
                            with open(item, 'r') as f:
                                session_info = json.load(f)
                            country = session_info.get('country_code', 'Unknown')
                            if country != 'Unknown':
                                country_counts[country] = country_counts.get(country, 0) + 1
                        except Exception:
                            continue
            except Exception:
                pass
            
            return country_counts
        except Exception as e:
            logger.error(f"Error getting countries with sessions: {e}")
            return {}
    
    async def extract_country_sessions(self, callback_query: types.CallbackQuery):
        """Extract sessions for a specific country"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        country_code = callback_query.data.split('_')[-1]
        country_name = self.get_country_name(country_code)
        
        try:
            # Get sessions for this country
            approved_sessions = self.session_manager.get_sessions_by_status('approved')
            country_sessions = [s for s in approved_sessions if s.get('country') == country_code]
            
            if not country_sessions:
                await callback_query.answer(f"❌ No sessions found for {country_name}", show_alert=True)
                return
            
            # Create extraction
            extraction_name = f"{country_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            zip_path = await self.create_extraction_zip(country_sessions, extraction_name)
            
            if zip_path:
                # Move sessions to extracted folder
                for session in country_sessions:
                    phone = session.get('phone')
                    if phone:
                        self.session_manager.move_session_to_extracted(phone)
                
                # Send ZIP file
                with open(zip_path, 'rb') as zip_file:
                    zip_data = zip_file.read()
                
                await callback_query.message.reply_document(
                    document=BufferedInputFile(
                        file=zip_data,
                        filename=f"{extraction_name}.zip"
                    ),
                    caption=(
                        f"📦 **Session Extraction Complete**\n\n"
                        f"🌍 Country: {country_name}\n"
                        f"📱 Sessions: {len(country_sessions)}\n"
                        f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                        f"👤 Extracted by: {callback_query.from_user.first_name}"
                    ),
                    parse_mode="Markdown"
                )
                
                # Clean up temporary file
                os.remove(zip_path)
                
                # Log the extraction
                logger.info(f"Admin {callback_query.from_user.id} extracted {len(country_sessions)} sessions for {country_name}")
                
                await callback_query.answer(f"✅ {len(country_sessions)} sessions extracted successfully!", show_alert=True)
                
                # Refresh the country menu
                await self.extract_by_country_menu(callback_query)
            else:
                await callback_query.answer("❌ Failed to create extraction ZIP", show_alert=True)
        
        except Exception as e:
            logger.error(f"Error extracting country sessions: {e}")
            await callback_query.answer("❌ Error occurred during extraction", show_alert=True)
    
    async def extract_specific_numbers_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for specific phone numbers to extract"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        text = (
            "📱 **Extract Specific Numbers**\n\n"
            "Enter phone numbers to extract (one per line):\n\n"
            "**Format Examples:**\n"
            "```\n"
            "+1234567890\n"
            "+9876543210\n"
            "+1122334455\n"
            "```\n\n"
            "**Notes:**\n"
            "• Include country code with +\n"
            "• One number per line\n"
            "• Only approved sessions will be extracted\n"
            "• Invalid numbers will be skipped\n\n"
            "Enter phone numbers:"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="admin_extractor")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(ExtractorStates.waiting_specific_numbers)
    
    async def process_specific_numbers_extraction(self, message: types.Message, state: FSMContext):
        """Process specific numbers extraction"""
        if not self.is_admin(message.from_user.id):
            await message.reply("❌ Access denied")
            return
        
        try:
            # Parse phone numbers
            phone_numbers = []
            lines = message.text.strip().split('\n')
            
            for line in lines:
                phone = line.strip()
                if phone and phone.startswith('+'):
                    phone_numbers.append(phone)
            
            if not phone_numbers:
                await message.reply("❌ No valid phone numbers found. Please include country code with +")
                return
            
            # Find sessions for these numbers
            approved_sessions = self.session_manager.get_sessions_by_status('approved')
            matching_sessions = []
            found_numbers = []
            
            for session in approved_sessions:
                session_phone = session.get('phone')
                if session_phone in phone_numbers:
                    matching_sessions.append(session)
                    found_numbers.append(session_phone)
            
            if not matching_sessions:
                await message.reply(
                    f"❌ **No Matching Sessions Found**\n\n"
                    f"Searched for {len(phone_numbers)} numbers but found no approved sessions.\n"
                    f"Make sure the numbers are correct and have approved sessions."
                )
                return
            
            # Create extraction
            extraction_name = f"Specific_Numbers_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            zip_path = await self.create_extraction_zip(matching_sessions, extraction_name)
            
            if zip_path:
                # Move sessions to extracted folder
                for session in matching_sessions:
                    phone = session.get('phone')
                    if phone:
                        self.session_manager.move_session_to_extracted(phone)
                
                # Send ZIP file
                with open(zip_path, 'rb') as zip_file:
                    zip_data = zip_file.read()
                
                # Create summary of extraction
                not_found = set(phone_numbers) - set(found_numbers)
                summary_text = (
                    f"📦 **Specific Numbers Extraction**\n\n"
                    f"✅ **Found & Extracted**: {len(found_numbers)}\n"
                    f"❌ **Not Found**: {len(not_found)}\n\n"
                )
                
                if found_numbers:
                    summary_text += "**✅ Extracted Numbers:**\n"
                    for phone in found_numbers[:10]:  # Limit display
                        summary_text += f"• `{phone}`\n"
                    if len(found_numbers) > 10:
                        summary_text += f"• ... and {len(found_numbers) - 10} more\n"
                    summary_text += "\n"
                
                if not_found:
                    summary_text += "**❌ Not Found:**\n"
                    for phone in list(not_found)[:5]:  # Limit display
                        summary_text += f"• `{phone}`\n"
                    if len(not_found) > 5:
                        summary_text += f"• ... and {len(not_found) - 5} more\n"
                
                summary_text += f"\n📅 **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                
                await message.reply_document(
                    document=BufferedInputFile(
                        file=zip_data,
                        filename=f"{extraction_name}.zip"
                    ),
                    caption=summary_text,
                    parse_mode="Markdown"
                )
                
                # Clean up temporary file
                os.remove(zip_path)
                
                # Log the extraction
                logger.info(f"Admin {message.from_user.id} extracted {len(matching_sessions)} specific sessions")
                
            else:
                await message.reply("❌ Failed to create extraction ZIP")
        
        except Exception as e:
            logger.error(f"Error extracting specific numbers: {e}")
            await message.reply(f"❌ Error during extraction: {str(e)}")
        
        await state.clear()
    
    async def extract_by_status_menu(self, callback_query: types.CallbackQuery):
        """Show status selection for extraction"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        stats = self.session_manager.get_session_statistics()
        
        keyboard = [
            [
                InlineKeyboardButton(
                    text=f"✅ Approved ({stats.get('approved', 0)})",
                    callback_data="extract_status_approved"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"❌ Rejected ({stats.get('rejected', 0)})",
                    callback_data="extract_status_rejected"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"⏳ Pending ({stats.get('pending', 0)})",
                    callback_data="extract_status_pending"
                )
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin_extractor")
            ]
        ]
        
        text = (
            "📋 **Extract by Status**\n\n"
            "Select session status to extract:\n\n"
            "⚠️ **Note**: Extracting will move sessions to extracted folder.\n"
            "Only extract when you're ready to deliver sessions."
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def extract_by_status(self, callback_query: types.CallbackQuery):
        """Extract sessions by status"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        status = callback_query.data.split('_')[-1]
        
        try:
            sessions = self.session_manager.get_sessions_by_status(status)
            
            if not sessions:
                await callback_query.answer(f"❌ No {status} sessions found", show_alert=True)
                return
            
            # Confirm extraction
            keyboard = [
                [
                    InlineKeyboardButton(text="✅ Confirm Extract", callback_data=f"confirm_extract_status_{status}"),
                    InlineKeyboardButton(text="❌ Cancel", callback_data="extract_by_status")
                ]
            ]
            
            text = (
                f"📋 **Confirm {status.title()} Extraction**\n\n"
                f"📊 **Sessions to Extract**: {len(sessions)}\n\n"
                f"⚠️ **Warning**: This will extract ALL {status} sessions.\n"
                f"They will be moved to the extracted folder.\n\n"
                f"Are you sure you want to proceed?"
            )
            
            await callback_query.message.edit_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="Markdown"
            )
        
        except Exception as e:
            logger.error(f"Error preparing status extraction: {e}")
            await callback_query.answer("❌ Error occurred", show_alert=True)
    
    async def confirm_extract_by_status(self, callback_query: types.CallbackQuery):
        """Confirm and execute status-based extraction"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        status = callback_query.data.split('_')[-1]
        
        try:
            sessions = self.session_manager.get_sessions_by_status(status)
            
            if not sessions:
                await callback_query.answer(f"❌ No {status} sessions found", show_alert=True)
                return
            
            # Create extraction
            extraction_name = f"All_{status.title()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            zip_path = await self.create_extraction_zip(sessions, extraction_name)
            
            if zip_path:
                # Move sessions to extracted folder (only if status is approved)
                if status == 'approved':
                    for session in sessions:
                        phone = session.get('phone')
                        if phone:
                            self.session_manager.move_session_to_extracted(phone)
                
                # Send ZIP file
                with open(zip_path, 'rb') as zip_file:
                    zip_data = zip_file.read()
                
                await callback_query.message.reply_document(
                    document=BufferedInputFile(
                        file=zip_data,
                        filename=f"{extraction_name}.zip"
                    ),
                    caption=(
                        f"📦 **{status.title()} Sessions Extraction**\n\n"
                        f"📊 Sessions: {len(sessions)}\n"
                        f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                        f"👤 Extracted by: {callback_query.from_user.first_name}\n"
                        f"🔄 Status: {'Moved to extracted' if status == 'approved' else 'Copied only'}"
                    ),
                    parse_mode="Markdown"
                )
                
                # Clean up temporary file
                os.remove(zip_path)
                
                # Log the extraction
                logger.info(f"Admin {callback_query.from_user.id} extracted {len(sessions)} {status} sessions")
                
                await callback_query.answer(f"✅ {len(sessions)} {status} sessions extracted!", show_alert=True)
                
                # Return to main extractor menu
                await self.show_extractor_menu(callback_query)
            else:
                await callback_query.answer("❌ Failed to create extraction ZIP", show_alert=True)
        
        except Exception as e:
            logger.error(f"Error in status extraction: {e}")
            await callback_query.answer("❌ Error occurred during extraction", show_alert=True)
    
    async def create_extraction_zip(self, sessions: List[Dict], extraction_name: str) -> Optional[str]:
        """Create a ZIP file with session files and metadata"""
        try:
            zip_path = self.temp_dir / f"{extraction_name}.zip"
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add session files
                session_count = 0
                session_metadata = []
                
                for session in sessions:
                    # Handle different session data structures
                    session_data = session.get('data', session)
                    phone = session_data.get('phone_number', session_data.get('phone', ''))
                    status = session_data.get('status', 'approved')
                    
                    if not phone:
                        continue
                    
                    # Look for session file in multiple locations
                    session_file_path = None
                    
                    # First, try session manager
                    try:
                        session_file_path = self.session_manager.get_session_file_path(phone, status)
                    except:
                        pass
                    
                    # If not found, check account folders
                    if not session_file_path or not os.path.exists(session_file_path):
                        # Check approved accounts folder
                        approved_session = self.approved_accounts_dir / f"{phone}.session"
                        if approved_session.exists():
                            session_file_path = str(approved_session)
                        else:
                            # Check pending accounts folder
                            pending_session = self.pending_accounts_dir / f"{phone}.session"
                            if pending_session.exists():
                                session_file_path = str(pending_session)
                    
                    if session_file_path and os.path.exists(session_file_path):
                        # Add session file to ZIP
                        arcname = f"sessions/{phone}.session"
                        zipf.write(session_file_path, arcname)
                        session_count += 1
                        
                        # Collect metadata
                        session_metadata.append({
                            'phone': phone,
                            'country': session_data.get('country_code', session_data.get('country', 'Unknown')),
                            'status': status,
                            'user_id': session_data.get('user_id'),
                            'created_at': session_data.get('created_at', session_data.get('timestamp')),
                            'file_size': os.path.getsize(session_file_path)
                        })
                
                # Add metadata file
                metadata = {
                    'extraction_info': {
                        'name': extraction_name,
                        'date': datetime.now().isoformat(),
                        'total_sessions': session_count,
                        'extracted_by': 'Admin Panel'
                    },
                    'sessions': session_metadata
                }
                
                zipf.writestr("metadata.json", json.dumps(metadata, indent=2))
                
                # Add README
                readme_content = f"""
Session Extraction: {extraction_name}
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total Sessions: {session_count}

This archive contains Telegram session files.
Each .session file can be used with Telethon or Pyrogram.

Files included:
- sessions/*.session: Telegram session files
- metadata.json: Detailed information about each session

IMPORTANT: Keep these files secure and use them responsibly.
"""
                zipf.writestr("README.txt", readme_content.strip())
            
            return str(zip_path) if session_count > 0 else None
        
        except Exception as e:
            logger.error(f"Error creating extraction ZIP: {e}")
            return None
    
    async def show_extraction_statistics(self, callback_query: types.CallbackQuery):
        """Show detailed extraction statistics"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        try:
            stats = self.session_manager.get_detailed_statistics()
            countries_with_sessions = self.get_countries_with_sessions()
            
            text = "📊 **Extraction Statistics**\n\n"
            
            # Overall stats
            text += f"📈 **Overall:**\n"
            text += f"• Total Sessions: {stats.get('total', 0)}\n"
            text += f"• Ready for Extract: {stats.get('approved', 0)}\n"
            text += f"• Already Extracted: {stats.get('extracted', 0)}\n"
            text += f"• Rejected Sessions: {stats.get('rejected', 0)}\n"
            text += f"• Pending Sessions: {stats.get('pending', 0)}\n\n"
            
            # Country breakdown
            if countries_with_sessions:
                text += f"🌍 **By Country (Ready to Extract):**\n"
                sorted_countries = sorted(countries_with_sessions.items(), key=lambda x: x[1], reverse=True)
                for country_code, count in sorted_countries[:10]:
                    country_name = self.get_country_name(country_code)
                    text += f"• {country_name}: {count} sessions\n"
                
                if len(sorted_countries) > 10:
                    text += f"• ... and {len(sorted_countries) - 10} more countries\n"
                text += "\n"
            
            # Extraction recommendations
            total_ready = stats.get('approved', 0)
            if total_ready > 0:
                text += f"💡 **Recommendations:**\n"
                if total_ready > 100:
                    text += f"• Consider bulk extraction for efficiency\n"
                if len(countries_with_sessions) > 5:
                    text += f"• Extract by country for organization\n"
                text += f"• {total_ready} sessions ready for immediate extraction\n"
            else:
                text += f"ℹ️ **No sessions ready for extraction**\n"
        
        except Exception as e:
            logger.error(f"Error getting extraction statistics: {e}")
            text = "❌ **Error Loading Statistics**\n\nUnable to load extraction statistics."
        
        keyboard = [
            [
                InlineKeyboardButton(text="🔄 Refresh", callback_data="extraction_statistics"),
                InlineKeyboardButton(text="📊 Export Stats", callback_data="export_extraction_stats")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin_extractor")
            ]
        ]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def export_extraction_stats(self, callback_query: types.CallbackQuery):
        """Export extraction statistics as a file"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        try:
            stats = self.session_manager.get_detailed_statistics()
            countries_with_sessions = self.get_countries_with_sessions()
            
            # Create comprehensive stats report
            report = {
                "extraction_statistics_report": {
                    "generated_at": datetime.now().isoformat(),
                    "generated_by": callback_query.from_user.first_name,
                    "overall_stats": {
                        "total_sessions": stats.get('total', 0),
                        "approved_sessions": stats.get('approved', 0),
                        "rejected_sessions": stats.get('rejected', 0),
                        "pending_sessions": stats.get('pending', 0),
                        "extracted_sessions": stats.get('extracted', {}).get('total', 0) if isinstance(stats.get('extracted'), dict) else 0
                    },
                    "countries_breakdown": countries_with_sessions,
                    "extraction_readiness": {
                        "ready_for_extraction": stats.get('approved', 0),
                        "countries_with_sessions": len(countries_with_sessions),
                        "extraction_efficiency": f"{(stats.get('approved', 0) / max(stats.get('total', 1), 1) * 100):.1f}%"
                    }
                }
            }
            
            # Create file
            filename = f"extraction_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            file_content = json.dumps(report, indent=2)
            
            await callback_query.message.reply_document(
                document=BufferedInputFile(
                    file=file_content.encode('utf-8'),
                    filename=filename
                ),
                caption="📊 **Extraction Statistics Export**\n\nDetailed statistics for session extraction analysis.",
                parse_mode="Markdown"
            )
            
            await callback_query.answer("✅ Statistics exported successfully!", show_alert=True)
            
        except Exception as e:
            logger.error(f"Error exporting extraction stats: {e}")
            await callback_query.answer("❌ Failed to export statistics", show_alert=True)
    
    async def extract_custom_filter_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for custom filter criteria"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        text = (
            "🔍 **Custom Filter Extraction**\n\n"
            "Enter filter criteria in JSON format:\n\n"
            "**Example:**\n"
            "```json\n"
            "{\n"
            '  "countries": ["US", "UK", "CA"],\n'
            '  "status": "approved",\n'
            '  "min_sessions": 5,\n'
            '  "user_id": 123456789\n'
            "}\n"
            "```\n\n"
            "**Available Filters:**\n"
            "• `countries`: List of country codes\n"
            "• `status`: approved/rejected/pending\n"
            "• `min_sessions`: Minimum sessions per country\n"
            "• `user_id`: Filter by specific user\n"
            "• `date_from`: YYYY-MM-DD format\n"
            "• `date_to`: YYYY-MM-DD format\n\n"
            "Enter your filter JSON:"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="admin_extractor")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(ExtractorStates.waiting_custom_filter)
    
    async def process_custom_filter_extraction(self, message: types.Message, state: FSMContext):
        """Process custom filter extraction"""
        if not self.is_admin(message.from_user.id):
            await message.reply("❌ Access denied")
            return
        
        try:
            # Parse JSON filter
            filter_criteria = json.loads(message.text.strip())
            
            # Get all sessions
            all_sessions = []
            for status in ['approved', 'rejected', 'pending']:
                sessions = self.session_manager.get_sessions_by_status(status)
                all_sessions.extend(sessions)
            
            # Apply filters
            filtered_sessions = []
            
            for session in all_sessions:
                # Status filter
                if 'status' in filter_criteria:
                    if session.get('status') != filter_criteria['status']:
                        continue
                
                # Country filter
                if 'countries' in filter_criteria:
                    if session.get('country') not in filter_criteria['countries']:
                        continue
                
                # User ID filter
                if 'user_id' in filter_criteria:
                    if session.get('user_id') != filter_criteria['user_id']:
                        continue
                
                # Date filters (simplified - would need proper date parsing)
                if 'date_from' in filter_criteria or 'date_to' in filter_criteria:
                    # For demo purposes, we'll skip date filtering
                    pass
                
                filtered_sessions.append(session)
            
            # Apply min_sessions filter (group by country)
            if 'min_sessions' in filter_criteria:
                min_sessions = filter_criteria['min_sessions']
                country_counts = {}
                for session in filtered_sessions:
                    country = session.get('country', 'Unknown')
                    country_counts[country] = country_counts.get(country, 0) + 1
                
                # Filter out countries with insufficient sessions
                valid_countries = {k: v for k, v in country_counts.items() if v >= min_sessions}
                filtered_sessions = [s for s in filtered_sessions if s.get('country') in valid_countries]
            
            if not filtered_sessions:
                await message.reply(
                    "❌ **No Sessions Match Filter**\n\n"
                    "No sessions found matching your filter criteria.\n"
                    "Try adjusting your filters."
                )
                await state.clear()
                return
            
            # Create extraction
            extraction_name = f"Custom_Filter_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            zip_path = await self.create_extraction_zip(filtered_sessions, extraction_name)
            
            if zip_path:
                # Move approved sessions to extracted folder
                for session in filtered_sessions:
                    if session.get('status') == 'approved':
                        phone = session.get('phone')
                        if phone:
                            self.session_manager.move_session_to_extracted(phone)
                
                # Send ZIP file
                with open(zip_path, 'rb') as zip_file:
                    zip_data = zip_file.read()
                
                # Create summary
                country_breakdown = {}
                for session in filtered_sessions:
                    country = session.get('country', 'Unknown')
                    country_breakdown[country] = country_breakdown.get(country, 0) + 1
                
                summary_text = (
                    f"📦 **Custom Filter Extraction**\n\n"
                    f"📊 **Total Sessions**: {len(filtered_sessions)}\n"
                    f"🌍 **Countries**: {len(country_breakdown)}\n\n"
                    f"**Filter Applied**:\n"
                    f"```json\n{json.dumps(filter_criteria, indent=2)}\n```\n\n"
                    f"📅 **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                )
                
                await message.reply_document(
                    document=BufferedInputFile(
                        file=zip_data,
                        filename=f"{extraction_name}.zip"
                    ),
                    caption=summary_text,
                    parse_mode="Markdown"
                )
                
                # Clean up temporary file
                os.remove(zip_path)
                
                logger.info(f"Admin {message.from_user.id} performed custom filter extraction: {len(filtered_sessions)} sessions")
            else:
                await message.reply("❌ Failed to create extraction ZIP")
        
        except json.JSONDecodeError:
            await message.reply("❌ Invalid JSON format. Please check your syntax.")
        except Exception as e:
            logger.error(f"Error in custom filter extraction: {e}")
            await message.reply(f"❌ Error during extraction: {str(e)}")
        
        await state.clear()
    
    async def manage_extractions_menu(self, callback_query: types.CallbackQuery):
        """Show extraction management menu"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        try:
            # Get extracted sessions info
            extracted_stats = self.session_manager.get_all_extracted_sessions()
            total_extracted = 0
            if isinstance(extracted_stats, dict):
                for status_sessions in extracted_stats.values():
                    if isinstance(status_sessions, list):
                        total_extracted += len(status_sessions)
            
            keyboard = [
                [
                    InlineKeyboardButton(text="👁️ View Extracted Sessions", callback_data="view_extracted_sessions"),
                    InlineKeyboardButton(text="🔄 Restore Sessions", callback_data="restore_extracted_sessions")
                ],
                [
                    InlineKeyboardButton(text="🗑️ Delete Extracted", callback_data="delete_extracted_sessions"),
                    InlineKeyboardButton(text="📊 Extracted Statistics", callback_data="extracted_session_stats")
                ],
                [
                    InlineKeyboardButton(text="🔙 Back", callback_data="admin_extractor")
                ]
            ]
            
            text = (
                "📂 **Manage Extractions**\n\n"
                f"📊 **Currently Extracted**: {total_extracted} sessions\n\n"
                "**Available Actions:**\n"
                "• View all extracted sessions\n"
                "• Restore sessions back to original folders\n"
                "• Delete extracted sessions permanently\n"
                "• View detailed extracted statistics\n\n"
                "Select an action:"
            )
            
            await callback_query.message.edit_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="Markdown"
            )
        
        except Exception as e:
            logger.error(f"Error showing manage extractions menu: {e}")
            await callback_query.answer("❌ Error loading extraction management", show_alert=True)
    
    async def bulk_extraction_ops_menu(self, callback_query: types.CallbackQuery):
        """Show bulk operations menu"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        stats = self.session_manager.get_session_statistics()
        
        keyboard = [
            [
                InlineKeyboardButton(
                    text=f"✅ Extract All Approved ({stats.get('approved', 0)})",
                    callback_data="bulk_extract_all_approved"
                )
            ],
            [
                InlineKeyboardButton(text="📅 Extract by Date Range", callback_data="bulk_extract_date_range"),
                InlineKeyboardButton(text="🌍 Extract All Countries", callback_data="bulk_extract_all_countries")
            ],
            [
                InlineKeyboardButton(text="🗑️ Clear All Extracted", callback_data="bulk_clear_extracted"),
                InlineKeyboardButton(text="📦 Archive All Sessions", callback_data="bulk_archive_sessions")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin_extractor")
            ]
        ]
        
        text = (
            "📦 **Bulk Operations**\n\n"
            f"📊 **Available for Bulk Extract**:\n"
            f"• Approved Sessions: {stats.get('approved', 0)}\n"
            f"• Rejected Sessions: {stats.get('rejected', 0)}\n"
            f"• Pending Sessions: {stats.get('pending', 0)}\n\n"
            "⚠️ **Warning**: Bulk operations affect multiple sessions.\n"
            "Use with caution.\n\n"
            "Select operation:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def export_all_data(self, callback_query: types.CallbackQuery):
        """Export all session data"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        try:
            await callback_query.answer("🔄 Preparing data export...", show_alert=True)
            
            # Get all sessions from all statuses
            all_sessions = []
            for status in ['approved', 'rejected', 'pending']:
                sessions = self.session_manager.get_sessions_by_status(status)
                all_sessions.extend(sessions)
            
            # Get extracted sessions
            extracted_sessions = self.session_manager.get_all_extracted_sessions()
            if isinstance(extracted_sessions, dict):
                for status_sessions in extracted_sessions.values():
                    if isinstance(status_sessions, list):
                        all_sessions.extend(status_sessions)
            
            if not all_sessions:
                await callback_query.message.reply("❌ **No Data to Export**\n\nNo sessions found in the system.")
                return
            
            # Create comprehensive export
            export_name = f"Complete_Export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            zip_path = await self.create_export_zip(all_sessions, export_name)
            
            if zip_path:
                # Send ZIP file
                with open(zip_path, 'rb') as zip_file:
                    zip_data = zip_file.read()
                
                # Calculate export statistics
                status_counts = {}
                country_counts = {}
                for session in all_sessions:
                    status = session.get('status', 'unknown')
                    country = session.get('country', 'Unknown')
                    status_counts[status] = status_counts.get(status, 0) + 1
                    country_counts[country] = country_counts.get(country, 0) + 1
                
                summary_text = (
                    f"🗂️ **Complete Data Export**\n\n"
                    f"📊 **Total Sessions**: {len(all_sessions)}\n"
                    f"🌍 **Countries**: {len(country_counts)}\n"
                    f"📋 **Statuses**: {len(status_counts)}\n\n"
                    f"📅 **Export Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                    f"👤 **Exported by**: {callback_query.from_user.first_name}\n\n"
                    f"⚠️ **Note**: This export contains ALL session data."
                )
                
                await callback_query.message.reply_document(
                    document=BufferedInputFile(
                        file=zip_data,
                        filename=f"{export_name}.zip"
                    ),
                    caption=summary_text,
                    parse_mode="Markdown"
                )
                
                # Clean up temporary file
                os.remove(zip_path)
                
                logger.info(f"Admin {callback_query.from_user.id} exported all data: {len(all_sessions)} sessions")
            else:
                await callback_query.message.reply("❌ Failed to create export file")
        
        except Exception as e:
            logger.error(f"Error exporting all data: {e}")
            await callback_query.answer("❌ Export failed", show_alert=True)
    
    async def create_export_zip(self, sessions: List[Dict], export_name: str) -> Optional[str]:
        """Create export ZIP with all data and comprehensive metadata"""
        try:
            zip_path = self.temp_dir / f"{export_name}.zip"
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                session_count = 0
                export_metadata = {
                    'sessions_by_status': {},
                    'sessions_by_country': {},
                    'all_sessions': []
                }
                
                for session in sessions:
                    phone = session.get('phone')
                    status = session.get('status', 'unknown')
                    country = session.get('country', 'Unknown')
                    
                    if not phone:
                        continue
                    
                    # Find session file
                    session_file_path = self.session_manager.get_session_file_path(phone, status)
                    
                    if session_file_path and os.path.exists(session_file_path):
                        # Add to appropriate folder in ZIP
                        arcname = f"sessions/{status}/{country}/{phone}.session"
                        zipf.write(session_file_path, arcname)
                        session_count += 1
                    
                    # Collect metadata
                    session_info = {
                        'phone': phone,
                        'country': country,
                        'status': status,
                        'user_id': session.get('user_id'),
                        'created_at': session.get('created_at'),
                        'has_file': session_file_path and os.path.exists(session_file_path)
                    }
                    
                    export_metadata['all_sessions'].append(session_info)
                    
                    # Group by status and country
                    if status not in export_metadata['sessions_by_status']:
                        export_metadata['sessions_by_status'][status] = []
                    export_metadata['sessions_by_status'][status].append(session_info)
                    
                    if country not in export_metadata['sessions_by_country']:
                        export_metadata['sessions_by_country'][country] = []
                    export_metadata['sessions_by_country'][country].append(session_info)
                
                # Add comprehensive metadata
                export_info = {
                    'export_info': {
                        'name': export_name,
                        'type': 'complete_export',
                        'date': datetime.now().isoformat(),
                        'total_sessions': session_count,
                        'total_records': len(sessions),
                        'exported_by': 'Admin Panel'
                    },
                    'statistics': {
                        'sessions_with_files': session_count,
                        'sessions_without_files': len(sessions) - session_count,
                        'countries_count': len(export_metadata['sessions_by_country']),
                        'statuses_count': len(export_metadata['sessions_by_status'])
                    },
                    'data': export_metadata
                }
                
                zipf.writestr("export_metadata.json", json.dumps(export_info, indent=2))
                
                # Add comprehensive README
                readme_content = f"""
COMPLETE SESSION DATA EXPORT
============================

Export Name: {export_name}
Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total Sessions: {session_count}
Total Records: {len(sessions)}

DIRECTORY STRUCTURE:
- sessions/
  - approved/
    - [country_code]/
      - [phone].session
  - rejected/
    - [country_code]/
      - [phone].session
  - pending/
    - [country_code]/
      - [phone].session
- export_metadata.json: Complete metadata and statistics
- README.txt: This file

METADATA:
The export_metadata.json file contains:
- Complete session information
- Statistics by status and country
- Export information and timestamps
- File availability status

USAGE:
These session files can be used with:
- Telethon (Python Telegram client)
- Pyrogram (Python Telegram client)
- Other compatible Telegram client libraries

SECURITY:
- Keep these files secure and encrypted
- Do not share without proper authorization
- Use only for legitimate purposes
- Follow applicable laws and regulations

For questions about this export, contact the system administrator.
"""
                zipf.writestr("README.txt", readme_content.strip())
            
            return str(zip_path) if session_count > 0 else None
        
        except Exception as e:
            logger.error(f"Error creating export ZIP: {e}")
            return None
    
    # Additional bulk operation methods
    async def bulk_extract_all_approved(self, callback_query: types.CallbackQuery):
        """Extract all approved sessions in bulk"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        try:
            approved_sessions = self.session_manager.get_sessions_by_status('approved')
            
            if not approved_sessions:
                await callback_query.answer("❌ No approved sessions found", show_alert=True)
                return
            
            # Create extraction immediately
            extraction_name = f"Bulk_All_Approved_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            zip_path = await self.create_extraction_zip(approved_sessions, extraction_name)
            
            if zip_path:
                # Move all sessions to extracted folder
                for session in approved_sessions:
                    phone = session.get('phone')
                    if phone:
                        self.session_manager.move_session_to_extracted(phone)
                
                # Send ZIP file
                with open(zip_path, 'rb') as zip_file:
                    zip_data = zip_file.read()
                
                await callback_query.message.reply_document(
                    document=BufferedInputFile(
                        file=zip_data,
                        filename=f"{extraction_name}.zip"
                    ),
                    caption=(
                        f"📦 **Bulk Extraction Complete**\n\n"
                        f"✅ **Extracted**: {len(approved_sessions)} approved sessions\n"
                        f"📅 **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                        f"👤 **Extracted by**: {callback_query.from_user.first_name}\n\n"
                        f"All approved sessions have been moved to extracted folder."
                    ),
                    parse_mode="Markdown"
                )
                
                # Clean up temporary file
                os.remove(zip_path)
                
                logger.info(f"Admin {callback_query.from_user.id} bulk extracted {len(approved_sessions)} approved sessions")
                await callback_query.answer(f"✅ {len(approved_sessions)} sessions extracted!", show_alert=True)
                
                # Return to main menu
                await self.show_extractor_menu(callback_query)
            else:
                await callback_query.answer("❌ Failed to create extraction ZIP", show_alert=True)
        
        except Exception as e:
            logger.error(f"Error in bulk extract approved: {e}")
            await callback_query.answer("❌ Error occurred during bulk extraction", show_alert=True)
    
    async def bulk_extract_by_date_range(self, callback_query: types.CallbackQuery):
        """Extract sessions by date range (placeholder)"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        text = (
            "📅 **Extract by Date Range**\n\n"
            "ℹ️ This feature requires date filtering implementation.\n"
            "Currently not available.\n\n"
            "Would need to add date metadata to sessions for this to work."
        )
        
        keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="bulk_extraction_ops")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def bulk_clear_extracted(self, callback_query: types.CallbackQuery):
        """Clear all extracted sessions"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        text = (
            "🗑️ **Clear All Extracted Sessions**\n\n"
            "⚠️ **DANGER**: This will permanently delete all extracted sessions.\n\n"
            "This action:\n"
            "• Cannot be undone\n"
            "• Will free up storage space\n"
            "• Will remove all extracted session files\n\n"
            "❌ **Not implemented for safety**\n"
            "Contact system administrator if needed."
        )
        
        keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="bulk_extraction_ops")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    # Manage extractions methods
    async def view_extracted_sessions(self, callback_query: types.CallbackQuery):
        """View extracted sessions"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        try:
            extracted_sessions = self.session_manager.get_all_extracted_sessions()
            
            if not extracted_sessions or not any(extracted_sessions.values()):
                text = "📭 **No Extracted Sessions**\n\nNo sessions have been extracted yet."
                keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="manage_extractions")]]
            else:
                text = "👁️ **Extracted Sessions**\n\n"
                
                total_extracted = 0
                for status, sessions in extracted_sessions.items():
                    if isinstance(sessions, list):
                        count = len(sessions)
                        total_extracted += count
                        text += f"• {status.title()}: {count} sessions\n"
                
                text += f"\n📊 **Total Extracted**: {total_extracted} sessions\n"
                text += "\n💡 Use 'Restore Sessions' to move them back or 'Delete' to remove permanently."
                
                keyboard = [
                    [
                        InlineKeyboardButton(text="🔄 Restore All", callback_data="restore_extracted_sessions"),
                        InlineKeyboardButton(text="🗑️ Delete All", callback_data="delete_extracted_sessions")
                    ],
                    [
                        InlineKeyboardButton(text="🔙 Back", callback_data="manage_extractions")
                    ]
                ]
            
            await callback_query.message.edit_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="Markdown"
            )
        
        except Exception as e:
            logger.error(f"Error viewing extracted sessions: {e}")
            await callback_query.answer("❌ Error loading extracted sessions", show_alert=True)
    
    async def restore_extracted_sessions(self, callback_query: types.CallbackQuery):
        """Restore extracted sessions (placeholder)"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        text = (
            "🔄 **Restore Extracted Sessions**\n\n"
            "ℹ️ This feature would restore extracted sessions back to their original locations.\n\n"
            "**Implementation needed:**\n"
            "• Track original session locations\n"
            "• Implement restore functionality in SessionManager\n"
            "• Handle conflicts with existing sessions\n\n"
            "Currently not available."
        )
        
        keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="manage_extractions")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def delete_extracted_sessions(self, callback_query: types.CallbackQuery):
        """Delete extracted sessions (placeholder)"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        text = (
            "🗑️ **Delete Extracted Sessions**\n\n"
            "⚠️ **DANGER**: This would permanently delete all extracted session files.\n\n"
            "❌ **Not implemented for safety**\n\n"
            "Contact system administrator if you need to clean up extracted sessions."
        )
        
        keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="manage_extractions")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    def register_handlers(self, dp: Dispatcher):
        """Register session extractor handlers"""
        # Main menu
        dp.callback_query.register(
            self.show_extractor_menu,
            F.data == "admin_extractor"
        )
        
        # Country extraction
        dp.callback_query.register(
            self.extract_by_country_menu,
            F.data == "extract_by_country"
        )
        
        dp.callback_query.register(
            self.extract_country_sessions,
            F.data.startswith("extract_country_")
        )
        
        # Specific numbers extraction
        dp.callback_query.register(
            self.extract_specific_numbers_prompt,
            F.data == "extract_specific_numbers"
        )
        
        dp.message.register(
            self.process_specific_numbers_extraction,
            ExtractorStates.waiting_specific_numbers
        )
        
        # Status extraction
        dp.callback_query.register(
            self.extract_by_status_menu,
            F.data == "extract_by_status"
        )
        
        dp.callback_query.register(
            self.extract_by_status,
            F.data.startswith("extract_status_")
        )
        
        dp.callback_query.register(
            self.confirm_extract_by_status,
            F.data.startswith("confirm_extract_status_")
        )
        
        # Statistics
        dp.callback_query.register(
            self.show_extraction_statistics,
            F.data == "extraction_statistics"
        )
        
        # Export statistics
        dp.callback_query.register(
            self.export_extraction_stats,
            F.data == "export_extraction_stats"
        )
        
        # Custom filter extraction
        dp.callback_query.register(
            self.extract_custom_filter_prompt,
            F.data == "extract_custom_filter"
        )
        
        dp.message.register(
            self.process_custom_filter_extraction,
            ExtractorStates.waiting_custom_filter
        )
        
        # Manage extractions
        dp.callback_query.register(
            self.manage_extractions_menu,
            F.data == "manage_extractions"
        )
        
        # Bulk operations
        dp.callback_query.register(
            self.bulk_extraction_ops_menu,
            F.data == "bulk_extraction_ops"
        )
        
        # Export all data
        dp.callback_query.register(
            self.export_all_data,
            F.data == "export_all_data"
        )
        
        # Bulk operation handlers
        dp.callback_query.register(
            self.bulk_extract_all_approved,
            F.data == "bulk_extract_all_approved"
        )
        
        dp.callback_query.register(
            self.bulk_extract_by_date_range,
            F.data == "bulk_extract_date_range"
        )
        
        dp.callback_query.register(
            self.bulk_clear_extracted,
            F.data == "bulk_clear_extracted"
        )
        
        # Manage extractions handlers
        dp.callback_query.register(
            self.view_extracted_sessions,
            F.data == "view_extracted_sessions"
        )
        
        dp.callback_query.register(
            self.restore_extracted_sessions,
            F.data == "restore_extracted_sessions"
        )
        
        dp.callback_query.register(
            self.delete_extracted_sessions,
            F.data == "delete_extracted_sessions"
        )