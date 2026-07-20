@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: Create a Desktop shortcut that launches like an app (.vbs, no black console)
:: Icon: apps/desktop/icon.ico (圆软小夜枭品牌标)

set "ICON=%~dp0apps\desktop\icon.ico"
if not exist "%ICON%" (
  echo [ERROR] Missing brand icon: %ICON%
  echo Run: python scripts\export_owl_icon.py
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update_desktop_shortcut.ps1"
if errorlevel 1 (
  echo [ERROR] Failed to create shortcut
  pause
  exit /b 1
)

echo.
echo Done. Double-click "SuperVideoGenerator" on your Desktop to start.
echo (Owl brand icon applied. Full installer packaging is not required.)
pause
