#!/usr/bin/env python3
"""
scripts/harvest_nse_quarterly_history.py
MIL 2.0 Phase 11 — Multi-Year NSE Quarterly Results & XBRL Archive Harvest (2017-2026).

Harvests historical quarterly filings from NSE's corporate financial results API:
  https://www.nseindia.com/api/corporates-financial-results?index=equities&symbol=...
with session-cookie warm-up, exponential backoff, strict broadcast_Date/creation_Date
IST timestamp extraction, standalone vs. consolidated deduplication (preferring
consolidated), and carry-forward duplicate flagging.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.fundamentals.ttm_builder import flag_carry_forward_duplicates
from src.ml.features.pead_engine import calculate_pead_features
from src.storage.database import DatabaseManager

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("MIL.NSEQuarterly")

NSE_HOME_URL = "https://www.nseindia.com"
NSE_FIN_RESULTS_URL = "https://www.nseindia.com/api/corporates-financial-results"

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results",
}


def _safe_float(val: Any) -> Optional[float]:
    if val is None or val == "" or str(val).strip() in ("-", "NA", "null", "None"):
        return None
    try:
        return float(str(val).replace(",", "").strip())
    except Exception:
        return None


def _parse_nse_date(raw_dt: Any) -> Optional[str]:
    if not raw_dt or str(raw_dt).strip() in ("-", "", "null", "None"):
        return None
    try:
        dt = pd.to_datetime(str(raw_dt).strip(), dayfirst=True, errors="coerce")
        if pd.isna(dt):
            dt = pd.to_datetime(str(raw_dt).strip(), errors="coerce")
        if pd.isna(dt):
            return None
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return None


def _parse_nse_ist_timestamp(raw_ts: Any, period_end: str) -> str:
    """
    Extracts exact IST filing/broadcast timestamp when present; falls back to
    conservative SEBI LODR lag (45d Q1-Q3 / 60d Q4) at 18:00 IST.
    """
    if raw_ts and str(raw_ts).strip() not in ("-", "", "null", "None"):
        try:
            dt = pd.to_datetime(str(raw_ts).strip(), dayfirst=True, errors="coerce")
            if pd.isna(dt):
                dt = pd.to_datetime(str(raw_ts).strip(), errors="coerce")
            if not pd.isna(dt):
                if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
                    return dt.strftime("%Y-%m-%d 18:00:00")
                return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    p_dt = pd.to_datetime(period_end)
    lag = 60 if p_dt.month == 3 else 45
    return (p_dt + timedelta(days=lag)).strftime("%Y-%m-%d 18:00:00")


def parse_and_deduplicate_nse_quarterly(
    records: List[Dict[str, Any]],
    symbol: str,
) -> List[Dict[str, Any]]:
    """
    Normalizes raw NSE corporate-financial-results JSON records for `symbol`,
    deduplicates by (symbol, period_end_date) strictly preferring Consolidated
    over Standalone, and runs flag_carry_forward_duplicates().
    """
    sym = symbol.strip().upper()
    by_period: Dict[str, Dict[str, Any]] = {}

    for rec in records or []:
        if not isinstance(rec, dict):
            continue

        p_end = _parse_nse_date(rec.get("toDate") or rec.get("periodEnd") or rec.get("to_date"))
        if not p_end:
            continue

        basis_raw = str(rec.get("consolidated") or rec.get("re_nature") or "Standalone").strip().lower()
        is_consolidated = ("consolidated" in basis_raw) and ("non-consolidated" not in basis_raw) and ("standalone" not in basis_raw)
        priority = 2 if is_consolidated else 1

        ts_raw = (
            rec.get("broadcast_Date")
            or rec.get("broadCastDate")
            or rec.get("filingDate")
            or rec.get("creation_Date")
            or rec.get("reAppDate")
        )
        pub_ist = _parse_nse_ist_timestamp(ts_raw, p_end)

        rev = _safe_float(rec.get("re_net_sale") or rec.get("income") or rec.get("re_tot_inc"))
        net_profit = _safe_float(rec.get("re_net_profit") or rec.get("netProfit") or rec.get("re_pro_loss_aft_tax"))
        eps = _safe_float(rec.get("re_diluted_eps") or rec.get("re_basic_eps_for_cont_ops") or rec.get("re_basic_eps"))
        ebitda = _safe_float(rec.get("re_ebitda") or rec.get("re_pro_loss_bef_tax"))

        if rev is None and net_profit is None and eps is None:
            continue

        existing = by_period.get(p_end)
        if existing is not None and existing["_priority"] >= priority:
            continue

        by_period[p_end] = {
            "symbol": sym,
            "period_end_date": p_end,
            "filing_date": pub_ist[:10],
            "published_at_ist": pub_ist,
            "reporting_basis": "CONSOLIDATED" if is_consolidated else "STANDALONE",
            "revenue": rev,
            "ebitda": ebitda,
            "net_profit": net_profit,
            "eps": eps,
            "eps_diluted": eps,
            "is_audited": 1 if "audited" in str(rec.get("audited") or "").lower() and "un-audited" not in str(rec.get("audited") or "").lower() else 0,
            "_priority": priority,
        }

    ordered = sorted(by_period.values(), key=lambda x: x["period_end_date"])
    for item in ordered:
        item.pop("_priority", None)

    return flag_carry_forward_duplicates(ordered)


class NseQuarterlyHarvester:
    """Cookie-warmed NSE quarterly financial results harvester with exponential backoff."""

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout
        self.client: Optional[httpx.Client] = None

    def _ensure_session(self) -> httpx.Client:
        if self.client is None:
            self.client = httpx.Client(
                headers=NSE_HEADERS,
                timeout=self.timeout,
                follow_redirects=True,
            )
            try:
                self.client.get(NSE_HOME_URL)
                time.sleep(0.6)
            except Exception as e:
                logger.debug(f"NSE cookie warmup notice: {e}")
        return self.client

    def fetch_symbol_quarterly(self, symbol: str, max_retries: int = 3) -> List[Dict[str, Any]]:
        client = self._ensure_session()
        params = {"index": "equities", "symbol": symbol.strip().upper()}

        for attempt in range(max_retries):
            try:
                resp = client.get(NSE_FIN_RESULTS_URL, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        return data
                    if isinstance(data, dict) and isinstance(data.get("data"), list):
                        return data["data"]
                    return []
                if resp.status_code in (401, 403, 429):
                    backoff = (1.5 ** attempt) + random.uniform(0.3, 0.9)
                    time.sleep(backoff)
                    try:
                        client.get(NSE_HOME_URL)
                    except Exception:
                        pass
                else:
                    return []
            except Exception:
                time.sleep((1.5 ** attempt) + 0.3)
        return []

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None


def run_nse_quarterly_harvest(
    db_path: str = "data/market_lab.db",
    universe_limit: int = 100,
    max_symbols_remote: int = 50,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Harvests historical quarterly filings from NSE API for top active symbols,
    deduplicates standalone vs. consolidated, flags carry-forward duplicates,
    and inserts idempotently into financial_statements_quarterly.
    """
    db = DatabaseManager(db_path)
    with db.get_connection() as conn:
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

    inserted = 0
    flagged_dups = 0
    symbols_harvested = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    if not dry_run:
        harvester = NseQuarterlyHarvester()
        try:
            with db.get_connection() as conn:
                for sym in symbols[:max_symbols_remote]:
                    raw = harvester.fetch_symbol_quarterly(sym)
                    if not raw:
                        continue
                    parsed = parse_and_deduplicate_nse_quarterly(raw, sym)
                    if not parsed:
                        continue
                    symbols_harvested += 1
                    for q in parsed:
                        if q.get("is_carry_forward_duplicate"):
                            flagged_dups += 1
                            continue
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO financial_statements_quarterly (
                                symbol, period_end_date, filing_date, source_url, is_audited,
                                revenue, ebitda, net_profit, eps, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                sym,
                                q["period_end_date"],
                                q["filing_date"],
                                f"{NSE_FIN_RESULTS_URL}?index=equities&symbol={sym}",
                                q["is_audited"],
                                q["revenue"],
                                q["ebitda"],
                                q["net_profit"],
                                q["eps"],
                                now_iso,
                            ),
                        )
                        inserted += 1
                    time.sleep(0.25)
                conn.commit()
        finally:
            harvester.close()

    with db.get_connection() as conn:
        total_q = conn.execute("SELECT COUNT(*) FROM financial_statements_quarterly").fetchone()[0]

    summary = {
        "generated_at": now_iso,
        "symbols_targeted": len(symbols[:max_symbols_remote]),
        "symbols_harvested_from_nse": symbols_harvested,
        "quarterly_rows_inserted": inserted,
        "carry_forward_duplicates_skipped": flagged_dups,
        "total_quarterly_statements_in_db": total_q,
    }

    out_p = Path("data/nse_quarterly_harvest_manifest.json")
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info(
        f"[NSE-QUARTERLY] Harvested {symbols_harvested} symbols -> +{inserted} filings "
        f"({flagged_dups} carry-forward duplicates skipped), total DB={total_q}"
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description="MIL 2.0 Phase 11 NSE Multi-Year Quarterly Harvester")
    parser.add_argument("--universe-limit", type=int, default=500)
    parser.add_argument("--max-symbols-remote", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    res = run_nse_quarterly_harvest(
        universe_limit=args.universe_limit,
        max_symbols_remote=args.max_symbols_remote,
        dry_run=args.dry_run,
    )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
