@echo off
echo Starting ORION System...

:: Start Backend
start "ORION Brain (Backend)" cmd /k "uvicorn backend.app.main:app --reload --port 8000"

:: Wait for Backend to initialize
timeout /t 5

:: Start Client
start "ORION Body (Client)" cmd /k "python client/run_client.py"

echo ORION is running.
pause
