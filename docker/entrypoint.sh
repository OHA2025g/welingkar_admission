#!/bin/sh
set -eu

cd /app/backend
uvicorn server:app --host 127.0.0.1 --port 8001 --proxy-headers --forwarded-allow-ips='*' &
backend_pid=$!

shutdown() {
  kill "$backend_pid" 2>/dev/null || true
  nginx -s quit 2>/dev/null || true
  wait "$backend_pid" 2>/dev/null || true
  exit 0
}
trap shutdown TERM INT

i=0
ready=0
while [ "$i" -lt 90 ]; do
  if curl -sf http://127.0.0.1:8001/api/openapi.json >/dev/null; then
    ready=1
    break
  fi
  if ! kill -0 "$backend_pid" 2>/dev/null; then
    echo "backend exited before it was ready"
    wait "$backend_pid" || true
    exit 1
  fi
  i=$((i + 1))
  sleep 2
done

if [ "$ready" -ne 1 ]; then
  echo "backend did not become ready in time"
  kill "$backend_pid" 2>/dev/null || true
  exit 1
fi

nginx -g 'daemon off;' &
nginx_pid=$!

while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$nginx_pid" 2>/dev/null; do
  sleep 2
done

echo "a process exited; stopping container"
kill "$backend_pid" "$nginx_pid" 2>/dev/null || true
wait || true
exit 1
