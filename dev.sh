#!/bin/bash
# 一键启动前后端服务
# 使用方式: bash dev.sh
#   --api  仅启动 API
#   --web  仅启动前端

cd "$(dirname "$0")"

start_api() {
  echo "=== 启动 FastAPI 后端 (port 8000) ==="
  if [ -f .env ]; then
    export $(grep -v '^#' .env | grep -v '^$' | sed 's/#.*//' | xargs)
  fi
  if [ -f .venv/bin/python ]; then
    PYTHON=".venv/bin/python"
  else
    PYTHON="python"
  fi
  $PYTHON -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000 --reload \
    --reload-exclude 'data/*'
}

start_web() {
  echo "=== 启动 React 前端 (port 5173) ==="
  cd apps/web
  npm run dev
}

case "${1:-}" in
  --api)
    start_api
    ;;
  --web)
    start_web
    ;;
  *)
    echo "=== SuperVideoGenerator 开发模式 ==="
    echo "API:  http://localhost:8000/docs"
    echo "Web:  http://localhost:5173"
    echo ""
    # 并行启动
    start_api &
    API_PID=$!
    sleep 2
    start_web &
    WEB_PID=$!

    trap "kill $API_PID $WEB_PID 2>/dev/null; exit" INT TERM
    wait
    ;;
esac
