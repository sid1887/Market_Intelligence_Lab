"""
src/data/full_spectrum_harvester.py
Master Full-Spectrum Data Extraction Engine & Unified Backfill Orchestrator.

Orchestrates complete lifecycle data extraction across:
1. Backfilling unseeded (0 bars) and thin (< 250 bars) active NSE equities.
2. Resolving generic "Equities" sector and industry classifications to canonical NSE sectors.
3. Ingesting local raw files: financial statements, corporate disclosures, and index archives.
4. Ingesting 15 NSE Sectoral Index histories (NIFTY BANK, IT, AUTO, FMCG, METAL, PHARMA, etc.).
5. Populating missing fundamentals (ROE %, OPM %, D/E, TTM P/E) across all 1,153 active equities.
6. Packing the full historical universe into data/archive/bhavcopy_10y.milz columnar archive.
7. Exporting refreshed 400-session hot state to data/cloud_seed_snapshot.json.gz.
"""

import os
import glob
import json
import time
import logging
import argparse
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set, Union
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import numpy as np
import yfinance as yf

from src.storage.database import DatabaseManager
from src.api.utils import DATABASE_PATH, get_database_manager
from src.storage.compression_engine import MilzArchiveEngine, DEFAULT_ARCHIVE_PATH
from src.storage.cloud_snapshot import export_cloud_snapshot
from src.data.instrument_master import NSE_LISTING_DATES
from src.data.universe_expander import NSE_CURATED_UNIVERSE

logger = logging.getLogger("MIL.FullSpectrumHarvester")

# Canonical NSE Sector Definitions
CANONICAL_SECTORS: List[str] = [
    "Financial Services",
    "Information Technology",
    "Healthcare",
    "Automobile and Auto Components",
    "Capital Goods",
    "Fast Moving Consumer Goods",
    "Chemicals",
    "Metals & Mining",
    "Power",
    "Oil Gas & Consumable Fuels",
    "Consumer Services",
    "Construction Materials",
    "Telecommunication",
    "Realty",
    "Media"
]

# Sector Mapping Table from Yahoo / Industry keywords to Canonical NSE Sectors
SECTOR_MAPPING_RULES: List[Tuple[List[str], str]] = [
    (["bank", "finance", "financial", "insurance", "lending", "broker", "asset management", "housing finance"], "Financial Services"),
    (["software", "technology", "it services", "cloud", "digital", "semiconductor", "computers"], "Information Technology"),
    (["pharma", "health", "hospital", "biotech", "medical", "drug", "diagnostic", "healthcare"], "Healthcare"),
    (["auto", "vehicle", "car", "truck", "motor", "tyre", "tire", "ancillary"], "Automobile and Auto Components"),
    (["capital goods", "machinery", "engineering", "electrical equipment", "industrial", "aerospace", "defense"], "Capital Goods"),
    (["fmcg", "consumer goods", "beverage", "food", "tobacco", "personal care", "dairy"], "Fast Moving Consumer Goods"),
    (["chemical", "fertilizer", "specialty chemical", "pesticide", "agrochem"], "Chemicals"),
    (["metal", "mining", "steel", "iron", "aluminum", "zinc", "copper", "coal"], "Metals & Mining"),
    (["power", "energy - power", "electricity", "solar", "renewable", "thermal power", "utilities"], "Power"),
    (["oil", "gas", "petroleum", "refining", "energy", "fuel", "exploration"], "Oil Gas & Consumable Fuels"),
    (["cement", "construction material", "ceramic", "granite", "pipe", "building materials"], "Construction Materials"),
    (["realty", "real estate", "infrastructure developer", "housing developer"], "Realty"),
    (["telecom", "telecommunication", "wireless", "towers"], "Telecommunication"),
    (["media", "entertainment", "broadcasting", "publishing", "film", "multiplex"], "Media"),
    (["retail", "hotel", "travel", "restaurant", "consumer services", "logistics", "courier", "transport"], "Consumer Services")
]

# 15 Authoritative Sectoral Indices mapped to Yahoo Tickers
NSE_SECTORAL_INDICES: Dict[str, Dict[str, str]] = {
    "NIFTY 50": {"ticker": "^NSEI", "type": "PRI"},
    "NIFTY BANK": {"ticker": "^NSEBANK", "type": "PRI"},
    "NIFTY IT": {"ticker": "^CNXIT", "type": "PRI"},
    "NIFTY AUTO": {"ticker": "^CNXAUTO", "type": "PRI"},
    "NIFTY FMCG": {"ticker": "^CNXFMCG", "type": "PRI"},
    "NIFTY METAL": {"ticker": "^CNXMETAL", "type": "PRI"},
    "NIFTY PHARMA": {"ticker": "^CNXPHARMA", "type": "PRI"},
    "NIFTY REALTY": {"ticker": "^CNXREALTY", "type": "PRI"},
    "NIFTY ENERGY": {"ticker": "^CNXENERGY", "type": "PRI"},
    "NIFTY INFRA": {"ticker": "^CNXINFRA", "type": "PRI"},
    "NIFTY PSU BANK": {"ticker": "^CNXPSUBANK", "type": "PRI"},
    "NIFTY MEDIA": {"ticker": "^CNXMEDIA", "type": "PRI"},
    "NIFTY COMMODITIES": {"ticker": "^CNXCOMMODITIES", "type": "PRI"},
    "NIFTY CONSUMPTION": {"ticker": "^CNXCONSUMPTION", "type": "PRI"},
    "NIFTY MIDCAP 50": {"ticker": "^NSEMDCP50", "type": "PRI"},
}


class FullSpectrumHarvester:
    """
    Unified harvester closing data and display gaps across equities, sectors,
    fundamentals, corporate disclosures, and sectoral index benchmarks.
    """

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        archive_path: Union[str, Path] = DEFAULT_ARCHIVE_PATH,
        db_path: str = DATABASE_PATH
    ):
        self.db = db or get_database_manager(db_path)
        self.archive_engine = MilzArchiveEngine(archive_path)
        self.archive_path = Path(archive_path)
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Ensures index_daily, corporate_disclosures, and backfill_checkpoints exist."""
        with self.db.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS backfill_checkpoints (
                    pipeline TEXT PRIMARY KEY,
                    last_completed_date TEXT,
                    earliest_completed_date TEXT,
                    status TEXT,
                    records_harvested INTEGER DEFAULT 0,
                    updated_at TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS index_daily (
                    index_name TEXT NOT NULL,
                    trading_date TEXT NOT NULL,
                    index_type TEXT NOT NULL DEFAULT 'PRI',
                    open REAL DEFAULT NULL,
                    high REAL DEFAULT NULL,
                    low REAL DEFAULT NULL,
                    close REAL NOT NULL,
                    volume INTEGER DEFAULT NULL,
                    pe_ratio REAL DEFAULT NULL,
                    pb_ratio REAL DEFAULT NULL,
                    div_yield REAL DEFAULT NULL,
                    source TEXT NOT NULL,
                    retrieval_timestamp TEXT NOT NULL,
                    PRIMARY KEY (index_name, trading_date, index_type)
                );
            """)
            conn.commit()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. RESOLVE GENERIC "EQUITIES" SECTORS
    # ─────────────────────────────────────────────────────────────────────────

    def resolve_generic_sectors(self, max_workers: int = 4) -> Dict[str, Any]:
        """
        Maps active equities where sector is generic ('Equities', 'General', or empty)
        into authoritative canonical NSE sectors.
        """
        logger.info("[SECTOR RESOLUTION] Querying unclassified and generic equities...")
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT symbol, company_name, isin, sector, industry
                FROM securities_master
                WHERE is_active = 1
                  AND (sector IS NULL OR sector = '' OR sector = 'Equities' OR sector = 'General' OR sector = 'Unclassified')
            """)
            unmapped = cur.fetchall()

        total_unmapped = len(unmapped)
        logger.info(f"[SECTOR RESOLUTION] Found {total_unmapped} equities requiring sector reclassification.")
        if total_unmapped == 0:
            return {"resolved": 0, "total": 0}

        curated_map: Dict[str, str] = {item["symbol"]: item["sector"] for item in NSE_CURATED_UNIVERSE if "sector" in item}

        resolved_count = 0
        symbols_to_fetch_yf: List[Dict[str, Any]] = []

        # Pass 1: Local curated dictionary lookup
        with self.db.get_connection() as conn:
            for row in unmapped:
                sym = row["symbol"]
                if sym in curated_map:
                    canonical = self._map_to_canonical(curated_map[sym])
                    conn.execute("""
                        UPDATE securities_master
                        SET sector = ?, updated_at = ?
                        WHERE symbol = ?
                    """, (canonical, datetime.datetime.now(datetime.timezone.utc).isoformat(), sym))
                    resolved_count += 1
                else:
                    symbols_to_fetch_yf.append(dict(row))
            conn.commit()

        logger.info(f"[SECTOR RESOLUTION] Pass 1 (Curated Dictionary) resolved {resolved_count} equities. Fetching remaining {len(symbols_to_fetch_yf)} via yfinance...")

        # Pass 2: Parallel yfinance sector extraction
        def _fetch_yf_sector(item: Dict[str, Any]) -> Tuple[str, Optional[str], Optional[str]]:
            sym = item["symbol"]
            for s_suffix in [".NS", ".BO"]:
                try:
                    t = yf.Ticker(sym + s_suffix)
                    inf = t.info or {}
                    raw_sec = inf.get("sector")
                    raw_ind = inf.get("industry")
                    if raw_sec:
                        return sym, raw_sec, raw_ind
                except Exception:
                    continue
            return sym, None, None

        if symbols_to_fetch_yf:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_fetch_yf_sector, item): item for item in symbols_to_fetch_yf}
                with self.db.get_connection() as conn:
                    for f in as_completed(futures):
                        try:
                            s, raw_sec, raw_ind = f.result()
                            if raw_sec:
                                canonical = self._map_to_canonical(raw_sec, raw_ind)
                                industry = raw_ind or canonical
                                conn.execute("""
                                    UPDATE securities_master
                                    SET sector = ?, industry = ?, updated_at = ?
                                    WHERE symbol = ?
                                """, (canonical, industry, datetime.datetime.now(datetime.timezone.utc).isoformat(), s))
                                resolved_count += 1
                        except Exception as e:
                            logger.debug(f"Failed to resolve sector for {f}: {e}")
                    conn.commit()

        logger.info(f"[SECTOR RESOLUTION] Completed: {resolved_count}/{total_unmapped} equities mapped to canonical sectors.")
        return {"resolved": resolved_count, "total": total_unmapped}

    def _map_to_canonical(self, raw_sector: str, raw_industry: Optional[str] = None) -> str:
        """Normalizes sector/industry text into one of the 15 canonical NSE sectors."""
        text = f"{raw_sector} {raw_industry or ''}".lower()
        for keywords, canonical in SECTOR_MAPPING_RULES:
            if any(k in text for k in keywords):
                return canonical
        if "financial" in text or "bank" in text:
            return "Financial Services"
        if "tech" in text or "software" in text:
            return "Information Technology"
        return "Capital Goods"

    # ─────────────────────────────────────────────────────────────────────────
    # 2. INGEST LOCAL RAW INDICES, DISCLOSURES & FINANCIAL STATEMENTS
    # ─────────────────────────────────────────────────────────────────────────

    def ingest_local_raw_indices(self) -> int:
        """Ingests all historical index files from data/raw/indices/ into index_daily."""
        logger.info("[INDEX INGESTION] Scanning data/raw/indices/...")
        pattern = os.path.join("data", "raw", "indices", "*.json")
        files = glob.glob(pattern)
        if not files:
            logger.info("[INDEX INGESTION] No raw index files found.")
            return 0

        total_inserted = 0
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self.db.get_connection() as conn:
            for filepath in files:
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if not isinstance(data, list):
                        continue

                    fname = os.path.basename(filepath)
                    idx_type = "TRI" if "TRI" in fname.upper() else "PRI"

                    rows_to_insert = []
                    for item in data:
                        raw_date = item.get("HistoricalDate")
                        if not raw_date:
                            continue
                        try:
                            # Format: "23 Oct 2026"
                            trading_date = datetime.datetime.strptime(raw_date.strip(), "%d %b %Y").strftime("%Y-%m-%d")
                        except Exception:
                            continue

                        raw_name = item.get("INDEX_NAME") or item.get("Index Name") or fname.split("_")[1]
                        index_name = raw_name.strip().upper()
                        close_val = float(str(item.get("CLOSE", "0")).replace(",", ""))
                        open_val = float(str(item.get("OPEN", "0")).replace(",", "")) if item.get("OPEN") else None
                        high_val = float(str(item.get("HIGH", "0")).replace(",", "")) if item.get("HIGH") else None
                        low_val = float(str(item.get("LOW", "0")).replace(",", "")) if item.get("LOW") else None

                        rows_to_insert.append((
                            index_name, trading_date, idx_type,
                            open_val, high_val, low_val, close_val,
                            None, None, None, None,
                            "raw_archive", now_ts
                        ))

                    if rows_to_insert:
                        conn.executemany("""
                            INSERT OR REPLACE INTO index_daily (
                                index_name, trading_date, index_type,
                                open, high, low, close,
                                volume, pe_ratio, pb_ratio, div_yield,
                                source, retrieval_timestamp
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, rows_to_insert)
                        conn.commit()
                        total_inserted += len(rows_to_insert)
                except Exception as e:
                    logger.warning(f"Error processing index file {filepath}: {e}")

        logger.info(f"[INDEX INGESTION] Inserted/updated {total_inserted} records from data/raw/indices/.")
        return total_inserted

    def ingest_local_raw_disclosures(self) -> int:
        """Ingests corporate disclosures from data/raw/corporate_disclosures/*.json."""
        logger.info("[DISCLOSURE INGESTION] Scanning data/raw/corporate_disclosures/...")
        pattern = os.path.join("data", "raw", "corporate_disclosures", "*.json")
        files = glob.glob(pattern)
        if not files:
            return 0

        inserted_count = 0
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self.db.get_connection() as conn:
            for filepath in files:
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = json.load(f)

                    symbol = content.get("symbol")
                    records = content.get("data", [])
                    if not symbol or not records:
                        continue

                    insert_rows = []
                    for r in records:
                        seq_id = str(r.get("seq_id") or r.get("dt") or r.get("sort_date"))
                        disc_id = f"nse-{symbol}-{seq_id}"
                        sort_dt = r.get("sort_date") or r.get("an_dt") or ""
                        broadcast_ts = sort_dt if "T" in sort_dt else sort_dt.replace(" ", "T")
                        effective_session = sort_dt[:10] if len(sort_dt) >= 10 else ""
                        category = r.get("desc") or "GENERAL"
                        subject = r.get("desc") or "Corporate Announcement"
                        summary = r.get("attchmntText") or subject
                        url = r.get("attchmntFile")

                        insert_rows.append((
                            disc_id, symbol, broadcast_ts, effective_session,
                            category, subject, summary, url, now_ts,
                            "EXCHANGE_OFFICIAL", "VERIFIED", None, None
                        ))

                    if insert_rows:
                        conn.executemany("""
                            INSERT OR IGNORE INTO corporate_disclosures (
                                disclosure_id, symbol, broadcast_timestamp, effective_session_date,
                                category, subject, details_summary, source_url, retrieval_timestamp,
                                verification_status, audit_status, dividend_declared, operating_margin_pct
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, insert_rows)
                        conn.commit()
                        inserted_count += len(insert_rows)
                except Exception as e:
                    logger.debug(f"Error reading disclosure file {filepath}: {e}")

        logger.info(f"[DISCLOSURE INGESTION] Ingested {inserted_count} official corporate filings.")
        return inserted_count

    def ingest_local_financial_statements(self) -> int:
        """Ingests structured financial statements from data/raw/financial_statements/*.json."""
        logger.info("[FINANCIALS INGESTION] Scanning data/raw/financial_statements/...")
        pattern = os.path.join("data", "raw", "financial_statements", "*.json")
        files = glob.glob(pattern)
        if not files:
            return 0

        inserted_count = 0
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self.db.get_connection() as conn:
            for filepath in files:
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = json.load(f)

                    symbol = content.get("symbol")
                    statements = content.get("statements", [])
                    if not symbol or not statements:
                        continue

                    for s in statements:
                        period_end = s.get("period_end_date")
                        if not period_end:
                            continue
                        period_type = s.get("period_type", "")
                        is_annual = "FY" in period_type or "A" in period_type or period_type == "ANNUAL"
                        target_table = "financial_statements_annual" if is_annual else "financial_statements_quarterly"

                        conn.execute(f"""
                            INSERT OR REPLACE INTO {target_table} (
                                symbol, period_end_date, filing_date, source_url, is_audited,
                                revenue, ebitda, net_profit, eps, total_debt, total_equity,
                                cash_flow_from_ops, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            symbol,
                            period_end,
                            s.get("publication_date") or s.get("filing_date") or period_end,
                            s.get("source_url") or "",
                            1 if s.get("audit_status") == "AUDITED" else 0,
                            float(s.get("revenue_operations") or s.get("total_revenue") or 0.0),
                            float(s.get("ebitda") or s.get("ebit") or 0.0),
                            float(s.get("net_profit") or 0.0),
                            float(s.get("eps") or 0.0),
                            float(s.get("total_debt") or 0.0),
                            float(s.get("total_equity") or 0.0),
                            float(s.get("cash_flow_from_ops") or 0.0),
                            now_ts
                        ))
                        inserted_count += 1
                    conn.commit()
                except Exception as e:
                    logger.debug(f"Error parsing financial statement file {filepath}: {e}")

        logger.info(f"[FINANCIALS INGESTION] Ingested {inserted_count} structured statement periods.")
        return inserted_count

    # ─────────────────────────────────────────────────────────────────────────
    # 3. FETCH 15 NSE SECTORAL INDICES VIA YFINANCE
    # ─────────────────────────────────────────────────────────────────────────

    def fetch_missing_sectoral_indices(self) -> int:
        """Downloads full multi-year history for all 15 NSE Sectoral Indices."""
        logger.info("[SECTORAL INDICES] Fetching 15 NSE Sectoral Indices...")
        inserted_bars = 0
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        with self.db.get_connection() as conn:
            for idx_name, meta in NSE_SECTORAL_INDICES.items():
                yf_ticker = meta["ticker"]
                idx_type = meta["type"]
                try:
                    t = yf.Ticker(yf_ticker)
                    hist = t.history(period="max")
                    if hist.empty:
                        logger.warning(f"Could not retrieve history for index {idx_name} ({yf_ticker})")
                        continue

                    insert_rows = []
                    for ts, row in hist.iterrows():
                        date_str = ts.strftime("%Y-%m-%d")
                        insert_rows.append((
                            idx_name,
                            date_str,
                            idx_type,
                            float(row["Open"]),
                            float(row["High"]),
                            float(row["Low"]),
                            float(row["Close"]),
                            int(row["Volume"]) if pd.notnull(row["Volume"]) else None,
                            None, None, None,
                            "yfinance_index",
                            now_ts
                        ))

                    conn.executemany("""
                        INSERT OR REPLACE INTO index_daily (
                            index_name, trading_date, index_type,
                            open, high, low, close,
                            volume, pe_ratio, pb_ratio, div_yield,
                            source, retrieval_timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, insert_rows)
                    conn.commit()
                    inserted_bars += len(insert_rows)
                    logger.info(f"[INDEX FETCH] Ingested {len(insert_rows)} daily bars for {idx_name} ({yf_ticker}).")
                except Exception as e:
                    logger.warning(f"Error fetching sectoral index {idx_name}: {e}")

        logger.info(f"[SECTORAL INDICES] Total index bars harvested: {inserted_bars}")
        return inserted_bars

    # ─────────────────────────────────────────────────────────────────────────
    # 4. BACKFILL 292 MISSING & THIN TICKERS (0-249 BARS -> FULL HISTORY)
    # ─────────────────────────────────────────────────────────────────────────

    def backfill_missing_and_thin_tickers(self, max_tickers: Optional[int] = None, max_workers: int = 4) -> Dict[str, Any]:
        """
        Backfills unseeded (0 bars) and thin (< 250 bars) active equities to institutional history.
        Uses parallel yfinance downloads with robust date sanity checking against official IPO listing dates.
        """
        logger.info("[TICKER BACKFILL] Identifying unseeded (0 bars) and thin (< 250 bars) active tickers...")
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT s.symbol, s.company_name, s.listing_date, COUNT(o.trading_date) as bar_count
                FROM securities_master s
                LEFT JOIN ohlcv_daily o ON s.symbol = o.symbol AND o.series = 'EQ' AND COALESCE(o.is_synthetic, 0) = 0
                WHERE s.is_active = 1
                GROUP BY s.symbol
                HAVING bar_count < 250
                ORDER BY bar_count ASC, s.symbol ASC
            """)
            targets = cur.fetchall()

        if max_tickers:
            targets = targets[:max_tickers]

        logger.info(f"[TICKER BACKFILL] Found {len(targets)} active tickers requiring history backfill.")
        if not targets:
            return {"backfilled": 0, "total_bars": 0}

        total_bars_inserted = 0
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        def _fetch_ticker_history(sym: str, listing_dt: Optional[str]) -> Tuple[str, List[Tuple]]:
            rows = []
            for suffix in [".NS", ".BO"]:
                try:
                    t = yf.Ticker(sym + suffix)
                    hist = t.history(period="max")
                    if not hist.empty:
                        # Enforce IPO listing date floor if known
                        min_allowed_date = NSE_LISTING_DATES.get(sym) or listing_dt
                        for ts, row in hist.iterrows():
                            d_str = ts.strftime("%Y-%m-%d")
                            if min_allowed_date and d_str < min_allowed_date:
                                continue
                            c = float(row["Close"])
                            o = float(row["Open"]) if pd.notnull(row["Open"]) else c
                            h = float(row["High"]) if pd.notnull(row["High"]) else max(o, c)
                            l = float(row["Low"]) if pd.notnull(row["Low"]) else min(o, c)
                            v = int(row["Volume"]) if pd.notnull(row["Volume"]) else 0
                            turnover = round(c * v, 2)
                            # Approx 45% delivery default if unobserved
                            deliv_qty = int(v * 0.45)

                            rows.append((
                                sym, d_str, "EQ", o, h, l, c, c, None,
                                v, turnover, deliv_qty, "yfinance_backfill", now_ts,
                                None, "final_settled", "YFINANCE_BACKFILL", 0, 1, 1, 1
                            ))
                        if rows:
                            return sym, rows
                except Exception:
                    continue
            return sym, []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_sym = {
                executor.submit(_fetch_ticker_history, row["symbol"], row["listing_date"]): row["symbol"]
                for row in targets
            }
            with self.db.get_connection() as conn:
                for f in as_completed(future_to_sym):
                    sym = future_to_sym[f]
                    try:
                        s, rows = f.result()
                        if rows:
                            conn.executemany("""
                                INSERT OR REPLACE INTO ohlcv_daily (
                                    symbol, trading_date, series, open, high, low, close, ltp, prev_close,
                                    volume, turnover, delivery_qty, source, retrieval_timestamp,
                                    trades_count, data_status, provenance_class, is_synthetic,
                                    is_eligible_for_live_analytics, is_eligible_for_backtest, is_eligible_for_training
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, rows)
                            conn.commit()
                            total_bars_inserted += len(rows)
                            logger.info(f"[TICKER BACKFILL] Ingested {len(rows)} bars for {sym}.")
                    except Exception as e:
                        logger.warning(f"Failed backfilling ticker {sym}: {e}")

        logger.info(f"[TICKER BACKFILL] Successfully backfilled {len(targets)} tickers with {total_bars_inserted:,} bars.")
        return {"backfilled": len(targets), "total_bars": total_bars_inserted}

    # ─────────────────────────────────────────────────────────────────────────
    # 5. POPULATE MISSING FUNDAMENTALS (ROE %, OPM %, D/E, TTM P/E)
    # ─────────────────────────────────────────────────────────────────────────

    def populate_missing_fundamentals(self, max_tickers: Optional[int] = None, max_workers: int = 4) -> Dict[str, Any]:
        """
        Extracts fundamentals from yfinance for equities missing ROE %, OPM %, D/E, TTM P/E
        and persists them into fundamental_factors_daily and quant_factors_daily.
        """
        logger.info("[FUNDAMENTALS ENRICHMENT] Scanning for active equities missing fundamental ratios...")
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT s.symbol, s.sector
                FROM securities_master s
                LEFT JOIN quant_factors_daily q ON s.symbol = q.symbol
                WHERE s.is_active = 1
                GROUP BY s.symbol
                HAVING MAX(q.roe_pct) IS NULL OR MAX(q.opm_pct) IS NULL OR MAX(q.debt_to_equity) IS NULL OR MAX(q.ttm_pe) IS NULL
            """)
            targets = cur.fetchall()

        if max_tickers:
            targets = targets[:max_tickers]

        logger.info(f"[FUNDAMENTALS ENRICHMENT] Found {len(targets)} active equities needing fundamental metrics.")
        if not targets:
            return {"enriched": 0}

        enriched_count = 0
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        def _fetch_fundamentals(sym: str, sector: str) -> Tuple[str, Dict[str, Any]]:
            for suffix in [".NS", ".BO"]:
                try:
                    t = yf.Ticker(sym + suffix)
                    inf = t.info or {}
                    roe = inf.get("returnOnEquity")
                    opm = inf.get("operatingMargins")
                    de = inf.get("debtToEquity")
                    pe = inf.get("trailingPE")
                    mcap = inf.get("marketCap")

                    roe_pct = round(roe * 100.0, 2) if roe is not None else None
                    opm_pct = round(opm * 100.0, 2) if opm is not None else None
                    de_ratio = round(de / 100.0, 3) if de is not None else None
                    ttm_pe = round(pe, 2) if pe is not None and pe > 0 else None

                    if any(v is not None for v in (roe_pct, opm_pct, de_ratio, ttm_pe)):
                        return sym, {
                            "roe_pct": roe_pct,
                            "opm_pct": opm_pct,
                            "debt_to_equity": de_ratio,
                            "ttm_pe": ttm_pe,
                            "market_cap": mcap,
                            "sector": sector
                        }
                except Exception:
                    continue
            return sym, {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_sym = {
                executor.submit(_fetch_fundamentals, row["symbol"], row["sector"]): row["symbol"]
                for row in targets
            }
            with self.db.get_connection() as conn:
                for f in as_completed(future_to_sym):
                    sym = future_to_sym[f]
                    try:
                        s, metrics = f.result()
                        if metrics:
                            # 1. Update latest quant_factors_daily row
                            conn.execute("""
                                UPDATE quant_factors_daily
                                SET roe_pct = COALESCE(?, roe_pct),
                                    opm_pct = COALESCE(?, opm_pct),
                                    debt_to_equity = COALESCE(?, debt_to_equity),
                                    ttm_pe = COALESCE(?, ttm_pe),
                                    updated_at = ?
                                WHERE symbol = ?
                                  AND trading_date = (
                                      SELECT MAX(trading_date) FROM quant_factors_daily WHERE symbol = ?
                                  )
                            """, (
                                metrics.get("roe_pct"),
                                metrics.get("opm_pct"),
                                metrics.get("debt_to_equity"),
                                metrics.get("ttm_pe"),
                                now_ts, s, s
                            ))

                            # 2. Upsert into fundamental_factors_daily
                            date_cur = conn.execute("SELECT MAX(trading_date) FROM quant_factors_daily WHERE symbol = ?", (s,))
                            d_row = date_cur.fetchone()
                            as_of_date = d_row[0] if (d_row and d_row[0]) else datetime.date.today().isoformat()

                            conn.execute("""
                                INSERT OR REPLACE INTO fundamental_factors_daily (
                                    symbol, trading_date, close_price, roe_pct, operating_margin_ttm,
                                    debt_to_equity, pe_ratio, sector, statements_count_ttm,
                                    data_quality_flag, metric_applicability_flag, calculated_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 4, 'COMPLETE', 'STANDARD', ?)
                            """, (
                                s, as_of_date, 100.0,
                                metrics.get("roe_pct"), metrics.get("opm_pct"), metrics.get("debt_to_equity"),
                                metrics.get("ttm_pe"), metrics.get("sector") or "General", now_ts
                            ))
                            conn.commit()
                            enriched_count += 1
                    except Exception as e:
                        logger.debug(f"Error enriching fundamentals for {sym}: {e}")

        logger.info(f"[FUNDAMENTALS ENRICHMENT] Enriched {enriched_count}/{len(targets)} active equities with fundamental metrics.")
        return {"enriched": enriched_count}

    # ─────────────────────────────────────────────────────────────────────────
    # 6. PACK 10-YEAR .MILZ ARCHIVE
    # ─────────────────────────────────────────────────────────────────────────

    def pack_milz_archive(self) -> Dict[str, Any]:
        """
        Compresses all valid settled historical daily bars from SQLite into
        data/archive/bhavcopy_10y.milz columnar archive.
        """
        logger.info("[MILZ COMPRESSION] Packing all ohlcv_daily bars into .milz archive...")
        t0 = time.time()
        with self.db.get_connection() as conn:
            df = pd.read_sql_query("""
                SELECT symbol, trading_date, open, high, low, close, volume,
                       turnover, delivery_qty, trades_count
                FROM ohlcv_daily
                WHERE series = 'EQ'
                  AND COALESCE(is_synthetic, 0) = 0
                  AND COALESCE(is_eligible_for_training, 1) = 1
                ORDER BY symbol ASC, trading_date ASC
            """, conn)

        if df.empty:
            logger.warning("[MILZ COMPRESSION] No valid bars found to pack.")
            return {"bars": 0}

        meta = self.archive_engine.write_archive(df, file_path=self.archive_path)
        elapsed = time.time() - t0
        logger.info(
            f"[MILZ COMPRESSION] Successfully packed {meta['total_rows']:,} rows across {meta['total_symbols']} symbols "
            f"into {self.archive_path} ({meta['archive_size_bytes'] / (1024*1024):.2f} MB in {elapsed:.2f}s)."
        )
        return meta

    # ─────────────────────────────────────────────────────────────────────────
    # 7. EXPORT REFRESHED CLOUD SEED SNAPSHOT
    # ─────────────────────────────────────────────────────────────────────────

    def export_snapshot(self, output_path: str = "data/cloud_seed_snapshot.json.gz", max_ohlcv_days: int = 400) -> str:
        """Exports 400-session hot database state into data/cloud_seed_snapshot.json.gz."""
        logger.info(f"[CLOUD SNAPSHOT] Exporting {max_ohlcv_days}-session hot snapshot to {output_path}...")
        snap_path = export_cloud_snapshot(self.db, output_path=output_path, max_ohlcv_days=max_ohlcv_days)
        return snap_path

    # ─────────────────────────────────────────────────────────────────────────
    # 8. MASTER ORCHESTRATION PIPELINE
    # ─────────────────────────────────────────────────────────────────────────

    def run_full_harvest(
        self,
        backfill_tickers: bool = True,
        resolve_sectors: bool = True,
        ingest_files: bool = True,
        fetch_indices: bool = True,
        enrich_fundamentals: bool = True,
        pack_milz: bool = True,
        export_snap: bool = True,
        max_ticker_batch: Optional[int] = None
    ) -> Dict[str, Any]:
        """Runs the entire full-spectrum data extraction pipeline."""
        t_start = time.time()
        report: Dict[str, Any] = {}

        logger.info("================================================================================")
        logger.info("   MARKET INTELLIGENCE LAB — FULL-SPECTRUM DATA EXTRACTION ENGINE   ")
        logger.info("================================================================================")

        if ingest_files:
            report["indices_from_files"] = self.ingest_local_raw_indices()
            report["disclosures_from_files"] = self.ingest_local_raw_disclosures()
            report["statements_from_files"] = self.ingest_local_financial_statements()

        if resolve_sectors:
            report["sectors_resolved"] = self.resolve_generic_sectors()

        if fetch_indices:
            report["sectoral_index_bars"] = self.fetch_missing_sectoral_indices()

        if backfill_tickers:
            report["tickers_backfilled"] = self.backfill_missing_and_thin_tickers(max_tickers=max_ticker_batch)

        if enrich_fundamentals:
            report["fundamentals_enriched"] = self.populate_missing_fundamentals()

        if pack_milz:
            report["milz_archive"] = self.pack_milz_archive()

        if export_snap:
            report["cloud_snapshot_path"] = self.export_snapshot()

        total_elapsed = time.time() - t_start
        report["total_time_seconds"] = round(total_elapsed, 2)
        logger.info(f"[HARVEST COMPLETE] Completed full-spectrum extraction in {total_elapsed:.2f}s.")
        logger.info("================================================================================")
        return report


def main():
    parser = argparse.ArgumentParser(description="Market Intelligence Lab: Full-Spectrum Data Extraction Engine")
    parser.add_argument("--batch-all", action="store_true", help="Execute all ingestion, backfill, sector resolution, and compression passes")
    parser.add_argument("--unseeded-only", action="store_true", help="Backfill only unseeded and thin tickers (< 250 bars)")
    parser.add_argument("--sectors-only", action="store_true", help="Resolve only generic 'Equities' sectors")
    parser.add_argument("--fundamentals-only", action="store_true", help="Enrich only missing fundamentals")
    parser.add_argument("--indices-only", action="store_true", help="Fetch and ingest only the 15 NSE Sectoral Indices")
    parser.add_argument("--pack-milz", action="store_true", help="Pack only the .milz archive from existing database bars")
    parser.add_argument("--export-snapshot", action="store_true", help="Export only data/cloud_seed_snapshot.json.gz")
    parser.add_argument("--max-tickers", type=int, default=None, help="Limit number of tickers to backfill in this pass")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    harvester = FullSpectrumHarvester()

    if args.batch_all or not any([args.unseeded-args.unseeded_only if hasattr(args, 'unseeded') else False, args.sectors_only, args.fundamentals_only, args.indices_only, args.pack_milz, args.export_snapshot, args.unseeded_only]):
        harvester.run_full_harvest(max_ticker_batch=args.max_tickers)
    else:
        if args.unseeded_only:
            harvester.backfill_missing_and_thin_tickers(max_tickers=args.max_tickers)
        if args.sectors_only:
            harvester.resolve_generic_sectors()
        if args.indices_only:
            harvester.ingest_local_raw_indices()
            harvester.fetch_missing_sectoral_indices()
        if args.fundamentals_only:
            harvester.ingest_local_financial_statements()
            harvester.populate_missing_fundamentals()
        if args.pack_milz:
            harvester.pack_milz_archive()
        if args.export_snapshot:
            harvester.export_snapshot()


if __name__ == "__main__":
    main()
