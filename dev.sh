#!/bin/bash
# 一键启动前后端服务
# 使用方式: bash dev.sh
#   --api  仅启动 API
#   --web  仅启动前端

cd "$(dirname "$0")"

wait_for_api() {
  echo "等待 API health 就绪..."
  for i in $(seq 1 120); do
    if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
      echo "API 已就绪。"
      return 0
    fi
    sleep 0.5
  done
  echo "[警告] API 未在 60 秒内就绪，请检查 API 进程；仍将启动前端。"
  return 1
}

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
  # 不使用 --reload：热重载会中断正在执行的主编排，并可能误报为「用户已中止」
  $PYTHON -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
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
    echo "API 无热重载（避免长任务中途被进程重启打断）"
    echo ""
    start_api &
    API_PID=$!
    wait_for_api || true
    start_web &
    WEB_PID=$!

    trap "kill $API_PID $WEB_PID 2>/dev/null; exit" INT TERM
    wait
    ;;
esac
