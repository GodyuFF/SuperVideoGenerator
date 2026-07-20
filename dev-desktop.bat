@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: Dev alias: same as launch-desktop.bat (Electron manages API+Vite)
call "%~dp0launch-desktop.bat"
