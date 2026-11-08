#!/usr/bin/env python3
"""
scripts/run_stage2_backfill.py
Stage 2 Historical Backfill Runner (January 2020 – December 2022).

Ingests authentic NSE official daily settlement bhavcopies across:
- Era 1: Legacy format (2020-01-01 to 2022-12-31, 36 calendar months)

Maintains strict truth-layer invariants:
- Zero price fabrication (is_synthetic = 0).
- InstrumentMaster listing date guards (pre-IPO marked NOT_YET_LISTED).
- Fail-closed quarantine on missing source data (MISSING_SOURCE_DATA).
- Per-month atomic SQLite transaction commits.
- Telemetry reporting: download throughput (files/s, KB/s, bars/s) and checkpoint progress.
"""

import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timezone

from src.storage.database import DatabaseManager
from src.data.corporate_actions import CorporateActionsManager
from src.data.instrument_master import InstrumentMaster
from src.data.nse_archive_fetcher import NSEArchiveFetcher
from src.data.historical_backfill import HistoricalBackfillCoordinator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("MIL.Stage2Backfill")


def run_stage2():
    print("=" * 80)
    print("Market Intelligence Lab (MIL) — Stage 2 Historical Backfill (2020–2022)")
    print("Authentic NSE Exchange Bhavcopy Ingestion Engine")
    print("=" * 80)

    db = DatabaseManager("data/market_lab.db")
    ca_manager = CorporateActionsManager(db)
    instrument_master = InstrumentMaster(db)
    fetcher = NSEArchiveFetcher(cache_dir="data/raw/bhavcopies")
    coordinator = HistoricalBackfillCoordinator(
        db=db,
        ca_manager=ca_manager,
        instrument_master=instrument_master,
        bhavcopy_dir="data/raw/bhavcopies",
        archive_fetcher=fetcher
    )

    universe_symbols = coordinator.get_universe_symbols()
    print(f"[*] Universe initialized: {len(universe_symbols)} active symbols.")

    # Target months: 2020-01 to 2022-12 (36 calendar months)
    target_months = []
    for y in [2020, 2021, 2022]:
        for m in range(1, 13):
            target_months.append((y, m))

    total_months = len(target_months)
    print(f"[*] Total target periods: {total_months} months (2020-01 to 2022-12).")

    # Initial checkpoint stats
    initial_stats = coordinator.get_checkpoint_stats()
    print(f"[*] Initial Checkpoint Matrix State: {initial_stats['completed_units']} completed, "
          f"{initial_stats['pending_units']} pending, {initial_stats['not_yet_listed_units']} not yet listed.")
    print("-" * 80)

    t_start = time.time()
    cum_bars = 0
    cum_completed = 0
    cum_not_yet_listed = 0
    cum_missing_source = 0

    for idx, (y, m) in enumerate(target_months, 1):
        period_str = f"{y}-{m:02d}"
        print(f"\n>>> [{idx:02d}/{total_months}] Processing {period_str}...")

        m_t0 = time.time()
        res = coordinator.ingest_month(year=y, month=m)
        m_elapsed = time.time() - m_t0

        bars = res["total_bars_inserted"]
        comp = res["completed_units"]
        nyl = res["not_yet_listed_units"]
        ms = res["missing_source_units"]

        cum_bars += bars
        cum_completed += comp
        cum_not_yet_listed += nyl
        cum_missing_source += ms

        bars_per_sec = round(bars / m_elapsed, 1) if m_elapsed > 0 else 0.0

        print(f"    ✓ Ingested {bars:,} authentic bars ({bars_per_sec:,} bars/s in {m_elapsed:.2f}s)")
        print(f"    ✓ Work units: {comp} COMPLETED | {nyl} NOT_YET_LISTED | {ms} MISSING_SOURCE")

    total_time = time.time() - t_start
    final_stats = coordinator.get_checkpoint_stats()

    print("\n" + "=" * 80)
    print("STAGE 2 HISTORICAL BACKFILL SUMMARY")
    print("=" * 80)
    print(f"Total Execution Duration:     {total_time:.2f} seconds ({total_time / 60.0:.2f} minutes)")
    print(f"Total Authentic Bars Ingested:{cum_bars:,} rows")
    print(f"Overall Ingestion Velocity:   {round(cum_bars / total_time, 1):,} bars/second")
    print(f"Completed Work Units:         {final_stats['completed_units']} / {final_stats['total_work_units']} ({final_stats['completion_pct']}%)")
    print(f"Not-Yet-Listed Units (Pre-IPO):{final_stats['not_yet_listed_units']}")
    print(f"Missing Source Units:         {final_stats['missing_source_units']}")
    print(f"Pending Remaining Units:      {final_stats['pending_units']}")
    print("=" * 80)


if __name__ == "__main__":
    run_stage2()
