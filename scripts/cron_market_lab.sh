#!/bin/bash
# ==============================================================================
# Market Intelligence Lab — Automated Post-Market Cron Entry Point
# Timezone: Asia/Kolkata (IST = UTC+05:30)
#
# Recommended Crontab Schedule (Mon-Fri at 16:30 IST):
# 30 16 * * 1-5 /home/siddharth/Desktop/Market_Intelligence_Lab/scripts/cron_market_lab.sh >> /home/siddharth/Desktop/Market_Intelligence_Lab/data/cron.log 2>&1
#
# Daily Morning Recovery Schedule (Daily at 08:30 IST, including Monday catch-up):
# 30 08 * * * /home/siddharth/Desktop/Market_Intelligence_Lab/scripts/cron_market_lab.sh --recovery >> /home/siddharth/Desktop/Market_Intelligence_Lab/data/cron_recovery.log 2>&1
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${WORKSPACE_DIR}"

export TZ="Asia/Kolkata"
TODAY_DATE="$(date +%Y-%m-%d)"

echo "------------------------------------------------------------------------"
echo "Starting Market Intelligence Lab Production Workflow at $(date)"
echo "Target Date: ${TODAY_DATE}"
echo "------------------------------------------------------------------------"

# If --recovery flag is present in arguments, run missing session recovery
if [[ "$*" == *"--recovery"* ]]; then
    echo "[CRON] Executing Morning Recovery Scan (08:30 IST)..."
    python3 scripts/run_production_pipeline.py --recover-missing --max-attempts 5 "$@"
else
    # Execute daily post-market production pipeline with 17 bounded retries (15-min interval through 20:30 IST)
    python3 scripts/run_production_pipeline.py --date "${TODAY_DATE}" --max-attempts 17 --poll-interval 900 "$@"
fi
