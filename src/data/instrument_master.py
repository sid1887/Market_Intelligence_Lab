"""
src/data/instrument_master.py
Authoritative Registry of Instrument Listing Dates for the National Stock Exchange (NSE).
Phase 10.1: Enforces data truth and prevents ghost/survivor-bias trading bars for securities
prior to their official exchange IPO listing dates (e.g. AADHARHFC listed May 15, 2024).
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime

from src.storage.database import DatabaseManager

logger = logging.getLogger("MIL.InstrumentMaster")

# Authoritative NSE listing dates for universe equities
# Format: Symbol -> 'YYYY-MM-DD'
NSE_LISTING_DATES: Dict[str, str] = {
    # Recent IPOs and Modern Listings (2020 - 2026)
    "AADHARHFC": "2024-05-15",    # Aadhar Housing Finance IPO listing
    "ACMESOLAR": "2024-11-13",
    "AFCONS": "2024-11-04",
    "BAJAJHFL": "2024-09-16",
    "FIRSTCRY": "2024-08-13",
    "BHARTIHEXA": "2024-04-12",
    "AZAD": "2023-12-28",
    "CONCORDBIO": "2023-08-18",
    "JIOFIN": "2023-08-21",
    "DRONACHRYA": "2022-12-23",
    "KAYNES": "2022-11-22",
    "MEDANTA": "2022-11-16",
    "SYRMA": "2022-08-26",
    "AETHER": "2022-06-03",
    "LIC": "2022-05-17",
    "LICI": "2022-05-17",
    "AWL": "2022-02-08",
    "ANANDRATHI": "2021-12-14",
    "MAPMYINDIA": "2021-12-21",
    "PAYTM": "2021-11-18",
    "POLICYBZR": "2021-11-15",
    "NYKAA": "2021-11-10",
    "ABSLAMC": "2021-10-11",
    "APTUS": "2021-08-24",
    "CARTRADE": "2021-08-20",
    "ETERNAL": "2021-07-23",     # Zomato IPO listing date
    "ZOMATO": "2021-07-23",
    "CLEAN": "2021-07-19",
    "CRAFTSMAN": "2021-03-25",
    "ANGELONE": "2020-10-05",
    "CAMS": "2020-10-01",
    "MAXHEALTH": "2020-08-21",
    "TMPV": "2025-10-24",        # Tata Motors Passenger Vehicle demerger listing

    # Pre-2020 Historical Listings
    "IRCTC": "2019-10-14",
    "RVNL": "2019-04-11",
    "ADANIGREEN": "2018-06-18",
    "HAL": "2018-03-28",
    "BANDHANBNK": "2018-03-27",
    "LTIM": "2016-07-21",
    "ADANIENSOL": "2015-07-31",
    "COALINDIA": "2010-11-04",
    "ADANIPOWER": "2009-08-20",
    "BAJAJFINSV": "2008-05-26",
    "BAJAJ-AUTO": "2008-05-26",
    "ADANIPORTS": "2007-11-27",
    "POWERGRID": "2007-10-05",
    "IDEA": "2007-03-09",
    "TECHM": "2006-08-28",
    "SUZLON": "2005-10-19",
    "JSWSTEEL": "2005-03-25",
    "NTPC": "2004-11-05",
    "COFORGE": "2004-08-30",
    "TCS": "2004-08-25",
    "ULTRACEMCO": "2004-08-24",
    "MARUTI": "2003-07-09",
    "DIVISLAB": "2003-03-12",
    "BHARTIARTL": "2002-02-18",
    "TRIDENT": "2001-07-04",
    "DRREDDY": "2001-05-30",
    "HCLTECH": "2000-01-12",
    "AXISBANK": "1998-11-16",
    "BAJFINANCE": "1998-07-01",
    "ICICIBANK": "1997-09-17",
    "ADANIENT": "1997-06-04",
    "GAIL": "1997-03-12",
    "KOTAKBANK": "1996-03-27",
    "APOLLOHOSP": "1996-01-10",
    "WIPRO": "1995-11-08",
    "BPCL": "1995-09-13",
    "ONGC": "1995-07-19",
    "IOC": "1995-07-19",
    "HINDUNILVR": "1995-07-06",
    "BHEL": "1995-06-21",
    "ASIANPAINT": "1995-05-31",
    "NESTLEIND": "1995-05-31",
    "EICHERMOT": "1995-05-31",
    "HEROMOTOCO": "1995-05-31",
    "MOREPENLAB": "1995-05-24",
    "HDFCBANK": "1995-05-19",
    "HINDALCO": "1995-05-10",
    "GRASIM": "1995-05-08",
    "SBIN": "1995-03-01",
    "SUNPHARMA": "1995-02-08",
    "CIPLA": "1995-02-08",
    "AARTIIND": "1995-02-08",
    "INFY": "1993-06-14",
    "TATACONSUM": "1990-01-01",
    "TATASTEEL": "1990-01-01",
    "TATAPOWER": "1990-01-01",
    "TITAN": "1987-03-09",
    "RELIANCE": "1977-11-29",
    "ITC": "1970-01-01",
    "LT": "1950-01-01",
}


class InstrumentMaster:
    """Authoritative registry for NSE listing dates and instrument lifecycle validity."""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self._cache: Dict[str, Optional[str]] = {}
        self._load_dates_from_db()

    def _load_dates_from_db(self) -> None:
        """Preloads listing dates from securities_master table."""
        try:
            with self.db.get_connection() as conn:
                cur = conn.execute("SELECT symbol, listing_date FROM securities_master WHERE listing_date IS NOT NULL")
                for r in cur.fetchall():
                    self._cache[r[0]] = r[1]
        except Exception as e:
            logger.warning(f"Could not preload listing dates from DB: {e}")

    def get_listing_date(self, symbol: str) -> Optional[str]:
        """
        Returns authoritative NSE listing date ('YYYY-MM-DD') for symbol.
        Checks DB cache first, then official registry, falling back to None if unlisted/unknown.
        """
        sym = symbol.strip().upper()
        if sym in self._cache and self._cache[sym] is not None:
            return self._cache[sym]

        if sym in NSE_LISTING_DATES:
            ld = NSE_LISTING_DATES[sym]
            self._cache[sym] = ld
            return ld

        return None

    def is_symbol_listed_on_date(self, symbol: str, target_date: str) -> bool:
        """
        Returns True if symbol was officially listed on or before target_date.
        If symbol has a known listing date: target_date >= listing_date.
        If listing date is unknown: returns True (permissive for established historical equities).
        """
        ld = self.get_listing_date(symbol)
        if not ld:
            return True
        return target_date >= ld

    def is_month_prior_to_listing(self, symbol: str, year: int, month: int) -> bool:
        """
        Returns True if the entire calendar month (year, month) is strictly earlier
        than the instrument's official NSE listing date.
        Example: AADHARHFC (listed 2024-05-15).
        - 2020-01 (last day 2020-01-31) < 2024-05-15 -> True (NOT_YET_LISTED)
        - 2024-05 (last day 2024-05-31) < 2024-05-15 -> False (Active month)
        """
        ld = self.get_listing_date(symbol)
        if not ld:
            return False

        import calendar
        _, last_day = calendar.monthrange(year, month)
        month_end = f"{year:04d}-{month:02d}-{last_day:02d}"
        return month_end < ld

    def sync_listing_dates_to_db(self) -> int:
        """Synchronizes authoritative listing dates into securities_master."""
        updated = 0
        with self.db.get_connection() as conn:
            for sym, ld in NSE_LISTING_DATES.items():
                cur = conn.execute(
                    "UPDATE securities_master SET listing_date = ? WHERE symbol = ?",
                    (ld, sym)
                )
                if cur.rowcount > 0:
                    updated += cur.rowcount
            conn.commit()
        logger.info(f"Synchronized listing dates for {updated} securities in securities_master.")
        return updated
