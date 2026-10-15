#!/bin/sh
# Starts the API (internal) and the web app (public port) in one container.
set -e
cd /app/backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
# wait for the API so the first page load doesn't hit a 502
for i in $(seq 1 60); do
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/sources')" 2>/dev/null && break
  kill -0 $API_PID 2>/dev/null || { echo "API failed to start"; exit 1; }
  sleep 1
done
cd /app/frontend
exec node node_modules/next/dist/bin/next start -H 0.0.0.0 -p "${PORT:-10000}"
