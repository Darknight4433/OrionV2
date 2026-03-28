@echo off
REM ORION Test Suite Quick Start
REM This script prepares and runs the validation test suite

setlocal enabledelayedexpansion

echo.
echo ============================================================================
echo ORION END-TO-END VALIDATION TEST SUITE
echo ============================================================================
echo.

REM Check prerequisites
echo [PRE-CHECK] Verifying prerequisites...

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found in PATH
    exit /b 1
)
echo OK: Python found

REM Check if backend directory exists
if not exist backend\app\main.py (
    echo ERROR: backend/app/main.py not found
    exit /b 1
)
echo OK: Backend code found

REM Check if test file exists
if not exist test_orion_validation.py (
    echo ERROR: test_orion_validation.py not found
    exit /b 1
)
echo OK: Test suite found

echo.
echo [SETUP] Installing required dependencies...
pip install requests aiohttp pydantic -q

echo.
echo ============================================================================
echo WHAT DO YOU WANT TO RUN?
echo ============================================================================
echo.
echo 1) Quick Test (Phase 1-6, ~15 min)
echo 2) Single Phase Test (choose 1-6)
echo 3) Continuous 3-Hour Stress Test
echo 4) View Last Results
echo.

set /p choice="Enter choice (1-4): "

if "%choice%"=="1" (
    goto run_all_tests
) else if "%choice%"=="2" (
    goto run_single_phase
) else if "%choice%"=="3" (
    goto run_continuous
) else if "%choice%"=="4" (
    goto view_results
) else (
    echo Invalid choice
    exit /b 1
)

:run_all_tests
echo.
echo [INFO] Running all 6 phases...
echo [INFO] Make sure:
echo   - Backend is running: python backend/app/main.py
echo   - Ollama is running: ollama serve
echo   - Internet is connected
echo.
pause
python test_orion_validation.py
goto end

:run_single_phase
echo.
set /p phase="Enter phase number (1-6): "
if "%phase%" geq "1" if "%phase%" leq "6" (
    python test_orion_validation.py --phase %phase%
) else (
    echo Invalid phase number
    exit /b 1
)
goto end

:run_continuous
echo.
set /p duration="Enter duration (minutes, default 180): "
if "%duration%"=="" set duration=180
python test_orion_validation.py --continuous --duration %duration%
goto end

:view_results
echo.
if exist test_orion_validation_results.json (
    type test_orion_validation_results.json
) else (
    echo No results file found. Run tests first.
)
goto end

:end
echo.
echo ============================================================================
echo Test completed!
echo Results saved to:
echo   - test_orion_validation.log (full log)
echo   - test_orion_validation_results.json (machine-readable)
echo ============================================================================
echo.
pause
