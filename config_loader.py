# config_loader.py
import os
import sys
from dataclasses import dataclass
from typing import Dict

@dataclass
class AccountConfig:
    """Структура для хранения конфигурации одного аккаунта."""
    emulator_id: str
    mitm_port: int
    nickname: str
    player_id: str
    log_path: str

def get_base_path():
    """Возвращает путь к папке, где находится .exe или .py файл."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

def load_accounts(filename="valera.txt") -> Dict[str, AccountConfig]:
    """Загружает все аккаунты из файла конфигурации."""
    accounts = {}
    base_path = get_base_path()
    full_path = os.path.join(base_path, filename)
    
    print(f"Загрузка конфигурации из: {full_path}")

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                print("Файл конфигурации пуст.")
                return {}

            records = content.split(';')
            for i, record in enumerate(records):
                if not record.strip():
                    continue
                
                parts = record.strip().split(',')
                if len(parts) == 4:
                    nick = parts[2].strip()
                    log_filename = f"{nick}_log.txt"
                    accounts[nick] = AccountConfig(
                        emulator_id=parts[0].strip(),
                        mitm_port=int(parts[1].strip()),
                        nickname=nick,
                        player_id=parts[3].strip(),
                        log_path=os.path.join(base_path, log_filename)
                    )
                else:
                    print(f"Предупреждение: Неверный формат записи #{i+1} в файле {filename}")

    except FileNotFoundError:
        print(f"ОШИБКА: Файл конфигурации '{full_path}' не найден!")
        sys.exit(1)
    except Exception as e:
        print(f"ОШИБКА: Не удалось прочитать или разобрать файл {full_path}: {e}")
        sys.exit(1)
        
    return accounts