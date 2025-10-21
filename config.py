# config.py - Централизованная конфигурация
import os
import json
from typing import Dict, Any

class LogLevel:
    """Уровни логирования"""
    CRITICAL = 0  # Только критические ошибки
    IMPORTANT = 1  # Важные события (решения GNU, ходы)
    INFO = 2      # Информационные сообщения
    DEBUG = 3     # Отладочная информация
    VERBOSE = 4   # Подробная отладка

class Config:
    """Глобальная конфигурация приложения"""
    
    def __init__(self):
        # Загружаем из переменных окружения или используем значения по умолчанию
        self.WORK_DIR = os.environ.get("BOT_WORK_DIR", os.path.dirname(os.path.abspath(__file__)))
        self.LOG_LEVEL = int(os.environ.get("BOT_LOG_LEVEL", LogLevel.IMPORTANT))
        self.AUTO_PLAY = os.environ.get("BOT_AUTO_PLAY", "true").lower() == "true"
        
        # ADB настройки
        self.ADB_HOST = os.environ.get("ADB_HOST", "127.0.0.1")
        self.ADB_PORT = int(os.environ.get("ADB_PORT", 5037))
        
        # Пути к файлам
        self.LOGS_DIR = os.path.join(self.WORK_DIR, "logs")
        self.DATA_DIR = os.path.join(self.WORK_DIR, "data")
        self.CONFIG_FILE = os.path.join(self.WORK_DIR, "bot_config.json")
        
        # Создаем необходимые директории
        os.makedirs(self.LOGS_DIR, exist_ok=True)
        os.makedirs(self.DATA_DIR, exist_ok=True)
        
        # Загружаем дополнительные настройки из файла, если существует
        if os.path.exists(self.CONFIG_FILE):
            with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                additional_config = json.load(f)
                for key, value in additional_config.items():
                    setattr(self, key, value)
    
    def save_config(self):
        """Сохранение текущей конфигурации в файл"""
        config_dict = {
            "LOG_LEVEL": self.LOG_LEVEL,
            "AUTO_PLAY": self.AUTO_PLAY,
            "ADB_HOST": self.ADB_HOST,
            "ADB_PORT": self.ADB_PORT,
        }
        with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)

# Глобальный экземпляр конфигурации
config = Config()

class Logger:
    """Централизованный логгер с управлением уровнями"""
    
    @staticmethod
    def log(message: str, level: int = LogLevel.INFO, prefix: str = ""):
        """Вывод сообщения если уровень логирования позволяет"""
        if level <= config.LOG_LEVEL:
            if prefix:
                print(f"[{prefix}] {message}")
            else:
                print(message)
    
    @staticmethod
    def critical(message: str, prefix: str = "CRITICAL"):
        Logger.log(message, LogLevel.CRITICAL, prefix)
    
    @staticmethod
    def important(message: str, prefix: str = ""):
        Logger.log(message, LogLevel.IMPORTANT, prefix)
    
    @staticmethod
    def info(message: str, prefix: str = "INFO"):
        Logger.log(message, LogLevel.INFO, prefix)
    
    @staticmethod
    def debug(message: str, prefix: str = "DEBUG"):
        Logger.log(message, LogLevel.DEBUG, prefix)
    
    @staticmethod
    def verbose(message: str, prefix: str = "VERBOSE"):
        Logger.log(message, LogLevel.VERBOSE, prefix)