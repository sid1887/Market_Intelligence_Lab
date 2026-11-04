#!/bin/bash
# Market Intelligence Lab - Platform Bootstrapper (Milestones B6.3, B6.4.1 & B6.5)
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

# Wait for FastAPI to initialize and verify health check
echo "Awaiting backend readiness..."
MAX_RETRIES=10
RETRIES=0
until curl -s "http://localhost:8000/api/v1/health" > /dev/null 2>&1 || [ $RETRIES -ge $MAX_RETRIES ]; do
    sleep 0.8
    RETRIES=$((RETRIES+1))
done

if [ $RETRIES -ge $MAX_RETRIES ]; then
    echo "[!] Warning: Backend health check timed out on port 8000."
else
    echo "[✓] FastAPI backend is live and healthy."
fi

# Cloudflare Tunnel Watchdog Check
echo "Checking Cloudflare Tunnel status..."
if systemctl is-active --quiet cloudflared 2>/dev/null; then
    echo "[✓] Cloudflare tunnel service (cloudflared) is ACTIVE as a systemd daemon."
elif pgrep -x cloudflared > /dev/null 2>&1; then
    echo "[✓] Cloudflare tunnel process is active."
else
    echo "[i] Cloudflare tunnel is not running as a daemon. To configure permanent tunnel:"
    echo "    Run: ./scripts/setup_permanent_tunnel.sh <tunnel_name>"
fi

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
echo "Tunnel Ingress Target: http://localhost:8000"
echo "Vercel Environment: Set NEXT_PUBLIC_API_URL to your permanent tunnel URL (e.g. https://<tunnel-host>/api/v1)"
echo "Press Ctrl+C to terminate."

wait $BACKEND_PID $FRONTEND_PID
