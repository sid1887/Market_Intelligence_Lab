#!/usr/bin/env bash
# ==============================================================================
# scripts/azure_burst_research.sh
# MIL 2.0 Phase 8 — Budget-Safe Azure R&D Burst Runner (Standard_D4s_v5, 16 GB RAM)
#
# 3-Layer Cost & Security Protection:
#   1. Zero Public IP (`--public-ip-address ""`) — accessed only via `az vm run-command invoke`
#   2. Mandatory Azure VM Auto-Shutdown at 23:30 IST (18:00 UTC)
#   3. Bash EXIT/ERR/INT/TERM trap executing `az vm deallocate --no-wait` on finish/failure
# ==============================================================================
set -euo pipefail

RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-rg-mil-research}"
LOCATION="${AZURE_LOCATION:-indiasouthcentral}"
VM_NAME="${AZURE_BURST_VM_NAME:-mil-burst-worker}"
VM_SIZE="${AZURE_BURST_VM_SIZE:-Standard_D4s_v5}"
STORAGE_ACCOUNT="${AZURE_STORAGE_ACCOUNT:-milstatearchive74b8}"
STORAGE_CONTAINER="${AZURE_STORAGE_CONTAINER:-mil-durable-state}"
REPO_URL="${MIL_REPO_URL:-https://github.com/sid1887/Market_Intelligence_Lab.git}"
AUTO_SHUTDOWN_UTC="1800"  # 18:00 UTC == 23:30 IST

DRY_RUN="${1:-}"

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

# 3. Run Heavy Calibration (3-State HMM + Adaptive Conformal Cones) via Run-Command
echo "[3/4] Executing offline HMM + Conformal calibration on 16 GB RAM worker..."
CONN_STR="${AZURE_STORAGE_CONNECTION_STRING:-$(az storage account show-connection-string --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" --query connectionString -o tsv)}"

az vm run-command invoke \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VM_NAME" \
    --command-id RunShellScript \
    --scripts "
set -euo pipefail
WORK_DIR=/tmp/mil_burst
rm -rf \$WORK_DIR
git clone --depth 1 ${REPO_URL} \$WORK_DIR
cd \$WORK_DIR
python3 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
python3 -c '
from src.quant.regime_hmm import train_and_export_regime_hmm
from src.quant.conformal_cones import calibrate_and_export_conformal_cones
train_and_export_regime_hmm()
calibrate_and_export_conformal_cones()
'
" --output table

# 4. Upload local calibrated artifacts to private Azure Blob Storage
echo "[4/4] Syncing calibrated artifacts to ${STORAGE_ACCOUNT}/${STORAGE_CONTAINER}..."
for ARTIFACT in data/models/regime_hmm_state.json data/models/conformal_quantiles.json data/models/tournament_summary.json; do
    if [[ -f "$ARTIFACT" ]]; then
        BLOB_NAME="models/$(basename "$ARTIFACT")"
        az storage blob upload \
            --connection-string "$CONN_STR" \
            --container-name "$STORAGE_CONTAINER" \
            --name "$BLOB_NAME" \
            --file "$ARTIFACT" \
            --overwrite \
            --output none
        echo "  Uploaded -> ${BLOB_NAME}"
    fi
done

echo "[SUCCESS] Burst R&D cycle complete. Trap will deallocate ${VM_NAME} now."
