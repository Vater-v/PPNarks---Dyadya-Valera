#!/usr/bin/env python3
"""
Удобный запуск бота с конфигурацией
"""
import os
import sys
import json
import argparse
from pathlib import Path

def create_default_config(config_path):
    """Создание файла конфигурации по умолчанию"""
    default_config = {
        "work_dir": str(Path.cwd()),
        "adb": {
            "host": "127.0.0.1",
            "port": 5037
        },
        "proxy": {
            "port": 8080,
            "upstream": None
        },
        "gnubg": {
            "ply": 2,
            "noise": 0.01
        },
        "bot": {
            "log_level": 1,  # IMPORTANT
            "auto_play": True
        }
    }
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(default_config, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Создан файл конфигурации: {config_path}")
    return default_config

def load_config(config_path):
    """Загрузка конфигурации из файла"""
    if not os.path.exists(config_path):
        return create_default_config(config_path)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠ Ошибка чтения конфигурации: {e}")
        print("Использую настройки по умолчанию...")
        return create_default_config(config_path + ".backup")

def main():
    parser = argparse.ArgumentParser(
        description="Backgammon Bot - удобный запуск",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  python run_bot.py                    # Запуск с конфигом по умолчанию
  python run_bot.py --config my.json   # Использовать свой конфиг
  python run_bot.py --log-level 0      # Только критические ошибки
  python run_bot.py --no-auto          # Отключить автоигру
  python run_bot.py --adb 192.168.1.100:5037  # Удаленный эмулятор
        """
    )
    
    parser.add_argument('--config', default='bot_config.json',
                       help='Путь к файлу конфигурации (по умолчанию: bot_config.json)')
    parser.add_argument('--work-dir',
                       help='Рабочая директория для логов и данных')
    parser.add_argument('--adb',
                       help='ADB подключение в формате host:port (например: 127.0.0.1:5037)')
    parser.add_argument('--proxy-port', type=int,
                       help='Порт для mitmdump прокси')
    parser.add_argument('--upstream-proxy',
                       help='Внешний прокси (формат: http://host:port)')
    parser.add_argument('--ply', type=int, choices=[1, 2, 3, 4],
                       help='Глубина анализа GNU Backgammon (1-4)')
    parser.add_argument('--noise', type=float,
                       help='Уровень шума GNU Backgammon (0.0-1.0)')
    parser.add_argument('--log-level', type=int, choices=[0, 1, 2, 3, 4],
                       help='Уровень логирования (0=критические, 1=важные, 2=инфо, 3=отладка, 4=подробно)')
    parser.add_argument('--no-auto', action='store_true',
                       help='Отключить автоматическую игру')
    parser.add_argument('--save-config', action='store_true',
                       help='Сохранить текущие настройки в конфиг')
    
    args = parser.parse_args()
    
    # Загружаем базовую конфигурацию
    config = load_config(args.config)
    
    # Применяем параметры командной строки
    if args.work_dir:
        config['work_dir'] = args.work_dir
    
    if args.adb:
        try:
            host, port = args.adb.split(':')
            config['adb']['host'] = host
            config['adb']['port'] = int(port)
        except ValueError:
            print(f"⚠ Неверный формат ADB: {args.adb}. Используйте host:port")
            sys.exit(1)
    
    if args.proxy_port:
        config['proxy']['port'] = args.proxy_port
    
    if args.upstream_proxy:
        config['proxy']['upstream'] = args.upstream_proxy
    
    if args.ply:
        config['gnubg']['ply'] = args.ply
    
    if args.noise is not None:
        config['gnubg']['noise'] = args.noise
    
    if args.log_level is not None:
        config['bot']['log_level'] = args.log_level
    
    if args.no_auto:
        config['bot']['auto_play'] = False
    
    # Сохраняем конфигурацию если запрошено
    if args.save_config:
        with open(args.config, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"✓ Конфигурация сохранена в {args.config}")
    
    # Устанавливаем переменные окружения
    os.environ['BOT_WORK_DIR'] = config['work_dir']
    os.environ['ADB_HOST'] = config['adb']['host']
    os.environ['ADB_PORT'] = str(config['adb']['port'])
    os.environ['BOT_LOG_LEVEL'] = str(config['bot']['log_level'])
    os.environ['BOT_AUTO_PLAY'] = 'true' if config['bot']['auto_play'] else 'false'
    
    # Создаем необходимые директории
    work_dir = Path(config['work_dir'])
    (work_dir / 'logs').mkdir(parents=True, exist_ok=True)
    (work_dir / 'data').mkdir(parents=True, exist_ok=True)
    
    # Выводим конфигурацию
    print("\n" + "="*50)
    print("     BACKGAMMON BOT - ЗАПУСК")
    print("="*50)
    print(f"📁 Рабочая директория: {config['work_dir']}")
    print(f"📱 ADB: {config['adb']['host']}:{config['adb']['port']}")
    print(f"🌐 Прокси порт: {config['proxy']['port']}")
    if config['proxy'].get('upstream'):
        print(f"🔗 Внешний прокси: {config['proxy']['upstream']}")
    print(f"🎲 GNU Backgammon: ply={config['gnubg']['ply']}, noise={config['gnubg']['noise']}")
    print(f"📊 Уровень логов: {config['bot']['log_level']} ({['CRITICAL', 'IMPORTANT', 'INFO', 'DEBUG', 'VERBOSE'][config['bot']['log_level']]})")
    print(f"🎮 Автоигра: {'✓' if config['bot']['auto_play'] else '✗'}")
    print("="*50 + "\n")
    
    # Формируем команду запуска
    cmd_parts = [
        sys.executable,  # Python интерпретатор
        'main.py',
        '--port', str(config['proxy']['port']),
        '--ply', str(config['gnubg']['ply']),
        '--noise', str(config['gnubg']['noise']),
    ]
    
    if config['proxy'].get('upstream'):
        cmd_parts.extend(['--upstream-proxy', config['proxy']['upstream']])
    
    # Переходим в рабочую директорию
    os.chdir(config['work_dir'])
    
    # Запускаем основной скрипт
    import subprocess
    try:
        result = subprocess.run(cmd_parts, check=False)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n\n⚠ Остановлено пользователем (Ctrl+C)")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Ошибка запуска: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()