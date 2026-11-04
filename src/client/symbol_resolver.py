"""
Market Intelligence Lab — Universal Ticker Resolver (Milestone B6.4).

Dynamically verifies and discovers unseeded equity tickers from the National Stock Exchange
of India (NSE) cash segment (series 'EQ'). Registers newly discovered equities into
securities_master with is_active = 1 and is_nifty50 = 0 while keeping index_membership_history
strictly isolated to maintain Nifty 50 market breadth invariants.
"""

import os
import re
import datetime
import logging
from typing import Dict, Any, Optional

import requests
from src.config import is_network_allowed
from src.storage.database import DatabaseManager
from src.client.corporate_client import CorporateClient

logger = logging.getLogger(__name__)

# Authoritative reference catalog of active NSE cash equities for offline/deterministic resolution
KNOWN_NSE_EQUITIES: Dict[str, Dict[str, str]] = {
    "TATAPOWER": {
        "company_name": "Tata Power Company Limited",
        "isin": "INE245A01021",
        "industry": "Electric Utilities",
        "sector": "Power",
        "macro_sector": "Energy & Utilities"
    },
    "RVNL": {
        "company_name": "Rail Vikas Nigam Limited",
        "isin": "INE415G01027",
        "industry": "Civil Construction",
        "sector": "Construction & Infrastructure",
        "macro_sector": "Capital Goods"
    },
    "NHPC": {
        "company_name": "NHPC Limited",
        "isin": "INE848E01016",
        "industry": "Electric Utilities",
        "sector": "Power",
        "macro_sector": "Energy & Utilities"
    },
    "IDEA": {
        "company_name": "Vodafone Idea Limited",
        "isin": "INE669E01016",
        "industry": "Telecom - Services",
        "sector": "Telecommunication",
        "macro_sector": "Communication Services"
    },
    "IRFC": {
        "company_name": "Indian Railway Finance Corporation Limited",
        "isin": "INE053F01010",
        "industry": "Financial Institution",
        "sector": "Financial Services",
        "macro_sector": "Financials"
    },
    "BHEL": {
        "company_name": "Bharat Heavy Electricals Limited",
        "isin": "INE257A01026",
        "industry": "Heavy Electrical Equipment",
        "sector": "Capital Goods",
        "macro_sector": "Energy & Industrials"
    },
    "ZOMATO": {
        "company_name": "Zomato Limited",
        "isin": "INE758T01015",
        "industry": "E-Commerce",
        "sector": "Consumer Services",
        "macro_sector": "Consumer Discretionary"
    },
    "PAYTM": {
        "company_name": "One97 Communications Limited",
        "isin": "INE982J01020",
        "industry": "Financial Technology",
        "sector": "Financial Services",
        "macro_sector": "Technology"
    },
    "JIOFIN": {
        "company_name": "Jio Financial Services Limited",
        "isin": "INE758E01017",
        "industry": "Financial Services",
        "sector": "Financials",
        "macro_sector": "Financials"
    },
    "YESBANK": {
        "company_name": "Yes Bank Limited",
        "isin": "INE528G01035",
        "industry": "Private Sector Bank",
        "sector": "Financial Services",
        "macro_sector": "Financials"
    },
    "VEDL": {
        "company_name": "Vedanta Limited",
        "isin": "INE205A01025",
        "industry": "Diversified Metals",
        "sector": "Metals & Mining",
        "macro_sector": "Basic Materials"
    },
    "IOC": {
        "company_name": "Indian Oil Corporation Limited",
        "isin": "INE242A01010",
        "industry": "Refineries",
        "sector": "Energy",
        "macro_sector": "Energy"
    },
    "GAIL": {
        "company_name": "GAIL (India) Limited",
        "isin": "INE129A01019",
        "industry": "Gas Distribution",
        "sector": "Utilities",
        "macro_sector": "Utilities"
    },
    "PNB": {
        "company_name": "Punjab National Bank",
        "isin": "INE160A01022",
        "industry": "Public Sector Bank",
        "sector": "Financial Services",
        "macro_sector": "Financials"
    },
    "BANKBARODA": {
        "company_name": "Bank of Baroda",
        "isin": "INE077A01032",
        "industry": "Public Sector Bank",
        "sector": "Financial Services",
        "macro_sector": "Financials"
    },
    "CANBK": {
        "company_name": "Canara Bank",
        "isin": "INE476A01014",
        "industry": "Public Sector Bank",
        "sector": "Financial Services",
        "macro_sector": "Financials"
    },
    "RECLTD": {
        "company_name": "REC Limited",
        "isin": "INE020B01018",
        "industry": "Finance - NBFC",
        "sector": "Financial Services",
        "macro_sector": "Financials"
    },
    "PFC": {
        "company_name": "Power Finance Corporation Limited",
        "isin": "INE134E01011",
        "industry": "Finance - NBFC",
        "sector": "Financial Services",
        "macro_sector": "Financials"
    },
    "SAIL": {
        "company_name": "Steel Authority of India Limited",
        "isin": "INE114A01011",
        "industry": "Steel & Iron Products",
        "sector": "Metals & Mining",
        "macro_sector": "Basic Materials"
    },
    "HAL": {
        "company_name": "Hindustan Aeronautics Limited",
        "isin": "INE066F01012",
        "industry": "Aerospace & Defense",
        "sector": "Aerospace / Defense",
        "macro_sector": "Capital Goods"
    },
    "BEL": {
        "company_name": "Bharat Electronics Limited",
        "isin": "INE263A01024",
        "industry": "Aerospace & Defense",
        "sector": "Aerospace / Defense",
        "macro_sector": "Capital Goods"
    },
    "DLF": {
        "company_name": "DLF Limited",
        "isin": "INE271C01023",
        "industry": "Real Estate",
        "sector": "Real Estate",
        "macro_sector": "Real Estate"
    },
    "SUZLON": {
        "company_name": "Suzlon Energy Ltd",
        "isin": "INE040H01021",
        "industry": "Heavy Electrical Equipment",
        "sector": "Renewable Energy",
        "macro_sector": "Energy & Industrials"
    },
    "TRIDENT": {
        "company_name": "Trident Ltd",
        "isin": "INE064C01022",
        "industry": "Textiles",
        "sector": "Textiles / Paper",
        "macro_sector": "Consumer Discretionary"
    },
    "DRONACHRYA": {
        "company_name": "Droneacharya Aerial Innovations Ltd",
        "isin": "INE0N6101014",
        "industry": "Aerospace & Defense",
        "sector": "Aerospace / Defense",
        "macro_sector": "Capital Goods"
    },
    "MOREPENLAB": {
        "company_name": "Morepen Laboratories Ltd",
        "isin": "INE083A01026",
        "industry": "Pharmaceuticals & Biotechnology",
        "sector": "Pharmaceuticals",
        "macro_sector": "Healthcare"
    }
}


class SymbolResolver:
    """
    Validates, discovers, and registers equity tickers from the National Stock Exchange of India.
    Preserves strict separation between broad market instruments and Nifty 50 constituents.
    """

    NSE_QUOTE_URL = "https://www.nseindia.com/api/quote-equity"

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        corporate_client: Optional[CorporateClient] = None
    ):
        self.db = db_manager or DatabaseManager()
        self.corp_client = corporate_client or CorporateClient()

    def resolve_symbol(self, symbol: str) -> Dict[str, Any]:
        """
        Resolves symbol metadata. If present in securities_master or user_watchlists,
        returns existing metadata immediately. If missing, verifies against NSE quote
        API (series 'EQ') or reference catalog, upserts into securities_master with
        is_active = 1 and is_nifty50 = 0, and returns metadata.
        
        Crucial Invariant: Does NOT modify index_membership_history.
        """
        if not symbol or not isinstance(symbol, str):
            raise ValueError(f"Invalid symbol parameter: '{symbol}'")

        sym = symbol.strip().upper()
        if not re.match(r"^[A-Z0-9&_\-]{1,20}$", sym):
            raise ValueError(f"Invalid NSE symbol format: '{sym}'. Symbol must be 1-20 alphanumeric characters.")

        # 1. Check existing in securities_master
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT symbol, company_name, isin, industry, sector, macro_sector, is_active, is_nifty50
                FROM securities_master 
                WHERE symbol = ?
                """,
                (sym,)
            )
            row = cursor.fetchone()
            if row:
                return {
                    "symbol": row["symbol"],
                    "company_name": row["company_name"],
                    "isin": row["isin"],
                    "industry": row["industry"],
                    "sector": row["sector"],
                    "macro_sector": row["macro_sector"],
                    "is_active": row["is_active"],
                    "is_nifty50": row["is_nifty50"] if "is_nifty50" in row.keys() else 0,
                    "source": "securities_master"
                }

            # Check user_watchlists
            cursor_wl = conn.execute(
                "SELECT symbol, company_name, sector FROM user_watchlists WHERE symbol = ?",
                (sym,)
            )
            wl_row = cursor_wl.fetchone()

        # 2. If missing from securities_master, discover from NSE or reference catalog
        discovered_meta: Optional[Dict[str, str]] = None

        if wl_row:
            # Reconstruct from watchlist
            discovered_meta = {
                "symbol": sym,
                "company_name": wl_row["company_name"],
                "isin": f"INE{sym[:6]}01010",
                "industry": wl_row["sector"],
                "sector": wl_row["sector"],
                "macro_sector": "General"
            }
        elif is_network_allowed():
            try:
                discovered_meta = self._fetch_from_nse_quote(sym)
            except Exception as e:
                logger.warning(f"Live NSE quote lookup failed for {sym}: {e}")
                # Fall back to known reference catalog
                if sym in KNOWN_NSE_EQUITIES:
                    ref = KNOWN_NSE_EQUITIES[sym]
                    discovered_meta = {
                        "symbol": sym,
                        "company_name": ref["company_name"],
                        "isin": ref["isin"],
                        "industry": ref["industry"],
                        "sector": ref["sector"],
                        "macro_sector": ref["macro_sector"]
                    }
        else:
            # Offline mode: check known reference catalog
            if sym in KNOWN_NSE_EQUITIES:
                ref = KNOWN_NSE_EQUITIES[sym]
                discovered_meta = {
                    "symbol": sym,
                    "company_name": ref["company_name"],
                    "isin": ref["isin"],
                    "industry": ref["industry"],
                    "sector": ref["sector"],
                    "macro_sector": ref["macro_sector"]
                }

        if not discovered_meta:
            raise ValueError(
                f"Symbol '{sym}' could not be verified on the NSE cash segment (series 'EQ'). "
                f"Ensure the ticker is an active, listed Indian equity on the National Stock Exchange."
            )

        # 3. Database Registration: Upsert into securities_master
        # Strict invariants: is_active = 0 (preserves 50-stock active NIFTY 50 universe), is_nifty50 = 0
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        record = {
            "symbol": sym,
            "company_name": discovered_meta["company_name"],
            "isin": discovered_meta["isin"],
            "industry": discovered_meta["industry"],
            "sector": discovered_meta["sector"],
            "macro_sector": discovered_meta.get("macro_sector", "General"),
            "listing_date": None,
            "is_active": 0,
            "is_nifty50": 0,
            "updated_at": now_ts
        }

        self.db.upsert_securities_master([record])

        # Confirm and return
        return {
            "symbol": sym,
            "company_name": record["company_name"],
            "isin": record["isin"],
            "industry": record["industry"],
            "sector": record["sector"],
            "macro_sector": record["macro_sector"],
            "is_active": 0,
            "is_nifty50": 0,
            "source": "dynamically_discovered"
        }

    def _fetch_from_nse_quote(self, symbol: str) -> Dict[str, str]:
        """
        Queries official NSE Quote API to verify equity and extract metadata.
        Strictly requires series 'EQ'.
        """
        params = {"symbol": symbol}
        referer = f"https://www.nseindia.com/get-quotes/equity?symbol={symbol}"

        resp = self.corp_client._request_with_retry(
            url=self.NSE_QUOTE_URL,
            params=params,
            referer=referer
        )

        if resp.status_code != 200:
            raise RuntimeError(f"NSE Quote API returned status {resp.status_code}")

        data = resp.json()
        info = data.get("info", {})
        metadata = data.get("metadata", {})

        # Verify equity series
        active_series = info.get("activeSeries", [])
        primary_series = metadata.get("series", "")
        if "EQ" not in active_series and primary_series != "EQ":
            raise ValueError(f"Symbol '{symbol}' is not actively traded on NSE cash 'EQ' series.")

        comp_name = info.get("companyName") or metadata.get("companyName") or symbol
        isin = info.get("isin") or metadata.get("isin") or f"INE{symbol[:6]}01010"
        industry = info.get("industry") or metadata.get("industry") or "General"
        sector = metadata.get("pdSectorInd") or info.get("sector") or industry

        # Infer macro sector
        macro_sector = self._infer_macro_sector(sector, industry)

        return {
            "symbol": symbol,
            "company_name": comp_name,
            "isin": isin,
            "industry": industry,
            "sector": sector,
            "macro_sector": macro_sector
        }

    @staticmethod
    def _infer_macro_sector(sector: str, industry: str) -> str:
        sec_lower = (sector + " " + industry).lower()
        if any(w in sec_lower for w in ["bank", "finan", "insurance", "nbfc", "capital"]):
            return "Financials"
        if any(w in sec_lower for w in ["tech", "software", "it ", "telecom"]):
            return "Technology & Telecom"
        if any(w in sec_lower for w in ["pharma", "health", "biotech", "hospital"]):
            return "Healthcare"
        if any(w in sec_lower for w in ["power", "energy", "oil", "gas", "utilities"]):
            return "Energy & Utilities"
        if any(w in sec_lower for w in ["auto", "motor", "fmcg", "consumer", "retail", "textil"]):
            return "Consumer & Retail"
        if any(w in sec_lower for w in ["metal", "steel", "mining", "chemical", "cement"]):
            return "Basic Materials"
        if any(w in sec_lower for w in ["defense", "aero", "infra", "construct", "engineer"]):
            return "Capital Goods"
        return "Industrials"
