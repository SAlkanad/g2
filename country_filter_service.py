"""
Country Filter Service - Centralized country availability and filtering logic

This module provides a clean interface for filtering countries based on:
- is_active status in database
- Available slots (target_quantity - approved_count)
- User-specific restrictions

Separates business logic from UI components for better maintainability.
"""

import logging
from typing import List, Dict, Optional, Tuple
from database.database import Database

logger = logging.getLogger(__name__)


class CountryFilterService:
    """Service for filtering and validating country availability"""
    
    def __init__(self, database: Database):
        self.database = database
    
    def get_available_countries(self) -> List[Dict]:
        """
        Get all available countries with proper filtering
        
        Returns:
            List[Dict]: Countries that are active AND have available slots
        """
        try:
            # Get countries marked as active in database
            active_countries = self.database.get_countries(active_only=True)
            available_countries = []
            
            for country in active_countries:
                # Validate country has required fields
                if not self._validate_country_data(country):
                    logger.warning(f"Skipping country {country.get('country_code', 'UNKNOWN')} - invalid data")
                    continue
                
                # Calculate available slots
                availability_info = self._calculate_country_availability(country)
                
                if availability_info['has_slots']:
                    # Add calculated fields to country data
                    country.update(availability_info)
                    available_countries.append(country)
            
            # Sort by priority (descending) then by name
            available_countries.sort(
                key=lambda x: (-x.get('priority', 1), x.get('country_name', ''))
            )
            
            logger.info(f"Found {len(available_countries)} available countries out of {len(active_countries)} active")
            return available_countries
            
        except Exception as e:
            logger.error(f"Error getting available countries: {e}")
            return []
    
    def validate_country_selection(self, country_code: str) -> Tuple[Optional[Dict], str]:
        """
        Validate if a specific country is available for account submission
        
        Args:
            country_code: Country code to validate
            
        Returns:
            Tuple[Optional[Dict], str]: (country_data, error_message)
            - If valid: (country_dict, "")
            - If invalid: (None, error_message)
        """
        try:
            # Get active countries only
            active_countries = self.database.get_countries(active_only=True)
            country = next((c for c in active_countries if c['country_code'] == country_code), None)
            
            if not country:
                return None, "Selected country is no longer available"
            
            # Validate country data
            if not self._validate_country_data(country):
                return None, "Selected country has invalid configuration"
            
            # Check availability
            availability_info = self._calculate_country_availability(country)
            
            if not availability_info['has_slots']:
                return None, f"No slots available for {country['country_name']} currently. Please choose another country."
            
            # Add calculated fields
            country.update(availability_info)
            return country, ""
            
        except Exception as e:
            logger.error(f"Error validating country {country_code}: {e}")
            return None, "Error validating country availability"
    
    def get_countries_by_continent(self, countries: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Group countries by continent
        
        Args:
            countries: List of country dictionaries
            
        Returns:
            Dict[str, List[Dict]]: Countries grouped by continent
        """
        continent_mapping = self._get_country_continent_mapping()
        continent_countries = {}
        
        for country in countries:
            country_code = country.get('country_code', '')
            continent = continent_mapping.get(country_code, 'Other')
            
            if continent not in continent_countries:
                continent_countries[continent] = []
            continent_countries[continent].append(country)
        
        return continent_countries
    
    def _validate_country_data(self, country: Dict) -> bool:
        """Validate that country has all required fields"""
        required_fields = ['country_code', 'country_name', 'price', 'target_quantity']
        return all(field in country for field in required_fields)
    
    def _calculate_country_availability(self, country: Dict) -> Dict:
        """
        Calculate availability information for a country
        
        Returns:
            Dict with keys:
            - available_quantity: int
            - approved_count: int  
            - has_slots: bool
            - target_quantity: int
        """
        country_code = country['country_code']
        
        # Get current approved count
        approved_count = self.database.get_approved_sessions_count_by_country(country_code)
        
        # Calculate available slots
        target_quantity = country.get('target_quantity', 0)
        available_quantity = max(0, target_quantity - approved_count)
        
        return {
            'available_quantity': available_quantity,
            'approved_count': approved_count,
            'has_slots': available_quantity > 0,
            'target_quantity': target_quantity
        }
    
    def _get_country_continent_mapping(self) -> Dict[str, str]:
        """Get mapping of country codes to continents"""
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
            'HU': 'Europe', 'IS': 'Europe', 'IE': 'Europe', 'IT': 'Europe', 'LV': 'Europe',
            'LI': 'Europe', 'LT': 'Europe', 'LU': 'Europe', 'MT': 'Europe', 'MD': 'Europe',
            'MC': 'Europe', 'ME': 'Europe', 'NL': 'Europe', 'MK': 'Europe', 'NO': 'Europe',
            'PL': 'Europe', 'PT': 'Europe', 'RO': 'Europe', 'RU': 'Europe', 'SM': 'Europe',
            'RS': 'Europe', 'SK': 'Europe', 'SI': 'Europe', 'ES': 'Europe', 'SE': 'Europe',
            'CH': 'Europe', 'UA': 'Europe', 'GB': 'Europe', 'VA': 'Europe',
            
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


def get_continent_emoji(continent: str) -> str:
    """Get emoji representation for continent"""
    continent_emojis = {
        'Africa': '🌍',
        'Asia': '🌏', 
        'Europe': '🌍',
        'North America': '🌎',
        'South America': '🌎',
        'Oceania': '🌏'
    }
    return continent_emojis.get(continent, '🌍')