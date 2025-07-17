#!/usr/bin/env python3
"""
Default Data Initialization Module
Contains all default data for countries, settings, and content.
This module is used to initialize the database with default values.
"""

import sqlite3
import logging
from typing import List, Dict, Tuple

# Use centralized logging
from logging_config import get_logger
logger = get_logger(__name__)

class DefaultDataInitializer:
    """Class to handle all default data initialization"""
    
    def __init__(self, db_path: str = "bot_database_v2.db"):
        self.db_path = db_path
    
    def get_default_countries(self) -> List[Dict]:
        """Get list of ALL world countries with initial settings, using country_code and country_name keys consistently"""
        return [
            # Africa
            {'country_code': 'DZ', 'country_name': 'Algeria', 'dialing_code': '+213', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'AO', 'country_name': 'Angola', 'dialing_code': '+244', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BJ', 'country_name': 'Benin', 'dialing_code': '+229', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BW', 'country_name': 'Botswana', 'dialing_code': '+267', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BF', 'country_name': 'Burkina Faso', 'dialing_code': '+226', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BI', 'country_name': 'Burundi', 'dialing_code': '+257', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'CV', 'country_name': 'Cape Verde', 'dialing_code': '+238', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'CM', 'country_name': 'Cameroon', 'dialing_code': '+237', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'CF', 'country_name': 'Central African Republic', 'dialing_code': '+236', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'TD', 'country_name': 'Chad', 'dialing_code': '+235', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'KM', 'country_name': 'Comoros', 'dialing_code': '+269', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'CG', 'country_name': 'Congo', 'dialing_code': '+242', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'CD', 'country_name': 'Democratic Republic of the Congo', 'dialing_code': '+243', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'DJ', 'country_name': 'Djibouti', 'dialing_code': '+253', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'EG', 'country_name': 'Egypt', 'dialing_code': '+20', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'GQ', 'country_name': 'Equatorial Guinea', 'dialing_code': '+240', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'ER', 'country_name': 'Eritrea', 'dialing_code': '+291', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SZ', 'country_name': 'Eswatini', 'dialing_code': '+268', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'ET', 'country_name': 'Ethiopia', 'dialing_code': '+251', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'GA', 'country_name': 'Gabon', 'dialing_code': '+241', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'GM', 'country_name': 'Gambia', 'dialing_code': '+220', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'GH', 'country_name': 'Ghana', 'dialing_code': '+233', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'GN', 'country_name': 'Guinea', 'dialing_code': '+224', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'GW', 'country_name': 'Guinea-Bissau', 'dialing_code': '+245', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'CI', 'country_name': 'Ivory Coast', 'dialing_code': '+225', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'KE', 'country_name': 'Kenya', 'dialing_code': '+254', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'LS', 'country_name': 'Lesotho', 'dialing_code': '+266', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'LR', 'country_name': 'Liberia', 'dialing_code': '+231', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'LY', 'country_name': 'Libya', 'dialing_code': '+218', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MG', 'country_name': 'Madagascar', 'dialing_code': '+261', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MW', 'country_name': 'Malawi', 'dialing_code': '+265', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'ML', 'country_name': 'Mali', 'dialing_code': '+223', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MR', 'country_name': 'Mauritania', 'dialing_code': '+222', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MU', 'country_name': 'Mauritius', 'dialing_code': '+230', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MA', 'country_name': 'Morocco', 'dialing_code': '+212', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MZ', 'country_name': 'Mozambique', 'dialing_code': '+258', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'NA', 'country_name': 'Namibia', 'dialing_code': '+264', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'NE', 'country_name': 'Niger', 'dialing_code': '+227', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'NG', 'country_name': 'Nigeria', 'dialing_code': '+234', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'RW', 'country_name': 'Rwanda', 'dialing_code': '+250', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'ST', 'country_name': 'Sao Tome and Principe', 'dialing_code': '+239', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SN', 'country_name': 'Senegal', 'dialing_code': '+221', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SC', 'country_name': 'Seychelles', 'dialing_code': '+248', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SL', 'country_name': 'Sierra Leone', 'dialing_code': '+232', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SO', 'country_name': 'Somalia', 'dialing_code': '+252', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'ZA', 'country_name': 'South Africa', 'dialing_code': '+27', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SS', 'country_name': 'South Sudan', 'dialing_code': '+211', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SD', 'country_name': 'Sudan', 'dialing_code': '+249', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'TZ', 'country_name': 'Tanzania', 'dialing_code': '+255', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'TG', 'country_name': 'Togo', 'dialing_code': '+228', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'TN', 'country_name': 'Tunisia', 'dialing_code': '+216', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'UG', 'country_name': 'Uganda', 'dialing_code': '+256', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'ZM', 'country_name': 'Zambia', 'dialing_code': '+260', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'ZW', 'country_name': 'Zimbabwe', 'dialing_code': '+263', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            
            # Asia
            {'country_code': 'AF', 'country_name': 'Afghanistan', 'dialing_code': '+93', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'AM', 'country_name': 'Armenia', 'dialing_code': '+374', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'AZ', 'country_name': 'Azerbaijan', 'dialing_code': '+994', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BH', 'country_name': 'Bahrain', 'dialing_code': '+973', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BD', 'country_name': 'Bangladesh', 'dialing_code': '+880', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BT', 'country_name': 'Bhutan', 'dialing_code': '+975', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BN', 'country_name': 'Brunei', 'dialing_code': '+673', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'KH', 'country_name': 'Cambodia', 'dialing_code': '+855', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'CN', 'country_name': 'China', 'dialing_code': '+86', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'CY', 'country_name': 'Cyprus', 'dialing_code': '+357', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'GE', 'country_name': 'Georgia', 'dialing_code': '+995', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'IN', 'country_name': 'India', 'dialing_code': '+91', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'ID', 'country_name': 'Indonesia', 'dialing_code': '+62', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'IR', 'country_name': 'Iran', 'dialing_code': '+98', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'IQ', 'country_name': 'Iraq', 'dialing_code': '+964', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'IL', 'country_name': 'Israel', 'dialing_code': '+972', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'JP', 'country_name': 'Japan', 'dialing_code': '+81', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'JO', 'country_name': 'Jordan', 'dialing_code': '+962', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'KZ', 'country_name': 'Kazakhstan', 'dialing_code': '+7', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'KW', 'country_name': 'Kuwait', 'dialing_code': '+965', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'KG', 'country_name': 'Kyrgyzstan', 'dialing_code': '+996', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'LA', 'country_name': 'Laos', 'dialing_code': '+856', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'LB', 'country_name': 'Lebanon', 'dialing_code': '+961', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MY', 'country_name': 'Malaysia', 'dialing_code': '+60', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MV', 'country_name': 'Maldives', 'dialing_code': '+960', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MN', 'country_name': 'Mongolia', 'dialing_code': '+976', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MM', 'country_name': 'Myanmar', 'dialing_code': '+95', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'NP', 'country_name': 'Nepal', 'dialing_code': '+977', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'KP', 'country_name': 'North Korea', 'dialing_code': '+850', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'OM', 'country_name': 'Oman', 'dialing_code': '+968', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'PK', 'country_name': 'Pakistan', 'dialing_code': '+92', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'PS', 'country_name': 'Palestine', 'dialing_code': '+970', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'PH', 'country_name': 'Philippines', 'dialing_code': '+63', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'QA', 'country_name': 'Qatar', 'dialing_code': '+974', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SA', 'country_name': 'Saudi Arabia', 'dialing_code': '+966', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SG', 'country_name': 'Singapore', 'dialing_code': '+65', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'KR', 'country_name': 'South Korea', 'dialing_code': '+82', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'LK', 'country_name': 'Sri Lanka', 'dialing_code': '+94', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SY', 'country_name': 'Syria', 'dialing_code': '+963', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'TW', 'country_name': 'Taiwan', 'dialing_code': '+886', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'TJ', 'country_name': 'Tajikistan', 'dialing_code': '+992', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'TH', 'country_name': 'Thailand', 'dialing_code': '+66', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'TL', 'country_name': 'Timor-Leste', 'dialing_code': '+670', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'TR', 'country_name': 'Turkey', 'dialing_code': '+90', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'TM', 'country_name': 'Turkmenistan', 'dialing_code': '+993', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'AE', 'country_name': 'United Arab Emirates', 'dialing_code': '+971', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'UZ', 'country_name': 'Uzbekistan', 'dialing_code': '+998', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'VN', 'country_name': 'Vietnam', 'dialing_code': '+84', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'YE', 'country_name': 'Yemen', 'dialing_code': '+967', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            
            # Europe
            {'country_code': 'AL', 'country_name': 'Albania', 'dialing_code': '+355', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'AD', 'country_name': 'Andorra', 'dialing_code': '+376', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'AT', 'country_name': 'Austria', 'dialing_code': '+43', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BY', 'country_name': 'Belarus', 'dialing_code': '+375', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BE', 'country_name': 'Belgium', 'dialing_code': '+32', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BA', 'country_name': 'Bosnia and Herzegovina', 'dialing_code': '+387', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BG', 'country_name': 'Bulgaria', 'dialing_code': '+359', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'HR', 'country_name': 'Croatia', 'dialing_code': '+385', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'CZ', 'country_name': 'Czech Republic', 'dialing_code': '+420', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'DK', 'country_name': 'Denmark', 'dialing_code': '+45', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'EE', 'country_name': 'Estonia', 'dialing_code': '+372', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'FI', 'country_name': 'Finland', 'dialing_code': '+358', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'FR', 'country_name': 'France', 'dialing_code': '+33', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'DE', 'country_name': 'Germany', 'dialing_code': '+49', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'GR', 'country_name': 'Greece', 'dialing_code': '+30', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'HU', 'country_name': 'Hungary', 'dialing_code': '+36', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'IS', 'country_name': 'Iceland', 'dialing_code': '+354', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'IE', 'country_name': 'Ireland', 'dialing_code': '+353', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'IT', 'country_name': 'Italy', 'dialing_code': '+39', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'LV', 'country_name': 'Latvia', 'dialing_code': '+371', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'LI', 'country_name': 'Liechtenstein', 'dialing_code': '+423', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'LT', 'country_name': 'Lithuania', 'dialing_code': '+370', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'LU', 'country_name': 'Luxembourg', 'dialing_code': '+352', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MT', 'country_name': 'Malta', 'dialing_code': '+356', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MD', 'country_name': 'Moldova', 'dialing_code': '+373', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MC', 'country_name': 'Monaco', 'dialing_code': '+377', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'ME', 'country_name': 'Montenegro', 'dialing_code': '+382', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'NL', 'country_name': 'Netherlands', 'dialing_code': '+31', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MK', 'country_name': 'North Macedonia', 'dialing_code': '+389', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'NO', 'country_name': 'Norway', 'dialing_code': '+47', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'PL', 'country_name': 'Poland', 'dialing_code': '+48', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'PT', 'country_name': 'Portugal', 'dialing_code': '+351', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'RO', 'country_name': 'Romania', 'dialing_code': '+40', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'RU', 'country_name': 'Russia', 'dialing_code': '+7', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SM', 'country_name': 'San Marino', 'dialing_code': '+378', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'RS', 'country_name': 'Serbia', 'dialing_code': '+381', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SK', 'country_name': 'Slovakia', 'dialing_code': '+421', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SI', 'country_name': 'Slovenia', 'dialing_code': '+386', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'ES', 'country_name': 'Spain', 'dialing_code': '+34', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SE', 'country_name': 'Sweden', 'dialing_code': '+46', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'CH', 'country_name': 'Switzerland', 'dialing_code': '+41', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'UA', 'country_name': 'Ukraine', 'dialing_code': '+380', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'GB', 'country_name': 'United Kingdom', 'dialing_code': '+44', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'VA', 'country_name': 'Vatican City', 'dialing_code': '+39', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            
            # North America
            {'country_code': 'AG', 'country_name': 'Antigua and Barbuda', 'dialing_code': '+1', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BS', 'country_name': 'Bahamas', 'dialing_code': '+1', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BB', 'country_name': 'Barbados', 'dialing_code': '+1', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BZ', 'country_name': 'Belize', 'dialing_code': '+501', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'CA', 'country_name': 'Canada', 'dialing_code': '+1', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'CR', 'country_name': 'Costa Rica', 'dialing_code': '+506', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'CU', 'country_name': 'Cuba', 'dialing_code': '+53', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'DM', 'country_name': 'Dominica', 'dialing_code': '+1', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'DO', 'country_name': 'Dominican Republic', 'dialing_code': '+1', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SV', 'country_name': 'El Salvador', 'dialing_code': '+503', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'GD', 'country_name': 'Grenada', 'dialing_code': '+1', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'GT', 'country_name': 'Guatemala', 'dialing_code': '+502', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'HT', 'country_name': 'Haiti', 'dialing_code': '+509', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'HN', 'country_name': 'Honduras', 'dialing_code': '+504', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'JM', 'country_name': 'Jamaica', 'dialing_code': '+1', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MX', 'country_name': 'Mexico', 'dialing_code': '+52', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'NI', 'country_name': 'Nicaragua', 'dialing_code': '+505', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'PA', 'country_name': 'Panama', 'dialing_code': '+507', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'KN', 'country_name': 'Saint Kitts and Nevis', 'dialing_code': '+1', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'LC', 'country_name': 'Saint Lucia', 'dialing_code': '+1', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'VC', 'country_name': 'Saint Vincent and the Grenadines', 'dialing_code': '+1', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'TT', 'country_name': 'Trinidad and Tobago', 'dialing_code': '+1', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'US', 'country_name': 'United States', 'dialing_code': '+1', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            
            # Oceania
            {'country_code': 'AU', 'country_name': 'Australia', 'dialing_code': '+61', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'FJ', 'country_name': 'Fiji', 'dialing_code': '+679', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'KI', 'country_name': 'Kiribati', 'dialing_code': '+686', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'MH', 'country_name': 'Marshall Islands', 'dialing_code': '+692', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'FM', 'country_name': 'Micronesia', 'dialing_code': '+691', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'NR', 'country_name': 'Nauru', 'dialing_code': '+674', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'NZ', 'country_name': 'New Zealand', 'dialing_code': '+64', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'PW', 'country_name': 'Palau', 'dialing_code': '+680', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'PG', 'country_name': 'Papua New Guinea', 'dialing_code': '+675', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'WS', 'country_name': 'Samoa', 'dialing_code': '+685', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SB', 'country_name': 'Solomon Islands', 'dialing_code': '+677', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'TO', 'country_name': 'Tonga', 'dialing_code': '+676', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'TV', 'country_name': 'Tuvalu', 'dialing_code': '+688', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'VU', 'country_name': 'Vanuatu', 'dialing_code': '+678', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            
            # South America
            {'country_code': 'AR', 'country_name': 'Argentina', 'dialing_code': '+54', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BO', 'country_name': 'Bolivia', 'dialing_code': '+591', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'BR', 'country_name': 'Brazil', 'dialing_code': '+55', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'CL', 'country_name': 'Chile', 'dialing_code': '+56', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'CO', 'country_name': 'Colombia', 'dialing_code': '+57', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'EC', 'country_name': 'Ecuador', 'dialing_code': '+593', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'GY', 'country_name': 'Guyana', 'dialing_code': '+592', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'PY', 'country_name': 'Paraguay', 'dialing_code': '+595', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'PE', 'country_name': 'Peru', 'dialing_code': '+51', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'SR', 'country_name': 'Suriname', 'dialing_code': '+597', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'UY', 'country_name': 'Uruguay', 'dialing_code': '+598', 'price': 0.5, 'target_quantity': 10, 'is_active': False},
            {'country_code': 'VE', 'country_name': 'Venezuela', 'dialing_code': '+58', 'price': 0.5, 'target_quantity': 10, 'is_active': False}
        ]
    
    def init_default_countries(self):
        """Initialize default countries using the comprehensive country list"""
        try:
            default_countries = self.get_default_countries()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for country in default_countries:
                    cursor.execute("""
                        INSERT OR IGNORE INTO countries 
                        (country_code, country_name, price, target_quantity, is_active, dialing_code) 
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        country['country_code'], 
                        country['country_name'], 
                        country['price'], 
                        country['target_quantity'],
                        country['is_active'],
                        country['dialing_code']
                    ))
                conn.commit()
                logger.info(f"Initialized {len(default_countries)} default countries")
        except Exception as e:
            logger.error(f"Error initializing default countries: {e}")
    
    def init_default_settings(self):
        """Initialize default admin settings"""
        defaults = {
            'default_price': '1.0',
            'approval_hours': '24',
            'session_timeout_hours': '23',
            'min_balance_withdraw': '10.0',
            'bot_commission': '0.1',
            'max_accounts_per_user': '10',
            'verification_required': '1',
            'auto_approval_enabled': '0',
            'auto_sync_enabled': '1',
            'sync_interval_hours': '24',
            'last_sync_time': ''
        }
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for key, value in defaults.items():
                    cursor.execute("""
                        INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)
                    """, (key, value))
                conn.commit()
                logger.info(f"Initialized {len(defaults)} default settings")
        except Exception as e:
            logger.error(f"Error initializing default settings: {e}")
    
    def init_default_content(self):
        """Initialize default multilingual content"""
        try:
            from languages.languages import translations, get_supported_languages
            
            content_types = ['rules', 'updates', 'support']
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for lang in get_supported_languages():
                    for content_type in content_types:
                        default_key = f'default_{content_type}'
                        if default_key in translations[lang]:
                            cursor.execute("""
                                INSERT OR IGNORE INTO content (content_type, language, content)
                                VALUES (?, ?, ?)
                            """, (content_type, lang, translations[lang][default_key]))
                
                conn.commit()
                logger.info(f"Initialized default content for {len(get_supported_languages())} languages")
        except Exception as e:
            logger.error(f"Error initializing default content: {e}")
    
    
    def get_default_countries_data(self) -> List[Tuple[str, str, float, int]]:
        """Get the default countries data as a list of tuples"""
        return [
            ('+1', 'USA', 0.5, 1000),
            ('+44', 'UK', 0.4, 500), 
            ('+49', 'Germany', 0.6, 300),
            ('+33', 'France', 0.4, 300),
            ('+7', 'Russia', 0.3, 800),
            ('+86', 'China', 0.2, 2000),
            ('+98', 'Iran', 0.3, 500),
            ('+966', 'Saudi Arabia', 0.5, 400),
            ('+971', 'UAE', 0.6, 200),
            ('+91', 'India', 0.2, 1500),
            ('+880', 'Bangladesh', 0.1, 1000),
            ('+93', 'Afghanistan', 0.3, 500),
            ('+92', 'Pakistan', 0.2, 800),
            ('+90', 'Turkey', 0.4, 600),
            ('+81', 'Japan', 0.8, 200),
            ('+82', 'South Korea', 0.7, 300),
            ('+84', 'Vietnam', 0.2, 700),
            ('+62', 'Indonesia', 0.2, 900),
            ('+60', 'Malaysia', 0.3, 400),
            ('+65', 'Singapore', 0.9, 100),
            ('+66', 'Thailand', 0.3, 500),
            ('+55', 'Brazil', 0.3, 800),
            ('+54', 'Argentina', 0.4, 400),
            ('+52', 'Mexico', 0.3, 600),
            ('+39', 'Italy', 0.5, 300),
            ('+34', 'Spain', 0.4, 400),
            ('+31', 'Netherlands', 0.6, 200),
            ('+46', 'Sweden', 0.7, 150),
            ('+47', 'Norway', 0.8, 100),
            ('+358', 'Finland', 0.7, 100),
            ('+20', 'Egypt', 0.2, 800),
            ('+234', 'Nigeria', 0.1, 1000),
            ('+27', 'South Africa', 0.3, 400),
            ('+212', 'Morocco', 0.2, 500),
            ('+213', 'Algeria', 0.2, 600),
            ('+216', 'Tunisia', 0.3, 300),
            ('+218', 'Libya', 0.4, 200),
            ('+963', 'Syria', 0.3, 400),
            ('+964', 'Iraq', 0.3, 500),
            ('+961', 'Lebanon', 0.4, 300),
            ('+962', 'Jordan', 0.4, 300),
            ('+965', 'Kuwait', 0.6, 200),
            ('+974', 'Qatar', 0.7, 100),
            ('+968', 'Oman', 0.5, 200),
            ('+973', 'Bahrain', 0.6, 100),
            ('+967', 'Yemen', 0.2, 400),
            ('+994', 'Azerbaijan', 0.3, 300),
            ('+995', 'Georgia', 0.4, 200),
            ('+996', 'Kyrgyzstan', 0.2, 300),
            ('+998', 'Uzbekistan', 0.2, 400),
            ('+992', 'Tajikistan', 0.2, 200),
            ('+993', 'Turkmenistan', 0.3, 150)
        ]
    
    def get_default_settings_data(self) -> Dict[str, str]:
        """Get the default settings data as a dictionary"""
        return {
            'default_price': '1.0',
            'approval_hours': '24',
            'session_timeout_hours': '23',
            'min_balance_withdraw': '10.0',
            'bot_commission': '0.1',
            'max_accounts_per_user': '10',
            'verification_required': '1',
            'auto_approval_enabled': '0',
            'auto_sync_enabled': '1',
            'sync_interval_hours': '24',
            'last_sync_time': ''
        }
    
    def initialize_all_defaults(self):
        """Initialize all default data"""
        logger.info("Starting initialization of all default data...")
        
        try:
            self.init_default_settings()
            self.init_default_countries()
            self.init_default_content()
            
            logger.info("✅ All default data initialization completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error during default data initialization: {e}")
            return False

# Convenience functions for backwards compatibility
def init_default_countries(db_path: str = "bot_database_v2.db"):
    """Initialize default countries - convenience function"""
    initializer = DefaultDataInitializer(db_path)
    initializer.init_default_countries()

def init_default_settings(db_path: str = "bot_database_v2.db"):
    """Initialize default settings - convenience function"""
    initializer = DefaultDataInitializer(db_path)
    initializer.init_default_settings()

def init_default_content(db_path: str = "bot_database_v2.db"):
    """Initialize default content - convenience function"""
    initializer = DefaultDataInitializer(db_path)
    initializer.init_default_content()


def initialize_all_defaults(db_path: str = "bot_database_v2.db"):
    """Initialize all default data - convenience function"""
    initializer = DefaultDataInitializer(db_path)
    return initializer.initialize_all_defaults()