"""
Notification Service - Handles broadcasting notifications to users based on language and content type
"""

import asyncio
import logging
from typing import List, Dict, Optional
from aiogram import Bot
from database.database import Database

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications to users"""
    
    def __init__(self, bot: Bot, database: Database):
        self.bot = bot
        self.database = database
    
    async def notify_content_change(self, content_type: str, language: str, title: str, message: str):
        """
        Notify users about content changes (rules, updates, live support)
        Only notifies users with matching language
        """
        try:
            # Get all users with the specific language
            users = self.database.get_users_by_language(language)
            
            if not users:
                logger.info(f"No users found for language: {language}")
                return
            
            logger.info(f"Sending {content_type} notification to {len(users)} users in {language}")
            
            # Send notifications in batches to avoid rate limits
            batch_size = 30  # Telegram rate limit is ~30 messages per second
            success_count = 0
            failed_count = 0
            
            for i in range(0, len(users), batch_size):
                batch = users[i:i + batch_size]
                
                # Send to batch
                tasks = []
                for user in batch:
                    task = self._send_notification_to_user(user['user_id'], title, message)
                    tasks.append(task)
                
                # Wait for batch to complete
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Count results
                for result in results:
                    if isinstance(result, Exception):
                        failed_count += 1
                    else:
                        success_count += 1
                
                # Rate limiting delay between batches
                if i + batch_size < len(users):
                    await asyncio.sleep(1)
            
            logger.info(f"Notification sent - Success: {success_count}, Failed: {failed_count}")
            
            # Store notification statistics (if method exists in database)
            try:
                self.database.add_notification_log(
                    content_type=content_type,
                    language=language,
                    title=title,
                    total_users=len(users),
                    success_count=success_count,
                    failed_count=failed_count
                )
            except AttributeError:
                # Method doesn't exist in database, skip logging
                pass
            
        except Exception as e:
            logger.error(f"Error sending content change notification: {e}")
    
    async def _send_notification_to_user(self, user_id: int, title: str, message: str) -> bool:
        """Send notification to a single user"""
        try:
            notification_text = f"📢 **{title}**\n\n{message}"
            
            await self.bot.send_message(
                user_id,
                notification_text,
                parse_mode="Markdown"
            )
            return True
            
        except Exception as e:
            logger.debug(f"Failed to send notification to user {user_id}: {e}")
            return False
    
    async def notify_all_users(self, title: str, message: str, exclude_languages: List[str] = None):
        """
        Send notification to all users
        """
        try:
            # Get all active users
            users = self.database.get_all_active_users()
            
            if not users:
                logger.info("No users found for broadcast")
                return
            
            # Filter by language if needed
            if exclude_languages:
                users = [u for u in users if u.get('language') not in exclude_languages]
            
            logger.info(f"Broadcasting notification to {len(users)} users")
            
            # Send notifications in batches
            batch_size = 30
            success_count = 0
            failed_count = 0
            
            for i in range(0, len(users), batch_size):
                batch = users[i:i + batch_size]
                
                tasks = []
                for user in batch:
                    task = self._send_notification_to_user(user['user_id'], title, message)
                    tasks.append(task)
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, Exception):
                        failed_count += 1
                    else:
                        success_count += 1
                
                if i + batch_size < len(users):
                    await asyncio.sleep(1)
            
            logger.info(f"Broadcast complete - Success: {success_count}, Failed: {failed_count}")
            
        except Exception as e:
            logger.error(f"Error broadcasting notification: {e}")
    
    async def notify_rules_change(self, language: str):
        """Notify users about rules change"""
        title = "📋 Rules Updated"
        
        # Language-specific messages
        messages = {
            'en': "The rules have been updated. Please review the new rules to stay compliant.",
            'ar': "تم تحديث القوانين. يرجى مراجعة القوانين الجديدة للبقاء ملتزماً.",
            'fa': "قوانین به‌روزرسانی شده‌اند. لطفاً قوانین جدید را بررسی کنید تا مطابق باشید.",
            'tr': "Kurallar güncellendi. Uyumlu kalmak için lütfen yeni kuralları inceleyin.",
            'ru': "Правила были обновлены. Пожалуйста, ознакомьтесь с новыми правилами.",
            'es': "Las reglas han sido actualizadas. Por favor revisa las nuevas reglas para mantenerte conforme.",
            'fr': "Les règles ont été mises à jour. Veuillez consulter les nouvelles règles pour rester conforme.",
            'de': "Die Regeln wurden aktualisiert. Bitte überprüfen Sie die neuen Regeln, um konform zu bleiben.",
            'it': "Le regole sono state aggiornate. Si prega di rivedere le nuove regole per rimanere conformi.",
            'pt': "As regras foram atualizadas. Por favor, revise as novas regras para permanecer em conformidade."
        }
        
        message = messages.get(language, messages['en'])
        
        await self.notify_content_change("rules", language, title, message)
    
    async def notify_updates_change(self, language: str):
        """Notify users about bot updates"""
        title = "🔄 Bot Updates"
        
        # Language-specific messages
        messages = {
            'en': "New updates are available! Check the updates section to see what's new.",
            'ar': "تحديثات جديدة متاحة! تحقق من قسم التحديثات لرؤية ما الجديد.",
            'fa': "به‌روزرسانی‌های جدید موجود است! بخش به‌روزرسانی‌ها را بررسی کنید تا ببینید چه چیز جدیدی وجود دارد.",
            'tr': "Yeni güncellemeler mevcut! Yenilikleri görmek için güncellemeler bölümünü kontrol edin.",
            'ru': "Доступны новые обновления! Проверьте раздел обновлений, чтобы увидеть что нового.",
            'es': "¡Nuevas actualizaciones disponibles! Revisa la sección de actualizaciones para ver las novedades.",
            'fr': "Nouvelles mises à jour disponibles ! Consultez la section des mises à jour pour voir les nouveautés.",
            'de': "Neue Updates verfügbar! Überprüfen Sie den Update-Bereich, um zu sehen, was neu ist.",
            'it': "Nuovi aggiornamenti disponibili! Controlla la sezione aggiornamenti per vedere le novità.",
            'pt': "Novas atualizações disponíveis! Verifique a seção de atualizações para ver as novidades."
        }
        
        message = messages.get(language, messages['en'])
        
        await self.notify_content_change("updates", language, title, message)
    
    async def notify_live_support_change(self):
        """Notify all users about live support message change"""
        title = "💬 Live Support Updated"
        
        # Get the new live support message
        new_message = self.database.get_live_support_message()
        if not new_message:
            new_message = "Live support message has been updated."
        
        notification_message = f"The live support information has been updated:\n\n{new_message}"
        
        # Notify all users regardless of language since live support affects everyone
        await self.notify_all_users(title, notification_message)


# Global notification service instance (will be initialized in main bot)
notification_service = None


def init_notification_service(bot: Bot, database: Database):
    """Initialize the global notification service"""
    global notification_service
    notification_service = NotificationService(bot, database)
    return notification_service


def get_notification_service() -> Optional[NotificationService]:
    """Get the global notification service instance"""
    return notification_service