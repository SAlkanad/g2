"""
Rules Management Module

Handles rules content management for different languages
"""

import logging
from typing import List, Dict
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database.database import Database
from languages.languages import get_supported_languages, get_text
from notification_service import NotificationService
from admin.auth_service import AuthService

logger = logging.getLogger(__name__)


class RulesStates(StatesGroup):
    """FSM states for rules management"""
    waiting_rules_content = State()


class RulesManager:
    """Manages rules content for different languages"""
    
    def __init__(self, bot: Bot, database: Database, admin_ids: List[int]):
        self.bot = bot
        self.database = database
        self.notification_service = NotificationService(bot, database)
        self.admin_ids = admin_ids
        self.auth_service = AuthService(database, admin_ids)
    
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
    
    async def show_rules_management(self, callback_query: types.CallbackQuery):
        """Show rules management menu"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        # Get available languages
        languages = get_supported_languages()
        
        keyboard = []
        for lang in languages:
            if lang == 'en':
                keyboard.append([InlineKeyboardButton(text="🇺🇸 English", callback_data=f"rules_edit_{lang}")])
            elif lang == 'ar':
                keyboard.append([InlineKeyboardButton(text="🇸🇦 العربية", callback_data=f"rules_edit_{lang}")])
            else:
                keyboard.append([InlineKeyboardButton(text=f"🌐 {lang.upper()}", callback_data=f"rules_edit_{lang}")])
        
        keyboard.extend([
            [
                InlineKeyboardButton(text="👁️ View All Rules", callback_data="rules_view_all"),
                InlineKeyboardButton(text="🗑️ Clear Rules", callback_data="rules_clear_menu")
            ],
            [InlineKeyboardButton(text="🔙 Back to Admin Panel", callback_data="admin_panel")]
        ])
        
        # Get current rules statistics
        rules_stats = self.get_rules_statistics()
        
        text = (
            "📜 **Rules Management**\n\n"
            f"📊 **Current Status:**\n"
            f"• Languages with rules: {rules_stats['languages_count']}\n"
            f"• Total rules entries: {rules_stats['total_entries']}\n\n"
            "**Actions:**\n"
            "• Select a language to edit rules\n"
            "• View all current rules\n"
            "• Clear rules for specific languages\n\n"
            "Choose an action:"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def show_rules_edit(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Show rules edit interface for specific language"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        language = callback_query.data.split('_')[-1]  # Extract language from callback_data
        
        # Get current rules for this language
        current_rules = self.database.get_content('rules', language)
        
        keyboard = [
            [InlineKeyboardButton(text="📝 Edit Rules", callback_data=f"rules_start_edit_{language}")],
            [
                InlineKeyboardButton(text="👁️ Preview", callback_data=f"rules_preview_{language}"),
                InlineKeyboardButton(text="🗑️ Clear", callback_data=f"rules_clear_{language}")
            ],
            [InlineKeyboardButton(text="🔙 Back", callback_data="admin_rules")]
        ]
        
        text = (
            f"📜 **Rules Management - {language.upper()}**\n\n"
            f"**Current Rules:**\n"
        )
        
        if current_rules:
            # Show preview of current rules (first 200 chars)
            preview = current_rules[:200] + "..." if len(current_rules) > 200 else current_rules
            text += f"```\n{preview}\n```\n\n"
            text += f"**Length:** {len(current_rules)} characters\n\n"
        else:
            text += "*No rules set for this language*\n\n"
        
        text += "**Actions:**\n"
        text += "• Edit: Modify the rules content\n"
        text += "• Preview: View full current rules\n"
        text += "• Clear: Remove rules for this language"
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def start_rules_edit(self, callback_query: types.CallbackQuery, state: FSMContext):
        """Start editing rules content"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        language = callback_query.data.split('_')[-1]
        
        # Get current rules
        current_rules = self.database.get_content('rules', language)
        
        text = (
            f"📝 **Editing Rules - {language.upper()}**\n\n"
            "Send the new rules content.\n\n"
            "**Current rules:**\n"
        )
        
        if current_rules:
            text += f"```\n{current_rules}\n```\n\n"
        else:
            text += "*No rules currently set*\n\n"
        
        text += (
            "**Instructions:**\n"
            "• Send your new rules text\n"
            "• You can use Markdown formatting\n"
            "• Send /cancel to abort editing\n\n"
            "📝 **Send your new rules:**"
        )
        
        keyboard = [
            [InlineKeyboardButton(text="❌ Cancel", callback_data=f"rules_edit_{language}")]
        ]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
        
        # Set state to wait for rules content
        await state.set_state(RulesStates.waiting_rules_content)
        await state.update_data(language=language, action="edit_rules")
    
    async def process_rules_content(self, message: types.Message, state: FSMContext):
        """Process new rules content"""
        if not self.is_admin(message.from_user.id):
            await message.reply("❌ Access denied")
            return
        
        data = await state.get_data()
        language = data.get('language')
        
        if not language:
            await message.reply("❌ Error: No language specified")
            await state.clear()
            return
        
        new_content = message.text.strip()
        
        if not new_content or new_content == '/cancel':
            await message.reply("❌ Rules editing cancelled")
            await state.clear()
            return
        
        try:
            # Save the new rules content
            success = self.database.update_content('rules', language, new_content)
            
            if success:
                await message.reply(
                    f"✅ **Rules Updated Successfully!**\n\n"
                    f"**Language:** {language.upper()}\n"
                    f"**Length:** {len(new_content)} characters\n\n"
                    f"The rules for {language.upper()} have been updated.",
                    parse_mode="Markdown"
                )
                
                # Send notifications to users with this language about rules change
                await self.notification_service.notify_content_change(
                    content_type='rules',
                    language=language,
                    title=f"Rules Updated ({language.upper()})",
                    message=f"The rules have been updated for {language.upper()}. Please review the new rules."
                )
                
                logger.info(f"Admin {message.from_user.id} updated rules for language {language}")
            else:
                await message.reply("❌ Failed to update rules. Please try again.")
        
        except Exception as e:
            logger.error(f"Error updating rules for {language}: {e}")
            await message.reply("❌ Error occurred while updating rules.")
        
        await state.clear()
    
    async def preview_rules(self, callback_query: types.CallbackQuery):
        """Preview rules for specific language"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        language = callback_query.data.split('_')[-1]
        rules_content = self.database.get_content('rules', language)
        
        if not rules_content:
            await callback_query.answer(f"❌ No rules set for {language.upper()}", show_alert=True)
            return
        
        # Split long content into chunks if needed
        if len(rules_content) > 4000:
            chunks = [rules_content[i:i+4000] for i in range(0, len(rules_content), 4000)]
            
            await callback_query.message.reply(
                f"📜 **Rules Preview - {language.upper()}** (Part 1/{len(chunks)})\n\n{chunks[0]}",
                parse_mode="Markdown"
            )
            
            for i, chunk in enumerate(chunks[1:], 2):
                await callback_query.message.reply(
                    f"📜 **Rules Preview - {language.upper()}** (Part {i}/{len(chunks)})\n\n{chunk}",
                    parse_mode="Markdown"
                )
        else:
            await callback_query.message.reply(
                f"📜 **Rules Preview - {language.upper()}**\n\n{rules_content}",
                parse_mode="Markdown"
            )
        
        await callback_query.answer("✅ Rules preview sent")
    
    async def clear_rules(self, callback_query: types.CallbackQuery):
        """Clear rules for specific language"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        language = callback_query.data.split('_')[-1]
        
        keyboard = [
            [
                InlineKeyboardButton(text="✅ Yes, Clear", callback_data=f"rules_confirm_clear_{language}"),
                InlineKeyboardButton(text="❌ Cancel", callback_data=f"rules_edit_{language}")
            ]
        ]
        
        text = (
            f"🗑️ **Clear Rules - {language.upper()}**\n\n"
            f"⚠️ **Warning**: This will permanently delete all rules content for {language.upper()}.\n\n"
            f"Are you sure you want to proceed?"
        )
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    async def confirm_clear_rules(self, callback_query: types.CallbackQuery):
        """Confirm and clear rules for specific language"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        language = callback_query.data.split('_')[-1]
        
        try:
            success = self.database.update_content('rules', language, "")
            
            if success:
                await callback_query.answer(f"✅ Rules cleared for {language.upper()}", show_alert=True)
                logger.info(f"Admin {callback_query.from_user.id} cleared rules for language {language}")
                
                # Go back to rules edit for this language
                await self.show_rules_edit(callback_query, None)
            else:
                await callback_query.answer("❌ Failed to clear rules", show_alert=True)
        
        except Exception as e:
            logger.error(f"Error clearing rules for {language}: {e}")
            await callback_query.answer("❌ Error occurred while clearing rules", show_alert=True)
    
    async def view_all_rules(self, callback_query: types.CallbackQuery):
        """View all rules across all languages"""
        if not self.is_admin(callback_query.from_user.id):
            await callback_query.answer("❌ Access denied", show_alert=True)
            return
        
        languages = get_supported_languages()
        all_rules = {}
        
        for lang in languages:
            content = self.database.get_content('rules', lang)
            if content:
                all_rules[lang] = content
        
        if not all_rules:
            text = "📭 **No Rules Found**\n\nNo rules have been set for any language yet."
        else:
            text = "📜 **All Rules Overview**\n\n"
            for lang, content in all_rules.items():
                preview = content[:100] + "..." if len(content) > 100 else content
                text += f"**{lang.upper()}:** {preview}\n\n"
        
        keyboard = [[InlineKeyboardButton(text="🔙 Back", callback_data="admin_rules")]]
        
        await callback_query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
            parse_mode="Markdown"
        )
    
    def get_rules_statistics(self) -> Dict:
        """Get statistics about rules content"""
        languages = get_supported_languages()
        stats = {
            'languages_count': 0,
            'total_entries': 0,
            'languages_with_content': []
        }
        
        for lang in languages:
            content = self.database.get_content('rules', lang)
            if content and content.strip():
                stats['languages_count'] += 1
                stats['total_entries'] += len(content)
                stats['languages_with_content'].append(lang)
        
        return stats
    
    def register_handlers(self, dp: Dispatcher):
        """Register rules management handlers"""
        # Main rules management
        dp.callback_query.register(
            self.show_rules_management,
            F.data == "admin_rules"
        )
        
        # Edit rules for specific language
        dp.callback_query.register(
            self.show_rules_edit,
            F.data.startswith("rules_edit_")
        )
        
        # Start editing rules content
        dp.callback_query.register(
            self.start_rules_edit,
            F.data.startswith("rules_start_edit_")
        )
        
        # Preview rules
        dp.callback_query.register(
            self.preview_rules,
            F.data.startswith("rules_preview_")
        )
        
        # Clear rules
        dp.callback_query.register(
            self.clear_rules,
            F.data.startswith("rules_clear_") & ~F.data.startswith("rules_clear_menu")
        )
        
        # Confirm clear rules
        dp.callback_query.register(
            self.confirm_clear_rules,
            F.data.startswith("rules_confirm_clear_")
        )
        
        # View all rules
        dp.callback_query.register(
            self.view_all_rules,
            F.data == "rules_view_all"
        )
        
        # Process rules content
        dp.message.register(
            self.process_rules_content,
            RulesStates.waiting_rules_content
        )