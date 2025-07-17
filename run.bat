@echo off
cd /d "%~dp0"

echo Starting Telegram Bot...
echo ================================

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed or not in PATH
    pause
    exit /b 1
)

:: Check if virtual environment exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Install/Update dependencies
echo Installing dependencies...
pip install -r requirements.txt

:: Check if .env file exists
if not exist ".env" (
    echo ERROR: .env file not found!
    echo Please create a .env file with your configuration
    pause
    exit /b 1
)

:: Run the bot
echo Starting bot...
python startup.py

pause