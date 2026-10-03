@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo              EIS Gold Studio - Windows EXE Builder
echo ============================================================
echo.
echo 1. One-folder build  (recommended: easiest to test and share)
echo 2. One-file build    (single EXE, slower startup)
echo.
set /p BUILD_MODE=Choose 1 or 2 [1]: 
if "%BUILD_MODE%"=="" set BUILD_MODE=1
if not "%BUILD_MODE%"=="1" if not "%BUILD_MODE%"=="2" (
    echo Invalid choice.
    pause
    exit /b 1
)

where py >nul 2>nul
if errorlevel 1 (
    echo ERROR: Python launcher "py" was not found.
    echo Install 64-bit Python 3.11 or 3.12 from python.org and enable the launcher.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating isolated build environment...
    py -3 -m venv .venv
    if errorlevel 1 goto :failed
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :failed

echo Updating packaging tools...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :failed

echo Installing EIS Gold Studio dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 goto :failed

echo Installing PyInstaller...
python -m pip install --upgrade pyinstaller
if errorlevel 1 goto :failed

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "EIS Gold Studio.spec" del /q "EIS Gold Studio.spec"

set COMMON=--noconfirm --clean --windowed --name "EIS Gold Studio" --icon "assets\eis_gold_studio.ico" --add-data "assets;assets" --hidden-import openpyxl --hidden-import PySide6.QtSvg
if "%BUILD_MODE%"=="2" (
    echo Building a single executable. This can take several minutes...
    python -m PyInstaller %COMMON% --onefile main.py
) else (
    echo Building the recommended one-folder application...
    python -m PyInstaller %COMMON% --onedir main.py
)
if errorlevel 1 goto :failed

echo.
echo ============================================================
echo BUILD COMPLETED
if "%BUILD_MODE%"=="2" (
    echo EXE: "%CD%\dist\EIS Gold Studio.exe"
    explorer "%CD%\dist"
) else (
    echo EXE: "%CD%\dist\EIS Gold Studio\EIS Gold Studio.exe"
    explorer "%CD%\dist\EIS Gold Studio"
)
echo ============================================================
echo Test the application on this computer before sharing it.
pause
exit /b 0

:failed
echo.
echo BUILD FAILED. Read BUILD_EXE_WINDOWS.md and review the error above.
pause
exit /b 1
