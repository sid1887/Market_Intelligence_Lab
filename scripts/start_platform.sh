#!/bin/bash
# Market Intelligence Lab - Platform Bootstrapper (Milestones B6.3, B6.4.1 & B6.5)
# Supports:
#   1. Unified Mode (Default): Shows BOTH Backend, Frontend & Worker logs in the live terminal with colored prefixes.
#   2. Separate Terminal Mode (--split or -s): Automatically spawns a dedicated terminal window for the Backend.
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="unified"
if [ "$1" = "--split" ] || [ "$1" = "-s" ] || [ "$1" = "--separate" ] || [ "$SEPARATE_TERMINAL" = "1" ] || [ "$MIL_SEPARATE_TERMINAL" = "true" ]; then
    MODE="split"
elif [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
    echo "Market Intelligence Lab - Bootstrapper Usage:"
    echo "  ./scripts/start_platform.sh           # Unified Mode: Stream BOTH Backend & Frontend logs in this terminal"
    echo "  ./scripts/start_platform.sh --split   # Separate Mode: Automatically invoke a separate window for Backend"
    echo "  ./scripts/start_platform.sh --unified # Explicit unified mode"
    echo "  ./scripts/start_backend.sh            # Run only FastAPI Backend & Worker"
    echo "  ./scripts/start_frontend.sh           # Run only Next.js Frontend"
    exit 0
fi

echo -e "\033[1;34m=====================================================\033[0m"
echo -e "\033[1;34m  Market Intelligence Lab — Platform Bootstrapper     \033[0m"
echo -e "\033[1;34m=====================================================\033[0m"

# Clean up any stale listeners on ports 8000 and 3000
echo "Verifying ports 8000 and 3000..."
fuser -k 8000/tcp >/dev/null 2>&1 || true
fuser -k 3000/tcp >/dev/null 2>&1 || true
echo "[✓] Ports 8000 & 3000 ready."
sleep 0.5

VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    VENV_PYTHON="python3"
fi
export PYTHONUNBUFFERED=1

# Helper for stream tagging with high-precision timestamps (HH:MM:SS.mmm)
prefix_stream() {
    local tag="$1"
    local color="$2"
    "$VENV_PYTHON" -u "$ROOT_DIR/scripts/prefix_stream.py" "$tag" "$color"
}

log_system() {
    local msg="$1"
    local color="${2:-\033[1;34m}"
    local dim="\033[2m"
    local reset="\033[0m"
    local ts
    ts=$(date +"%H:%M:%S.%3N")
    printf "${dim}%s${reset} ${color}%-16s${reset} │ %s\n" "$ts" "[SYSTEM]" "$msg"
}

# Function to detect available terminal emulator
detect_terminal() {
    if command -v gnome-terminal >/dev/null 2>&1; then
        echo "gnome-terminal"
    elif command -v x-terminal-emulator >/dev/null 2>&1; then
        echo "x-terminal-emulator"
    elif command -v konsole >/dev/null 2>&1; then
        echo "konsole"
    elif command -v xfce4-terminal >/dev/null 2>&1; then
        echo "xfce4-terminal"
    elif command -v xterm >/dev/null 2>&1; then
        echo "xterm"
    else
        echo ""
    fi
}

TERM_BIN=$(detect_terminal)

# If split mode requested but no GUI display or terminal available, fall back to unified
if [ "$MODE" = "split" ]; then
    if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
        echo -e "\033[1;33m[!] No GUI display detected. Falling back to Unified Live Stream mode.\033[0m"
        MODE="unified"
    elif [ -z "$TERM_BIN" ]; then
        echo -e "\033[1;33m[!] No supported terminal emulator detected. Falling back to Unified Live Stream mode.\033[0m"
        MODE="unified"
    fi
fi

# Ensure autonomous universe daemon is running in background
systemctl --user start market-universe-daemon.service 2>/dev/null || true

# ==============================================================================
# MODE 1: SEPARATE TERMINAL FOR BACKEND
# ==============================================================================
if [ "$MODE" = "split" ]; then
    echo -e "\033[1;32m[MODE: SEPARATE TERMINAL]\033[0m Invoking dedicated terminal for Backend API & Worker..."
    
    if [ "$TERM_BIN" = "gnome-terminal" ]; then
        gnome-terminal --title="Market Intelligence Lab - Backend (FastAPI :8000)" -- "$ROOT_DIR/scripts/start_backend.sh"
    elif [ "$TERM_BIN" = "konsole" ]; then
        konsole --new-tab -p tabtitle="Market Intelligence Lab - Backend" -e "$ROOT_DIR/scripts/start_backend.sh" &
    elif [ "$TERM_BIN" = "xfce4-terminal" ]; then
        xfce4-terminal --title="Market Intelligence Lab - Backend" -e "$ROOT_DIR/scripts/start_backend.sh" &
    else
        $TERM_BIN -T "Market Intelligence Lab - Backend" -e "$ROOT_DIR/scripts/start_backend.sh" &
    fi

    echo "Awaiting backend readiness on http://localhost:8000/api/v1/health..."
    MAX_RETRIES=20
    RETRIES=0
    until curl -s "http://localhost:8000/api/v1/health" > /dev/null 2>&1 || [ $RETRIES -ge $MAX_RETRIES ]; do
        sleep 0.6
        RETRIES=$((RETRIES+1))
    done

    if [ $RETRIES -ge $MAX_RETRIES ]; then
        echo -e "\033[1;31m[!] Backend health check timed out. Check the backend terminal for logs.\033[0m"
    else
        echo -e "\033[1;32m[✓] Backend is healthy & running in separate terminal.\033[0m"
    fi

    echo -e "\033[1;35mStarting Next.js Frontend in this terminal (http://localhost:3000)...\033[0m"
    
    CLEANED_UP=0
    cleanup_split() {
        if [ "$CLEANED_UP" -eq 1 ]; then return; fi
        CLEANED_UP=1
        echo -e "\n\033[1;31mShutting down platform...\033[0m"
        fuser -k 3000/tcp >/dev/null 2>&1 || true
        fuser -k 8000/tcp >/dev/null 2>&1 || true
        exit 0
    }
    trap cleanup_split SIGINT SIGTERM EXIT

    cd "$ROOT_DIR/frontend"
    exec npm run dev -- -p 3000
fi

# ==============================================================================
# MODE 2: UNIFIED LIVE STREAM (DEFAULT)
# Both Backend, Frontend & Worker logs live-streamed with color prefixes
# ==============================================================================
echo -e "\033[1;36m[MODE: UNIFIED LIVE STREAM]\033[0m Streaming Backend + Frontend + Worker logs together."
echo -e "\033[0;90mTip: To launch Backend in a separate window automatically, run:\033[0m \033[1;37m./scripts/start_platform.sh --split\033[0m\n"

# Start FastAPI backend with prefix and auto-reload on file changes
$VENV_PYTHON -u -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload --access-log --log-level info \
    > >(prefix_stream "[BACKEND:8000]" "cyan") 2>&1 &
BACKEND_PID=$!

# Wait for FastAPI readiness
log_system "Awaiting backend readiness..." "\033[1;36m"
MAX_RETRIES=20
RETRIES=0
until curl -s "http://localhost:8000/api/v1/health" > /dev/null 2>&1 || [ $RETRIES -ge $MAX_RETRIES ]; do
    sleep 0.5
    RETRIES=$((RETRIES+1))
done

if [ $RETRIES -ge $MAX_RETRIES ]; then
    log_system "Warning: Backend health check timed out." "\033[1;31m"
else
    log_system "[✓] FastAPI backend is live and healthy on :8000" "\033[1;32m"
fi

# Start Durable Asynchronous Job Worker Daemon with prefix
$VENV_PYTHON -u scripts/run_worker.py \
    > >(prefix_stream "[WORKER:JOBS]" "yellow") 2>&1 &
WORKER_PID=$!
log_system "[✓] Durable Job Worker started (PID: $WORKER_PID)" "\033[1;33m"

# Start Next.js frontend with prefix
(cd "$ROOT_DIR/frontend" && npm run dev -- -p 3000) \
    > >(prefix_stream "[FRONTEND:3000]" "magenta") 2>&1 &
FRONTEND_PID=$!
log_system "[✓] Next.js frontend started on :3000" "\033[1;35m"

CLEANED_UP=0
cleanup_unified() {
    if [ "$CLEANED_UP" -eq 1 ]; then return; fi
    CLEANED_UP=1
    printf "\n"
    log_system "Shutting down Market Intelligence Lab platform..." "\033[1;31m"
    pkill -P $BACKEND_PID 2>/dev/null || true
    kill $BACKEND_PID 2>/dev/null || true
    pkill -P $FRONTEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    pkill -P $WORKER_PID 2>/dev/null || true
    kill $WORKER_PID 2>/dev/null || true
    fuser -k 8000/tcp >/dev/null 2>&1 || true
    fuser -k 3000/tcp >/dev/null 2>&1 || true
    log_system "Platform stopped cleanly." "\033[1;31m"
}
trap cleanup_unified SIGINT SIGTERM EXIT

log_system "Platform fully operational. Real-time interleaved logs streaming below:" "\033[1;32m"
echo -e "\033[0;90m────────────────────────────────────────────────────────────────────────────────────────\033[0m"

wait $BACKEND_PID $FRONTEND_PID $WORKER_PID
