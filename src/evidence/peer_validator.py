"""
Market Intelligence Lab: Synthetic Peer Basket Validator.
Validates candidate peers for synthetic baskets:
- Audits individual peer membership, active status, and historical price availability.
- Enforces exclusion of the investigated stock.
- Enforces the minimum 3 eligible peers threshold.
- Labels synthetic baskets strictly as proxies with survivorship bias flags.
- Specifically audits Reliance and its energy-related peer group.
"""

from typing import List, Dict, Any, Optional, Tuple, Set
from src.storage.database import DatabaseManager
from src.evidence.models import SectorBenchmarkType, SectorBenchmarkContext
from src.evidence.constants import MINIMUM_SYNTHETIC_PEERS


class PeerBasketValidationError(ValueError):
    """Raised when candidate synthetic peer basket fails validation criteria."""
    pass


class SyntheticPeerValidator:
    """
    Validates and constructs verified synthetic peer baskets from local SQLite records.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    def audit_individual_peer(self, symbol: str) -> Dict[str, Any]:
        """
        Audits an individual candidate peer for:
        1. Existence in securities_master
        2. Active listing status (is_active == 1)
        3. Historical OHLCV availability (row count, min_date, max_date)
        4. Sector / industry assignment
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            sec_row = cursor.execute(
                "SELECT symbol, company_name, sector, industry, macro_sector, is_active FROM securities_master WHERE symbol = ?",
                (symbol,)
            ).fetchone()

            if not sec_row:
                return {
                    "symbol": symbol,
                    "exists": False,
                    "is_active": False,
                    "ohlcv_count": 0,
                    "min_date": None,
                    "max_date": None,
                    "sector": None,
                    "is_eligible": False,
                    "rejection_reason": "Symbol not found in securities_master"
                }

            ohlcv_row = cursor.execute(
                "SELECT count(*), min(trading_date), max(trading_date) FROM ohlcv_daily WHERE symbol = ?",
                (symbol,)
            ).fetchone()

            ohlcv_count = ohlcv_row[0] if ohlcv_row else 0
            min_date = ohlcv_row[1] if ohlcv_row else None
            max_date = ohlcv_row[2] if ohlcv_row else None

            is_active = bool(sec_row["is_active"])
            is_eligible = is_active and (ohlcv_count > 0)

            rejection_reason = None
            if not is_active:
                rejection_reason = "Symbol marked inactive (is_active=0) in benchmark master"
            elif ohlcv_count == 0:
                rejection_reason = "Zero historical OHLCV records found in database"

            return {
                "symbol": symbol,
                "exists": True,
                "company_name": sec_row["company_name"],
                "sector": sec_row["sector"],
                "industry": sec_row["industry"],
                "macro_sector": sec_row["macro_sector"],
                "is_active": is_active,
                "ohlcv_count": ohlcv_count,
                "min_date": min_date,
                "max_date": max_date,
                "is_eligible": is_eligible,
                "rejection_reason": rejection_reason
            }

    def validate_peer_basket(
        self,
        target_symbol: str,
        candidate_peers: List[str],
        basket_name: str = "SYNTHETIC_PEER_BASKET",
        min_peers: int = MINIMUM_SYNTHETIC_PEERS
    ) -> Dict[str, Any]:
        """
        Validates a candidate peer group:
        1. Excludes target_symbol from candidate peers
        2. Audits every peer individually
        3. Partitions into eligible and rejected peers
        4. Verifies len(eligible_peers) >= min_peers
        """
        # Exclude target symbol
        cleaned_candidates = [p for p in candidate_peers if p != target_symbol]
        excluded_target = (target_symbol in candidate_peers)

        peer_audits = {}
        eligible_peers = []
        rejected_peers = []

        for p in cleaned_candidates:
            audit = self.audit_individual_peer(p)
            peer_audits[p] = audit
            if audit["is_eligible"]:
                eligible_peers.append(p)
            else:
                rejected_peers.append({
                    "symbol": p,
                    "reason": audit["rejection_reason"]
                })

        is_valid = len(eligible_peers) >= min_peers
        status_note = ""
        if not is_valid:
            status_note = (
                f"Validation Failed: {basket_name} has only {len(eligible_peers)} eligible peers "
                f"({len(rejected_peers)} rejected). Minimum {min_peers} required."
            )
        else:
            status_note = (
                f"Validation Passed: {basket_name} contains {len(eligible_peers)} verified eligible peers. "
                f"Proxy label applied; survivorship bias flagged."
            )

        return {
            "basket_name": basket_name,
            "target_symbol": target_symbol,
            "target_excluded": excluded_target,
            "candidate_count": len(cleaned_candidates),
            "eligible_count": len(eligible_peers),
            "eligible_peers": eligible_peers,
            "rejected_peers": rejected_peers,
            "peer_audits": peer_audits,
            "is_valid": is_valid,
            "min_peers_required": min_peers,
            "is_survivorship_biased_proxy": True,
            "status_note": status_note
        }

    def audit_reliance_energy_basket(self) -> Dict[str, Any]:
        """
        Specific Requirement: Validate ONGC, BPCL, and COALINDIA individually
        for Reliance's proposed energy basket.
        Demonstrates why BPCL is rejected and explains the fallback resolution.
        """
        proposed_peers = ["ONGC", "BPCL", "COALINDIA"]
        res_narrow = self.validate_peer_basket(
            target_symbol="RELIANCE",
            candidate_peers=proposed_peers,
            basket_name="PROPOSED_RELIANCE_ENERGY_BASKET",
            min_peers=3
        )

        # Expanded Energy & Power Conglomerate Proxy (including NTPC and POWERGRID)
        expanded_peers = ["ONGC", "COALINDIA", "NTPC", "POWERGRID"]
        res_expanded = self.validate_peer_basket(
            target_symbol="RELIANCE",
            candidate_peers=expanded_peers,
            basket_name="SYNTHETIC_ENERGY_AND_POWER_CONGLOMERATE_PROXY",
            min_peers=3
        )

        return {
            "target": "RELIANCE",
            "conglomerate_nature_note": (
                "Reliance Industries Ltd is a diversified conglomerate with significant "
                "telecom (Jio) and retail operations alongside petrochemicals and refining. "
                "Any peer basket must be explicitly designated as an energy-related proxy, "
                "not an official or perfectly comparable sector index."
            ),
            "narrow_proposal": res_narrow,
            "expanded_proxy": res_expanded,
            "recommended_resolution": (
                "Narrow basket fails (BPCL has 0 OHLCV rows, leaving only 2 peers). "
                "System must either use the 4-peer SYNTHETIC_ENERGY_AND_POWER_CONGLOMERATE_PROXY "
                "(ONGC, COALINDIA, NTPC, POWERGRID) or fall back to BROAD_MARKET_NIFTY50_PRI."
            )
        }
