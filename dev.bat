@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: SuperVideoGenerator 一键启动脚本
:: dev.bat        同时启动 API 和前端
:: dev.bat --api  仅启动 API
:: dev.bat --web  仅启动前端

if /i "%~1"=="--api" goto :api
if /i "%~1"=="--web" goto :web

:: 默认：并行启动前后端
echo ============================================
echo   SuperVideoGenerator 开发模式 (前后端)
echo   API:  http://localhost:8000/docs
echo   Web:  http://localhost:5173
echo ============================================
echo.

echo 正在启动 API 服务...
start "SVG-API" cmd /c ".venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload --reload-exclude data/*"

timeout /t 3 /nobreak >nul

echo 正在启动前端服务...
start "SVG-Web" cmd /c "cd /d %~dp0apps\web && npm run dev"

echo.
echo 两个服务已在新窗口中启动。
echo 关闭对应窗口即可停止服务。
pause
exit /b

:api
echo === SuperVideoGenerator API Server ===
echo 启动地址: http://localhost:8000
echo API 文档:  http://localhost:8000/docs
echo.
.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload --reload-exclude "data/*"
pause
exit /b

:web
cd /d "%~dp0apps\web"
echo === SuperVideoGenerator Web Frontend ===
echo 启动地址: http://localhost:5173
echo API 代理:  -^> http://localhost:8000
echo.
call npm run dev
pause
exit /b
