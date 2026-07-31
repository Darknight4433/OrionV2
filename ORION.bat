@echo off
title ORION V2
cd /d "%~dp0"

echo.
echo  ██████╗ ██████╗ ██╗ ██████╗ ███╗   ██╗
echo  ██╔══██╗██╔══██╗██║██╔═══██╗████╗  ██║
echo  ██║  ██║██████╔╝██║██║   ██║██╔██╗ ██║
echo  ██║  ██║██╔══██╗██║██║   ██║██║╚██╗██║
echo  ██████╔╝██║  ██║██║╚██████╔╝██║ ╚████║
echo  ╚═════╝ ╚═╝  ╚═╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝
echo.
echo  Starting ORION V2...
echo ═══════════════════════════════════════════════

REM ── Check .env exists ──
if not exist ".env" (
    echo [SETUP] .env not found. Creating from template...
    copy .env.example .env
    echo [!] Please edit .env and add your GROQ_API_KEY
    notepad .env
)

REM ── Show your IP for Pi setup ──
echo.
echo [NET] Your PC IP (for Pi .env):
ipconfig | findstr /i "IPv4"
echo.

REM ── Start Ollama in background (offline fallback) ──
where ollama >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [AI] Starting Ollama...
    start /min "Ollama" ollama serve
    timeout /t 2 /nobreak >nul
    echo [OK] Ollama running on :11434
) else (
    echo [WARN] Ollama not found - offline fallback unavailable
)

REM ── Start FastAPI backend in background ──
echo.
echo [1/2] Starting ORION Backend...
start /min "ORION Backend" cmd /c "cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000"
timeout /t 4 /nobreak >nul
echo [OK] Backend running on :8000

REM ── Start GUI client ──
echo [2/2] Starting ORION Dashboard...
echo.
python client\gui_client.py

REM ── Cleanup on exit ──
echo.
echo [SHUTDOWN] Closing ORION...
taskkill /fi "WindowTitle eq ORION Backend" /f >nul 2>&1
taskkill /fi "WindowTitle eq Ollama" /f >nul 2>&1
