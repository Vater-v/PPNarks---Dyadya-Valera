# main.py (обновленная версия)
import atexit
import argparse
import os
import sys
from mitm_starter import StartMitm
from security import verify_machine
from config_loader import load_accounts

mitm_process = None

def cleanup():
    global mitm_process
    if mitm_process and mitm_process.poll() is None:
        mitm_process.terminate()
        mitm_process.wait()
    # Удалена остановка кликера, так как он не хранит состояние

def main():
    parser = argparse.ArgumentParser(description="Запуск программы для конкретного аккаунта.")
    
    # --- ИЗМЕНЕНИЯ В АРГУМЕНТАХ ---
    parser.add_argument(
        '--nickname', 
        type=str, 
        required=True, # Аргумент стал обязательным
        help='Никнейм аккаунта из valera.txt, для которого запускается бот.'
    )
    # Аргумент --port удален, так как порт берется из файла
    parser.add_argument(
        '--upstream-proxy', 
        type=str, 
        default=None, 
        help='Адрес внешней прокси для mitmdump в формате http[s]://host:port.'
    )
    parser.add_argument('--ply', type=int, default=2, help='Уровень анализа (plies) для GNU Backgammon.')
    parser.add_argument('--noise', type=float, default=0.01, help='Уровень шума (noise) для GNU Backgammon.')
    
    args = parser.parse_args()

    # --- НОВАЯ ЛОГИКА ЗАГРУЗКИ КОНФИГА ---
    accounts = load_accounts()
    if not accounts:
        print("В valera.txt не найдено ни одного аккаунта. Завершение работы.")
        return

    account_config = accounts.get(args.nickname)
    if not account_config:
        print(f"ОШИБКА: Аккаунт с ником '{args.nickname}' не найден в valera.txt.")
        print(f"Доступные аккаунты: {list(accounts.keys())}")
        return
    
    print("\n--- 🚀 ЗАПУСК ДЛЯ АККАУНТА ---")
    print(f"  👤 Никнейм:      {account_config.nickname}")
    print(f"  🆔 ID игрока:    {account_config.player_id[:12]}...")
    print(f"  📱 Эмулятор:     {account_config.emulator_id}")
    print(f"  🌐 Порт MITM:    {account_config.mitm_port}")
    print(f"  📋 Файл логов:   {os.path.basename(account_config.log_path)}")
    print("-----------------------------\n")

    # --- УСТАНОВКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ---
    # Эти переменные будут "видны" всем дочерним модулям и процессам
    os.environ['MITM_LOG_FILE'] = account_config.log_path
    os.environ['TARGET_EMULATOR'] = account_config.emulator_id
    os.environ['HERO_PLAYER_ID'] = account_config.player_id

    verify_machine()
    global mitm_process
    atexit.register(cleanup)
    
    from log_parser import StartParsing
    # Запускаем mitmdump с портом из конфига
    mitm_process = StartMitm(port=account_config.mitm_port, upstream_proxy=args.upstream_proxy)
    
    if not mitm_process:
        print("Не удалось запустить mitmdump. Программа завершает работу.")
        return
        
    # Запускаем парсер с путем к лог-файлу из конфига
    StartParsing(account_config.log_path)

if __name__ == '__main__':
    main()