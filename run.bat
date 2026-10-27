@echo off
title FRAS Enterprise - Face Recognition Attendance System
echo =========================================================================
echo   Enterprise Face Recognition Attendance System (FRAS)
echo =========================================================================
echo.

:: Check Python availability
set PYTHON_BIN=python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    py --version >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_BIN=py
    ) else (
        echo [ERROR] Python is not installed or not in PATH!
        echo Please install Python 3.10+ from python.org and add it to PATH.
        pause
        exit /b
    )
)

:: Initialize .env from .env.example if missing
if not exist .env (
    if exist .env.example (
        echo [*] Initializing .env configuration from .env.example...
        copy .env.example .env >nul
    )
)

:: Install / Update Dependencies
echo [*] Checking dependencies from requirements.txt...
%PYTHON_BIN% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [WARNING] Some dependencies had warnings during install. Proceeding with launch...
)

:: Launch Application
echo.
echo [*] Launching FRAS Enterprise Server...
echo [*] Admin management CLI available via: %PYTHON_BIN% manage_admin.py
echo [*] Press Ctrl+C to stop the server.
echo.

%PYTHON_BIN% main.py

pause
