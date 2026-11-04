@echo off
setlocal
cd /d "%~dp0"
if not exist .venv (
    python -m venv .venv || exit /b 1
    .venv\Scripts\pip install -r requirements-dev.txt || exit /b 1
)
.venv\Scripts\pyinstaller --noconsole --onefile --name pk-auto --add-data "assets;assets_default" src/main.py || exit /b 1
copy /y LEEME.txt dist\LEEME.txt >nul || exit /b 1
copy /y README.txt dist\README.txt >nul || exit /b 1
