#!/usr/bin/env python3
"""
Backfills 1-year historical daily records for all remaining Nifty 50 constituents.
"""
import sys
import os
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.storage.database import DatabaseManager
from src.client.universe_manager import UniverseManager
from src.client.backfill_manager import BackfillManager

def main():
    db = DatabaseManager("data/market_lab.db")
    mgr = UniverseManager(db)
    constituents = mgr.get_constituents_for_date("2026-10-23")["constituents"]

    bf = BackfillManager(db, min_required_records=200)
    needing = bf.get_symbols_needing_backfill(constituents)
    print(f"Total constituents in universe: {len(constituents)}")
    print(f"Constituents needing backfill: {len(needing)}")

    if not needing:
        print("All constituents already have complete historical data.")
        return

    t0 = time.time()
    res = bf.backfill_universe(needing, total_months=12, end_date="2026-10-23")
    elapsed = time.time() - t0

    print(f"\nBackfill finished in {elapsed:.1f}s:")
    print(f" -> Completed: {res['completed_count']}")
    print(f" -> Failed: {res['failed_count']}")
    print(f" -> Total records upserted: {res['total_records_upserted']}")

    if res['failed_count'] > 0:
        print("Failed symbols:")
        for d in res['details']:
            if d['status'] == 'FAILED':
                print(f"  * {d['symbol']}: {d.get('error')}")

if __name__ == "__main__":
    main()
