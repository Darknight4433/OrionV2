@echo off
setlocal

:: ═══════════════════════════════════════════════
:: ORION EXECUTIVE SYSTEM — UNIFIED BOOT LOADER
:: ═══════════════════════════════════════════════

title ORION Executive System
cd /d "%~dp0"

echo.
echo    [ ORION BOOT SEQUENCER ]
echo -----------------------------------------------

:: 1. Virtual Environment Activation
if exist ".venv\Scripts\activate.bat" (
    echo [OK] Activating virtual environment...
    call .venv\Scripts\activate.bat
) else (
    echo [WARN] .venv not found. Attempting global python...
)

:: 2. Cleanup old sessions
echo [OK] Clearing stale processes...
taskkill /F /IM python.exe /T 2>nul
timeout /t 1 /nobreak >nul

:: 3. Directory Verification
if not exist "logs" mkdir logs
if not exist "data" mkdir data

:: 4. Start Brain (Background)
echo [1/2] Initializing ORION Brain (FastAPI)...
start "ORION Brain (Logs)" cmd /k "uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"

:: 5. Wait for Brain to stabilize
echo       Waiting for neural initialization (10s)...
timeout /t 10 /nobreak >nul

:: 6. Launch Dashboard (Foreground)
echo [2/2] Launching Dashboard Interface...
python client\gui_client.py

echo.
echo ORION Session Ended.
pause
