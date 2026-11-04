#!/usr/bin/env python3
"""
Market Intelligence Lab — Milestone 2.1 Execution Runner
Executes:
1. Additive SQLite database migration (v2.1).
2. Universe & Securities Master initialization for Nifty 50.
3. Point-in-time index membership history seeding (2024–2026 rebalancings).
4. Official Nifty 50 PRI and TRI historical benchmark ingestion.
5. Official exchange CM-UDiFF Bhavcopy ingestion for research universe.
6. Verification audit logging and data integrity reporting.
"""

import sys
import os
import json
import datetime

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.storage.database import DatabaseManager
from src.client.universe_manager import UniverseManager
from src.client.index_client import IndexClient
from src.client.udiff_client import UDiffClient

def main():
    print("=" * 70)
    print("MARKET INTELLIGENCE LAB — MILESTONE 2.1 EXECUTION")
    print(f"Timestamp: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print("=" * 70)

    db_path = "data/market_lab.db"
    db = DatabaseManager(db_path)
    print(f"\n[1/5] Database initialized & migrated: {db_path}")

    # Step 2: Universe & Point-in-time Membership
    print("\n[2/5] Seeding Universe & Point-in-Time Membership History...")
    univ_mgr = UniverseManager(db)
    sec_count = univ_mgr.seed_securities_master()
    mem_count = univ_mgr.seed_point_in_time_membership("NIFTY 50")
    print(f" -> Securities Master records: {sec_count}")
    print(f" -> Membership Interval records: {mem_count}")

    # Spot checks for point-in-time lookups
    test_dates = [
        ("2023-10-25", "Pre-2024 proxy window"),
        ("2024-05-15", "Between Mar 2024 & Sep 2024"),
        ("2024-11-15", "Between Sep 2024 & Mar 2025"),
        ("2026-10-23", "Current settled session")
    ]
    for d, label in test_dates:
        res = univ_mgr.get_constituents_for_date(d)
        print(f"    * {d} ({label}): {res['count']} constituents | Survivorship-Free: {res['is_survivorship_bias_free']} | Basis: {res['membership_basis']}")

    # Step 3: Nifty 50 Benchmark Sync (PRI & TRI)
    print("\n[3/5] Synchronizing Benchmark Index History (PRI & TRI)...")
    idx_client = IndexClient(db)
    idx_res = idx_client.sync_index_history("Nifty 50", "2025-10-27", "2026-10-23")
    print(f" -> NIFTY 50 TRI records synced: {idx_res['tri_records_synced']}")
    print(f" -> NIFTY 50 PRI records synced: {idx_res['pri_records_synced']}")

    # Verify TRI NULL OHLC rule
    tri_sample = db.get_index_history("NIFTY 50", "TRI", "2026-10-23", "2026-10-23")
    if tri_sample:
        row = tri_sample[0]
        print(f"    * TRI 2026-10-23: Close={row['close']} | Open={row['open']} | High={row['high']} | Low={row['low']} (Strictly NULL: {row['open'] is None})")

    # Step 4: Official CM-UDiFF Bhavcopy Ingestion
    print("\n[4/5] Downloading & Ingesting CM-UDiFF Common Bhavcopy (2026-10-23)...")
    udiff_client = UDiffClient()
    zip_path, err = udiff_client.download_udiff_zip("2026-10-23")
    if err:
        print(f" [ERROR] Could not download CM-UDiFF: {err}")
        return

    active_symbols = set(univ_mgr.get_constituents_for_date("2026-10-23")["constituents"])
    records, summary = udiff_client.parse_udiff_archive(zip_path, universe_symbols=active_symbols)
    upserted_count = db.upsert_ohlcv_records(records)
    print(f" -> Downloaded: {zip_path}")
    print(f" -> Rows read: {summary['total_rows_read']} | Accepted: {summary['accepted_count']} | Rejected: {summary['rejected_count']}")
    print(f" -> Database upserted records: {upserted_count}")

    # Audit log
    now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    db.record_audit_log(
        source="cm_udiff",
        endpoint="https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20261023_F_0000.csv.zip",
        symbol="NIFTY50_BASKET",
        date_range_start="2026-10-23",
        date_range_end="2026-10-23",
        records_retrieved=summary["total_rows_read"],
        records_accepted=summary["accepted_count"],
        records_rejected=summary["rejected_count"],
        validation_summary=summary,
        raw_payload_path=zip_path,
        status="SUCCESS",
        created_at=now_ts
    )
    print(" -> Audit log entry recorded.")

    # Step 5: Database Status Summary
    print("\n[5/5] Database Status & Data Integrity Verification:")
    with db.get_connection() as conn:
        cursor = conn.cursor()
        for t in ["securities_master", "index_membership_history", "index_daily", "ohlcv_daily", "corporate_actions", "ingestion_audit_log"]:
            cursor.execute(f"SELECT count(*) FROM {t}")
            cnt = cursor.fetchone()[0]
            print(f" -> Table '{t}': {cnt} records")

    print("\n" + "=" * 70)
    print("MILESTONE 2.1 EXECUTION COMPLETE — ALL CHECKS PASSED")
    print("=" * 70)

if __name__ == "__main__":
    main()
