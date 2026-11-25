#!/usr/bin/env python3
"""
scripts/backfill_pit_warehouse.py
MIL 2.0 Phase 10 — Full-Universe PIT Fundamentals, Dividends & Ownership Warehouse Backfill.

Designed for offline execution locally, on GitHub Actions (16 GB), or via
`scripts/azure_burst_research.sh` (Standard_D4s_v5, 16 GB RAM).

Features:
1. Harvests & normalizes quarterly financial statements, cash dividends, splits/bonuses,
   and institutional/promoter shareholding patterns across active NSE symbols.
2. Enforces conservative SEBI 45d/60d PIT publication lags when exact exchange
   broadcast timestamps are unavailable.
3. Runs `flag_carry_forward_duplicates()` and `apply_adjustments_to_ohlcv()` idempotently.
4. Optionally uploads the enriched PIT warehouse manifest/archive to Azure Blob Storage
   (`milstatearchive74b8` / `mil-durable-state`).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.corporate_actions import CorporateActionsManager
from src.fundamentals.ttm_builder import flag_carry_forward_duplicates
from src.storage.database import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("MIL.PITBackfill")


def ensure_shareholding_table(conn: sqlite3.Connection) -> None:
    """Creates shareholding_patterns table idempotently for PIT FII/DII/Promoter deltas."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS shareholding_patterns (
            symbol TEXT NOT NULL,
            period_end_date TEXT NOT NULL,
            eligible_from_date TEXT NOT NULL,
            promoter_pct REAL DEFAULT 0.0,
            fii_pct REAL DEFAULT 0.0,
            dii_pct REAL DEFAULT 0.0,
            promoter_pledge_pct REAL DEFAULT 0.0,
            source TEXT DEFAULT 'yfinance_pit',
            retrieval_timestamp TEXT,
            PRIMARY KEY (symbol, period_end_date)
        );
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sh_sym_elig ON shareholding_patterns(symbol, eligible_from_date);"
    )
    conn.commit()


def _conservative_filing_date(period_end_str: str) -> str:
    """Applies conservative SEBI LODR lag (45 days Q1-Q3, 60 days Q4/FY) to period_end_date."""
    dt = pd.to_datetime(period_end_str)
    lag_days = 60 if dt.month == 3 else 45
    return (dt + timedelta(days=lag_days)).strftime("%Y-%m-%d")


def backfill_symbol_yfinance(
    conn: sqlite3.Connection,
    symbol: str,
    dry_run: bool = False,
) -> Dict[str, int]:
    """
    Harvests quarterly financials, dividends/splits, and ownership snapshot for `symbol`
    via yfinance, inserting idempotently into SQLite.
    """
    counts = {"financials": 0, "corporate_actions": 0, "shareholding": 0}
    if dry_run:
        return counts

    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance not installed; skipping remote harvest.")
        return counts

    now_iso = datetime.now(timezone.utc).isoformat()
    ticker = yf.Ticker(f"{symbol}.NS")

    # 1. Quarterly Financials -> financial_statements_quarterly
    try:
        q_fin = ticker.quarterly_financials
        q_bs = ticker.quarterly_balance_sheet
        if q_fin is not None and not q_fin.empty:
            for col_dt in q_fin.columns:
                p_end = pd.to_datetime(col_dt).strftime("%Y-%m-%d")
                filing_dt = _conservative_filing_date(p_end)

                def _get_val(df_src, keys):
                    if df_src is None or df_src.empty or col_dt not in df_src.columns:
                        return None
                    for k in keys:
                        if k in df_src.index:
                            v = df_src.loc[k, col_dt]
                            if pd.notna(v):
                                return float(v)
                    return None

                rev = _get_val(q_fin, ["Total Revenue", "Operating Revenue"])
                ebitda = _get_val(q_fin, ["EBITDA", "Normalized EBITDA"])
                net_inc = _get_val(q_fin, ["Net Income", "Net Income Common Stockholders"])
                eps = _get_val(q_fin, ["Diluted EPS", "Basic EPS"])
                debt = _get_val(q_bs, ["Total Debt", "Long Term Debt"])
                eq = _get_val(q_bs, ["Stockholders Equity", "Total Equity Gross Minority Interest"])

                if rev is not None or net_inc is not None:
                    conn.execute("""
                        INSERT OR IGNORE INTO financial_statements_quarterly (
                            symbol, period_end_date, filing_date, is_audited,
                            revenue, ebitda, net_profit, eps, total_debt, total_equity, created_at
                        ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?)
                    """, (symbol, p_end, filing_dt, rev, ebitda, net_inc, eps, debt, eq, now_iso))
                    counts["financials"] += 1
    except Exception as e:
        logger.debug(f"[{symbol}] Quarterly financials harvest notice: {e}")

    # 2. Dividends & Splits -> corporate_actions
    try:
        divs = ticker.dividends
        if divs is not None and not divs.empty:
            for idx_dt, amt in divs.items():
                ex_dt = pd.to_datetime(idx_dt).strftime("%Y-%m-%d")
                if pd.notna(amt) and float(amt) > 0:
                    conn.execute("""
                        INSERT OR IGNORE INTO corporate_actions (
                            symbol, action_type, ex_date, effective_date, purpose,
                            adjustment_factor, source, retrieval_timestamp
                        ) VALUES (?, 'DIVIDEND', ?, ?, ?, ?, 'yfinance_pit', ?)
                    """, (symbol, ex_dt, ex_dt, f"Cash Dividend Rs {float(amt):.2f}", float(amt), now_iso))
                    counts["corporate_actions"] += 1
    except Exception as e:
        logger.debug(f"[{symbol}] Dividends harvest notice: {e}")

    try:
        splits = ticker.splits
        if splits is not None and not splits.empty:
            for idx_dt, ratio in splits.items():
                ex_dt = pd.to_datetime(idx_dt).strftime("%Y-%m-%d")
                if pd.notna(ratio) and float(ratio) > 0 and float(ratio) != 1.0:
                    conn.execute("""
                        INSERT OR IGNORE INTO corporate_actions (
                            symbol, action_type, ex_date, effective_date, purpose,
                            adjustment_factor, adjustment_ratio, source, retrieval_timestamp
                        ) VALUES (?, 'SPLIT', ?, ?, ?, ?, ?, 'yfinance_pit', ?)
                    """, (symbol, ex_dt, ex_dt, f"Stock Split {float(ratio):.2f}:1", float(ratio), float(ratio), now_iso))
                    counts["corporate_actions"] += 1
    except Exception as e:
        logger.debug(f"[{symbol}] Splits harvest notice: {e}")

    # 3. Institutional Ownership -> shareholding_patterns
    try:
        mh = ticker.major_holders
        if mh is not None and not mh.empty:
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            # Conservative quarter end & SEBI 21-day submission lag
            q_end = pd.Timestamp(today_str).to_period("Q").start_time.strftime("%Y-%m-%d")
            elig = (pd.to_datetime(q_end) + timedelta(days=21)).strftime("%Y-%m-%d")
            inst_pct = 0.0
            prom_pct = 0.0
            for idx_lbl, row_vals in mh.iterrows():
                lbl = str(idx_lbl).lower()
                val = float(row_vals.iloc[0]) * 100.0 if pd.notna(row_vals.iloc[0]) else 0.0
                if val > 100.0:
                    val = val / 100.0
                if "insider" in lbl:
                    prom_pct = round(val, 2)
                elif "institution" in lbl:
                    inst_pct = round(val, 2)
            if inst_pct > 0 or prom_pct > 0:
                conn.execute("""
                    INSERT OR IGNORE INTO shareholding_patterns (
                        symbol, period_end_date, eligible_from_date,
                        promoter_pct, fii_pct, dii_pct, promoter_pledge_pct,
                        source, retrieval_timestamp
                    ) VALUES (?, ?, ?, ?, ?, 0.0, 0.0, 'yfinance_pit', ?)
                """, (symbol, q_end, elig, prom_pct, inst_pct, now_iso))
                counts["shareholding"] += 1
    except Exception as e:
        logger.debug(f"[{symbol}] Ownership harvest notice: {e}")

    conn.commit()
    return counts


def run_warehouse_backfill(
    db_path: str = "data/market_lab.db",
    universe_limit: int = 500,
    harvest_remote: bool = False,
    upload_azure: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Executes idempotent PIT warehouse normalization, carry-forward duplicate flagging,
    corporate action total-return adjustments, and optional remote harvest + Azure archival.
    """
    db = DatabaseManager(db_path)
    with db.get_connection() as conn:
        ensure_shareholding_table(conn)

        rows = conn.execute(
            """
            SELECT symbol FROM securities_master
            WHERE is_active = 1
            ORDER BY is_nifty50 DESC, symbol ASC
            LIMIT ?
            """,
            (universe_limit,),
        ).fetchall()
        symbols = [str(r[0]) for r in rows]

        totals = {"symbols_scanned": len(symbols), "financials": 0, "corporate_actions": 0, "shareholding": 0}
        if harvest_remote and not dry_run:
            for sym in symbols:
                res = backfill_symbol_yfinance(conn, sym, dry_run=dry_run)
                for k in ("financials", "corporate_actions", "shareholding"):
                    totals[k] += res[k]

        # Idempotent carry-forward duplicate audit across quarterly statements
        q_rows = conn.execute("""
            SELECT symbol, period_end_date, filing_date as published_at_ist,
                   revenue, ebitda, net_profit, eps as eps_diluted
            FROM financial_statements_quarterly
            ORDER BY symbol, period_end_date ASC
        """).fetchall()
        stmt_dicts = [dict(r) for r in q_rows]
        flagged = flag_carry_forward_duplicates(stmt_dicts)
        carry_fwd_count = sum(1 for s in flagged if s.get("is_carry_forward_duplicate"))

        sh_count = conn.execute("SELECT COUNT(*) FROM shareholding_patterns").fetchone()[0]
        ca_count = conn.execute("SELECT COUNT(*) FROM corporate_actions").fetchone()[0]
        fin_count = conn.execute("SELECT COUNT(*) FROM financial_statements_quarterly").fetchone()[0]

    # Idempotent corporate actions adjustment pass on OHLCV
    adj_stats = {"adjusted_symbols": 0}
    if not dry_run:
        try:
            ca_engine = CorporateActionsManager(db)
            adj_res = ca_engine.apply_adjustments_to_ohlcv()
            if isinstance(adj_res, dict):
                adj_stats = adj_res
        except Exception as e:
            logger.debug(f"Corporate actions adjustment pass notice: {e}")

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe_limit": universe_limit,
        "quarterly_statements_total": fin_count,
        "carry_forward_duplicates_flagged": carry_fwd_count,
        "corporate_actions_total": ca_count,
        "shareholding_records_total": sh_count,
        "harvest_totals": totals,
        "adjustment_stats": adj_stats,
    }

    manifest_path = Path("data/pit_warehouse_manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)

    if upload_azure and not dry_run:
        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
        if conn_str:
            try:
                from azure.storage.blob import BlobServiceClient
                bsc = BlobServiceClient.from_connection_string(conn_str)
                container = bsc.get_container_client("mil-durable-state")
                with open(manifest_path, "rb") as data_f:
                    container.upload_blob("warehouse/pit_warehouse_manifest.json", data_f, overwrite=True)
                logger.info("[PIT-WAREHOUSE] Uploaded pit_warehouse_manifest.json to Azure Blob.")
            except Exception as az_err:
                logger.warning(f"[PIT-WAREHOUSE] Azure upload skipped: {az_err}")

    logger.info(
        f"[PIT-WAREHOUSE] Complete: {fin_count} quarterly statements "
        f"({carry_fwd_count} carry-forward duplicates flagged), "
        f"{ca_count} corporate actions, {sh_count} shareholding rows."
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description="MIL 2.0 Phase 10 PIT Warehouse Backfill")
    parser.add_argument("--universe-limit", type=int, default=500)
    parser.add_argument("--harvest-remote", action="store_true", help="Fetch fresh filings/dividends from yfinance")
    parser.add_argument("--upload-azure", action="store_true", help="Upload manifest to Azure Blob Storage")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    res = run_warehouse_backfill(
        universe_limit=args.universe_limit,
        harvest_remote=args.harvest_remote,
        upload_azure=args.upload_azure,
        dry_run=args.dry_run,
    )
    print(json.dumps(res, indent=2, default=str))


if __name__ == "__main__":
    main()
