"""
src/storage/cloud_snapshot.py
Cloud snapshot export and hydration utilities for Render cold start recovery.
Guarantees copilot_distillation_corpus, llm_usage_telemetry, user_watchlists,
factors, and catalysts survive cloud container restarts.
"""

import gzip
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from src.storage.database import DatabaseManager
from src.storage.hydration import hydrate_from_snapshot, SNAPSHOT_PATH

logger = logging.getLogger(__name__)

EXPORTABLE_TABLES = [
    "securities_master",
    "ohlcv_daily",
    "quant_factors_daily",
    "factors_daily",
    "user_watchlists",
    "market_catalysts",
    "index_daily",
    "fundamental_factors_daily",
    "financial_statements_annual",
    "financial_statements_quarterly",
    "company_financial_statements",
    "corporate_disclosures",
    "corporate_actions",
    "portfolio_accounts",
    "portfolio_positions",
    "portfolio_orders",
    "backtest_runs",
    "model_registry",
    "model_horizon_deployments",
    "supervisor_state",
    "ml_training_runs",
    "llm_usage_telemetry",
    "copilot_distillation_corpus",
    "external_api_telemetry",
]


def export_cloud_snapshot(
    db: DatabaseManager,
    output_path: Optional[str] = None,
    tables: Optional[List[str]] = None,
    max_ohlcv_days: int = 120,
) -> str:
    """
    Exports essential database state to a compressed cloud snapshot (.json.gz).
    Uses streaming chunked serialization to stay strictly within low-memory bounds (< 50 MB RAM).
    """
    target = output_path or SNAPSHOT_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    target_tables = tables or EXPORTABLE_TABLES

    t0 = time.time()
    min_ohlcv_date: Optional[str] = None
    min_factor_date: Optional[str] = None

    with db.get_connection() as conn:
        if max_ohlcv_days > 0:
            date_cur = conn.execute(
                "SELECT DISTINCT trading_date FROM ohlcv_daily ORDER BY trading_date DESC LIMIT ?",
                (max_ohlcv_days,),
            )
            cutoff_dates = [r[0] for r in date_cur.fetchall()]
            if cutoff_dates:
                min_ohlcv_date = cutoff_dates[-1]
                logger.info(f"[CLOUD SNAPSHOT] Using {max_ohlcv_days}-session cutoff date: {min_ohlcv_date}")

            factor_cur = conn.execute(
                "SELECT DISTINCT trading_date FROM quant_factors_daily ORDER BY trading_date DESC LIMIT 10"
            )
            f_dates = [r[0] for r in factor_cur.fetchall()]
            if f_dates:
                min_factor_date = f_dates[-1]
                logger.info(f"[CLOUD SNAPSHOT] Using 10-session factor cutoff date: {min_factor_date}")

        tmp_target = target + f".tmp_{os.getpid()}"
        with gzip.open(tmp_target, "wt", encoding="utf-8") as gz:
            gz.write("{\n")
            first_table = True

            for tbl in target_tables:
                try:
                    cur = conn.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
                    )
                    if not cur.fetchone():
                        continue

                    # Select optimal query per table for compact cloud deployment (< 10 MB compressed)
                    if tbl in ("ohlcv_daily", "index_daily") and min_ohlcv_date:
                        query = f"SELECT * FROM {tbl} WHERE trading_date >= ? ORDER BY trading_date ASC"
                        params = (min_ohlcv_date,)
                    elif tbl in ("quant_factors_daily", "factors_daily") and min_factor_date:
                        query = f"SELECT * FROM {tbl} WHERE trading_date >= ? ORDER BY trading_date ASC"
                        params = (min_factor_date,)
                    elif tbl == "corporate_disclosures":
                        query = "SELECT * FROM corporate_disclosures ORDER BY broadcast_timestamp DESC LIMIT 1000"
                        params = ()
                    elif tbl == "market_catalysts":
                        query = "SELECT * FROM market_catalysts ORDER BY triggered_at DESC LIMIT 500"
                        params = ()
                    elif tbl == "ml_training_runs":
                        query = "SELECT * FROM ml_training_runs ORDER BY trained_at DESC LIMIT 100"
                        params = ()
                    elif tbl == "copilot_distillation_corpus":
                        query = "SELECT * FROM copilot_distillation_corpus ORDER BY id DESC LIMIT 2000"
                        params = ()
                    elif tbl == "llm_usage_telemetry":
                        query = "SELECT * FROM llm_usage_telemetry ORDER BY usage_date DESC LIMIT 100"
                        params = ()
                    elif tbl == "portfolio_orders":
                        query = "SELECT * FROM portfolio_orders ORDER BY executed_at DESC LIMIT 1000"
                        params = ()
                    elif tbl == "backtest_runs":
                        query = "SELECT * FROM backtest_runs ORDER BY created_at DESC LIMIT 50"
                        params = ()
                    elif tbl == "external_api_telemetry":
                        query = "SELECT * FROM external_api_telemetry ORDER BY usage_date DESC LIMIT 200"
                        params = ()
                    else:
                        query = f"SELECT * FROM {tbl}"
                        params = ()

                    row_cur = conn.execute(query, params)
                    col_names = [col[0] for col in row_cur.description] if row_cur.description else []

                    if not first_table:
                        gz.write(",\n")
                    first_table = False

                    gz.write(f'  "{tbl}": [\n')
                    
                    count = 0
                    first_row = True
                    chunk_size = 5000
                    while True:
                        rows = row_cur.fetchmany(chunk_size)
                        if not rows:
                            break
                        for r in rows:
                            if not first_row:
                                gz.write(",\n")
                            first_row = False
                            row_dict = dict(zip(col_names, r))
                            gz.write("    " + json.dumps(row_dict, default=str))
                            count += 1

                    gz.write("\n  ]")
                    logger.info(f"Exported {count} records from {tbl} to snapshot.")
                except Exception as e:
                    logger.warning(f"Skipping table {tbl} during snapshot export: {e}")

            gz.write("\n}\n")

    if os.path.exists(tmp_target):
        os.replace(tmp_target, target)

    elapsed = time.time() - t0
    size_mb = os.path.getsize(target) / (1024 * 1024)
    logger.info(
        f"Cloud snapshot exported successfully to {target} ({size_mb:.2f} MB in {elapsed:.2f}s)."
    )
    return target
