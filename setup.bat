@echo off
setlocal enabledelayedexpansion

echo ======================================
echo       MiniOS Windows Installer       
echo ======================================

:: Check for Python
where py >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=py"
    goto :found_python
)

where python >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=python"
    goto :found_python
)

echo [!] Error: Python is not installed or not in PATH.
echo Please install Python 3.8+ from https://www.python.org/
pause
exit /b 1

:found_python
echo [+] Using Python: %PY_CMD%

:: Setup Virtual Environment
if not exist ".venv" (
    echo [+] Creating virtual environment in .venv...
    %PY_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo [!] Failed to create virtualenv.
        pause
        exit /b 1
    )
) else (
    echo [+] Virtual environment .venv already exists.
)

:: Activate Virtual Environment
call .venv\Scripts\activate.bat

:: Install Requirements
echo [+] Installing requirements...
pip install --quiet -r requirements.txt
if %errorlevel% neq 0 (
    echo [!] Failed to install dependencies.
    pause
    exit /b 1
)
echo [+] Dependencies installed.

:: Configure .env
if not exist ".env" (
    echo [+] Creating .env from .env.example...
    copy .env.example .env >nul
    echo [+] Created .env. Fill in your API tokens if needed.
) else (
    echo [+] Existing .env found.
)

echo ======================================
echo       Setup Complete! Starting...     
echo ======================================
echo Starting MiniOS at http://127.0.0.1:2000/
python main.py
pause
