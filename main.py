import os
import logging
import sqlite3
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
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
        try:
            files = {'file': ('image.jpg', image_data, 'image/jpeg')}
            response = requests.post(self.telegraph_url, files=files, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result and len(result) > 0:
                    return f"https://telegra.ph{result[0]['src']}"
            return None
        except Exception as e:
            logging.error(f"Error uploading to Telegraph: {e}")
            return None

class ImageBot:
    def __init__(self, token: str):
        self.application = Application.builder().token(token).build()
        self.uploader = TelegraphUploader()
        self.db = Database()
        
        # Регистрация обработчиков
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("all", self.broadcast_command))
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
    
    def is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        return user_id == ADMIN_ID
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        user_id = user.id
        
        self.db.add_user(user_id, user.username, user.first_name, user.last_name)
        self.db.update_user_activity(user_id)
        
        welcome_text = """
👋 Привет! Я — бот для сохранения изображений на фотохостинге!

Как мной пользоваться:
1. Просто отправь мне изображение 📸.
2. Я сохраню его и пришлю тебе cсылку 🔗 на изображение.

Делись ссылкой с друзьями и размещай на форумах! 😊
        """
        await update.message.reply_text(welcome_text)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /stats (только для администратора)"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("❌ Эта команда доступна только администратору.")
            return
        
        try:
            bot_stats = self.db.get_bot_stats()
            
            stats_text = f"""
📊 Статистика бота:

👥 Всего пользователей: {bot_stats['total_users']}
📸 Всего изображений: {bot_stats['total_images']}
🔥 Активных пользователей: {bot_stats['active_users']}
            """
            
            await update.message.reply_text(stats_text)
            
        except Exception as e:
            logging.error(f"Error getting stats: {e}")
            await update.message.reply_text("❌ Ошибка при получении статистики.")
    
    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /all (рассылка, только для администратора)"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            await update.message.reply_text("❌ Эта команда доступна только администратору.")
            return
        
        if not context.args:
            await update.message.reply_text("❌ Использование: /all ваше сообщение")
            return
        
        message_text = " ".join(context.args)
        broadcast_message = f"""
📢 Сообщение от администратора:

{message_text}
        """
        
        try:
            all_users = self.db.get_all_users()
            total_users = len(all_users)
            successful_sends = 0
            
            progress_msg = await update.message.reply_text(f"🔄 Начинаю рассылку для {total_users} пользователей...")
            
            for user_id in all_users:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=broadcast_message
                    )
                    successful_sends += 1
                    
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logging.error(f"Error sending to user {user_id}: {e}")
                    continue
            
            report_text = f"""
✅ Рассылка завершена!

📊 Результаты:
👥 Всего пользователей: {total_users}
✅ Успешно отправлено: {successful_sends}
❌ Не удалось отправить: {total_users - successful_sends}
            """
            
            await progress_msg.edit_text(report_text)
            
        except Exception as e:
            logging.error(f"Error in broadcast: {e}")
            await update.message.reply_text("❌ Ошибка при рассылке сообщения.")
    
    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик получения фотографии"""
        user = update.effective_user
        user_id = user.id
        
        try:
            self.db.add_user(user_id, user.username, user.first_name, user.last_name)
            self.db.update_user_activity(user_id)
            
            # Скачиваем изображение
            photo_file = await update.message.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            
            # Загружаем на Telegraph
            image_url = self.uploader.upload_image(bytes(photo_bytes))
            
            if image_url:
                self.db.increment_images_count(user_id)
                self.db.add_image(user_id, image_url)
                
                # Отправляем результат
                caption_text = f"✅ Изображение загружено!\n\n🔗 Ссылка: {image_url}"
                await update.message.reply_photo(
                    photo=image_url,
                    caption=caption_text,
                    caption_above_media=True
                )
                
            else:
                await update.message.reply_text("❌ Ошибка при загрузке изображения. Попробуйте еще раз.")
                
        except Exception as e:
            logging.error(f"Error processing photo: {e}")
            await update.message.reply_text("❌ Произошла ошибка при обработке изображения.")
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений"""
        user = update.effective_user
        user_id = user.id
        
        self.db.add_user(user_id, user.username, user.first_name, user.last_name)
        self.db.update_user_activity(user_id)
        
        await update.message.reply_text("📸 Отправьте мне фотографию для загрузки на фотохостинг!")
    
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
