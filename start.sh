#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 关掉占用端口的进程
for port in 8000 3000; do
  pid=$(lsof -t -i:"$port" 2>/dev/null) && kill -9 "$pid" && echo "Killed pid $pid on port $port" || echo "Port $port is free"
done

# 启动后端
cd "$PROJECT_DIR"
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 &
echo $! > /tmp/backend.pid
echo "Backend starting on port 8000..."

# 启动前端
cd "$PROJECT_DIR/frontend"
npm run dev &
echo $! > /tmp/frontend.pid
echo "Frontend starting on port 3000..."

wait
