import os
import logging
import sqlite3
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command, CommandObject
from aiogram.enums import ParseMode
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

# Создаем роутер
router = Router()

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

class ImageUploader:
    def __init__(self):
        self.freeimage_url = "https://freeimage.host/api/1/upload"
        self.api_key = "6d207e02198a847aa98d0a2a901485a5"
    
    def upload_image(self, image_data: bytes) -> str:
        """Загружает изображение на FreeImage.host и возвращает URL"""
        try:
            files = {
                'source': ('image.jpg', image_data, 'image/jpeg')
            }
            
            data = {
                'key': self.api_key,
                'action': 'upload',
                'format': 'json'
            }
            
            response = requests.post(
                self.freeimage_url,
                files=files,
                data=data,
                timeout=30
            )
            
            logging.info(f"FreeImage response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logging.info(f"FreeImage response received")
                
                if result.get('success'):
                    image_url = result['image']['url']
                    logging.info(f"Image uploaded successfully: {image_url}")
                    return image_url
                else:
                    logging.error(f"FreeImage API error: {result}")
                    return None
            
            logging.error(f"FreeImage upload failed: {response.text}")
            return None
            
        except Exception as e:
            logging.error(f"FreeImage upload error: {e}")
            return None

class ImageBot:
    def __init__(self, token: str):
        self.bot = Bot(token=token)
        self.dp = Dispatcher()
        self.uploader = ImageUploader()
        self.db = Database()
        
        # Регистрация обработчиков
        self.dp.include_router(router)
        
    def is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        return user_id == ADMIN_ID
    
    async def run(self):
        """Запуск бота"""
        await self.dp.start_polling(self.bot)

# Создаем экземпляр бота
bot_manager = ImageBot(BOT_TOKEN)
db = Database()

@router.message(Command("start"))
async def start_command(message: Message):
    """Обработчик команды /start"""
    user = message.from_user
    user_id = user.id
    
    db.add_user(user_id, user.username, user.first_name, user.last_name)
    db.update_user_activity(user_id)
    
    welcome_text = """
👋 Привет! Я — бот для сохранения изображений на фотохостинге!

Как мной пользоваться:
1. Просто отправь мне изображение 📸.
2. Я сохраню его и пришлю тебе cсылку 🔗 на изображение.

Делись ссылкой с друзьями и размещай на форумах! 😊
    """
    await message.answer(welcome_text)

@router.message(Command("stats"))
async def stats_command(message: Message):
    """Обработчик команды /stats (только для администратора)"""
    user_id = message.from_user.id
    
    if not bot_manager.is_admin(user_id):
        await message.answer("❌ Эта команда доступна только администратору.")
        return
    
    try:
        bot_stats = db.get_bot_stats()
        
        stats_text = f"""
📊 Статистика бота:

👥 Всего пользователей: {bot_stats['total_users']}
📸 Всего изображений: {bot_stats['total_images']}
🔥 Активных пользователей: {bot_stats['active_users']}
        """
        
        await message.answer(stats_text)
        
    except Exception as e:
        logging.error(f"Error getting stats: {e}")
        await message.answer("❌ Ошибка при получении статистики.")

@router.message(Command("all"))
async def broadcast_command(message: Message, command: CommandObject):
    """Обработчик команды /all (рассылка, только для администратора)"""
    user_id = message.from_user.id
    
    if not bot_manager.is_admin(user_id):
        await message.answer("❌ Эта команда доступна только администратору.")
        return
    
    if not command.args:
        await message.answer("❌ Использование: /all ваше сообщение")
        return
    
    message_text = command.args
    broadcast_message = f"""
📢 Сообщение от администратора:

{message_text}
    """
    
    try:
        all_users = db.get_all_users()
        total_users = len(all_users)
        successful_sends = 0
        
        progress_msg = await message.answer(f"🔄 Начинаю рассылку для {total_users} пользователей...")
        
        for user_id in all_users:
            try:
                await bot_manager.bot.send_message(
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
        await message.answer("❌ Ошибка при рассылке сообщения.")

@router.message(F.photo)
async def handle_photo(message: Message):
    """Обработчик получения фотографии"""
    user = message.from_user
    user_id = user.id
    
    try:
        db.add_user(user_id, user.username, user.first_name, user.last_name)
        db.update_user_activity(user_id)
        
        # Скачиваем изображение
        photo = message.photo[-1]
        file_info = await bot_manager.bot.get_file(photo.file_id)
        photo_bytes = await bot_manager.bot.download_file(file_info.file_path)
        
        logging.info(f"Downloaded photo size: {len(photo_bytes.getvalue())} bytes")
        
        # Загружаем на FreeImage.host
        image_url = bot_manager.uploader.upload_image(photo_bytes.getvalue())
        
        if image_url:
            db.increment_images_count(user_id)
            db.add_image(user_id, image_url)
            
            # В Aiogram текст автоматически над медиа!
            caption_text = f"✅ Изображение загружено!\n\n🔗 Ссылка: {image_url}"
            await message.answer_photo(
                photo=image_url,
                caption=caption_text
            )
            
        else:
            await message.answer("❌ Ошибка при загрузке изображения. Попробуйте еще раз.")
            
    except Exception as e:
        logging.error(f"Error processing photo: {e}")
        await message.answer("❌ Произошла ошибка при обработке изображения.")

@router.message()
async def handle_text(message: Message):
    """Обработчик текстовых сообщений"""
    user = message.from_user
    user_id = user.id
    
    db.add_user(user_id, user.username, user.first_name, user.last_name)
    db.update_user_activity(user_id)
    
    await message.answer("📸 Отправьте мне фотографию для загрузки на фотохостинг!")

async def main():
    """Основная функция запуска"""
    if not BOT_TOKEN:
        print("❌ Токен бота не найден! Проверь файл .env")
        return
    
    await bot_manager.run()

if __name__ == "__main__":
    asyncio.run(main())