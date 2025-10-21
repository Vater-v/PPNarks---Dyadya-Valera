# session_logger.py
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional
import os, sys


def get_base_path():
    """
    Возвращает путь к папке, где находится .exe файл (или .py скрипт),
    независимо от того, откуда он был запущен.
    """
    if getattr(sys, 'frozen', False):
        # Если приложение "заморожено" в .exe файл
        return os.path.dirname(sys.executable)
    else:
        # Если это обычный .py скрипт
        return os.path.dirname(os.path.abspath(__file__))

# --- КОНФИГУРАЦИЯ ---
# Определяем базовый путь к папке с программой
_BASE_PATH = get_base_path()
# Создаем полные, абсолютные пути к файлам логов
JSON_LOG_FILE = os.path.join(_BASE_PATH, "session_log_json.txt")
HUMAN_LOG_FILE = os.path.join(_BASE_PATH, "session_log.txt")
# --------------------

def get_last_hash() -> Optional[str]:
    """
    Читает последнюю строку JSON-лога и возвращает её хеш.
    Это нужно для создания цепочки хешей, усложняющей подделку.
    """
    if not os.path.exists(JSON_LOG_FILE):
        return None
    try:
        with open(JSON_LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if not lines:
                return None
            # Пытаемся загрузить последнюю непустую строку
            for line in reversed(lines):
                if line.strip():
                    last_log_entry = json.loads(line)
                    return last_log_entry.get('hash')
    except (IOError, json.JSONDecodeError, IndexError):
        # Если файл поврежден или пуст, начинаем новую цепочку
        return None
    return None

def _create_entry_hash(data_to_hash: Dict, prev_hash: Optional[str]) -> str:
    """
    Создает SHA-256 хеш на основе данных матча и хеша предыдущей записи.
    """
    # Сериализуем данные в стабильную строку JSON (сортируем ключи)
    data_string = json.dumps(data_to_hash, sort_keys=True, ensure_ascii=False)
    
    # Используем хеш предыдущей записи. Если его нет, используем "genesis_block"
    prev_hash_str = prev_hash or "genesis_block_string_for_extra_security_000"
    
    # Конкатенируем и хешируем
    combined_string = data_string + prev_hash_str
    
    # Возвращаем hex-дайджест
    return hashlib.sha256(combined_string.encode('utf-8')).hexdigest()

def _format_human_readable_entry(log_data: Dict[str, Any]) -> str:
    """Форматирует лог в человекочитаемый вид."""
    
    ts = log_data['timestamp']
    start_data = log_data.get('match_start_data') or {}
    end_data = log_data['match_end_data']
    
    hero = end_data.get('hero_nickname', 'N/A')
    opp = end_data.get('opp_nickname', 'N/A')
    winner = end_data.get('winner', 'N/A')
    profit = end_data.get('profit')
    currency = end_data.get('bet_currency', '')
    
    # <<< НАЧАЛО ИЗМЕНЕНИЙ >>>
    start_hash = start_data.get('match_start_hash', 'N/A')
    # <<< КОНЕЦ ИЗМЕНЕНИЙ >>>
    
    result_str = "неизвестен"
    if profit is not None:
        if float(profit) >= 0:
            result_str = f"ВЫИГРЫШ {abs(profit)} {currency}"
        else:
            result_str = f"ПРОИГРЫШ {abs(profit)} {currency}"
            
    return (
        f"=====================================================\n"
        f"Время: {ts}\n"
        f"Матч: {hero} vs {opp}\n"
        f"Победитель: {winner}\n"
        f"Результат для нас: {result_str}\n"
        # <<< НАЧАЛО ИЗМЕНЕНИЙ >>>
        f"Хеш старта (для сверки с TG): {start_hash[:16]}...\n"
        # <<< КОНЕЦ ИЗМЕНЕНИЙ >>>
        f"Хеш записи: {log_data.get('hash', 'N/A')[:16]}...\n"
        f"=====================================================\n\n"
    )

def log_session(match_end_data: Dict[str, Any], match_start_data: Optional[Dict[str, Any]] = None): # <<< ИЗМЕНЕНО
    """
    Главная функция: принимает данные о матче и записывает их в оба лог-файла.
    """
    if not match_end_data:
        print("[LOGGER] Получены пустые данные, логирование отменено.")
        return

    print("[LOGGER] Запись сессии в лог...")
    
    try:
        # 1. Подготовка данных
        timestamp = datetime.now().isoformat()
        previous_hash = get_last_hash()
        
        # Для создания хеша записи теперь используем все данные
        combined_data_for_hash = {
            "start": match_start_data,
            "end": match_end_data
        }
        current_hash = _create_entry_hash(combined_data_for_hash, previous_hash) # <<< ИЗМЕНЕНО
        
        json_log_entry = {
            "timestamp": timestamp,
            "match_start_data": match_start_data, # <<< ДОБАВЛЕНО
            "match_end_data": match_end_data, # <<< ИЗМЕНЕНО (было match_data)
            "previous_hash": previous_hash,
            "hash": current_hash
        }

        # 2. Запись в JSON лог
        with open(JSON_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(json_log_entry, ensure_ascii=False) + '\n')
            
        # 3. Запись в человекочитаемый лог
        human_readable_entry = _format_human_readable_entry(json_log_entry)
        with open(HUMAN_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(human_readable_entry)
            
        print(f"[LOGGER] Сессия успешно записана. Хеш: {current_hash[:16]}...")

    except Exception as e:
        print(f"[LOGGER ERROR] Не удалось записать лог сессии: {e}")