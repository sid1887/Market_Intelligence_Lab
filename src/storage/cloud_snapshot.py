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
    "corporate_disclosures",
    "model_registry",
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
    Includes copilot distillation corpus and LLM usage telemetry.
    """
    target = output_path or SNAPSHOT_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    target_tables = tables or EXPORTABLE_TABLES

    snapshot_data: Dict[str, Any] = {}
    t0 = time.time()

    with db.get_connection() as conn:
        for tbl in target_tables:
            try:
                # Check if table exists
                cur = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
                )
                if not cur.fetchone():
                    continue

                if tbl == "ohlcv_daily" and max_ohlcv_days > 0:
                    # Export recent sessions to keep snapshot compact (< 15 MB)
                    date_cur = conn.execute(
                        "SELECT DISTINCT trading_date FROM ohlcv_daily ORDER BY trading_date DESC LIMIT ?",
                        (max_ohlcv_days,),
                    )
                    cutoff_dates = [r[0] for r in date_cur.fetchall()]
                    if cutoff_dates:
                        min_date = cutoff_dates[-1]
                        rows = conn.execute(
                            "SELECT * FROM ohlcv_daily WHERE trading_date >= ?", (min_date,)
                        ).fetchall()
                    else:
                        rows = conn.execute("SELECT * FROM ohlcv_daily").fetchall()
                elif tbl == "copilot_distillation_corpus":
                    # Keep latest 2,000 distilled traces
                    rows = conn.execute(
                        "SELECT * FROM copilot_distillation_corpus ORDER BY id DESC LIMIT 2000"
                    ).fetchall()
                elif tbl == "llm_usage_telemetry":
                    rows = conn.execute(
                        "SELECT * FROM llm_usage_telemetry ORDER BY usage_date DESC LIMIT 100"
                    ).fetchall()
                elif tbl == "external_api_telemetry":
                    rows = conn.execute(
                        "SELECT * FROM external_api_telemetry ORDER BY usage_date DESC LIMIT 200"
                    ).fetchall()
                else:
                    rows = conn.execute(f"SELECT * FROM {tbl}").fetchall()

                snapshot_data[tbl] = [dict(r) for r in rows]
                logger.info(f"Exported {len(rows)} records from {tbl} to snapshot.")
            except Exception as e:
                logger.warning(f"Skipping table {tbl} during snapshot export: {e}")

    # Compress and write to file
    encoded_bytes = json.dumps(snapshot_data, default=str).encode("utf-8")
    with gzip.open(target, "wb") as f:
        f.write(encoded_bytes)

    elapsed = time.time() - t0
    size_mb = os.path.getsize(target) / (1024 * 1024)
    logger.info(
        f"Cloud snapshot exported successfully to {target} ({size_mb:.2f} MB in {elapsed:.2f}s)."
    )
    return target
