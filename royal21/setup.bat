@echo off
REM Royal 21 Setup Script (Windows)

setlocal enabledelayedexpansion

echo ======================================
echo Royal 21 Setup
echo ======================================

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.11+
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✓ Python version: %PYTHON_VERSION%

REM Create virtual environment
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    echo ✓ Virtual environment created
) else (
    echo ✓ Virtual environment already exists
)

REM Activate virtual environment
call venv\Scripts\activate.bat
echo ✓ Virtual environment activated

REM Install dependencies
echo Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
echo ✓ Dependencies installed

REM Run tests
echo.
echo Running tests...
pytest test_engine.py -v

echo.
echo ======================================
echo ✓ Setup complete!
echo ======================================
echo.
echo To start the server:
echo   python main.py
echo.
echo Then open: http://localhost:8000
echo.

pause
