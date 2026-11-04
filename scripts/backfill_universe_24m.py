import time
import datetime
import sys
from typing import List, Dict, Any
from src.storage.database import DatabaseManager
from src.client.backfill_manager import BackfillManager
from src.client.nse_mcp_client import NseMcpClient

def main():
    print("=== Milestone B3.1: Resumable Authoritative 24-Month Universe Backfill ===")
    t0 = time.time()
    db = DatabaseManager("data/market_lab.db")
    mcp_client = NseMcpClient()
    bm = BackfillManager(db, mcp_client=mcp_client, min_required_records=480)

    # 1. Authoritative universe discovery from securities_master
    active_symbols = bm.get_active_universe()
    print(f"Authoritative active universe from securities_master: {len(active_symbols)} symbols")

    # 2. Resumable identification of symbols needing data
    to_process = bm.get_symbols_needing_backfill(active_symbols)
    print(f"Symbols requiring backfill to meet coverage criteria: {len(to_process)}")

    if to_process:
        mcp_client.initialize()
        for idx, sym in enumerate(to_process, 1):
            st = time.time()
            success = False
            last_res = None

            for attempt in range(1, 4):
                try:
                    res = bm.backfill_symbol(sym, total_months=24, end_date="2026-10-23")
                    last_res = res
                    status = res.get("status")
                    if status in ("COVERAGE_MET", "COVERAGE_EXCEPTION_TICKER_RENAME"):
                        success = True
                        break
                    elif status == "PARTIAL_COVERAGE":
                        print(f"  [{sym}] Attempt {attempt} returned PARTIAL_COVERAGE ({res.get('records_upserted', 0)} upserted). Retrying...")
                        time.sleep(1.0)
                        mcp_client.session_id = None
                    else:
                        print(f"  [{sym}] Attempt {attempt} returned FAILED ({res.get('error')}). Retrying...")
                        time.sleep(1.0)
                        mcp_client.session_id = None
                except Exception as e:
                    print(f"  [{sym}] Attempt {attempt} raised exception: {e}. Retrying...")
                    time.sleep(1.0)
                    mcp_client.session_id = None

            dur = time.time() - st
            final_status = last_res.get("status") if last_res else "FAILED"
            sessions = last_res.get("coverage", {}).get("session_count", 0) if last_res else 0
            drange = last_res.get("date_range", "") if last_res else ""
            print(f"[{idx:2d}/{len(to_process)}] {sym:12} -> {final_status:32} ({sessions} sessions, {drange}) in {dur:.2f}s", flush=True)
            time.sleep(0.2)

    total_time = time.time() - t0
    print(f"\n--- Ingestion Completed in {total_time:.2f}s ({total_time/60:.2f} min) ---")

    # 3. Post-ingestion coverage verification for all active constituents
    print("\n--- Universe-Wide Coverage Acceptance Verification ---")
    coverage_met = []
    coverage_exceptions = []
    coverage_unmet = []

    for sym in active_symbols:
        cov = bm.verify_symbol_coverage(sym)
        if cov["status"] == "COVERAGE_MET":
            coverage_met.append(cov)
        elif cov["status"] == "COVERAGE_EXCEPTION_TICKER_RENAME":
            coverage_exceptions.append(cov)
        else:
            coverage_unmet.append(cov)

    print(f"  COVERAGE_MET                     : {len(coverage_met):2d} / {len(active_symbols)}")
    print(f"  COVERAGE_EXCEPTION_TICKER_RENAME : {len(coverage_exceptions):2d} / {len(active_symbols)}")
    for exc in coverage_exceptions:
        print(f"    - {exc['symbol']}: {exc['session_count']} sessions ({exc['earliest_date']} to {exc['latest_date']}) - Reason: {exc['exception_reason']}")
    print(f"  UNMET / FAILED                   : {len(coverage_unmet):2d} / {len(active_symbols)}")

    if coverage_unmet:
        print("\nERROR: The following symbols failed coverage acceptance criteria:")
        for u in coverage_unmet:
            print(f"  FAILED: {u['symbol']} (Status: {u['status']}, Sessions: {u['session_count']}, Target: {u['target']}, Range: {u['earliest_date']} to {u['latest_date']})")
        sys.exit(1)

    print("\nSUCCESS: All 50 active constituents have verified valid coverage or documented approved exceptions!")
    sys.exit(0)

if __name__ == "__main__":
    main()
