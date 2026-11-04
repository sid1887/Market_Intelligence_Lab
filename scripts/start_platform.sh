#!/bin/bash
# Market Intelligence Lab - Platform Bootstrapper (Milestone B6.3 & B6.4.1)
set -e

# Base directory
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "=== Market Intelligence Lab: Platform Bootstrapping ==="

# Clean up any stale listeners on ports 8000 and 3000
fuser -k 8000/tcp 2>/dev/null || true
fuser -k 3000/tcp 2>/dev/null || true
sleep 1

echo "Starting FastAPI backend on port 8000..."

# Start FastAPI backend
python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait briefly for FastAPI to initialize
sleep 2

echo "Starting Next.js frontend on port 3000..."
# Start Next.js frontend
cd "$ROOT_DIR/frontend" && npm run dev -- -p 3000 &
FRONTEND_PID=$!

cleanup() {
    echo "Shutting down Market Intelligence Lab platform..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
}
trap cleanup SIGINT SIGTERM EXIT

echo "=== Market Intelligence Lab running ==="
echo "Backend:  http://localhost:8000 (Docs: http://localhost:8000/docs)"
echo "Frontend: http://localhost:3000"
echo "Press Ctrl+C to terminate."

wait $BACKEND_PID $FRONTEND_PID
