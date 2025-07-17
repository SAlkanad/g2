"""
Admin Countries Management Module

Handles all country-related administrative functions including:
- Adding new countries
- Editing existing countries  
- Toggling country availability
- Deleting countries
- Country statistics and management
"""

import logging
import re
from typing import List, Dict, Optional
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.database import Database
from admin.auth_service import AuthService
from languages.languages import get_text
from country_filter_service import CountryFilterService, get_continent_emoji

logger = logging.getLogger(__name__)


class CountryStates(StatesGroup):
    """FSM states for country management"""
    waiting_quick_edit_new = State()


class AdminCountries:
    """Admin module for country management"""
    
    def __init__(self, bot: Bot, database: Database, admin_ids: List[int]):
        self.bot = bot
        self.database = database
        self.admin_ids = admin_ids
        self.auth_service = AuthService(database, admin_ids)
        self.country_filter = CountryFilterService(database)
        
        # Initialize default countries if none exist
        self.initialize_default_countries()
    
    
    def initialize_default_countries(self):
        """Initialize default countries if database is empty"""
        try:
            existing_countries = self.database.get_countries()
            if not existing_countries:
                logger.info("No countries found in database. Initializing default countries...")
                # Use the defaultdata module for consistent initialization
                from database.defaultdata import DefaultDataInitializer
                initializer = DefaultDataInitializer(self.database.db_path)
                initializer.init_default_countries()
                
                logger.info("Initialized default countries using defaultdata module")
            else:
                logger.info(f"Found {len(existing_countries)} existing countries in database")
        except Exception as e:
            logger.error(f"Error initializing default countries: {e}")
    
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
    
    async def show_countries_menu(self, callback_query: types.CallbackQuery):
        """Show main countries management menu with only 'Edit Countries' button."""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        countries = self.database.get_countries(active_only=False)  # Fetch all countries to show total/active/inactive status
        total_countries = len(countries) if countries else 0
        active_countries = sum(1 for c in countries if c.get('is_active', False)) if countries else 0
        
        keyboard = [
            [
                InlineKeyboardButton(text="✏️ Edit Countries", callback_data="edit_countries_main")
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Admin Panel", callback_data="admin_panel")
            ]
        ]
        
        text = (
            "🌍 **Countries Management**\n\n"
            f"📊 **Overview:**\n"
            f"• Total Countries: {total_countries}\n"
            f"• Active Countries: {active_countries}\n"
            f"• Inactive Countries: {total_countries - active_countries}\n\n"
            "Choose an option:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def show_available_countries(self, callback_query: types.CallbackQuery):
        """Show available countries for management"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        countries = self.database.get_countries()
        available_countries = [c for c in countries if c.get('is_active', False)]
        
        if not available_countries:
            text = "📭 **No Available Countries**\n\nNo countries are currently available."
            keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="admin_countries")]]
        else:
            text = "📋 **Available Countries**\n\nSelect a country to manage:\n\n"
            keyboard = []
            
            # Add country buttons (2 per row)
            for i in range(0, len(available_countries), 2):
                row = []
                for j in range(2):
                    if i + j < len(available_countries):
                        country = available_countries[i + j]
                        sessions_count = self.database.get_country_session_count(country.get('code', ''))
                        btn_text = f"{country.get('name', 'Unknown')} ({country.get('code', 'XX')}) - {sessions_count} sessions"
                        row.append(
                            InlineKeyboardButton(
                                text=btn_text,
                                callback_data=f"manage_country_{country.get('code', '')}"
                            )
                        )
                keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_countries")])
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    def get_countries_by_continent(self) -> Dict[str, List[Dict]]:
        """Get countries organized by continent"""
        continent_mapping = {
            'Africa': ['DZ', 'AO', 'BJ', 'BW', 'BF', 'BI', 'CV', 'CM', 'CF', 'TD', 'KM', 'CG', 'CD', 'DJ', 'EG', 'GQ', 'ER', 'SZ', 'ET', 'GA', 'GM', 'GH', 'GN', 'GW', 'CI', 'KE', 'LS', 'LR', 'LY', 'MG', 'MW', 'ML', 'MR', 'MU', 'MA', 'MZ', 'NA', 'NE', 'NG', 'RW', 'ST', 'SN', 'SC', 'SL', 'SO', 'ZA', 'SS', 'SD', 'TZ', 'TG', 'TN', 'UG', 'ZM', 'ZW'],
            'Asia': ['AF', 'AM', 'AZ', 'BH', 'BD', 'BT', 'BN', 'KH', 'CN', 'CY', 'GE', 'IN', 'ID', 'IR', 'IQ', 'IL', 'JP', 'JO', 'KZ', 'KW', 'KG', 'LA', 'LB', 'MY', 'MV', 'MN', 'MM', 'NP', 'KP', 'OM', 'PK', 'PS', 'PH', 'QA', 'SA', 'SG', 'KR', 'LK', 'SY', 'TW', 'TJ', 'TH', 'TL', 'TR', 'TM', 'AE', 'UZ', 'VN', 'YE'],
            'Europe': ['AL', 'AD', 'AT', 'BY', 'BE', 'BA', 'BG', 'HR', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU', 'IS', 'IE', 'IT', 'LV', 'LI', 'LT', 'LU', 'MT', 'MD', 'MC', 'ME', 'NL', 'MK', 'NO', 'PL', 'PT', 'RO', 'RU', 'SM', 'RS', 'SK', 'SI', 'ES', 'SE', 'CH', 'UA', 'GB', 'VA'],
            'North America': ['AG', 'BS', 'BB', 'BZ', 'CA', 'CR', 'CU', 'DM', 'DO', 'SV', 'GD', 'GT', 'HT', 'HN', 'JM', 'MX', 'NI', 'PA', 'KN', 'LC', 'VC', 'TT', 'US'],
            'Oceania': ['AU', 'FJ', 'KI', 'MH', 'FM', 'NR', 'NZ', 'PW', 'PG', 'WS', 'SB', 'TO', 'TV', 'VU'],
            'South America': ['AR', 'BO', 'BR', 'CL', 'CO', 'EC', 'GY', 'PY', 'PE', 'SR', 'UY', 'VE']
        }
        
        # Get all countries from defaultdata module
        from database.defaultdata import DefaultDataInitializer
        initializer = DefaultDataInitializer(self.database.db_path)
        all_countries_data = initializer.get_default_countries()
        country_dict = {c['country_code']: c for c in all_countries_data}
        
        result = {}
        for continent, codes in continent_mapping.items():
            result[continent] = [country_dict[code] for code in codes if code in country_dict]
        
        return result
    
    async def show_add_countries_menu(self, callback_query: types.CallbackQuery):
        """Show continents for adding countries"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        keyboard = [
            [
                InlineKeyboardButton(text="🌍 Africa", callback_data="continent_Africa"),
                InlineKeyboardButton(text="🌏 Asia", callback_data="continent_Asia")
            ],
            [
                InlineKeyboardButton(text="🌍 Europe", callback_data="continent_Europe"),
                InlineKeyboardButton(text="🌎 North America", callback_data="continent_North America")
            ],
            [
                InlineKeyboardButton(text="🌏 Oceania", callback_data="continent_Oceania"),
                InlineKeyboardButton(text="🌎 South America", callback_data="continent_South America")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin_countries")
            ]
        ]
        
        text = (
            "➕ **Add Countries**\n\n"
            "Select a continent to view available countries:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def show_continent_countries(self, callback_query: types.CallbackQuery):
        """Show countries for a specific continent"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        # Handle both continent_ and continent_countries: formats
        if callback_query.data.startswith('continent_countries:'):
            continent = callback_query.data.replace('continent_countries:', '')
        else:
            continent = callback_query.data.replace('continent_', '')
        
        continent_countries = self.get_countries_by_continent()
        
        if continent not in continent_countries:
            await callback_query.answer("Continent not found", show_alert=True)
            return
        
        countries = continent_countries[continent]
        existing_countries = self.database.get_countries()
        existing_codes = {c.get('country_code') for c in existing_countries}
        
        # Filter out already added countries
        available_countries = [c for c in countries if c['country_code'] not in existing_codes]
        
        if not available_countries:
            text = f"🌍 **{continent}**\n\nAll countries from this continent are already added."
            keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="add_countries")]]
        else:
            text = f"🌍 **{continent}**\n\nSelect a country to add:\n\n"
            keyboard = []
            
            # Add country buttons (2 per row)
            for i in range(0, len(available_countries), 2):
                row = []
                for j in range(2):
                    if i + j < len(available_countries):
                        country = available_countries[i + j]
                        btn_text = f"{country['country_name']} ({country['country_code']})"
                        row.append(
                            InlineKeyboardButton(
                                text=btn_text,
                                callback_data=f"add_country_{country['country_code']}"
                            )
                        )
                keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="add_countries")])
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def add_country_from_continent(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Add a specific country from continent selection"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        country_code = callback_query.data.replace('add_country_', '')
        
        # Get country data from defaults
        # Get country data from defaultdata module
        from database.defaultdata import DefaultDataInitializer
        initializer = DefaultDataInitializer(self.database.db_path)
        all_countries_data = initializer.get_default_countries_data()
        country_data = next((c for c in all_countries_data if c[0] == country_code), None)
        
        if not country_data:
            await callback_query.answer("Country not found", show_alert=True)
            return
        
        # Check if country already exists
        existing_countries = self.database.get_countries()
        if any(c.get('code') == country_code for c in existing_countries):
            await callback_query.answer("Country already exists", show_alert=True)
            return
        
        text = (
            f"➕ **Add Country: {country_data['name']} ({country_code})**\n\n"
            f"**Default Settings:**\n"
            f"• Price: ${country_data['price']:.2f}\n"
            f"• Target Quantity: {country_data['target_quantity']}\n"
            f"• Status: {'Available' if country_data['is_active'] else 'Unavailable'}\n\n"
            "Enter new settings in format:\n"
            "```\n"
            "Price: 1.50\n"
            "Target: 50\n"
            "Available: true\n"
            "```\n\n"
            "Leave empty to use default values or press Add to use defaults."
        )
        
        keyboard = [
            [
                InlineKeyboardButton(text="✅ Add with Defaults", callback_data=f"confirm_add_{country_code}"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="add_countries")
            ]
        ]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(CountryStates.waiting_country_data)
        await state.update_data(country_code=country_code, country_data=country_data)
    
    async def confirm_add_country(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Confirm adding country with default settings"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        country_code = callback_query.data.replace('confirm_add_', '')
        
        # Get country data from defaults
        # Get country data from defaultdata module
        from database.defaultdata import DefaultDataInitializer
        initializer = DefaultDataInitializer(self.database.db_path)
        all_countries_data = initializer.get_default_countries_data()
        country_data = next((c for c in all_countries_data if c[0] == country_code), None)
        
        if not country_data:
            await callback_query.answer("Country not found", show_alert=True)
            return
        
        # Add country to database
        success = self.database.add_country(
            country_data['code'],
            country_data['name'],
            country_data['price'],
            country_data['target_quantity'],
            country_data.get('dialing_code')
        )
        
        if success:
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("country_added_success", user_language), show_alert=True)
            logger.info(f"Admin {callback_query.from_user.id} added country: {country_data['name']} ({country_code})")
            
            # Return to add countries menu
            await self.show_add_countries_menu(callback_query)
        else:
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("error_occurred", user_language), show_alert=True)
        
        await state.clear()
    
    async def manage_country(self, callback_query: types.CallbackQuery):
        """Show management options for a specific country"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        country_code = callback_query.data.split('_')[-1]
        countries = self.database.get_countries()
        country = next((c for c in countries if c.get('code') == country_code), None)
        
        if not country:
            await callback_query.answer("Country not found", show_alert=True)
            return
        
        sessions_count = self.database.get_country_session_count(country_code)
        status = "🟢 Available" if country.get('is_active', False) else "🔴 Unavailable"
        
        keyboard = [
            [
                InlineKeyboardButton(text="✏️ Quick Edit", callback_data=f"quick_edit_{country_code}")
            ],
            [
                InlineKeyboardButton(text="💰 Edit Price", callback_data=f"edit_price_{country_code}"),
                InlineKeyboardButton(text="📦 Edit Quantity", callback_data=f"edit_quantity_{country_code}")
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Toggle Status", 
                    callback_data=f"toggle_country_{country_code}"
                ),
                InlineKeyboardButton(text="🗑️ Delete", callback_data=f"delete_country_{country_code}")
            ],
            [
                InlineKeyboardButton(text="🔙 Back to Available Countries", callback_data="available_countries")
            ]
        ]
        
        text = (
            f"🏳️ **Managing: {country.get('name', 'Unknown')} ({country_code})**\n\n"
            f"📊 **Current Settings:**\n"
            f"• Status: {status}\n"
            f"• Price: ${country.get('price', 0):.2f}\n"
            f"• Target Quantity: {country.get('target_quantity', 0)}\n"
            f"• Current Sessions: {sessions_count}\n\n"
            "Select an action:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def view_all_countries(self, callback_query: types.CallbackQuery):
        """Display all countries with their details"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        countries = self.database.get_countries()
        
        if not countries:
            text = "📭 **No Countries Found**\n\nNo countries are currently configured."
        else:
            text = "🌍 **All Countries**\n\n"
            
            for country in countries:
                status = "✅ Active" if country.get('is_active', False) else "❌ Inactive"
                price = country.get('price', 0)
                target = country.get('target_quantity', 0)
                
                # Get session count for this country
                sessions_count = self.database.get_country_session_count(country.get('code', ''))
                
                text += (
                    f"🏳️ **{country.get('name', 'Unknown')} ({country.get('code', 'XX')})**\n"
                    f"• Status: {status}\n"
                    f"• Price: ${price:.2f}\n"
                    f"• Target: {target} sessions\n"
                    f"• Current Sessions: {sessions_count}\n\n"
                )
        
        keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="admin_countries")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def add_country_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for new country data"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        text = (
            "➕ **Add New Country**\n\n"
            "Please provide country information in the following format:\n\n"
            "```\n"
            "Code: US\n"
            "Name: United States\n"
            "Price: 2.50\n"
            "Target: 100\n"
            "```\n\n"
            "• **Code**: 2-letter country code\n"
            "• **Name**: Full country name\n"
            "• **Price**: Price per session in USD\n"
            "• **Target**: Target number of sessions"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="admin_countries")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(CountryStates.waiting_country_data)
    
    async def process_add_country(self, message: types.Message, state: FSMContext):
        """Process new country data"""
        if not self.is_admin(message.from_user.id):
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("access_denied", user_language))
            return
        
        try:
            # Parse country data
            lines = message.text.strip().split('\n')
            country_data = {}
            
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().lower()
                    value = value.strip()
                    
                    if key == 'code':
                        country_data['code'] = value.upper()
                    elif key == 'name':
                        country_data['name'] = value
                    elif key == 'price':
                        country_data['price'] = float(value)
                    elif key == 'target':
                        country_data['target_quantity'] = int(value)
            
            # Validate required fields
            required_fields = ['code', 'name', 'price', 'target_quantity']
            missing_fields = [field for field in required_fields if field not in country_data]
            
            if missing_fields:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                return
            
            # Check if country already exists
            existing_countries = self.database.get_countries()
            if any(c.get('code') == country_data['code'] for c in existing_countries):
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                return
            
            # Add country to database
            country_data['is_active'] = False
            success = self.database.add_country(
                country_data['code'],
                country_data['name'],
                country_data['price'],
                country_data['target_quantity']
            )
            
            if success:
                await message.reply(
                    f"✅ **Country Added Successfully**\n\n"
                    f"🏳️ **{country_data['name']} ({country_data['code']})**\n"
                    f"• Price: ${country_data['price']:.2f}\n"
                    f"• Target: {country_data['target_quantity']} sessions\n"
                    f"• Status: Active",
                    parse_mode="Markdown"
                )
                
                # Log the action
                logger.info(f"Admin {message.from_user.id} added country: {country_data}")
                
            else:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
        
        except ValueError as e:
            await message.reply(f"❌ Invalid data format: {str(e)}\nPlease check price and target values.")
        except Exception as e:
            logger.error(f"Error adding country: {e}")
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("error", user_language))
        
        await state.clear()
    
    async def select_edit_country(self, callback_query: types.CallbackQuery):
        """Show countries selection for editing"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        countries = self.database.get_countries()
        
        if not countries:
            await callback_query.answer("No countries available to edit", show_alert=True)
            return
        
        keyboard = []
        for country in countries:
            status_icon = "✅" if country.get('is_active', False) else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status_icon} {country.get('name', 'Unknown')} ({country.get('code', 'XX')})",
                    callback_data=f"edit_country_{country.get('code', '')}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_countries")])
        
        text = "✏️ **Select Country to Edit**\n\nChoose a country to modify its details:"
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def edit_country_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for editing country data"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        country_code = callback_query.data.split('_')[-1]
        countries = self.database.get_countries()
        country = next((c for c in countries if c.get('code') == country_code), None)
        
        if not country:
            await callback_query.answer("Country not found", show_alert=True)
            return
        
        text = (
            f"✏️ **Edit Country: {country.get('name')} ({country.get('code')})**\n\n"
            f"**Current Details:**\n"
            f"• Name: {country.get('name')}\n"
            f"• Price: ${country.get('price', 0):.2f}\n"
            f"• Target: {country.get('target_quantity', 0)} sessions\n"
            f"• Status: {'Active' if country.get('is_active', False) else 'Inactive'}\n\n"
            "Provide new information in the format:\n\n"
            "```\n"
            "Name: New Country Name\n"
            "Price: 3.00\n"
            "Target: 150\n"
            "```\n\n"
            "Leave a field empty to keep current value."
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data="admin_countries")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(CountryStates.waiting_edit_country)
        await state.update_data(country_code=country_code)
    
    async def process_edit_country(self, message: types.Message, state: FSMContext):
        """Process country edit data"""
        if not self.is_admin(message.from_user.id):
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("access_denied", user_language))
            return
        
        try:
            data = await state.get_data()
            country_code = data.get('country_code')
            
            if not country_code:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                await state.clear()
                return
            
            # Get current country data
            countries = self.database.get_countries()
            country = next((c for c in countries if c.get('code') == country_code), None)
            
            if not country:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                await state.clear()
                return
            
            # Parse edit data
            lines = message.text.strip().split('\n')
            updates = {}
            
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().lower()
                    value = value.strip()
                    
                    if value:  # Only update if value is provided
                        if key == 'name':
                            updates['name'] = value
                        elif key == 'price':
                            updates['price'] = float(value)
                        elif key == 'target':
                            updates['target_quantity'] = int(value)
            
            if not updates:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                await state.clear()
                return
            
            # Update country
            success = self.database.update_country(country_code, **updates)
            
            if success:
                # Get updated country data
                updated_countries = self.database.get_countries()
                updated_country = next((c for c in updated_countries if c.get('code') == country_code), None)
                
                await message.reply(
                    f"✅ **Country Updated Successfully**\n\n"
                    f"🏳️ **{updated_country.get('name')} ({updated_country.get('code')})**\n"
                    f"• Price: ${updated_country.get('price', 0):.2f}\n"
                    f"• Target: {updated_country.get('target_quantity', 0)} sessions\n"
                    f"• Status: {'Active' if updated_country.get('is_active', False) else 'Inactive'}",
                    parse_mode="Markdown"
                )
                
                # Log the action
                logger.info(f"Admin {message.from_user.id} updated country {country_code}: {updates}")
                
            else:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
        
        except ValueError as e:
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("error", user_language))
        except Exception as e:
            logger.error(f"Error updating country: {e}")
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("error", user_language))
        
        await state.clear()
    
    async def select_toggle_country(self, callback_query: types.CallbackQuery):
        """Show countries selection for toggling status"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        countries = self.database.get_countries()
        
        if not countries:
            await callback_query.answer("No countries available", show_alert=True)
            return
        
        keyboard = []
        for country in countries:
            status_icon = "✅" if country.get('is_active', False) else "❌"
            action = "Deactivate" if country.get('is_active', False) else "Activate"
            
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status_icon} {country.get('name', 'Unknown')} - {action}",
                    callback_data=f"toggle_country_{country.get('code', '')}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_countries")])
        
        text = "🔄 **Toggle Country Status**\n\nSelect a country to activate/deactivate:"
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def toggle_country_status(self, callback_query: types.CallbackQuery):
        """Toggle country active/inactive status"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        country_code = callback_query.data.split('_')[-1]
        
        try:
            success = self.database.toggle_country_status(country_code)
            
            if success:
                # Get updated country data
                countries = self.database.get_countries()
                country = next((c for c in countries if c.get('code') == country_code), None)
                
                if country:
                    status = "activated" if country.get('is_active', False) else "deactivated"
                    await callback_query.answer(f"✅ Country {status} successfully", show_alert=True)
                    
                    # Log the action
                    logger.info(f"Admin {callback_query.from_user.id} {status} country {country_code}")
                    
                    # Refresh the toggle menu
                    await self.select_toggle_country(callback_query)
                else:
                    user_language = self.get_user_language(callback_query.from_user.id)
                    await callback_query.answer(get_text("error", user_language), show_alert=True)
            else:
                user_language = self.get_user_language(callback_query.from_user.id)
                await callback_query.answer(get_text("error", user_language), show_alert=True)
        
        except Exception as e:
            logger.error(f"Error toggling country status: {e}")
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("error", user_language), show_alert=True)
    
    async def select_delete_country(self, callback_query: types.CallbackQuery):
        """Show countries selection for deletion"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        countries = self.database.get_countries()
        
        if not countries:
            await callback_query.answer("No countries available to delete", show_alert=True)
            return
        
        keyboard = []
        for country in countries:
            sessions_count = self.database.get_country_session_count(country.get('code', ''))
            warning = " ⚠️" if sessions_count > 0 else ""
            
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{country.get('name', 'Unknown')} ({sessions_count} sessions){warning}",
                    callback_data=f"delete_country_{country.get('code', '')}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_countries")])
        
        text = (
            "🗑️ **Delete Country**\n\n"
            "⚠️ **WARNING**: Deleting a country will:\n"
            "• Remove it from the database\n"
            "• Affect any existing sessions\n"
            "• Cannot be undone\n\n"
            "Countries with sessions are marked with ⚠️"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def confirm_delete_country(self, callback_query: types.CallbackQuery):
        """Confirm country deletion"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        country_code = callback_query.data.split('_')[-1]
        countries = self.database.get_countries()
        country = next((c for c in countries if c.get('code') == country_code), None)
        
        if not country:
            await callback_query.answer("Country not found", show_alert=True)
            return
        
        sessions_count = self.database.get_country_session_count(country_code)
        
        keyboard = [
            [
                InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"confirm_delete_{country_code}"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="admin_countries")
            ]
        ]
        
        text = (
            f"🗑️ **Confirm Deletion**\n\n"
            f"Are you sure you want to delete:\n"
            f"**{country.get('name')} ({country_code})**\n\n"
            f"📊 **Impact:**\n"
            f"• Sessions affected: {sessions_count}\n"
            f"• This action cannot be undone\n\n"
            "⚠️ **Proceed with caution!**"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def delete_country(self, callback_query: types.CallbackQuery):
        """Delete country from database"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        country_code = callback_query.data.split('_')[-1]
        
        try:
            success = self.database.delete_country(country_code)
            
            if success:
                await callback_query.answer("✅ Country deleted successfully", show_alert=True)
                
                # Log the action
                logger.info(f"Admin {callback_query.from_user.id} deleted country {country_code}")
                
                # Return to countries menu
                await self.show_countries_menu(callback_query)
            else:
                user_language = self.get_user_language(callback_query.from_user.id)
                await callback_query.answer(get_text("error", user_language), show_alert=True)
        
        except Exception as e:
            logger.error(f"Error deleting country: {e}")
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("error", user_language), show_alert=True)
    
    async def quick_edit_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for quick editing both price and quantity"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        country_code = callback_query.data.split('_')[-1]
        countries = self.database.get_countries()
        country = next((c for c in countries if c.get('code') == country_code), None)
        
        if not country:
            await callback_query.answer("Country not found", show_alert=True)
            return
        
        text = (
            f"⚡ **Quick Edit: {country.get('name', 'Unknown')} ({country_code})**\n\n"
            f"**Current Settings:**\n"
            f"• Price: ${country.get('price', 0):.2f}\n"
            f"• Target Quantity: {country.get('target_quantity', 0)}\n\n"
            "**Enter new values in format:** `price quantity`\n\n"
            "**Examples:**\n"
            "• `1 100` - Price: $1.00, Quantity: 100 (available)\n"
            "• `1.50 50` - Price: $1.50, Quantity: 50 (available)\n"
            "• `2 0` - Price: $2.00, Quantity: 0 (unavailable)\n\n"
            "**Note:** Setting quantity to 0 makes the country unavailable."
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data=f"manage_country_{country_code}")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(CountryStates.waiting_quick_edit)
        await state.update_data(country_code=country_code)
    
    async def process_quick_edit(self, message: types.Message, state: FSMContext):
        """Process quick edit for both price and quantity"""
        if not self.is_admin(message.from_user.id):
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("access_denied", user_language))
            return
        
        try:
            # Parse input
            parts = message.text.strip().split()
            if len(parts) != 2:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                return
            
            new_price = float(parts[0])
            new_quantity = int(parts[1])
            
            if new_price < 0:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                return
            
            if new_quantity < 0:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                return
            
            # Get country code from state
            data = await state.get_data()
            country_code = data.get('country_code')
            
            if not country_code:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                await state.clear()
                return
            
            # Get current country data for comparison
            countries = self.database.get_countries()
            country = next((c for c in countries if c.get('code') == country_code), None)
            
            if not country:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                await state.clear()
                return
            
            # Update country with new values
            update_params = {
                'price': new_price,
                'target_quantity': new_quantity
            }
            
            success = self.database.update_country(country_code, **update_params)
            
            if success:
                # Determine availability based on quantity (0 = unavailable)
                availability_status = "Available" if new_quantity > 0 else "Unavailable"
                
                # If quantity is 0, also update availability status
                if new_quantity == 0:
                    self.database.update_country(country_code, is_active=False)
                elif country.get('is_active', False) == False and new_quantity > 0:
                    # If quantity > 0 and country was unavailable, make it available
                    self.database.update_country(country_code, is_active=True)
                
                await message.reply(
                    f"✅ **{country.get('name', 'Unknown')} Updated Successfully**\n\n"
                    f"🏳️ **{country.get('name', 'Unknown')} ({country_code})**\n"
                    f"• Price: ${new_price:.2f}\n"
                    f"• Target Quantity: {new_quantity}\n"
                    f"• Status: {availability_status}",
                    parse_mode="Markdown"
                )
                
                logger.info(f"Admin {message.from_user.id} quick edited {country_code}: price={new_price}, quantity={new_quantity}")
                
            else:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                
        except ValueError as e:
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("error", user_language))
        except Exception as e:
            logger.error(f"Error in quick edit: {e}")
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("error", user_language))
        
        await state.clear()

    async def edit_price_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for editing country price"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        country_code = callback_query.data.split('_')[-1]
        countries = self.database.get_countries()
        country = next((c for c in countries if c.get('code') == country_code), None)
        
        if not country:
            await callback_query.answer("Country not found", show_alert=True)
            return
        
        text = (
            f"💰 **Edit Price for {country.get('name', 'Unknown')} ({country_code})**\n\n"
            f"Current price: ${country.get('price', 0):.2f}\n\n"
            "Enter the new price (e.g., 1.50):"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data=f"manage_country_{country_code}")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(CountryStates.waiting_edit_price)
        await state.update_data(country_code=country_code)
    
    async def process_edit_price(self, message: types.Message, state: FSMContext):
        """Process new price for country"""
        if not self.is_admin(message.from_user.id):
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("access_denied", user_language))
            return
        
        try:
            new_price = float(message.text.strip())
            if new_price < 0:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                return
            
            data = await state.get_data()
            country_code = data.get('country_code')
            
            success = self.database.update_country(country_code, price=new_price)
            
            if success:
                await message.reply(
                    f"✅ Price updated successfully to ${new_price:.2f}",
                    parse_mode="Markdown"
                )
                logger.info(f"Admin {message.from_user.id} updated price for {country_code} to {new_price}")
            else:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                
        except ValueError:
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("error", user_language))
        except Exception as e:
            logger.error(f"Error updating price: {e}")
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("error", user_language))
        
        await state.clear()
    
    async def edit_quantity_prompt(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Prompt for editing country target quantity"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        country_code = callback_query.data.split('_')[-1]
        countries = self.database.get_countries()
        country = next((c for c in countries if c.get('code') == country_code), None)
        
        if not country:
            await callback_query.answer("Country not found", show_alert=True)
            return
        
        text = (
            f"📦 **Edit Target Quantity for {country.get('name', 'Unknown')} ({country_code})**\n\n"
            f"Current target: {country.get('target_quantity', 0)}\n\n"
            "Enter the new target quantity:"
        )
        
        keyboard = [[InlineKeyboardButton(text="❌ Cancel", callback_data=f"manage_country_{country_code}")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(CountryStates.waiting_edit_quantity)
        await state.update_data(country_code=country_code)
    
    async def process_edit_quantity(self, message: types.Message, state: FSMContext):
        """Process new target quantity for country"""
        if not self.is_admin(message.from_user.id):
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("access_denied", user_language))
            return
        
        try:
            new_quantity = int(message.text.strip())
            if new_quantity < 0:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                return
            
            data = await state.get_data()
            country_code = data.get('country_code')
            
            success = self.database.update_country(country_code, target_quantity=new_quantity)
            
            if success:
                await message.reply(
                    f"✅ Target quantity updated successfully to {new_quantity}",
                    parse_mode="Markdown"
                )
                logger.info(f"Admin {message.from_user.id} updated quantity for {country_code} to {new_quantity}")
            else:
                user_language = self.get_user_language(message.from_user.id)
                await message.reply(get_text("error", user_language))
                
        except ValueError:
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("error", user_language))
        except Exception as e:
            logger.error(f"Error updating quantity: {e}")
            user_language = self.get_user_language(message.from_user.id)
            await message.reply(get_text("error", user_language))
        
        await state.clear()
    
    async def show_country_statistics(self, callback_query: types.CallbackQuery):
        """Show detailed country statistics"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        countries = self.database.get_countries()
        
        if not countries:
            text = "📭 **No Countries Found**\n\nNo countries are currently configured."
        else:
            text = "📈 **Country Statistics**\n\n"
            
            total_sessions = 0
            total_revenue = 0
            
            for country in countries:
                code = country.get('code', 'XX')
                sessions_count = self.database.get_country_session_count(code)
                price = country.get('price', 0)
                target = country.get('target_quantity', 0)
                revenue = sessions_count * price
                
                total_sessions += sessions_count
                total_revenue += revenue
                
                progress = (sessions_count / target * 100) if target > 0 else 0
                status = "✅" if country.get('is_active', False) else "❌"
                
                text += (
                    f"{status} **{country.get('name', 'Unknown')} ({code})**\n"
                    f"• Sessions: {sessions_count}/{target} ({progress:.1f}%)\n"
                    f"• Revenue: ${revenue:.2f}\n"
                    f"• Price: ${price:.2f}\n\n"
                )
            
            text += (
                f"📊 **Overall Totals:**\n"
                f"• Total Sessions: {total_sessions}\n"
                f"• Total Revenue: ${total_revenue:.2f}\n"
                f"• Active Countries: {sum(1 for c in countries if c.get('is_active', False))}\n"
                f"• Total Countries: {len(countries)}"
            )
        
        keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="admin_countries")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def show_edit_countries_main(self, callback_query: types.CallbackQuery):
        """Show main edit countries menu with available/unavailable options"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        keyboard = [
            [
                InlineKeyboardButton(text="✅ Available Countries", callback_data="edit_available_countries"),
                InlineKeyboardButton(text="❌ Unavailable Countries", callback_data="edit_unavailable_countries")
            ],
            [
                InlineKeyboardButton(text="🔙 Back", callback_data="admin_countries")
            ]
        ]
        
        text = (
            "✏️ **Edit Countries**\n\n"
            "Choose which countries to manage:\n\n"
            "• **Available Countries**: Countries currently active and available for users\n"
            "• **Unavailable Countries**: Countries currently inactive\n\n"
            "Select an option:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def show_edit_available_countries(self, callback_query: types.CallbackQuery):
        """Show available countries for editing, grouped by continent if > 20."""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        countries = self.database.get_countries(active_only=False)  # Get all countries from DB
        available_countries = [c for c in countries if c.get('is_active', False)]
        
        if not available_countries:
            text = "📭 **No Available Countries**\n\nNo countries are currently available for editing."
            keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="edit_countries_main")]]
        elif len(available_countries) <= 20:
            text = "✅ **Available Countries**\n\nSelect a country to edit:\n\n"
            keyboard = []
            
            for i in range(0, len(available_countries), 2):
                row = []
                for j in range(2):
                    if i + j < len(available_countries):
                        country = available_countries[i + j]
                        sessions_count = self.database.get_country_session_count(country.get('country_code', ''))
                        btn_text = f"{country.get('country_name', 'Unknown')} ({sessions_count})"
                        row.append(
                            InlineKeyboardButton(
                                text=btn_text,
                                callback_data=f"quick_edit_country_{country.get('country_code', '')}"
                            )
                        )
                keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="edit_countries_main")])
        else:
            return await self.show_continents_for_edit(callback_query, available_only=True)
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def show_edit_unavailable_countries(self, callback_query: types.CallbackQuery):
        """Show unavailable countries for editing, grouped by continent if > 20."""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        countries = self.database.get_countries(active_only=False)  # Get all countries from DB
        unavailable_countries = [c for c in countries if not c.get('is_active', False)]
        
        if not unavailable_countries:
            text = "📭 **No Unavailable Countries**\n\nAll countries are currently available."
            keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="edit_countries_main")]]
        elif len(unavailable_countries) <= 20:
            text = "❌ **Unavailable Countries**\n\nSelect a country to edit:\n\n"
            keyboard = []
            
            for i in range(0, len(unavailable_countries), 2):
                row = []
                for j in range(2):
                    if i + j < len(unavailable_countries):
                        country = unavailable_countries[i + j]
                        btn_text = f"{country.get('country_name', 'Unknown')}"
                        row.append(
                            InlineKeyboardButton(
                                text=btn_text,
                                callback_data=f"quick_edit_country_{country.get('country_code', '')}"
                            )
                        )
                keyboard.append(row)
            
            keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="edit_countries_main")])
        else:
            return await self.show_continents_for_edit(callback_query, available_only=False)
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def show_continents_for_edit(self, callback_query: types.CallbackQuery, available_only: bool):
        """Show continents when there are too many countries for direct display."""
        try:
            continent_countries = self.get_countries_by_continent()
            
            keyboard = []
            for continent, countries_list in continent_countries.items():
                filtered_countries = []
                for country_data in countries_list:
                    try:
                        # Safely get country information with fallback
                        current_country_info = self.get_country_info_safe(country_data['country_code'])
                        
                        if current_country_info:
                            is_active = current_country_info.get('is_active', False)
                            if (available_only and is_active) or (not available_only and not is_active):
                                filtered_countries.append(current_country_info)
                                
                    except Exception as e:
                        logger.error(f"Error processing country {country_data.get('country_code', 'unknown')}: {e}")
                        continue
                
                if filtered_countries:
                    continent_emoji = get_continent_emoji(continent)  # Use the helper function
                    
                    callback_data = f"edit_continent_{continent.replace(' ', '_')}_{'available' if available_only else 'unavailable'}"
                    keyboard.append([InlineKeyboardButton(
                        text=f"{continent_emoji} {continent} ({len(filtered_countries)})",
                        callback_data=callback_data
                    )])
            
            keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="edit_countries_main")])
            
            status_text = "Available" if available_only else "Unavailable"
            text = (
                f"{'✅' if available_only else '❌'} **{status_text} Countries by Continent**\n\n"
                f"Too many {status_text.lower()} countries to display. Select a continent:\n\n"
            )
            
            await callback_query.message.edit_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"Error in show_continents_for_edit: {e}")
            await callback_query.answer("❌ Error loading countries. Please try again.", show_alert=True)

    def get_country_info_safe(self, country_code: str) -> Dict:
        """Safely get country information with fallback"""
        try:
            # First try the database method if it exists
            if hasattr(self.database, 'get_country_by_code'):
                country_info = self.database.get_country_by_code(country_code)
                if country_info:
                    return country_info
            
            # Fallback to searching all countries
            countries = self.database.get_countries(active_only=False)
            country_info = next(
                (c for c in countries if c.get('country_code') == country_code), 
                None
            )
            
            if country_info:
                return country_info
            
            # If still not found, log warning and return minimal info
            logger.warning(f"Country {country_code} not found in database")
            return {
                'country_code': country_code,
                'country_name': 'Unknown',
                'price': 0.0,
                'target_quantity': 0,
                'is_active': False
            }
        
        except Exception as e:
            logger.error(f"Error getting country info for {country_code}: {e}")
            return {
                'country_code': country_code,
                'country_name': 'Unknown',
                'price': 0.0,
                'target_quantity': 0,
                'is_active': False
            }
    
    async def show_continent_countries_for_edit(self, callback_query: types.CallbackQuery):
        """Show countries in a continent for editing based on availability."""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        data_parts = callback_query.data.split('_')
        # Handle continent names with underscores (e.g. "North_America", "South_America")
        if len(data_parts) == 4:
            continent = data_parts[2]
            availability = data_parts[3]
        else:
            # For multi-word continents like "North_America"
            continent = ' '.join(data_parts[2:-1])
            availability = data_parts[-1]
        available_only = availability == 'available'
        
        all_db_countries = self.database.get_countries(active_only=False)  # Get all countries from DB
        
        filtered_countries = []
        for country in all_db_countries:  # Iterate through all countries from DB
            country_continent_map = self.get_countries_by_continent()
            continent_for_country = None
            for cont, codes_list in country_continent_map.items():
                if any(c['country_code'] == country['country_code'] for c in codes_list):
                    continent_for_country = cont
                    break
            
            if continent_for_country == continent:  # If country belongs to selected continent
                is_active = country.get('is_active', False)
                if (available_only and is_active) or (not available_only and not is_active):
                    filtered_countries.append(country)
        
        if not filtered_countries:
            status_text = "available" if available_only else "unavailable"
            text = f"📭 **No {status_text.title()} Countries in {continent}**\n\nNo {status_text} countries found in this continent."
            keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="edit_countries_main")]]
        else:
            status_emoji = "✅" if available_only else "❌"
            status_text = "Available" if available_only else "Unavailable"
            text = f"{status_emoji} **{status_text} Countries in {continent}**\n\nSelect a country to edit:\n\n"
            keyboard = []
            
            for i in range(0, len(filtered_countries), 2):
                row = []
                for j in range(2):
                    if i + j < len(filtered_countries):
                        country = filtered_countries[i + j]
                        sessions_count = self.database.get_country_session_count(country.get('country_code', ''))
                        if available_only:
                            btn_text = f"{country.get('country_name', 'Unknown')} ({sessions_count})"
                        else:
                            btn_text = f"{country.get('country_name', 'Unknown')}"
                        row.append(
                            InlineKeyboardButton(
                                text=btn_text,
                                callback_data=f"quick_edit_country_{country.get('country_code', '')}"
                            )
                        )
                keyboard.append(row)
            
            back_callback = f"edit_{'available' if available_only else 'unavailable'}_countries"
            keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data=back_callback)])
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def show_quick_edit_country(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Show country quick edit interface"""
        if not self.is_admin(callback_query.from_user.id):
            user_language = self.get_user_language(callback_query.from_user.id)
            await callback_query.answer(get_text("access_denied", user_language), show_alert=True)
            return
        
        country_code = callback_query.data.replace("quick_edit_country_", "")
        country = self.database.get_country_by_code(country_code)
        
        if not country:
            await callback_query.answer("❌ Country not found!", show_alert=True)
            return
        
        await state.update_data(editing_country_code=country_code)
        
        sessions_count = self.database.get_country_session_count(country_code)
        price = country.get('price', 0)
        target_quantity = country.get('target_quantity', 0)
        is_active = country.get('is_active', False)
        dialing_code = country.get('dialing_code', 'Unknown')
        
        text = (
            f"✏️ **Quick Edit: {country.get('country_name', 'Unknown')}**\n\n"
            f"🏴 **Country Code:** {country_code}\n"
            f"📞 **Dialing Code:** {dialing_code}\n"
            f"💰 **Current Price:** ${price:.2f}\n"
            f"📦 **Current Target Quantity:** {target_quantity}\n"
            f"📊 **Current Sessions:** {sessions_count}\n"
            f"🔄 **Status:** {'✅ Active' if is_active else '❌ Inactive'}\n\n"
            f"**Quick Edit Format:**\n"
            f"Send: `<price> <quantity>`\n\n"
            f"**Examples:**\n"
            f"• `1.5 10` = Price: $1.50, Quantity: 10, Status: Active\n"
            f"• `2.0 0` = Price: $2.00, Quantity: 0, Status: Inactive\n"
            f"• `0.5 25` = Price: $0.50, Quantity: 25, Status: Active\n\n"
            f"*Note: If quantity is 0, country becomes inactive*"
        )
        
        keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="edit_countries_main")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        await state.set_state(CountryStates.waiting_quick_edit_new)
    
    async def process_quick_edit_new(self, message: types.Message, state: FSMContext):
        """Process quick edit input: price quantity format"""
        if not self.is_admin(message.from_user.id):
            await message.reply("❌ Access denied!")
            return
        
        data = await state.get_data()
        country_code = data.get('editing_country_code')
        
        if not country_code:
            await message.reply("❌ No country selected for editing!")
            await state.clear()
            return
        
        try:
            parts = message.text.strip().split()
            if len(parts) != 2:
                await message.reply(
                    "❌ **Invalid format!**\n\n"
                    "Please use: `<price> <quantity>`\n"
                    "Example: `1.5 10`",
                    parse_mode="Markdown"
                )
                return
            
            price = float(parts[0])
            quantity = int(parts[1])
            
            if price < 0:
                await message.reply("❌ Price cannot be negative!")
                return
            
            if quantity < 0:
                await message.reply("❌ Quantity cannot be negative!")
                return
            
            is_active = quantity > 0
            
            success = self.database.update_country(
                country_code, 
                price=price, 
                target_quantity=quantity, 
                is_active=is_active
            )
            
            if success:
                country = self.database.get_country_by_code(country_code)
                status_text = "✅ Active" if is_active else "❌ Inactive"
                
                await message.reply(
                    f"✅ **Country Updated Successfully!**\n\n"
                    f"🏴 **{country.get('country_name', 'Unknown')} ({country_code})**\n"
                    f"💰 **Price:** ${price:.2f}\n"
                    f"📦 **Target Quantity:** {quantity}\n"
                    f"🔄 **Status:** {status_text}\n\n"
                    f"Changes have been saved to the database.",
                    parse_mode="Markdown"
                )
                
                logger.info(f"Admin {message.from_user.id} quick edited {country_code}: price=${price:.2f}, quantity={quantity}, active={is_active}")
            else:
                await message.reply("❌ Failed to update country. Please try again.")
        
        except ValueError:
            await message.reply(
                "❌ **Invalid input!**\n\n"
                "Price must be a number (e.g., 1.5)\n"
                "Quantity must be a whole number (e.g., 10)",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error in quick edit: {e}")
            await message.reply("❌ An error occurred while updating the country.")
        
        await state.clear()

    def register_handlers(self, dp: Dispatcher):
        """Register country management handlers"""
        # Main menu for admin countries
        dp.callback_query.register(
            self.show_countries_menu,
            F.data == "admin_countries"
        )
        
        # Main edit countries menu (new)
        dp.callback_query.register(
            self.show_edit_countries_main,
            F.data == "edit_countries_main"
        )
        
        # Show available countries for editing (can lead to continents)
        dp.callback_query.register(
            self.show_edit_available_countries,
            F.data == "edit_available_countries"
        )
        
        # Show unavailable countries for editing (can lead to continents)
        dp.callback_query.register(
            self.show_edit_unavailable_countries,
            F.data == "edit_unavailable_countries"
        )
        
        # Show countries within a continent for editing
        dp.callback_query.register(
            self.show_continent_countries_for_edit,
            F.data.startswith("edit_continent_")
        )
        
        # Quick edit specific country
        dp.callback_query.register(
            self.show_quick_edit_country,
            F.data.startswith("quick_edit_country_")
        )
        
        # Process input for quick editing (price quantity)
        dp.message.register(
            self.process_quick_edit_new,
            CountryStates.waiting_quick_edit_new
        )
