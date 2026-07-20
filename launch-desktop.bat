@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: Silent-ish console launcher (logs visible). Prefer double-click launch-desktop.vbs
:: or Desktop shortcut via scripts\update_desktop_shortcut.ps1

if not defined ELECTRON_MIRROR set "ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/"
set "BROWSER=none"
set "DESKTOP_WEB_URL=http://localhost:5173"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Missing .venv\Scripts\python.exe
  pause
  exit /b 1
)

echo Preparing Electron...
pushd apps\desktop
call node ensure-electron.cjs
if errorlevel 1 (
  echo [ERROR] ensure-electron failed
  popd
  pause
  exit /b 1
)

echo Starting SuperVideoGenerator Desktop...
echo API + Vite auto-start inside Electron. Close the app window to exit.
call npm start
set "_ec=%ERRORLEVEL%"
popd
if not "%_ec%"=="0" (
  echo [ERROR] exit %_ec%
  pause
  exit /b %_ec%
)
