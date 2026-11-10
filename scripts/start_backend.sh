#!/bin/bash
# Market Intelligence Lab - Dedicated Backend & Worker Runner
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo -e "\033[1;36m=====================================================\033[0m"
echo -e "\033[1;36m  Market Intelligence Lab — FastAPI Backend & Worker \033[0m"
echo -e "\033[1;36m=====================================================\033[0m"

# Clean up stale listeners on 8000
fuser -k 8000/tcp >/dev/null 2>&1 || true
sleep 0.5

VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
fi

export PYTHONUNBUFFERED=1

# Start Durable Asynchronous Job Worker Daemon in background
echo -e "\033[1;33m[WORKER]\033[0m Starting Durable Job Worker Daemon..."
$VENV_PYTHON -u scripts/run_worker.py &
WORKER_PID=$!
echo -e "\033[1;33m[WORKER]\033[0m Job Worker active (PID: $WORKER_PID)"

# Ensure systemd daemon is active
systemctl --user start market-universe-daemon.service 2>/dev/null || true

cleanup() {
    echo -e "\n\033[1;31mShutting down Backend & Worker services...\033[0m"
    kill $WORKER_PID 2>/dev/null || true
    fuser -k 8000/tcp >/dev/null 2>&1 || true
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

echo -e "\033[1;32m[BACKEND]\033[0m Launching FastAPI on http://0.0.0.0:8000 (Docs: http://localhost:8000/docs)..."
exec $VENV_PYTHON -u -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload --access-log --log-level info
