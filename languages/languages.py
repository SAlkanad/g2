"""
Multi-language support for the bot using JSON translation files
"""
import json
import os
from typing import Dict, Optional

class TranslationManager:
    """Manages translations for the bot"""
    
    def __init__(self):
        self.translations = {}
        self.default_language = 'en'
        self.supported_languages = ['en', 'ar', 'fa', 'bn']
        self.load_translations()
    
    def load_translations(self):
        """Load translations from JSON files"""
        for lang in self.supported_languages:
            try:
                # Get the directory where this file is located
                current_dir = os.path.dirname(os.path.abspath(__file__))
                file_path = os.path.join(current_dir, f"{lang}.json")
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        self.translations[lang] = json.load(f)
                else:
                    print(f"Warning: Translation file {file_path} not found")
                    self.translations[lang] = {}
            except Exception as e:
                print(f"Error loading translation file {lang}.json: {e}")
                self.translations[lang] = {}
    
    def get_text(self, key: str, language: str = None, **kwargs) -> str:
        """Get translated text for a key"""
        if language is None:
            language = self.default_language
        
        # Fallback to default language if not found
        if language not in self.translations:
            language = self.default_language
        
        # Get translation
        text = self.translations.get(language, {}).get(key)
        
        # Fallback to English if not found
        if text is None and language != self.default_language:
            text = self.translations.get(self.default_language, {}).get(key)
        
        # Final fallback to key itself
        if text is None:
            text = key
        
        # Format with kwargs if provided
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    
    def get_supported_languages(self) -> list:
        """Get list of supported languages"""
        return self.supported_languages
    
    def is_supported_language(self, language: str) -> bool:
        """Check if a language is supported"""
        return language in self.supported_languages

# Global translation manager instance
translator = TranslationManager()

def get_text(key: str, language: str = None, **kwargs) -> str:
    """Get translated text - convenience function"""
    return translator.get_text(key, language, **kwargs)

def get_supported_languages() -> list:
    """Get supported languages - convenience function"""
    return translator.get_supported_languages()

def is_supported_language(language: str) -> bool:
    """Check if language is supported - convenience function"""
    return translator.is_supported_language(language)

# Legacy dictionary for backward compatibility (will be removed in future)
# This ensures existing code continues to work during transition
translations = {
    'en': translator.translations.get('en', {}),
    'ar': translator.translations.get('ar', {}),
    'fa': translator.translations.get('fa', {}),
    'bn': translator.translations.get('bn', {})
}

# Language names for display
language_names = {
    'en': '🇺🇸 English',
    'ar': '🇸🇦 العربية',
    'fa': '🇮🇷 فارسی',
    'bn': '🇧🇩 বাংলা'
}

def get_language_name(language_code: str) -> str:
    """Get display name for a language code"""
    return language_names.get(language_code, language_code)

# Backward compatibility alias
get_available_languages = get_supported_languages