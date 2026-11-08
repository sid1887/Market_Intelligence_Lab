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
from typing import Dict, Any, List, Optional, Set, Union
import requests

logger = logging.getLogger("MIL.NSEArchiveFetcher")

UDIFF_CUTOVER_DATE = date(2024, 7, 8)


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

    def fetch_daily_bhavcopy(self, trading_date: Union[str, date]) -> Optional[Path]:
        """
        Retrieves local cached bhavcopy ZIP or fetches from NSE archive.
        Returns Path to valid ZIP archive, or None if weekend/holiday/unavailable.
        """
        if isinstance(trading_date, str):
            t_date = datetime.strptime(trading_date.strip(), "%Y-%m-%d").date()
        else:
            t_date = trading_date

        # Skip weekends (Saturday=5, Sunday=6)
        if t_date.weekday() >= 5:
            return None

        url, fn, is_udiff = self.get_archive_url_and_filename(t_date)
        year_str = str(t_date.year)
        month_str = f"{t_date.month:02d}"
        dest_dir = self.cache_dir / year_str / month_str
        dest_path = dest_dir / fn

        # 1. Check primary disk cache
        if dest_path.exists() and dest_path.stat().st_size > 0:
            if zipfile.is_zipfile(dest_path):
                return dest_path
            else:
                logger.warning(f"Corrupted zip in cache at {dest_path}, removing.")
                dest_path.unlink(missing_ok=True)

        # 2. Check fallback udiff directory if applicable
        if is_udiff:
            udiff_fallback = Path("data/raw/udiff") / fn
            if udiff_fallback.exists() and zipfile.is_zipfile(udiff_fallback):
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_path.write_bytes(udiff_fallback.read_bytes())
                return dest_path

        # 3. Download from official NSE archive with retry & exponential backoff
        dest_dir.mkdir(parents=True, exist_ok=True)
        temp_path = dest_dir / f"{fn}.tmp_{time.time_ns()}"

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                if resp.status_code == 200:
                    temp_path.write_bytes(resp.content)
                    if zipfile.is_zipfile(temp_path):
                        temp_path.replace(dest_path)
                        logger.info(f"Downloaded {fn} ({len(resp.content)} bytes) from NSE archive.")
                        return dest_path
                    else:
                        logger.warning(f"Response for {url} is not a valid zip archive.")
                        temp_path.unlink(missing_ok=True)
                        return None
                elif resp.status_code == 404:
                    # Trading holiday or unarchived date
                    logger.debug(f"Trading date {t_date} returned 404 (holiday/no session).")
                    return None
                elif resp.status_code in (403, 429, 500, 502, 503, 504):
                    backoff = (2 ** attempt) + random.uniform(0.1, 0.5)
                    logger.warning(f"HTTP {resp.status_code} for {url}. Retrying in {backoff:.2f}s (attempt {attempt}/{max_retries}).")
                    time.sleep(backoff)
                else:
                    logger.warning(f"Unexpected HTTP {resp.status_code} for {url}.")
                    return None
            except (requests.RequestException, OSError) as exc:
                backoff = (2 ** attempt) + random.uniform(0.1, 0.5)
                logger.warning(f"Network error fetching {url}: {exc}. Retrying in {backoff:.2f}s (attempt {attempt}/{max_retries}).")
                time.sleep(backoff)
            finally:
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)

        logger.warning(f"Failed to fetch bhavcopy for {t_date} after {max_retries} attempts.")
        return None

    def parse_bhavcopy(
        self,
        zip_path: Union[str, Path],
        universe_symbols: Optional[Set[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extracts CSV in-memory from ZIP and standardizes settlement records.
        Filters strictly for series == 'EQ' and symbol in universe_symbols.
        """
        z_path = Path(zip_path)
        if not z_path.exists() or not zipfile.is_zipfile(z_path):
            return []

        records: List[Dict[str, Any]] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            with zipfile.ZipFile(z_path) as zf:
                csv_members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
                if not csv_members:
                    return []

                with zf.open(csv_members[0]) as csv_file:
                    text_stream = io.TextIOWrapper(csv_file, encoding="utf-8", errors="replace")
                    reader = csv.reader(text_stream)

                    # Extract and clean headers
                    try:
                        raw_headers = next(reader)
                    except StopIteration:
                        return []

                    headers = [h.strip() for h in raw_headers]
                    is_udiff = "TckrSymb" in headers

                    sym_col = "TckrSymb" if is_udiff else "SYMBOL"
                    srs_col = "SctySrs" if is_udiff else "SERIES"
                    open_col = "OpnPric" if is_udiff else "OPEN"
                    high_col = "HghPric" if is_udiff else "HIGH"
                    low_col = "LwPric" if is_udiff else "LOW"
                    close_col = "ClsPric" if is_udiff else "CLOSE"
                    vol_col = "TtlTradgVol" if is_udiff else "TOTTRDQTY"
                    dt_col = "TradDt" if is_udiff else "TIMESTAMP"

                    # Verify required columns exist
                    required = [sym_col, srs_col, open_col, high_col, low_col, close_col, vol_col, dt_col]
                    if not all(col in headers for col in required):
                        logger.warning(f"Bhavcopy {z_path.name} missing required headers. Found: {headers}")
                        return []

                    col_idx = {col: headers.index(col) for col in required}

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

                        records.append({
                            "symbol": sym,
                            "trading_date": dt_iso,
                            "series": "EQ",
                            "open": o,
                            "high": h,
                            "low": l,
                            "close": c,
                            "volume": v,
                            "source": "NSE_BHAVCOPY_ARCHIVE",
                            "retrieval_timestamp": now_iso,
                            "data_status": "final_settled",
                            "provenance_class": "EXCHANGE_OFFICIAL",
                            "is_synthetic": 0,
                            "is_eligible_for_live_analytics": 1,
                            "is_eligible_for_backtest": 1,
                            "is_eligible_for_training": 1
                        })

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
