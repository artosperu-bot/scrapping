@echo off
setlocal
cd /d "%~dp0"
title Product Intelligence V9 - Construir EXE

echo =====================================================
echo   PRODUCT INTELLIGENCE V9 - BUILD WINDOWS
echo =====================================================
echo.

where py >nul 2>&1
if errorlevel 1 (
  echo ERROR: Necesitas Python 3.11 o 3.12 instalado en Windows.
  echo Descargalo desde python.org y marca "Add Python to PATH".
  pause
  exit /b 1
)

set PYVER=
py -3.12 -c "import sys" >nul 2>&1 && set PYVER=-3.12
if not defined PYVER py -3.11 -c "import sys" >nul 2>&1 && set PYVER=-3.11
if not defined PYVER (
  echo ERROR: Instala Python 3.12 o 3.11. Evita compilar este proyecto con Python 3.14 por compatibilidad de dependencias.
  pause
  exit /b 1
)

if not exist .venv-build (
  py %PYVER% -m venv .venv-build
)
call .venv-build\Scripts\activate.bat
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e ".[browser]" pyinstaller
if errorlevel 1 goto :error

if not exist vendor\ms-playwright mkdir vendor\ms-playwright
set PLAYWRIGHT_BROWSERS_PATH=%CD%\vendor\ms-playwright
python -m playwright install chromium
if errorlevel 1 goto :error

pyinstaller --noconfirm --clean ProductIntelligence.spec
if errorlevel 1 goto :error

echo.
echo =====================================================
echo EXE CREADO CORRECTAMENTE:
echo %CD%\dist\ProductIntelligence\ProductIntelligence.exe
echo =====================================================
start "" "%CD%\dist\ProductIntelligence"
pause
exit /b 0

:error
echo.
echo ERROR DURANTE LA COMPILACION. Revisa el texto anterior.
pause
exit /b 1
