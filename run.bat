@echo off
title FRAS Enterprise - Face Recognition Attendance System
echo =========================================================================
echo   Enterprise Face Recognition Attendance System (FRAS)
echo =========================================================================
echo.

:: Check Python availability
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python 3.10+ from python.org and add it to PATH.
    pause
    exit /b
)

:: Install / Update Dependencies
echo [*] Checking dependencies from requirements.txt...
pip install -r requirements.txt --quiet

:: Launch Application
echo.
echo [*] Launching FRAS Enterprise Server on http://127.0.0.1:8000 ...
echo [*] Press Ctrl+C to stop the server.
echo.

python main.py

pause
