@echo off
chcp 65001 >nul
:: 启动 FastAPI 后端 (port 8000)
cd /d "%~dp0"

echo === SuperVideoGenerator API Server ===
echo 启动地址: http://localhost:8000
echo API 文档:  http://localhost:8000/docs
echo.

.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload --reload-exclude "data/*"
pause
