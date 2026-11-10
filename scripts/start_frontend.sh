#!/bin/bash
# Market Intelligence Lab - Dedicated Next.js Frontend Runner
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo -e "\033[1;35m=====================================================\033[0m"
echo -e "\033[1;35m  Market Intelligence Lab — Next.js Frontend (3000)  \033[0m"
echo -e "\033[1;35m=====================================================\033[0m"

# Clean up stale listeners on 3000
fuser -k 3000/tcp >/dev/null 2>&1 || true
sleep 0.5

cleanup() {
    echo -e "\n\033[1;31mShutting down Frontend service...\033[0m"
    fuser -k 3000/tcp >/dev/null 2>&1 || true
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

cd "$ROOT_DIR/frontend"
exec npm run dev -- -p 3000
