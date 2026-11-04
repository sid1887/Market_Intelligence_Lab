#!/usr/bin/env python3
"""
Market Intelligence Lab — Idempotent Crontab Installer.

Safeguards:
1. Backs up existing crontab before modification.
2. Removes previous Market Intelligence Lab schedules cleanly to prevent duplicates.
3. Preserves any unrelated user crontab jobs.
4. Uses absolute paths for scripts, logs, and interpreter.
5. Verifies installation via `crontab -l`.
"""
import os
import sys
import subprocess
import datetime

MARKER_BEGIN = "# BEGIN MARKET_INTELLIGENCE_LAB_CRON"
MARKER_END = "# END MARKET_INTELLIGENCE_LAB_CRON"

def get_current_crontab() -> str:
    res = subprocess.run(["crontab", "-l"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode == 0:
        return res.stdout
    # Exit code 1 with "no crontab for user" is normal when crontab is empty
    return ""

def backup_crontab(content: str, backup_dir: str = "data") -> str:
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"crontab_backup_{ts}.txt")
    latest_backup = os.path.join(backup_dir, "crontab.backup")
    
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(content)
    with open(latest_backup, "w", encoding="utf-8") as f:
        f.write(content)
    
    return backup_path

def build_market_lab_block(workspace_dir: str) -> str:
    cron_script = os.path.join(workspace_dir, "scripts", "cron_market_lab.sh")
    cron_log = os.path.join(workspace_dir, "data", "cron.log")
    recovery_log = os.path.join(workspace_dir, "data", "cron_recovery.log")

    return f"""{MARKER_BEGIN}
# ==============================================================================
# Market Intelligence Lab — Production Scheduling (Asia/Kolkata)
# ==============================================================================
# 1. Primary Daily Post-Market Workflow (Monday through Friday at 16:30 IST)
# Bounded polling for CM-UDiFF Final Bhavcopy (17 attempts, 15m intervals to 20:30 IST),
# trading calendar preflight, quant factors, breadth, volume anomalies, and reports.
30 16 * * 1-5 {cron_script} >> {cron_log} 2>&1

# 2. Daily Morning Recovery Scan (Daily at 08:30 IST, including Monday catch-up)
# Scans lookback window for uningested trading days or pending releases; exits
# cleanly in milliseconds without unnecessary requests if data is up to date.
30 08 * * * {cron_script} --recovery >> {recovery_log} 2>&1
{MARKER_END}"""

def install_crontab(workspace_dir: str) -> bool:
    current = get_current_crontab()
    backup_file = backup_crontab(current, backup_dir=os.path.join(workspace_dir, "data"))
    print(f"[BACKUP] Existing crontab backed up to: {backup_file}")

    # Remove existing Market Lab entries
    lines = current.splitlines()
    filtered_lines = []
    inside_block = False

    for line in lines:
        if line.strip() == MARKER_BEGIN:
            inside_block = True
            continue
        if line.strip() == MARKER_END:
            inside_block = False
            continue
        if inside_block:
            continue
        # Also skip any stray lines referencing cron_market_lab.sh
        if "cron_market_lab.sh" in line:
            continue
        filtered_lines.append(line)

    clean_existing = "\n".join(filtered_lines).strip()
    new_block = build_market_lab_block(workspace_dir)

    if clean_existing:
        final_crontab = f"{clean_existing}\n\n{new_block}\n"
    else:
        final_crontab = f"{new_block}\n"

    # Write new crontab
    proc = subprocess.run(["crontab", "-"], input=final_crontab, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        print(f"[ERROR] Failed to install crontab: {proc.stderr}", file=sys.stderr)
        return False

    print("[SUCCESS] Idempotent crontab installation complete.")
    return True

def uninstall_crontab(workspace_dir: str) -> bool:
    current = get_current_crontab()
    backup_file = backup_crontab(current, backup_dir=os.path.join(workspace_dir, "data"))
    print(f"[BACKUP] Existing crontab backed up to: {backup_file}")

    lines = current.splitlines()
    filtered_lines = []
    inside_block = False

    for line in lines:
        if line.strip() == MARKER_BEGIN:
            inside_block = True
            continue
        if line.strip() == MARKER_END:
            inside_block = False
            continue
        if inside_block:
            continue
        if "cron_market_lab.sh" in line:
            continue
        filtered_lines.append(line)

    clean_existing = "\n".join(filtered_lines).strip()
    if clean_existing:
        final_crontab = f"{clean_existing}\n"
        proc = subprocess.run(["crontab", "-"], input=final_crontab, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        proc = subprocess.run(["crontab", "-r"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if proc.returncode != 0 and "no crontab for" not in proc.stderr.lower():
        print(f"[ERROR] Failed to uninstall crontab: {proc.stderr}", file=sys.stderr)
        return False

    print("[SUCCESS] Market Intelligence Lab crontab uninstalled.")
    return True

if __name__ == "__main__":
    ws_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, ws_dir)
    from src.config import is_network_allowed

    if len(sys.argv) > 1 and sys.argv[1] == "--uninstall":
        success = uninstall_crontab(ws_dir)
        if not success:
            sys.exit(1)
    elif len(sys.argv) > 1 and sys.argv[1] == "--install":
        if not is_network_allowed():
            print("[ERROR] Cannot install cron schedules: offline_mode is enabled in config/settings.json.", file=sys.stderr)
            sys.exit(1)
        success = install_crontab(ws_dir)
        if not success:
            sys.exit(1)
    else:
        print("Market Intelligence Lab — Crontab Schedule Manager (Locked / Offline)")
        print("Usage:")
        print("  python3 scripts/install_cron_schedules.py --uninstall   # Removes Market Lab cron jobs")
        print("  python3 scripts/install_cron_schedules.py --install     # Installs Market Lab cron jobs (requires network access)")
        print("  python3 scripts/install_cron_schedules.py --status      # Displays current crontab status")
        print("\n--- Current Crontab (`crontab -l`) ---")
        verified = get_current_crontab()
        print(verified if verified else "(empty)")
        sys.exit(0)

    print("\n--- Current Crontab (`crontab -l`) ---")
    verified = get_current_crontab()
    print(verified if verified else "(empty)")
