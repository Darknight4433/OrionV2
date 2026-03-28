@echo off
REM ORION Headless Client Launcher
REM Terminal-based interface (no GUI)

setlocal enabledelayedexpansion

echo.
echo ============================================================================
echo ORION HEADLESS CLIENT
echo ============================================================================
echo.

REM Check if running from correct directory
if not exist backend\app\main.py (
    echo ERROR: Must run from PROJECT-ORION root directory
    exit /b 1
)

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    exit /b 1
)

REM Check virtual environment
if not exist .venv\Scripts\python.exe (
    echo ERROR: Virtual environment not found
    echo Run: python -m venv .venv
    exit /b 1
)

REM Activate venv
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Could not activate virtual environment
    exit /b 1
)

REM Check client dependencies
echo [CHECK] Verifying dependencies...
python -c "import speech_recognition, requests, pyttsx3, pygame" 2>nul
if errorlevel 1 (
    echo [SETUP] Installing client dependencies...
    pip install -r client\requirements.txt -q
)

echo.
echo [INFO] Backend should be running at http://localhost:8000
echo [INFO] If not running, start it in another terminal:
echo        python backend/app/main.py
echo.

pause

REM Start client
cd client
python run_client.py

pause
