@echo off
title ORION LIVE DEBUGGER
cd /d "%~dp0"
echo.
echo    [ ORION DIAGNOSTIC MODE ]
echo -----------------------------------------------
echo.

:: Check for virtual environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

:: Run the script
python scripts\debug_orion.py

pause
