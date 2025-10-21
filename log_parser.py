# log_parser.py (обновленная версия)
import os
import time
import json
from log_handle import process_log_entry
from typing import Any, Dict, Optional

def follow(thefile):
    thefile.seek(0, os.SEEK_END)
    while True:
        line = thefile.readline()
        if not line:
            time.sleep(0.1)
            continue
        yield line

def parse_log_entry(line: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        # Убрано сообщение об ошибке, чтобы не засорять консоль
        return None

def StartParsing(log_path: str): # <-- ИЗМЕНЕНИЕ: принимаем путь как аргумент
    print(f"...::: Начало парсинга лога: {os.path.basename(log_path)} :::...")
    
    # Добавим ожидание, если mitm еще не успел создать файл
    retries = 5
    while not os.path.exists(log_path) and retries > 0:
        print(f"Файл лога пока не найден, ожидание... ({retries})")
        time.sleep(1)
        retries -= 1

    try:
        with open(log_path, 'r', encoding='utf-8') as logfile: # <-- ИЗМЕНЕНИЕ
            loglines = follow(logfile)
            for line in loglines:
                entry = parse_log_entry(line)
                if entry:
                    try:
                        process_log_entry(entry)
                    except Exception as e:
                        print(f"[WARN] Ошибка обработки записи: {e}")
    except FileNotFoundError:
        print(f"ОШИБКА: Файл лога не найден по пути: {log_path}")
    except Exception as e:
        print(f"Произошла непредвиденная ошибка на верхнем уровне: {e}")