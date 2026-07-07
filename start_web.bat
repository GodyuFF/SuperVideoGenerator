@echo off
chcp 65001 >nul
:: 启动 React 前端 (port 5173)
cd /d "%~dp0apps\web"

echo === SuperVideoGenerator Web Frontend ===
echo 启动地址: http://localhost:5173
echo API 代理:  -> http://localhost:8000
echo.

call npm run dev
pause
