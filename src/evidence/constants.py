"""
Market Intelligence Lab: Evidence & Sector Benchmarking Constants.
Codifies sector-to-index mappings, synthetic peer basket definitions,
deterministic scoring parameters, and compliance notices.
"""

from typing import Dict, List, Optional, Tuple, Set, Any
from src.evidence.models import SectorBenchmarkType

# Compliance & Data Governance Notice for Frozen Offline Benchmark
DATA_GOVERNANCE_NOTICE: str = (
    "DATA GOVERNANCE NOTICE: Market Intelligence Lab operates on a frozen historical "
    "research benchmark (October 2024 – October 2026). Automated web scraping is paused "
    "in compliance with exchange terms. Commercial deployment or live simulation requires "
    "authorized data licensing or academic agreements."
)

# Minimum eligible peers required to construct a valid synthetic peer basket
MINIMUM_SYNTHETIC_PEERS: int = 3

# Default contradiction penalty applied to an evidence hypothesis (configurable heuristic)
CONTRADICTION_PENALTY_DEFAULT: float = 30.0

# Base tier heuristic scores (out of 100)
BASE_TIER_SCORES: Dict[int, float] = {
    1: 60.0,  # Tier 1: Official exchange filings & board meeting outcomes
    2: 50.0,  # Tier 2: Verified financial statements & corporate actions
    3: 35.0,  # Tier 3: Sector & benchmark index movements, volume anomalies
    4: 20.0,  # Tier 4: Authorized macroeconomic calendar events
    5: 10.0   # Tier 5: Unverified or incomplete secondary disclosures
}

# Volume confirmation score deltas
VOLUME_SCORE_DELTAS: Dict[str, float] = {
    "EXTREME": 15.0,   # Volume Ratio >= 3.0
    "HIGH": 10.0,      # Volume Ratio >= 2.0
    "MUTED": -10.0     # Volume Ratio < 1.0 (lack of volume conviction)
}

# Abnormal return magnitude score deltas
ABNORMAL_RETURN_SCORE_DELTAS: Dict[str, float] = {
    "LARGE": 15.0,     # |AR| >= 3.0%
    "MODERATE": 10.0   # |AR| >= 1.5%
}

# Official Sector Index Mappings for NIFTY 50 Constituents
# Ref circulars and official Sectoral Indices of NSE Indices Ltd
OFFICIAL_BANK_SYMBOLS: Set[str] = {
    "HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "SBIN", "INDUSINDBK"
}

SECTOR_TO_OFFICIAL_INDEX: Dict[str, str] = {
    "Information Technology": "NIFTY IT",
    "Automobile and Auto Components": "NIFTY AUTO",
    "Automobile": "NIFTY AUTO",
    "Metals & Mining": "NIFTY METAL",
    "Fast Moving Consumer Goods": "NIFTY FMCG",
    "Consumer Goods": "NIFTY FMCG",
    "Healthcare": "NIFTY PHARMA",
    "Realty": "NIFTY REALTY"
}

SECTOR_TO_INDEX_MAP = SECTOR_TO_OFFICIAL_INDEX

# Industry / Sector Definitions for Synthetic Peer Baskets
# Used when no dedicated official sectoral index exists in the 9-index dataset.
SYNTHETIC_BASKET_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "ENERGY_AND_FUELS": {
        "name": "SYNTHETIC_ENERGY_BASKET",
        "description": "Equal-weighted basket of NIFTY 50 Energy and Fuel constituents",
        "sectors": {"Oil Gas & Consumable Fuels", "Energy"},
        "peers": ["RELIANCE", "ONGC", "BPCL", "COALINDIA"]
    },
    "CONSUMER_SERVICES": {
        "name": "SYNTHETIC_CONSUMER_SERVICES_BASKET",
        "description": "Equal-weighted basket of retail and platform consumer services",
        "sectors": {"Consumer Services"},
        "peers": ["ETERNAL", "TRENT"]  # Note: 2 peers; fails MINIMUM_SYNTHETIC_PEERS unless expanded
    },
    "CONSTRUCTION_MATERIALS": {
        "name": "SYNTHETIC_CEMENT_BASKET",
        "description": "Equal-weighted basket of cement and construction materials",
        "sectors": {"Construction Materials"},
        "peers": ["GRASIM", "ULTRACEMCO"]  # 2 peers; fails minimum 3
    },
    "CONSUMER_DURABLES": {
        "name": "SYNTHETIC_DURABLES_BASKET",
        "description": "Equal-weighted basket of consumer durables",
        "sectors": {"Consumer Durables"},
        "peers": ["ASIANPAINT", "TITAN"]  # 2 peers; fails minimum 3
    }
}


def resolve_sector_benchmark(
    symbol: str,
    sector: str,
    industry: str,
    active_universe_symbols: Optional[List[str]] = None
) -> Tuple[SectorBenchmarkType, str, List[str], bool, str]:
    """
    Implements the 4-tier sector benchmark resolution hierarchy:
    1. Official sector PRI index (OFFICIAL_SECTOR_PRI)
    2. Synthetic peer basket (SYNTHETIC_PEER_BASKET) with >= 3 eligible peers excluding the symbol
    3. NIFTY 50 PRI (BROAD_MARKET_NIFTY50_PRI) as broad-market context only
    4. SECTOR_BENCHMARK_UNAVAILABLE

    Returns:
        (benchmark_type, benchmark_name, peer_symbols, is_survivorship_biased_proxy, notes)
    """
    # 1. Financial Services Branching (Bank vs Non-Bank)
    if sector in {"Financial Services", "Financials", "Banking"}:
        ind_lower = industry.lower()
        is_bank = (
            symbol in OFFICIAL_BANK_SYMBOLS or
            ("bank" in ind_lower and "non-bank" not in ind_lower and "nbfc" not in ind_lower)
        )
        if is_bank:
            return (
                SectorBenchmarkType.OFFICIAL_SECTOR_PRI,
                "NIFTY BANK",
                [],
                False,
                "Primary official banking sector index (PRI)"
            )
        else:
            return (
                SectorBenchmarkType.OFFICIAL_SECTOR_PRI,
                "NIFTY FINANCIAL SERVICES",
                [],
                False,
                "Primary official financial services sector index (PRI)"
            )

    # 2. Other Official Sectoral Indices
    if sector in SECTOR_TO_OFFICIAL_INDEX:
        idx_name = SECTOR_TO_OFFICIAL_INDEX[sector]
        return (
            SectorBenchmarkType.OFFICIAL_SECTOR_PRI,
            idx_name,
            [],
            False,
            f"Official sectoral index (PRI): {idx_name}"
        )

    # 3. Synthetic Peer Basket Evaluation
    # Check defined synthetic baskets
    for basket_key, basket_def in SYNTHETIC_BASKET_DEFINITIONS.items():
        if sector in basket_def["sectors"]:
            candidate_peers = [p for p in basket_def["peers"] if p != symbol]
            # If active_universe_symbols provided, ensure peers are currently active
            if active_universe_symbols is not None:
                candidate_peers = [p for p in candidate_peers if p in active_universe_symbols]

            if len(candidate_peers) >= MINIMUM_SYNTHETIC_PEERS:
                return (
                    SectorBenchmarkType.SYNTHETIC_PEER_BASKET,
                    basket_def["name"],
                    candidate_peers,
                    True,  # Flagged as potentially survivorship-biased proxy
                    (f"Equal-weighted synthetic peer basket ({len(candidate_peers)} peers). "
                     "Never presented as an official index; flagged as current-universe proxy.")
                )
            else:
                # Fails minimum peers threshold
                notes = (
                    f"Sector '{sector}' has only {len(candidate_peers)} eligible peers (minimum {MINIMUM_SYNTHETIC_PEERS} required). "
                    "Synthetic peer basket rejected; falling back to broad-market NIFTY 50 PRI."
                )
                return (
                    SectorBenchmarkType.BROAD_MARKET_NIFTY50_PRI,
                    "NIFTY 50",
                    [],
                    False,
                    notes
                )

    # 4. Fallback to NIFTY 50 as broad-market context only
    return (
        SectorBenchmarkType.BROAD_MARKET_NIFTY50_PRI,
        "NIFTY 50",
        [],
        False,
        f"No official sector index or >= 3 synthetic peers for sector '{sector}'. Using NIFTY 50 PRI as broad-market context only."
    )
