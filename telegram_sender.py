# telegram_sender.py
import asyncio
from telegram import Bot
from typing import Dict, Any
import aiohttp

# --- ВАШИ ДАННЫЕ ---
# Замените на ваши значения
TELEGRAM_BOT_TOKEN = "8464514546:AAHHv49jVg1UBYicjgAJtKH6nzcffljkS1M"
TELEGRAM_CHAT_ID = "-1003118045362"       # ID основной группы
TELEGRAM_TOPIC_ID = 2                      # <<< ID вашей темы
# ------------------

async def send_notification(message: str):
    """Асинхронно отправляет сообщение в заданный чат и тему."""
    try:
        # Создаем новый экземпляр Bot для каждого вызова
        # Это предотвращает проблемы с закрытыми сессиями
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        
        # Используем контекстный менеджер для правильного управления ресурсами
        async with bot:
            await bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                message_thread_id=TELEGRAM_TOPIC_ID,
                text=message,
                parse_mode='Markdown'
            )
            print("[TG] Уведомление отправлено.")
            
    except Exception as e:
        print(f"[TG ERROR] Не удалось отправить сообщение: {e}")


# Альтернативная версия с использованием aiohttp напрямую
async def send_notification_direct(message: str):
    """Альтернативная версия отправки через прямой HTTP запрос."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "message_thread_id": TELEGRAM_TOPIC_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    print("[TG] Уведомление отправлено (direct).")
                else:
                    text = await response.text()
                    print(f"[TG ERROR] HTTP {response.status}: {text}")
    except Exception as e:
        print(f"[TG ERROR] Не удалось отправить сообщение (direct): {e}")