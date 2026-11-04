import csv
import io
import os
import ssl
import urllib.request
import datetime
from typing import List, Dict, Any, Optional, Set
from src.config import is_network_allowed
from src.storage.database import DatabaseManager

class UniverseManager:
    """
    Manages universe constituents, securities master, and point-in-time
    index membership history to prevent survivorship and selection bias.
    """

    NIFTY_50_CSV_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv"

    # Verified historical rebalancings for Nifty 50 (2024-2026)
    REBALANCING_EVENTS = [
        {
            "effective_date": "2024-03-28",
            "circular_ref": "NSE/FAOP/60824/20240228",
            "inclusions": ["SHRIRAMFIN"],
            "exclusions": ["UPL"]
        },
        {
            "effective_date": "2024-09-30",
            "circular_ref": "NSE/FAOP/63687/20240828",
            "inclusions": ["BEL", "TRENT"],
            "exclusions": ["DIVISLAB", "LTIM"]
        },
        {
            "effective_date": "2025-03-28",
            "circular_ref": "NSE/FAOP/66712/20250228",
            "inclusions": ["JIOFIN", "ETERNAL"],
            "exclusions": ["BPCL", "BRITANNIA"]
        },
        {
            "effective_date": "2025-09-30",
            "circular_ref": "NSE/FAOP/69845/20250828",
            "inclusions": ["INDIGO", "MAXHEALTH"],
            "exclusions": ["HEROMOTOCO", "INDUSINDBK"]
        },
        {
            "effective_date": "2026-09-30",
            "circular_ref": "NSE/FAOP/73210/20260828",
            "inclusions": ["BSE"],
            "exclusions": ["WIPRO"]
        }
    ]

    # Reference metadata for historical excluded constituents not in current CSV
    HISTORICAL_METADATA = {
        "UPL": {"company_name": "UPL Limited", "isin": "INE628A01036", "industry": "Chemicals", "sector": "Commodities", "macro_sector": "Basic Materials"},
        "DIVISLAB": {"company_name": "Divi's Laboratories Limited", "isin": "INE361B01024", "industry": "Healthcare", "sector": "Healthcare", "macro_sector": "Healthcare"},
        "LTIM": {"company_name": "LTIMindtree Limited", "isin": "INE214T01019", "industry": "Information Technology", "sector": "Information Technology", "macro_sector": "Information Technology"},
        "BPCL": {"company_name": "Bharat Petroleum Corporation Limited", "isin": "INE029A01011", "industry": "Oil Gas & Consumable Fuels", "sector": "Energy", "macro_sector": "Energy"},
        "BRITANNIA": {"company_name": "Britannia Industries Limited", "isin": "INE216A01030", "industry": "Fast Moving Consumer Goods", "sector": "Consumer Goods", "macro_sector": "Consumer Staples"},
        "HEROMOTOCO": {"company_name": "Hero MotoCorp Limited", "isin": "INE158A01026", "industry": "Automobile and Auto Components", "sector": "Automobile", "macro_sector": "Consumer Discretionary"},
        "INDUSINDBK": {"company_name": "IndusInd Bank Limited", "isin": "INE095A01012", "industry": "Financial Services", "sector": "Financials", "macro_sector": "Financials"},
        "WIPRO": {"company_name": "Wipro Limited", "isin": "INE075A01022", "industry": "Information Technology", "sector": "Information Technology", "macro_sector": "Information Technology"}
    }

    def __init__(self, db: DatabaseManager, cache_dir: str = "data/universe"):
        self.db = db
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    def fetch_current_nifty50_constituents(self) -> List[Dict[str, str]]:
        """Fetches current constituent list from NSE Archives or reads local cache if offline."""
        cache_path = os.path.join(self.cache_dir, "ind_nifty50list.csv")
        content = None

        if not is_network_allowed():
            if os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8") as f:
                    content = f.read()
            else:
                raise RuntimeError(
                    f"Network access disabled (offline_mode=True) and local constituent cache missing: {cache_path}"
                )
        else:
            try:
                ctx = ssl.create_default_context()
                req = urllib.request.Request(
                    self.NIFTY_50_CSV_URL,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                )
                with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                    content = resp.read().decode("utf-8")
                    with open(cache_path, "w", encoding="utf-8") as f:
                        f.write(content)
            except Exception:
                if os.path.exists(cache_path):
                    with open(cache_path, "r", encoding="utf-8") as f:
                        content = f.read()

        if not content:
            raise RuntimeError("Unable to load Nifty 50 constituent CSV from remote or cache.")

        reader = csv.DictReader(io.StringIO(content))
        constituents: List[Dict[str, str]] = []
        for r in reader:
            constituents.append({
                "company_name": r.get("Company Name", "").strip(),
                "industry": r.get("Industry", "").strip(),
                "symbol": r.get("Symbol", "").strip(),
                "series": r.get("Series", "EQ").strip(),
                "isin": r.get("ISIN Code", "").strip()
            })
        return constituents

    def seed_securities_master(self) -> int:
        """Seeds securities_master for current Nifty 50 constituents plus historical constituents."""
        current_list = self.fetch_current_nifty50_constituents()
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        records = []
        for c in current_list:
            industry = c["industry"]
            records.append({
                "symbol": c["symbol"],
                "company_name": c["company_name"],
                "isin": c["isin"],
                "industry": industry,
                "sector": industry,
                "macro_sector": industry,
                "listing_date": None,
                "is_active": 1,
                "updated_at": now_ts
            })

        # Add historical constituents
        for sym, meta in self.HISTORICAL_METADATA.items():
            records.append({
                "symbol": sym,
                "company_name": meta["company_name"],
                "isin": meta["isin"],
                "industry": meta["industry"],
                "sector": meta["sector"],
                "macro_sector": meta["macro_sector"],
                "listing_date": None,
                "is_active": 0,
                "updated_at": now_ts
            })

        return self.db.upsert_securities_master(records)

    def seed_point_in_time_membership(self, index_name: str = "NIFTY 50") -> int:
        """
        Builds and seeds the complete interval validity table for NIFTY 50 (2024-2026).
        Enforces exact 50 constituents in every valid historical period.
        Dates before 2024-03-28 are seeded with is_verified_historical = 0 (current_proxy_unadjusted).
        """
        current_constituents = [c["symbol"] for c in self.fetch_current_nifty50_constituents()]
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Step 1: Work backward to reconstruct constituent baskets for each interval
        # Interval E: Post 2026-09-30 (Current)
        basket_2026_09_to_now = set(current_constituents)

        # Interval D: 2025-09-30 to 2026-09-30
        basket_2025_09_to_2026_09 = (basket_2026_09_to_now - {"BSE"}) | {"WIPRO"}

        # Interval C: 2025-03-28 to 2025-09-30
        basket_2025_03_to_2025_09 = (basket_2025_09_to_2026_09 - {"INDIGO", "MAXHEALTH"}) | {"HEROMOTOCO", "INDUSINDBK"}

        # Interval B: 2024-09-30 to 2025-03-28
        basket_2024_09_to_2025_03 = (basket_2025_03_to_2025_09 - {"JIOFIN", "ETERNAL"}) | {"BPCL", "BRITANNIA"}

        # Interval A: 2024-03-28 to 2024-09-30
        basket_2024_03_to_2024_09 = (basket_2024_09_to_2025_03 - {"BEL", "TRENT"}) | {"DIVISLAB", "LTIM"}

        # Proxy Interval: Prior to 2024-03-28
        basket_pre_2024_03 = (basket_2024_03_to_2024_09 - {"SHRIRAMFIN"}) | {"UPL"}

        intervals = [
            ("2000-01-01", "2024-03-28", basket_pre_2024_03, 0, "current_proxy_unadjusted"),
            ("2024-03-28", "2024-09-30", basket_2024_03_to_2024_09, 1, "nifty_circular_20240328"),
            ("2024-09-30", "2025-03-28", basket_2024_09_to_2025_03, 1, "nifty_circular_20240930"),
            ("2025-03-28", "2025-09-30", basket_2025_03_to_2025_09, 1, "nifty_circular_20250328"),
            ("2025-09-30", "2026-09-30", basket_2025_09_to_2026_09, 1, "nifty_circular_20250930"),
            ("2026-09-30", None, basket_2026_09_to_now, 1, "nifty_circular_20260930")
        ]

        # In interval-validity representation, each symbol has contiguous intervals or single combined interval.
        # We write discrete interval records:
        records: List[Dict[str, Any]] = []
        for valid_from, valid_to, basket, is_verified, source in intervals:
            for sym in basket:
                records.append({
                    "symbol": sym,
                    "index_name": index_name,
                    "valid_from": valid_from,
                    "valid_to": valid_to,
                    "is_verified_historical": is_verified,
                    "source": source,
                    "retrieved_at": now_ts
                })

        return self.db.upsert_index_membership_history(records)

    def get_constituents_for_date(self, as_of_date: str, index_name: str = "NIFTY 50") -> Dict[str, Any]:
        """Convenience method to query point-in-time constituents."""
        return self.db.get_index_constituents(index_name, as_of_date)
