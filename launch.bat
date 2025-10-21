@echo off
REM ========================================
REM    Backgammon Bot Launcher
REM ========================================
setlocal

REM === НАСТРОЙКИ ПО УМОЛЧАНИЮ ===
set DEFAULT_WORK_DIR=%~dp0
set DEFAULT_ADB_HOST=127.0.0.1
set DEFAULT_ADB_PORT=5037
set DEFAULT_PROXY_PORT=8080
set DEFAULT_PLY=2
set DEFAULT_NOISE=0.01
set DEFAULT_LOG_LEVEL=1

REM === ПРОВЕРКА ПАРАМЕТРОВ ===
if "%1"=="" goto :show_menu
if "%1"=="help" goto :show_help
if "%1"=="-h" goto :show_help
if "%1"=="/?" goto :show_help

REM === БЫСТРЫЙ ЗАПУСК С ПАРАМЕТРАМИ ===
if "%1"=="quick" (
    set BOT_WORK_DIR=%DEFAULT_WORK_DIR%
    set ADB_HOST=%DEFAULT_ADB_HOST%
    set ADB_PORT=%DEFAULT_ADB_PORT%
    set BOT_LOG_LEVEL=%DEFAULT_LOG_LEVEL%
    goto :start_bot
)

REM === ИНТЕРАКТИВНОЕ МЕНЮ ===
:show_menu
cls
echo ========================================
echo    BACKGAMMON BOT - НАСТРОЙКА ЗАПУСКА
echo ========================================
echo.

REM Рабочая директория
echo Рабочая директория (Enter для текущей: %DEFAULT_WORK_DIR%):
set /p BOT_WORK_DIR=
if "%BOT_WORK_DIR%"=="" set BOT_WORK_DIR=%DEFAULT_WORK_DIR%

REM ADB настройки
echo.
echo === НАСТРОЙКИ ЭМУЛЯТОРА ===
echo IP адрес ADB (Enter для %DEFAULT_ADB_HOST%):
set /p ADB_HOST=
if "%ADB_HOST%"=="" set ADB_HOST=%DEFAULT_ADB_HOST%

echo Порт ADB (Enter для %DEFAULT_ADB_PORT%):
set /p ADB_PORT=
if "%ADB_PORT%"=="" set ADB_PORT=%DEFAULT_ADB_PORT%

REM Прокси настройки
echo.
echo === НАСТРОЙКИ ПРОКСИ ===
echo Порт прокси для mitmdump (Enter для %DEFAULT_PROXY_PORT%):
set /p PROXY_PORT=
if "%PROXY_PORT%"=="" set PROXY_PORT=%DEFAULT_PROXY_PORT%

echo Внешний прокси (формат: http://host:port, Enter если нет):
set /p UPSTREAM_PROXY=

REM GNU Backgammon настройки
echo.
echo === НАСТРОЙКИ GNU BACKGAMMON ===
echo Глубина анализа PLY (1-4, Enter для %DEFAULT_PLY%):
set /p PLY=
if "%PLY%"=="" set PLY=%DEFAULT_PLY%

echo Уровень шума NOISE (0.0-1.0, Enter для %DEFAULT_NOISE%):
set /p NOISE=
if "%NOISE%"=="" set NOISE=%DEFAULT_NOISE%

REM Уровень логирования
echo.
echo === УРОВЕНЬ ЛОГИРОВАНИЯ ===
echo 0 - Только критические ошибки
echo 1 - Важные события (рекомендуется)
echo 2 - Информационные сообщения
echo 3 - Отладочная информация
echo 4 - Подробная отладка
echo.
echo Выберите уровень (Enter для %DEFAULT_LOG_LEVEL%):
set /p BOT_LOG_LEVEL=
if "%BOT_LOG_LEVEL%"=="" set BOT_LOG_LEVEL=%DEFAULT_LOG_LEVEL%

REM Автоигра
echo.
echo Включить автоигру? (y/n, Enter для y):
set /p AUTO_PLAY_INPUT=
if "%AUTO_PLAY_INPUT%"=="" set AUTO_PLAY_INPUT=y
if /i "%AUTO_PLAY_INPUT%"=="y" (
    set BOT_AUTO_PLAY=true
) else (
    set BOT_AUTO_PLAY=false
)

goto :start_bot

REM === ЗАПУСК БОТА ===
:start_bot
cls
echo ========================================
echo           ЗАПУСК БОТА
echo ========================================
echo.
echo Конфигурация:
echo - Рабочая директория: %BOT_WORK_DIR%
echo - ADB: %ADB_HOST%:%ADB_PORT%
echo - Прокси порт: %PROXY_PORT%
echo - GNU PLY: %PLY%
echo - GNU NOISE: %NOISE%
echo - Уровень логов: %BOT_LOG_LEVEL%
echo - Автоигра: %BOT_AUTO_PLAY%
if not "%UPSTREAM_PROXY%"=="" echo - Внешний прокси: %UPSTREAM_PROXY%
echo.
echo Запускаю бота...
echo.

REM Экспортируем переменные окружения
set BOT_WORK_DIR=%BOT_WORK_DIR%
set ADB_HOST=%ADB_HOST%
set ADB_PORT=%ADB_PORT%
set BOT_LOG_LEVEL=%BOT_LOG_LEVEL%
set BOT_AUTO_PLAY=%BOT_AUTO_PLAY%

REM Создаем необходимые директории
if not exist "%BOT_WORK_DIR%\logs" mkdir "%BOT_WORK_DIR%\logs"
if not exist "%BOT_WORK_DIR%\data" mkdir "%BOT_WORK_DIR%\data"

REM Формируем команду запуска
set PYTHON_CMD=python main.py --port %PROXY_PORT% --ply %PLY% --noise %NOISE%
if not "%UPSTREAM_PROXY%"=="" set PYTHON_CMD=%PYTHON_CMD% --upstream-proxy %UPSTREAM_PROXY%

REM Переходим в рабочую директорию и запускаем
cd /d "%BOT_WORK_DIR%"
%PYTHON_CMD%

if errorlevel 1 (
    echo.
    echo ========================================
    echo    ОШИБКА ЗАПУСКА!
    echo ========================================
    echo Проверьте:
    echo 1. Установлен ли Python
    echo 2. Установлены ли все зависимости (pip install -r requirements.txt)
    echo 3. Запущен ли эмулятор Android
    echo 4. Правильно ли указаны пути и порты
    echo.
    pause
    goto :show_menu
)

goto :end

REM === СПРАВКА ===
:show_help
cls
echo ========================================
echo       BACKGAMMON BOT - СПРАВКА
echo ========================================
echo.
echo Использование:
echo   launch.bat           - Интерактивная настройка
echo   launch.bat quick     - Быстрый запуск с настройками по умолчанию
echo   launch.bat help      - Показать эту справку
echo.
echo Переменные окружения:
echo   BOT_WORK_DIR    - Рабочая директория для логов и данных
echo   ADB_HOST        - IP адрес для подключения к эмулятору
echo   ADB_PORT        - Порт ADB (обычно 5037)
echo   BOT_LOG_LEVEL   - Уровень логирования (0-4)
echo   BOT_AUTO_PLAY   - Автоматическая игра (true/false)
echo.
echo Примеры:
echo   launch.bat
echo   launch.bat quick
echo   set ADB_HOST=192.168.1.100 && launch.bat quick
echo.
pause
goto :end

:end
endlocal