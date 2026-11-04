#!/usr/bin/env bash
# ==============================================================================
# Market Intelligence Lab — EOD Settlement Daemon Launcher (Milestone B10.0)
#
# Launches the autonomous post-market settlement daemon (16:15 IST).
# Can be run interactively or detached with nohup.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOGS_DIR="$PROJECT_ROOT/logs"

mkdir -p "$LOGS_DIR"
cd "$PROJECT_ROOT"

LOG_FILE="$LOGS_DIR/eod_daemon.log"
PID_FILE="$LOGS_DIR/eod_daemon.pid"

if [[ "${1:-}" == "--status" ]]; then
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "EOD Settlement Daemon is RUNNING (PID $(cat "$PID_FILE"))."
        exit 0
    else
        echo "EOD Settlement Daemon is NOT running."
        exit 1
    fi
fi

if [[ "${1:-}" == "--stop" ]]; then
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        PID="$(cat "$PID_FILE")"
        echo "Stopping EOD Settlement Daemon (PID $PID)..."
        kill -15 "$PID" 2>/dev/null || kill -9 "$PID" 2>/dev/null
        rm -f "$PID_FILE"
        echo "Daemon stopped."
    else
        echo "No running EOD Settlement Daemon found."
    fi
    exit 0
fi

if [[ "${1:-}" == "--daemon" ]]; then
    echo "Starting EOD Settlement Daemon in background mode..."
    nohup /usr/bin/python3 -m src.tasks.eod_daemon > "$LOG_FILE" 2>&1 &
    DAEMON_PID=$!
    echo "$DAEMON_PID" > "$PID_FILE"
    echo "EOD Settlement Daemon started with PID $DAEMON_PID. Logs -> $LOG_FILE"
    exit 0
fi

# Default foreground mode (passes through arguments, e.g. --run-now)
echo "Starting EOD Settlement Daemon in foreground mode..."
exec /usr/bin/python3 -m src.tasks.eod_daemon "$@"
