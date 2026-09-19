@echo off
setlocal
:: %~dp0 = folder this script lives in, so the project works from any path.
cd /d "%~dp0"

set "PYEXE=python"
set "PYWEXE=pythonw"
if exist "venv\Scripts\python.exe" (
    set "PYEXE=venv\Scripts\python.exe"
    set "PYWEXE=venv\Scripts\pythonw.exe"
)

"%PYEXE%" --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found on PATH. Install it from python.org and
    echo         tick "Add Python to PATH" during setup.
    pause
    exit /b 1
)

if /i "%~1"=="debug" (
    echo Running in debug mode. Close this window to quit.
    "%PYEXE%" main.py
    pause
) else (
    start "" "%PYWEXE%" main.py
)
