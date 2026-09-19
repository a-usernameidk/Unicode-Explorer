@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Checking Python...
python --version >nul 2>&1 || (
    echo [ERROR] Python not found on PATH. Install from python.org first.
    pause & exit /b 1
)

echo [2/3] Creating virtual environment...
if not exist "venv\Scripts\python.exe" python -m venv venv || (
    echo [ERROR] Could not create venv.
    pause & exit /b 1
)

echo [3/3] Installing dependencies...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt || (
    echo [ERROR] Dependency install failed.
    pause & exit /b 1
)

echo.
echo Done. Launch with run.bat  (or "run.bat debug" to see logs).
pause
