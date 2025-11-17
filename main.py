import os
import logging
import sqlite3
import asyncio
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import requests
from io import BytesIO

# Загружаем переменные из .env
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# === КОНФИГУРАЦИЯ ===
BOT_TOKEN = os.getenv('BOT_TOKEN')  # Токен из .env
ADMIN_ID = 123456789  # Твой ID прямо в коде

# Тексты на разных языках
TEXTS = {
    'ru': {
        'welcome': '👋 Привет! Я — бот для сохранения изображений на фотохостинге!',
        'instructions': 'Как мной пользоваться:\n1. Просто отправь мне изображение 📸.\n2. Я сохраню его и пришлю тебе cсылку 🔗 на изображение.\n\nДелись ссылкой с друзьями и размещай на форумах! 😊',
        'success': '✅ Изображение загружено!\n\n🔗 Ссылка: {}',
        'error_upload': '❌ Ошибка при загрузке изображения. Попробуйте еще раз.',
        'error_processing': '❌ Произошла ошибка при обработке изображения.',
        'send_photo': '📸 Отправьте мне фотографию для загрузки на фотохостинг!',
        'admin_only': '❌ Эта команда доступна только администратору.',
        'stats': '📊 Статистика бота:\n\n👥 Всего пользователей: {}\n📸 Всего изображений: {}\n🔥 Активных пользователей: {}',
        'broadcast_usage': '❌ Использование: /all ваше сообщение',
        'broadcast_message': '📢 Сообщение от администратора:\n\n{}',
        'broadcast_start': '🔄 Начинаю рассылку для {} пользователей...',
        'broadcast_result': '✅ Рассылка завершена!\n\n📊 Результаты:\n👥 Всего пользователей: {}\n✅ Успешно отправлено: {}\n❌ Не удалось отправить: {}',
        'broadcast_error': '❌ Ошибка при рассылке сообщения.',
        'stats_error': '❌ Ошибка при получении статистики.',
        'choose_language': '🇷🇺 Выберите язык',
        'language_changed': '✅ Язык изменен на Русский!',
    },
    'en': {
        'welcome': '👋 Hello! I am a bot for saving images to a photo hosting service!',
        'instructions': 'How to use me:\n1. Just send me an image 📸.\n2. I will save it and send you a link 🔗 to the image.\n\nShare the link with friends and post on forums! 😊',
        'success': '✅ Image uploaded!\n\n🔗 Link: {}',
        'error_upload': '❌ Error uploading image. Please try again.',
        'error_processing': '❌ An error occurred while processing the image.',
        'send_photo': '📸 Send me a photo to upload to the photo hosting!',
        'admin_only': '❌ This command is available only to the administrator.',
        'stats': '📊 Bot statistics:\n\n👥 Total users: {}\n📸 Total images: {}\n🔥 Active users: {}',
        'broadcast_usage': '❌ Usage: /all your message',
        'broadcast_message': '📢 Message from administrator:\n\n{}',
        'broadcast_start': '🔄 Starting broadcast for {} users...',
        'broadcast_result': '✅ Broadcast completed!\n\n📊 Results:\n👥 Total users: {}\n✅ Successfully sent: {}\n❌ Failed to send: {}',
        'broadcast_error': '❌ Error sending broadcast message.',
        'stats_error': '❌ Error getting statistics.',
        'choose_language': '🇺🇸 Select a language',
        'language_changed': '✅ Language changed to English!',
    }
}

class Database:
    def __init__(self, db_path="users.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                language TEXT DEFAULT 'ru',
                images_count INTEGER DEFAULT 0,
                first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_active DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                image_url TEXT,
                upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_user(self, user_id, username, first_name, last_name):
        """Добавление нового пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name))
        
        conn.commit()
        conn.close()
    
    def get_user_language(self, user_id):
        """Получение языка пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT language FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else 'ru'
    
    def set_user_language(self, user_id, language):
        """Установка языка пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users SET language = ? 
            WHERE user_id = ?
        ''', (language, user_id))
        
        conn.commit()
        conn.close()
    
    def update_user_activity(self, user_id):
        """Обновление времени последней активности"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users SET last_active = CURRENT_TIMESTAMP 
            WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        conn.close()
    
    def increment_images_count(self, user_id):
        """Увеличение счетчика изображений пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE users SET images_count = images_count + 1 
            WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        conn.close()
    
    def add_image(self, user_id, image_url):
        """Добавление информации о загруженном изображении"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO images (user_id, image_url)
            VALUES (?, ?)
        ''', (user_id, image_url))
        
        conn.commit()
        conn.close()
    
    def get_all_users(self):
        """Получение списка всех пользователей"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM users')
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        return users
    
    def get_bot_stats(self):
        """Получение общей статистики бота"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        total_users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM images')
        total_images = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*) FROM users 
            WHERE last_active > datetime('now', '-30 days')
        ''')
        active_users = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_users': total_users,
            'total_images': total_images,
            'active_users': active_users
        }

class TelegraphUploader:
    def __init__(self):
        self.telegraph_url = "https://telegra.ph/upload"
    
    def upload_image(self, image_data: bytes) -> str:
        """Загружает изображение на Telegraph и возвращает URL"""
        files = {'file': ('image.jpg', image_data, 'image/jpeg')}
        response = requests.post(self.telegraph_url, files=files)
        
        if response.status_code == 200:
            result = response.json()
            if result and len(result) > 0:
                return f"https://telegra.ph{result[0]['src']}"
        return None

class ImageBot:
    def __init__(self, token: str):
        self.application = Application.builder().token(token).build()
        self.uploader = TelegraphUploader()
        self.db = Database()
        
        # Регистрация обработчиков
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("language", self.language_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("all", self.broadcast_command))
        self.application.add_handler(CallbackQueryHandler(self.language_callback, pattern="^lang_"))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
    
    def is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        return user_id == ADMIN_ID
    
    def get_user_text(self, user_id: int, text_key: str) -> str:
        """Получение текста на языке пользователя"""
        language = self.db.get_user_language(user_id)
        return TEXTS[language].get(text_key, TEXTS['ru'].get(text_key, text_key))
    
    async def show_language_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
        """Показать выбор языка"""
        keyboard = [
            [
                InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
                InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        choose_language_text = self.get_user_text(user_id, 'choose_language')
        
        if update.callback_query:
            await update.callback_query.message.reply_text(choose_language_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(choose_language_text, reply_markup=reply_markup)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        user_id = user.id
        
        self.db.add_user(user_id, user.username, user.first_name, user.last_name)
        self.db.update_user_activity(user_id)
        
        user_language = self.db.get_user_language(user_id)
        
        if user_language == 'ru':
            await self.show_language_selection(update, context, user_id)
        else:
            welcome_text = f"{self.get_user_text(user_id, 'welcome')}\n\n{self.get_user_text(user_id, 'instructions')}"
            await update.message.reply_text(welcome_text)
    
    async def language_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /language"""
        user = update.effective_user
        user_id = user.id
        
        self.db.add_user(user_id, user.username, user.first_name, user.last_name)
        self.db.update_user_activity(user_id)
        
        await self.show_language_selection(update, context, user_id)
    
    async def language_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик выбора языка"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        language = query.data.split('_')[1]
        
        self.db.set_user_language(user_id, language)
        
        confirmation_text = self.get_user_text(user_id, 'language_changed')
        await query.edit_message_text(confirmation_text)
        
        if not context.user_data.get('language_selected'):
            context.user_data['language_selected'] = True
            welcome_text = f"{self.get_user_text(user_id, 'welcome')}\n\n{self.get_user_text(user_id, 'instructions')}"
            await query.message.reply_text(welcome_text)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats (только для администратора)"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text(self.get_user_text(user_id, 'admin_only'))
            return
        
        try:
            bot_stats = self.db.get_bot_stats()
            
            stats_text = self.get_user_text(user_id, 'stats').format(
                bot_stats['total_users'], 
                bot_stats['total_images'], 
                bot_stats['active_users']
            )
            
            await update.message.reply_text(stats_text)
            
        except Exception as e:
            logging.error(f"Error getting stats: {e}")
            await update.message.reply_text(self.get_user_text(user_id, 'stats_error'))
    
    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /all (рассылка, только для администратора)"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text(self.get_user_text(user_id, 'admin_only'))
            return
        
        if not context.args:
            await update.message.reply_text(self.get_user_text(user_id, 'broadcast_usage'))
            return
        
        message_text = " ".join(context.args)
        
        try:
            all_users = self.db.get_all_users()
            total_users = len(all_users)
            successful_sends = 0
            
            progress_msg = await update.message.reply_text(
                self.get_user_text(user_id, 'broadcast_start').format(total_users)
            )
            
            for user_id in all_users:
                try:
                    user_language = self.db.get_user_language(user_id)
                    broadcast_text = TEXTS[user_language]['broadcast_message'].format(message_text)
                    
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=broadcast_text
                    )
                    successful_sends += 1
                    
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logging.error(f"Error sending to user {user_id}: {e}")
                    continue
            
            report_text = self.get_user_text(user_id, 'broadcast_result').format(
                total_users, successful_sends, total_users - successful_sends
            )
            
            await progress_msg.edit_text(report_text)
            
        except Exception as e:
            logging.error(f"Error in broadcast: {e}")
            await update.message.reply_text(self.get_user_text(user_id, 'broadcast_error'))
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик получения фотографии"""
        user = update.effective_user
        user_id = user.id
        
        try:
            self.db.add_user(user_id, user.username, user.first_name, user.last_name)
            self.db.update_user_activity(user_id)
            
            # УДАЛЕНО: сообщение "Обрабатываю изображение..."
            
            photo_file = await update.message.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            
            image_url = self.uploader.upload_image(bytes(photo_bytes))
            
            if image_url:
                self.db.increment_images_count(user_id)
                self.db.add_image(user_id, image_url)
                
                # Сразу отправляем результат
                caption_text = self.get_user_text(user_id, 'success').format(image_url)
                await update.message.reply_photo(
                    photo=image_url,
                    caption=caption_text,
                    caption_above_media=True
                )
                
            else:
                await update.message.reply_text(self.get_user_text(user_id, 'error_upload'))
                
        except Exception as e:
            logging.error(f"Error processing photo: {e}")
            await update.message.reply_text(self.get_user_text(user_id, 'error_processing'))
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений"""
        user = update.effective_user
        user_id = user.id
        
        self.db.add_user(user_id, user.username, user.first_name, user.last_name)
        self.db.update_user_activity(user_id)
        
        await update.message.reply_text(self.get_user_text(user_id, 'send_photo'))
    
    def run(self):
        """Запуск бота"""
        self.application.run_polling()

def main():
    """Основная функция запуска"""
    if not BOT_TOKEN:
        print("❌ Токен бота не найден! Проверь файл .env")
        return
    
    bot = ImageBot(BOT_TOKEN)
    print("🤖 Бот запущен...")
    print(f"👑 Администратор: {ADMIN_ID}")
    bot.run()

if __name__ == "__main__":
    main()