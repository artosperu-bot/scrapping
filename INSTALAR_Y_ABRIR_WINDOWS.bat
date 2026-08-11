@echo off
setlocal
cd /d "%~dp0"
title Product Intelligence V9
where py >nul 2>&1
if errorlevel 1 (
  echo Necesitas Python 3.11/3.12 instalado y agregado al PATH.
  pause
  exit /b 1
)
if not exist .venv (
  py -3 -m venv .venv
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -e ".[browser]"
set PLAYWRIGHT_BROWSERS_PATH=%LOCALAPPDATA%\ms-playwright
python -m playwright install chromium
python run_desktop.py
