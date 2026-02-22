#!/bin/sh
# Dev startup for unified container: API with --reload, Next.js, nginx
set -e

echo "Starting API server (reload) on port 8000..."
cd /app && python -m uvicorn src.api_server:app --host 127.0.0.1 --port 8000 --reload &
API_PID=$!

echo "Starting Next.js server on port 3001..."
cd /app/web && PORT=3001 HOSTNAME=127.0.0.1 node server.js &
NEXTJS_PID=$!

sleep 2

echo "Starting nginx on port 3000..."
nginx -g "daemon off;" &
NGINX_PID=$!

wait $API_PID $NEXTJS_PID $NGINX_PID
