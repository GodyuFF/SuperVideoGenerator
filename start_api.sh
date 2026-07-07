#!/bin/bash
# 启动 FastAPI 后端服务 (port 8000)
# 使用方式: bash start_api.sh

cd "$(dirname "$0")"

echo "=== SuperVideoGenerator API Server ==="
echo "启动地址: http://localhost:8000"
echo "API 文档:  http://localhost:8000/docs"
echo ""

# 加载 .env 环境变量
if [ -f .env ]; then
  export $(grep -v '^#' .env | grep -v '^$' | sed 's/#.*//' | xargs)
  echo "已加载 .env 配置"
fi

.venv/scripts/python.exe -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload \
  --reload-exclude 'data/*'
