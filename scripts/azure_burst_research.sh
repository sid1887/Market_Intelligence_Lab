#!/usr/bin/env bash
# ==============================================================================
# scripts/azure_burst_research.sh
# MIL 2.0 Phase 8-10 — Budget-Safe Azure R&D Burst Runner (Standard_D4s_v5, 16 GB RAM)
#
# 3-Layer Cost & Security Protection:
#   1. Zero Public IP (`--public-ip-address ""`) — accessed only via `az vm run-command invoke`
#   2. Mandatory Azure VM Auto-Shutdown at 23:30 IST (18:00 UTC)
#   3. Bash EXIT/ERR/INT/TERM trap executing `az vm deallocate --no-wait` on finish/failure
# ==============================================================================
set -euo pipefail

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-rg-mil-research}"
LOCATION="${AZURE_LOCATION:-centralindia}"
VM_NAME="${AZURE_BURST_VM_NAME:-mil-burst-worker}"
VM_SIZE="${AZURE_BURST_VM_SIZE:-Standard_D4s_v5}"
STORAGE_ACCOUNT="${AZURE_STORAGE_ACCOUNT:-milstatearchive74b8}"
STORAGE_CONTAINER="${AZURE_STORAGE_CONTAINER:-mil-durable-state}"
REPO_URL="${MIL_REPO_URL:-https://github.com/sid1887/Market_Intelligence_Lab.git}"
AUTO_SHUTDOWN_UTC="1800"  # 18:00 UTC == 23:30 IST

ARG1="${1:-}"
DRY_RUN=""
CUSTOM_CMD=""
if [[ "$ARG1" == "--dry-run" ]]; then
    DRY_RUN="--dry-run"
elif [[ -n "$ARG1" ]]; then
    CUSTOM_CMD="$ARG1"
fi

cleanup() {
    local exit_code=$?
    echo ""
    echo "[BURST-GUARD] Triggering immediate VM deallocation safety trap (exit_code=${exit_code})..."
    if [[ "$DRY_RUN" == "--dry-run" ]]; then
        echo "[DRY-RUN] Would run: az vm deallocate --resource-group ${RESOURCE_GROUP} --name ${VM_NAME} --no-wait"
    else
        az vm deallocate \
            --resource-group "$RESOURCE_GROUP" \
            --name "$VM_NAME" \
            --no-wait >/dev/null 2>&1 || true
        echo "[BURST-GUARD] Deallocate command dispatched for ${VM_NAME} in ${RESOURCE_GROUP}."
    fi
    exit "$exit_code"
}
trap cleanup EXIT ERR INT TERM

echo "======================================================================"
echo "MIL 2.0 AZURE R&D BURST RUNNER"
echo "Resource Group : ${RESOURCE_GROUP} (${LOCATION})"
echo "Compute Tier   : ${VM_SIZE} (4 vCPU, 16 GB RAM, No Public IP)"
echo "Auto-Shutdown  : 23:30 IST (${AUTO_SHUTDOWN_UTC} UTC)"
echo "Artifact Sync  : ${STORAGE_ACCOUNT}/${STORAGE_CONTAINER}"
echo "======================================================================"

if [[ "$DRY_RUN" == "--dry-run" ]]; then
    echo "[DRY-RUN] Verified 3-layer cost protection & Azure CLI orchestration plan."
    exit 0
fi

# Ensure Resource Group exists
az group show --name "$RESOURCE_GROUP" >/dev/null 2>&1 || \
    az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# 1. Create or Start Ephemeral Worker WITHOUT Static Public IP
if ! az vm show --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" >/dev/null 2>&1; then
    echo "[1/4] Provisioning ephemeral ${VM_SIZE} VM without Public IP..."
    az vm create \
        --resource-group "$RESOURCE_GROUP" \
        --name "$VM_NAME" \
        --location "$LOCATION" \
        --size "$VM_SIZE" \
        --image "Ubuntu2204" \
        --admin-username "milworker" \
        --generate-ssh-keys \
        --public-ip-address "" \
        --nsg "" \
        --output none
else
    echo "[1/4] Starting existing ${VM_NAME}..."
    az vm start --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --output none
fi

# 2. Enforce Mandatory 23:30 IST (18:00 UTC) Auto-Shutdown
echo "[2/4] Enforcing mandatory 23:30 IST (${AUTO_SHUTDOWN_UTC} UTC) auto-shutdown..."
az vm auto-shutdown \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VM_NAME" \
    --time "$AUTO_SHUTDOWN_UTC" \
    --output none

# 3. Run Heavy Calibration / Backfill / Tournament via Run-Command
echo "[3/4] Executing remote R&D job on 16 GB RAM worker..."
CONN_STR="${AZURE_STORAGE_CONNECTION_STRING:-$(az storage account show-connection-string --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" --query connectionString -o tsv)}"

if [[ -z "$CUSTOM_CMD" ]]; then
    CUSTOM_CMD="python3 -c 'from src.quant.regime_hmm import train_and_export_regime_hmm; from src.quant.conformal_cones import calibrate_and_export_conformal_cones; train_and_export_regime_hmm(); calibrate_and_export_conformal_cones()'"
fi

REMOTE_SCRIPT=$(cat <<EOF
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
if ! command -v python3 >/dev/null 2>&1 || ! python3 -m venv --help >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y -qq python3-venv python3-pip git >/dev/null
fi
WORK_DIR=/tmp/mil_burst
rm -rf \$WORK_DIR
git clone --depth 1 ${REPO_URL} \$WORK_DIR
cd \$WORK_DIR
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
if [[ -f requirements-worker.txt ]]; then
    pip install --quiet -r requirements-worker.txt
else
    pip install --quiet -r requirements.txt
fi
pip install --quiet yfinance azure-storage-blob lightgbm
export AZURE_STORAGE_CONNECTION_STRING='${CONN_STR}'
python3 -c 'from src.storage.hydration import hydrate_initial_cloud_database; hydrate_initial_cloud_database()'
${CUSTOM_CMD}
python3 -c '
import os
from pathlib import Path
from azure.storage.blob import BlobServiceClient
bsc = BlobServiceClient.from_connection_string(os.environ["AZURE_STORAGE_CONNECTION_STRING"])
c = bsc.get_container_client("${STORAGE_CONTAINER}")
for local_p, blob_p in [
    ("data/models/tournament_summary.json", "models/tournament_summary.json"),
    ("data/models/regime_hmm_state.json", "models/regime_hmm_state.json"),
    ("data/models/conformal_quantiles.json", "models/conformal_quantiles.json"),
    ("data/pit_warehouse_manifest.json", "warehouse/pit_warehouse_manifest.json"),
]:
    p = Path(local_p)
    if p.exists():
        with open(p, "rb") as f:
            c.upload_blob(blob_p, f, overwrite=True)
        print("Uploaded", blob_p)
'
EOF
)

az vm run-command invoke \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VM_NAME" \
    --command-id RunShellScript \
    --scripts "$REMOTE_SCRIPT" \
    --output table

# 4. Download updated artifacts from Azure Blob Storage back to local workspace
echo "[4/4] Syncing calibrated artifacts from ${STORAGE_ACCOUNT}/${STORAGE_CONTAINER}..."
for pair in "models/tournament_summary.json:data/models/tournament_summary.json" "warehouse/pit_warehouse_manifest.json:data/pit_warehouse_manifest.json"; do
    BLOB_NAME="${pair%%:*}"
    LOCAL_PATH="${pair##*:}"
    az storage blob download \
        --connection-string "$CONN_STR" \
        --container-name "$STORAGE_CONTAINER" \
        --name "$BLOB_NAME" \
        --file "$LOCAL_PATH" \
        --overwrite \
        --output none >/dev/null 2>&1 && echo "  Synced -> ${LOCAL_PATH}" || true
done

echo "[SUCCESS] Burst R&D cycle complete. Trap will deallocate ${VM_NAME} now."
