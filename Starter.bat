@echo off
title Dyadya Valera Development Environment

:: Переходим в директорию, где находится сам батник
cd /d "%~dp0"

echo [INFO] Preparing Dyadya Valera development environment...
echo.

:: Проверяем, существует ли папка venv, и если нет - создаем и устанавливаем зависимости
if not exist "venv" (
    echo [SETUP] Virtual environment not found. Creating it for the first time...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Python not found or failed to create venv.
        pause
        exit /b
    )
    
    echo [SETUP] Installing dependencies from requirements.txt...
    call .\venv\Scripts\activate.bat
    pip install -r requirements.txt
    echo [SUCCESS] Environment is ready.
)

echo [INFO] Activating virtual environment...
echo You can now use commands like 'pip', 'python', etc. within this terminal.
echo.

:: Запускаем новую сессию командной строки с уже активированным venv
cmd /k ".\venv\Scripts\activate.bat"
