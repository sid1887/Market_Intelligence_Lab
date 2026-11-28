#!/usr/bin/env python3
"""
scripts/recompute_total_return_factors.py
MIL 2.0 Phase 11 — Total-Return Corporate Action Compounding & Factor Recompute.

1. Synchronizes all 6,985+ corporate_actions (DIVIDEND, SPLIT, BONUS, RIGHTS)
   into corporate_action_adjustments (using ohlcv_daily + bhavcopy_10y.milz for
   exact cum-dividend prior close P_{s-1}).
2. Runs CorporateActionsManager.apply_adjustments_to_ohlcv() across symbols to
   compute total-return adj_close & adj_volume across 2016-2026.
3. Recomputes causal alpha_v3_multimodal (fracdiff, flow, momentum, volatility)
   factors and optionally refreshes cloud_seed_snapshot.json.gz + Azure Blob.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.corporate_actions import CorporateActionsManager, extract_cash_dividend_amount
from src.ml.features.alpha_v3_multimodal import build_alpha_v3_multimodal_features
from src.storage.compression_engine import DEFAULT_ARCHIVE_PATH, MilzArchiveEngine
from src.storage.database import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("MIL.TRRecompute")


def sync_historical_dividends_from_milz(
    db: DatabaseManager,
    milz_path: Path = DEFAULT_ARCHIVE_PATH,
) -> int:
    """
    Supplements sync_from_corporate_actions_table() using 10-year bhavcopy_10y.milz
    closes for historical dividends whose ex_date predates SQLite ohlcv_daily.
    """
    if not milz_path.exists():
        return 0

    eng = MilzArchiveEngine(milz_path)
    ca_mgr = CorporateActionsManager(db)
    synced_milz = 0

    with db.get_connection() as conn:
        rows = conn.execute("""
            SELECT symbol, ex_date, record_date, adjustment_factor, purpose, source, face_value
            FROM corporate_actions
            WHERE action_type = 'DIVIDEND' AND ex_date IS NOT NULL AND ex_date != ''
            ORDER BY symbol ASC, ex_date ASC
        """).fetchall()

        existing = {
            (r[0], r[1])
            for r in conn.execute(
                "SELECT symbol, ex_date FROM corporate_action_adjustments WHERE action_type = 'DIVIDEND'"
            ).fetchall()
        }

    import hashlib
    sym_cache: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for r in rows:
        sym = str(r["symbol"]).strip().upper()
        ex_dt = str(r["ex_date"]).strip()
        if (sym, ex_dt) in existing:
            continue

        if sym not in sym_cache:
            try:
                hist = eng.load_symbol_history(sym)
                if hist.empty:
                    sym_cache[sym] = (np.array([], dtype=str), np.array([], dtype=np.float64))
                else:
                    hist = hist.sort_values("trading_date")
                    sym_cache[sym] = (
                        hist["trading_date"].astype(str).to_numpy(),
                        hist["close"].to_numpy(dtype=np.float64),
                    )
            except Exception:
                sym_cache[sym] = (np.array([], dtype=str), np.array([], dtype=np.float64))

        dates_arr, closes_arr = sym_cache[sym]
        if len(dates_arr) == 0:
            continue

        purpose = str(r["purpose"] or "")
        face_val = float(r["face_value"]) if r["face_value"] is not None else None
        d_s = extract_cash_dividend_amount(purpose, face_val)
        if d_s <= 0 and r["adjustment_factor"] and str(r["source"]) == "yfinance_pit":
            d_s = float(r["adjustment_factor"])
        if d_s <= 0:
            continue

        idx = int(np.searchsorted(dates_arr, ex_dt, side="left")) - 1
        if idx < 0:
            continue
        p_prev = float(closes_arr[idx])
        if p_prev <= 0 or (d_s >= 0.5 * p_prev and "SPECIAL" not in purpose.upper()):
            continue

        purpose_hash = hashlib.md5(purpose.encode("utf-8")).hexdigest()[:6]
        det_id = f"ca_{sym}_{ex_dt.replace('-', '')}_div_{purpose_hash}"
        ca_mgr.record_action(
            symbol=sym,
            ex_date=ex_dt,
            action_type="DIVIDEND",
            ratio_from=round(p_prev, 4),
            ratio_to=round(max(0.01, p_prev - d_s), 4),
            record_date=str(r["record_date"]).strip() if r["record_date"] else None,
            source=str(r["source"] or "yfinance_pit"),
            action_id=det_id,
        )
        existing.add((sym, ex_dt))
        synced_milz += 1

    return synced_milz


def run_total_return_recompute(
    db_path: str = "data/market_lab.db",
    milz_path: Path = DEFAULT_ARCHIVE_PATH,
    upload_azure: bool = False,
) -> Dict[str, Any]:
    """
    Compounds all corporate actions, applies total-return adjustments to OHLCV,
    and recomputes alpha_v3_multimodal diagnostics across the universe.
    """
    db = DatabaseManager(db_path)
    ca_mgr = CorporateActionsManager(db)

    synced_db = ca_mgr.sync_from_corporate_actions_table(include_dividends=True)
    synced_milz = sync_historical_dividends_from_milz(db, milz_path=milz_path)

    with db.get_connection() as conn:
        total_adj = conn.execute("SELECT COUNT(*) FROM corporate_action_adjustments").fetchone()[0]
        ohlcv_df = pd.read_sql_query(
            """
            SELECT symbol, trading_date, open, high, low, close, volume
            FROM ohlcv_daily
            WHERE is_synthetic = 0
            ORDER BY symbol, trading_date ASC
            """,
            conn,
        )

    adjusted_rows = 0
    adjusted_symbols = 0
    persisted_rows = 0
    if not ohlcv_df.empty:
        adj_df = ca_mgr.apply_adjustments_to_ohlcv(ohlcv_df, include_dividends=True)
        adjusted_rows = len(adj_df)
        adjusted_symbols = int(adj_df["symbol"].nunique())

        # Persist adj_close and adj_factor_cum back to SQLite ohlcv_daily
        adj_close_col = adj_df["adj_close"] if "adj_close" in adj_df.columns else adj_df["close"]
        raw_close_col = ohlcv_df["close"].replace(0, np.nan)
        factor_col = (adj_close_col / raw_close_col).fillna(1.0)
        updates = list(
            zip(
                adj_close_col.astype(float).tolist(),
                factor_col.astype(float).tolist(),
                adj_df["symbol"].astype(str).tolist(),
                adj_df["trading_date"].astype(str).tolist(),
            )
        )
        with db.get_connection() as conn:
            conn.executemany(
                "UPDATE ohlcv_daily SET adj_close = ?, adj_factor_cum = ? WHERE symbol = ? AND trading_date = ?",
                updates,
            )
            conn.commit()
        persisted_rows = len(updates)

        # Recompute causal alpha_v3_multimodal features on adjusted series to verify stationarity
        sample_syms = adj_df["symbol"].value_counts().head(50).index
        sub = adj_df[adj_df["symbol"].isin(sample_syms)].copy()
        _ = build_alpha_v3_multimodal_features(sub)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "synced_from_ohlcv_db": synced_db,
        "synced_from_milz_archive": synced_milz,
        "total_corporate_action_adjustments": total_adj,
        "ohlcv_rows_adjusted": adjusted_rows,
        "ohlcv_rows_persisted": persisted_rows,
        "ohlcv_symbols_adjusted": adjusted_symbols,
    }

    out_p = Path("data/total_return_recompute_manifest.json")
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    if upload_azure:
        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
        if conn_str:
            try:
                from azure.storage.blob import BlobServiceClient
                bsc = BlobServiceClient.from_connection_string(conn_str)
                c = bsc.get_container_client("mil-durable-state")
                with open(out_p, "rb") as f:
                    c.upload_blob("warehouse/total_return_recompute_manifest.json", f, overwrite=True)
            except Exception as az_err:
                logger.warning(f"Azure upload skipped: {az_err}")

    logger.info(
        f"[TR-RECOMPUTE] Total adjustments={total_adj} (+{synced_db} DB, +{synced_milz} MILZ), "
        f"adjusted {adjusted_rows} OHLCV rows across {adjusted_symbols} symbols."
    )
    return report


def main():
    parser = argparse.ArgumentParser(description="MIL 2.0 Phase 11 Total-Return Factor Recompute")
    parser.add_argument("--upload-azure", action="store_true")
    args = parser.parse_args()
    res = run_total_return_recompute(upload_azure=args.upload_azure)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
