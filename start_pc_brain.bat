@echo off
REM ═══════════════════════════════════════════════════════════════
REM  ORION — PC BRAIN LAUNCHER
REM  Starts Ollama (TinyLlama) + FastAPI backend on your PC.
REM  Pi 3 connects to this over your local network.
REM
REM  SETUP (run once):
REM    1. Install Ollama from https://ollama.com/download
REM    2. Run this script — it pulls Gemma 3 automatically
REM    3. Set ORION_API_URL=http://<YOUR_PC_IP>:8000 on the Pi
REM ═══════════════════════════════════════════════════════════════

cd /d "%~dp0"
title ORION PC BRAIN

echo.
echo  ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗
echo  ██╔══██╗██╔══██╗██║██╔═══██╗████╗  ██║
echo  ██║  ██║██████╔╝██║██║   ██║██╔██╗ ██║
echo  ██║  ██║██╔══██╗██║██║   ██║██║╚██╗██║
echo  ██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║
echo  ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝
echo.
echo  [ PC BRAIN MODE ] — AI runs here, Pi connects remotely
echo ═══════════════════════════════════════════════════════════════

REM ── Step 1: Show your PC's IP so you can put it in Pi's .env ──
echo.
echo [INFO] Your PC's Local IP Addresses:
ipconfig | findstr /i "IPv4"
echo.
echo [TIP] Set ORION_API_URL=http://<YOUR_PC_IP>:8000 in your Pi's .env file
echo.

REM ── Step 2: Check Ollama is installed ──
where ollama >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Ollama is not installed!
    echo.
    echo  Download it from: https://ollama.com/download
    echo  Install it, then run this script again.
    echo.
    pause
    exit /b 1
)
echo [OK] Ollama found.

REM ── Step 3: Pull Gemma 3 if not already present ──
echo.
echo [AI] Checking for Gemma 3 model...
ollama list | findstr /i "gemma3" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [AI] Gemma 3 not found. Downloading now (~2.5GB for 4B)...
    echo      This only happens once. Go get a coffee.
    echo.
    ollama pull gemma3
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to pull Gemma 3. Check your internet connection.
        pause
        exit /b 1
    )
    echo [OK] Gemma 3 downloaded successfully.
) else (
    echo [OK] Gemma 3 already installed.
)

REM ── Step 4: Start Ollama server in background ──
echo.
echo [1/2] Starting Ollama server (port 11434)...
start /min "Ollama Server" ollama serve
timeout /t 3 /nobreak >nul
echo [OK] Ollama running at http://localhost:11434

REM ── Step 5: Set Ollama model in .env ──
if exist ".env" (
    powershell -Command "(Get-Content '.env') -replace 'OLLAMA_MODEL=.*', 'OLLAMA_MODEL=gemma3' | Set-Content '.env'"
    echo [OK] OLLAMA_MODEL set to gemma3 in .env
)

REM ── Step 6: Activate venv and start FastAPI backend ──
echo.
echo [2/2] Starting ORION Backend (FastAPI)...

if not exist ".venv" (
    echo [SETUP] Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

REM Install/upgrade dependencies
echo [SETUP] Checking dependencies...
pip install -q -r backend\requirements.txt

echo.
echo ═══════════════════════════════════════════════════════════════
echo  ORION Brain is starting...
echo  Backend API: http://localhost:8000
echo  AI Model:    Gemma 3 4B (via Ollama)
echo  Docs:        http://localhost:8000/docs
echo ═══════════════════════════════════════════════════════════════
echo.

REM Start uvicorn — bound to 0.0.0.0 so Pi can connect
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

pause
