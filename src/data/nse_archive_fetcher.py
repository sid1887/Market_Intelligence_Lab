"""
src/data/nse_archive_fetcher.py
Dual-Format Caching NSE Bhavcopy Archive Fetcher.

Provides authentic exchange settlement ingestion across two historical eras:
1. Era 1 (Legacy): 2020-01-01 -> 2024-07-05
   URL: https://archives.nseindia.com/content/historical/EQUITIES/{YYYY}/{MMM}/cm{DD}{MMM}{YYYY}bhav.csv.zip
   Schema: SYMBOL, SERIES, OPEN, HIGH, LOW, CLOSE, TOTTRDQTY, TIMESTAMP
2. Era 2 (UDIFF): 2024-07-08 -> Present
   URL: https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{YYYYMMDD}_F_0000.csv.zip
   Schema: TckrSymb, SctySrs, OpnPric, HghPric, LwPric, ClsPric, TtlTradgVol, TradDt

Enforces strict truth-layer invariants:
- Zero price fabrication / random-walk simulation (is_synthetic = 0).
- Local disk caching at data/raw/bhavcopies/{YYYY}/{MM}/ to eliminate redundant downloads.
- Filter strictly for series == 'EQ' and active universe tickers.
"""

import os
import io
import csv
import time
import random
import logging
import zipfile
import calendar
from pathlib import Path
from datetime import datetime, date, timezone
from typing import Dict, Any, List, Optional, Set, Union, Tuple
import requests

logger = logging.getLogger("MIL.NSEArchiveFetcher")

UDIFF_CUTOVER_DATE = date(2024, 7, 8)

USER_AGENT_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


class NSEArchiveFetcher:
    """
    Session-warmed, caching archive fetcher for NSE official daily bhavcopies.
    Downloads and parses both legacy and UDIFF formats into standardized settlement records.
    """

    def __init__(
        self,
        cache_dir: Union[str, Path] = "data/raw/bhavcopies",
        session: Optional[requests.Session] = None,
        timeout: int = 15
    ):
        self.cache_dir = Path(cache_dir)
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com"
        })
        # In-memory month cache: (year, month) -> {symbol: [bars]}
        self._month_cache: Dict[tuple[int, int], Dict[str, List[Dict[str, Any]]]] = {}

    def get_archive_url_and_filename(self, target_date: date) -> tuple[str, str, bool]:
        """
        Determines archive URL, expected filename, and format flag (is_udiff).
        """
        year_str = target_date.strftime("%Y")
        if target_date >= UDIFF_CUTOVER_DATE:
            # Modern UDIFF
            fn = f"BhavCopy_NSE_CM_0_0_0_{target_date.strftime('%Y%m%d')}_F_0000.csv.zip"
            url = f"https://nsearchives.nseindia.com/content/cm/{fn}"
            return url, fn, True
        else:
            # Legacy NSE Bhavcopy
            mmm = target_date.strftime("%b").upper()
            dd = target_date.strftime("%d")
            fn = f"cm{dd}{mmm}{year_str}bhav.csv.zip"
            url = f"https://archives.nseindia.com/content/historical/EQUITIES/{year_str}/{mmm}/{fn}"
            return url, fn, False

    def get_candidate_sources(self, target_date: date) -> List[Dict[str, Any]]:
        """
        Generates prioritized fallback candidate sources for a given trading session:
        1. Official NSE Primary Bhavcopy (Modern UDIFF / Legacy CM)
        2. NSE Security Bhavdata Full (contains delivery and trades)
        3. BSE Official Bhavcopy mirror
        """
        year_str = target_date.strftime("%Y")
        ddmmyyyy = target_date.strftime("%d%m%Y")
        candidates = []

        # 1. Primary NSE Archive
        primary_url, primary_fn, is_udiff = self.get_archive_url_and_filename(target_date)
        candidates.append({
            "source_id": "NSE_PRIMARY",
            "url": primary_url,
            "filename": primary_fn,
            "is_zip": True,
            "is_udiff": is_udiff
        })

        # 2. Secondary NSE Security Bhavdata Full
        sec_url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
        candidates.append({
            "source_id": "NSE_SEC_BHAVDATA_MODERN",
            "url": sec_url,
            "filename": f"sec_bhavdata_full_{ddmmyyyy}.csv",
            "is_zip": False,
            "is_udiff": False
        })

        sec_legacy_url = f"https://archives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
        candidates.append({
            "source_id": "NSE_SEC_BHAVDATA_LEGACY",
            "url": sec_legacy_url,
            "filename": f"sec_bhavdata_full_{ddmmyyyy}_legacy.csv",
            "is_zip": False,
            "is_udiff": False
        })

        # 3. BSE Bhavcopy Mirror
        bse_fn = f"BhavCopy_BSE_CM_0_0_0_{target_date.strftime('%Y%m%d')}_F_0000.csv"
        bse_url = f"https://www.bseindia.com/download/BhavCopy/Equity/{bse_fn}"
        candidates.append({
            "source_id": "BSE_MIRROR",
            "url": bse_url,
            "filename": bse_fn,
            "is_zip": False,
            "is_udiff": True
        })

        return candidates

    def fetch_daily_bhavcopy(self, trading_date: Union[str, date]) -> Optional[Path]:
        """
        Retrieves local cached bhavcopy or fetches across candidate matrix with retry jitter.
        Returns Path to valid archive / CSV, or None if weekend/holiday/unavailable.
        """
        if isinstance(trading_date, str):
            t_date = datetime.strptime(trading_date.strip(), "%Y-%m-%d").date()
        else:
            t_date = trading_date

        # Skip weekends (Saturday=5, Sunday=6)
        if t_date.weekday() >= 5:
            return None

        candidates = self.get_candidate_sources(t_date)
        year_str = str(t_date.year)
        month_str = f"{t_date.month:02d}"
        dest_dir = self.cache_dir / year_str / month_str
        dest_dir.mkdir(parents=True, exist_ok=True)

        # 1. Check primary or secondary existing cache
        for cand in candidates:
            cached_candidate = dest_dir / cand["filename"]
            if cached_candidate.exists() and cached_candidate.stat().st_size > 100:
                if cand["is_zip"]:
                    if zipfile.is_zipfile(cached_candidate):
                        return cached_candidate
                    else:
                        cached_candidate.unlink(missing_ok=True)
                else:
                    return cached_candidate

        # 2. Check fallback udiff directory for primary modern filename
        primary_cand = candidates[0]
        if primary_cand.get("is_udiff"):
            udiff_fallback = Path("data/raw/udiff") / primary_cand["filename"]
            if udiff_fallback.exists() and zipfile.is_zipfile(udiff_fallback):
                target_dest = dest_dir / primary_cand["filename"]
                target_dest.write_bytes(udiff_fallback.read_bytes())
                return target_dest

        # 3. Download across candidate matrix with retry jitter & rotating User-Agent
        max_retries = 2
        for cand in candidates:
            cand_url = cand["url"]
            cand_fn = cand["filename"]
            is_zip = cand["is_zip"]
            dest_path = dest_dir / cand_fn
            temp_path = dest_dir / f"{cand_fn}.tmp_{time.time_ns()}"

            for attempt in range(1, max_retries + 1):
                try:
                    headers = {
                        "User-Agent": random.choice(USER_AGENT_POOL),
                        "Accept": "*/*",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Referer": "https://www.nseindia.com"
                    }
                    resp = self.session.get(cand_url, headers=headers, timeout=self.timeout)
                    if resp.status_code == 200 and len(resp.content) > 100:
                        temp_path.write_bytes(resp.content)
                        if is_zip:
                            if zipfile.is_zipfile(temp_path):
                                temp_path.replace(dest_path)
                                logger.info(f"Downloaded {cand_fn} ({len(resp.content)} bytes) via {cand['source_id']}.")
                                return dest_path
                            else:
                                temp_path.unlink(missing_ok=True)
                        else:
                            temp_path.replace(dest_path)
                            logger.info(f"Downloaded CSV {cand_fn} ({len(resp.content)} bytes) via {cand['source_id']}.")
                            return dest_path
                    elif resp.status_code == 404:
                        logger.debug(f"{cand['source_id']} returned 404 for {t_date}.")
                        break  # Skip retries for this 404 candidate and try next candidate
                    elif resp.status_code in (403, 429, 500, 502, 503, 504):
                        backoff = (1.5 ** attempt) + random.uniform(0.1, 0.4)
                        logger.warning(f"HTTP {resp.status_code} for {cand_url}. Backoff {backoff:.2f}s (attempt {attempt}/{max_retries}).")
                        time.sleep(backoff)
                    else:
                        break
                except (requests.RequestException, OSError) as exc:
                    backoff = (1.5 ** attempt) + random.uniform(0.1, 0.4)
                    logger.warning(f"Network error on {cand_url}: {exc}. Backoff {backoff:.2f}s.")
                    time.sleep(backoff)
                finally:
                    if temp_path.exists():
                        temp_path.unlink(missing_ok=True)

        logger.warning(f"Failed to fetch bhavcopy for {t_date} across all candidate sources.")
        return None

    def parse_bhavcopy(
        self,
        zip_path: Union[str, Path],
        universe_symbols: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extracts CSV in-memory from ZIP or directly from CSV, standardizing settlement records.
        Captures OHLCV alongside turnover, delivery volume, and trades if present.
        Filters strictly for series == 'EQ' and symbol in universe_symbols.
        """
        z_path = Path(zip_path)
        if not z_path.exists():
            return []

        records: List[Dict[str, Any]] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        def process_reader(reader: csv.reader) -> List[Dict[str, Any]]:
            extracted = []
            try:
                raw_headers = next(reader)
            except StopIteration:
                return []

            headers = [h.strip() for h in raw_headers]
            is_udiff = "TckrSymb" in headers

            sym_col = "TckrSymb" if is_udiff else ("SYMBOL" if "SYMBOL" in headers else ("Symbol" if "Symbol" in headers else None))
            srs_col = "SctySrs" if is_udiff else ("SERIES" if "SERIES" in headers else ("Series" if "Series" in headers else None))
            open_col = "OpnPric" if is_udiff else ("OPEN" if "OPEN" in headers else ("OPEN_PRICE" if "OPEN_PRICE" in headers else None))
            high_col = "HghPric" if is_udiff else ("HIGH" if "HIGH" in headers else ("HIGH_PRICE" if "HIGH_PRICE" in headers else None))
            low_col = "LwPric" if is_udiff else ("LOW" if "LOW" in headers else ("LOW_PRICE" if "LOW_PRICE" in headers else None))
            close_col = "ClsPric" if is_udiff else ("CLOSE" if "CLOSE" in headers else ("CLOSE_PRICE" if "CLOSE_PRICE" in headers else None))
            vol_col = "TtlTradgVol" if is_udiff else ("TOTTRDQTY" if "TOTTRDQTY" in headers else ("TTL_TRD_QNTY" if "TTL_TRD_QNTY" in headers else None))
            dt_col = "TradDt" if is_udiff else ("TIMESTAMP" if "TIMESTAMP" in headers else ("DATE1" if "DATE1" in headers else None))

            # Optional / enriched microstructure columns
            prev_col = "PrvsClsgPric" if "PrvsClsgPric" in headers else ("PREVCLOSE" if "PREVCLOSE" in headers else ("PREV_CLOSE" if "PREV_CLOSE" in headers else None))
            turnover_col = "TtlTrfVal" if "TtlTrfVal" in headers else ("TOTTRDVAL" if "TOTTRDVAL" in headers else ("TURNOVER_LACS" if "TURNOVER_LACS" in headers else None))
            trades_col = "TtlNbOfTxsExctd" if "TtlNbOfTxsExctd" in headers else ("TOTALTRADES" if "TOTALTRADES" in headers else ("NO_OF_TRADES" if "NO_OF_TRADES" in headers else None))
            deliv_col = "DELIV_QTY" if "DELIV_QTY" in headers else ("DlvryQty" if "DlvryQty" in headers else None)
            deliv_pct_col = "DELIV_PER" if "DELIV_PER" in headers else ("DlvryPct" if "DlvryPct" in headers else None)

            # Verify required columns exist
            required = [sym_col, srs_col, open_col, high_col, low_col, close_col, vol_col, dt_col]
            if not all(col is not None and col in headers for col in required):
                logger.warning(f"Bhavcopy {z_path.name} missing required headers. Found: {headers}")
                return []

            col_idx = {col: headers.index(col) for col in required if col is not None}
            opt_idx = {
                "prev": headers.index(prev_col) if prev_col in headers else None,
                "turnover": headers.index(turnover_col) if turnover_col in headers else None,
                "trades": headers.index(trades_col) if trades_col in headers else None,
                "deliv": headers.index(deliv_col) if deliv_col in headers else None,
                "deliv_pct": headers.index(deliv_pct_col) if deliv_pct_col in headers else None,
            }

            for row in reader:
                if not row or len(row) <= max(col_idx.values()):
                    continue

                srs = row[col_idx[srs_col]].strip()
                if srs != "EQ":
                    continue

                sym = row[col_idx[sym_col]].strip()
                if universe_symbols is not None and sym not in universe_symbols:
                    continue

                raw_dt = row[col_idx[dt_col]].strip()
                if is_udiff:
                    dt_iso = raw_dt
                else:
                    dt_iso = raw_dt
                    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%d-%m-%Y", "%Y-%m-%d"):
                        try:
                            dt_iso = datetime.strptime(raw_dt, fmt).strftime("%Y-%m-%d")
                            break
                        except ValueError:
                            pass

                try:
                    o = float(row[col_idx[open_col]])
                    h = float(row[col_idx[high_col]])
                    l = float(row[col_idx[low_col]])
                    c = float(row[col_idx[close_col]])
                    v = int(float(row[col_idx[vol_col]]))
                except (ValueError, TypeError):
                    continue

                # Optional columns parsing
                turnover = None
                if opt_idx["turnover"] is not None and len(row) > opt_idx["turnover"]:
                    t_str = row[opt_idx["turnover"]].strip()
                    if t_str and t_str != "-":
                        try:
                            val = float(t_str)
                            turnover = val * 100000.0 if turnover_col == "TURNOVER_LACS" else val
                        except ValueError:
                            pass

                prev_close = None
                if opt_idx["prev"] is not None and len(row) > opt_idx["prev"]:
                    p_str = row[opt_idx["prev"]].strip()
                    if p_str and p_str != "-":
                        try:
                            prev_close = float(p_str)
                        except ValueError:
                            pass

                trades = None
                if opt_idx["trades"] is not None and len(row) > opt_idx["trades"]:
                    tr_str = row[opt_idx["trades"]].strip()
                    if tr_str and tr_str != "-":
                        try:
                            trades = int(float(tr_str))
                        except ValueError:
                            pass

                deliv_qty = None
                if opt_idx["deliv"] is not None and len(row) > opt_idx["deliv"]:
                    dq_str = row[opt_idx["deliv"]].strip()
                    if dq_str and dq_str != "-":
                        try:
                            deliv_qty = int(float(dq_str))
                        except ValueError:
                            pass

                deliv_pct = None
                if opt_idx["deliv_pct"] is not None and len(row) > opt_idx["deliv_pct"]:
                    dp_str = row[opt_idx["deliv_pct"]].strip()
                    if dp_str and dp_str != "-":
                        try:
                            deliv_pct = float(dp_str)
                        except ValueError:
                            pass
                elif deliv_qty is not None and v > 0:
                    deliv_pct = round((deliv_qty / v) * 100.0, 2)

                extracted.append({
                    "symbol": sym,
                    "trading_date": dt_iso,
                    "series": "EQ",
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": v,
                    "turnover": turnover,
                    "prev_close": prev_close,
                    "delivery_qty": deliv_qty,
                    "delivery_pct": deliv_pct,
                    "total_trades": trades,
                    "source": "NSE_BHAVCOPY_ARCHIVE",
                    "retrieval_timestamp": now_iso,
                    "data_status": "final_settled",
                    "provenance_class": "EXCHANGE_OFFICIAL",
                    "is_synthetic": 0,
                    "is_eligible_for_live_analytics": 1,
                    "is_eligible_for_backtest": 1,
                    "is_eligible_for_training": 1
                })
            return extracted

        try:
            if zipfile.is_zipfile(z_path):
                with zipfile.ZipFile(z_path) as zf:
                    csv_members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
                    if not csv_members:
                        return []
                    with zf.open(csv_members[0]) as csv_file:
                        text_stream = io.TextIOWrapper(csv_file, encoding="utf-8", errors="replace")
                        reader = csv.reader(text_stream)
                        records = process_reader(reader)
            elif z_path.suffix.lower() == ".csv":
                with open(z_path, "r", encoding="utf-8", errors="replace") as csv_file:
                    reader = csv.reader(csv_file)
                    records = process_reader(reader)
        except Exception as err:
            logger.error(f"Error parsing bhavcopy {z_path}: {err}", exc_info=True)
            return []

        return records

    def fetch_and_parse_day(
        self,
        trading_date: Union[str, date],
        universe_symbols: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches daily bhavcopy and parses records for universe symbols.
        """
        path = self.fetch_daily_bhavcopy(trading_date)
        if not path:
            return []
        return self.parse_bhavcopy(path, universe_symbols=universe_symbols)

    def fetch_and_parse_month(
        self,
        year: int,
        month: int,
        universe_symbols: Optional[Set[str]] = None,
        max_date: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetches and parses all trading days for a calendar month.
        Returns mapping from symbol to chronologically sorted list of bars.
        Caches result in-memory.
        """
        cache_key = (year, month)
        if cache_key in self._month_cache:
            return self._month_cache[cache_key]

        _, num_days = calendar.monthrange(year, month)
        symbol_bars: Dict[str, List[Dict[str, Any]]] = {}

        for day in range(1, num_days + 1):
            d_str = f"{year:04d}-{month:02d}-{day:02d}"
            if max_date and d_str > max_date:
                continue

            day_bars = self.fetch_and_parse_day(d_str, universe_symbols=universe_symbols)
            for bar in day_bars:
                sym = bar["symbol"]
                if sym not in symbol_bars:
                    symbol_bars[sym] = []
                symbol_bars[sym].append(bar)

        # Sort bars per symbol
        for sym in symbol_bars:
            symbol_bars[sym].sort(key=lambda b: b["trading_date"])

        self._month_cache[cache_key] = symbol_bars
        return symbol_bars

    def clear_month_cache(self, keep_latest: bool = True) -> None:
        """Clears in-memory month cache to conserve RAM."""
        if not keep_latest or not self._month_cache:
            self._month_cache.clear()
        else:
            # Keep only the last inserted key
            last_key = list(self._month_cache.keys())[-1]
            last_val = self._month_cache[last_key]
            self._month_cache = {last_key: last_val}
