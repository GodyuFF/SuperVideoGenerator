#!/bin/bash
# 启动 Vite React 前端开发服务器 (port 5173)
# 使用方式: bash start_web.sh

cd "$(dirname "$0")/apps/web"

echo "=== SuperVideoGenerator Web Frontend ==="
echo "启动地址: http://localhost:5173"
echo "API 代理:  http://localhost:5173/api -> http://localhost:8000"
echo ""

npm run dev
