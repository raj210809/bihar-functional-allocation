#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Free port 8080 if an old static server is still running
if command -v ss >/dev/null 2>&1; then
  OLD_PID=$(ss -tlnp 2>/dev/null | grep ':8080' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
  if [ -n "$OLD_PID" ]; then kill "$OLD_PID" 2>/dev/null || kill -9 "$OLD_PID" 2>/dev/null || true; fi
fi

if [ ! -d "server/.venv" ]; then
  python3 -m venv server/.venv
  server/.venv/bin/pip install -q -r server/requirements.txt
fi

echo "Starting dashboard + live scraper on http://localhost:8080"
exec server/.venv/bin/python server/app.py
