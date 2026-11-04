"""
Market Intelligence Lab: Unified Evidence Data Models.
Provides strictly typed, immutable dataclasses and enumerations for
evidence normalization, sector benchmarking, and movement attribution.
"""

from enum import Enum, IntEnum
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
import json
import datetime


class EvidenceTier(IntEnum):
    """
    Hierarchical evidence quality tiers.
    Tier 1: Official exchange disclosures, board meeting intimations & outcomes.
    Tier 2: Verified company financial statements, dividends, splits, bonus issues.
    Tier 3: Official sector & benchmark market data, breadth, volume anomalies.
    Tier 4: Authorized macroeconomic calendar events (RBI MPC, Union Budget).
    Tier 5: Unverified secondary sources, proxy announcements.
    """
    TIER_1_OFFICIAL_FILING = 1
    TIER_2_FINANCIAL_ACTION = 2
    TIER_3_SECTOR_BENCHMARK = 3
    TIER_4_MACRO_AUTHORIZED = 4
    TIER_5_UNVERIFIED = 5


class EvidenceCategory(str, Enum):
    """Classification of event catalyst categories."""
    EARNINGS_RELEASE = "EARNINGS_RELEASE"
    EARNINGS_REVISION = "EARNINGS_REVISION"
    DIVIDEND_DECLARATION = "DIVIDEND_DECLARATION"
    BONUS_SPLIT_EVENT = "BONUS_SPLIT_EVENT"
    BOARD_MEETING_OUTCOME = "BOARD_MEETING_OUTCOME"
    SECTOR_MOMENTUM = "SECTOR_MOMENTUM"
    VALUATION_RE_RATING = "VALUATION_RE_RATING"
    VOLUME_LIQUIDITY_SURGE = "VOLUME_LIQUIDITY_SURGE"
    UNKNOWN_CATALYST = "UNKNOWN_CATALYST"


class EvidenceDirection(str, Enum):
    """Expected directional impact of the evidence item."""
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    AMBIGUOUS = "AMBIGUOUS"


class ExpectationSurprise(str, Enum):
    """
    Classification of results relative to consensus expectations.
    Strict Requirement: If analyst expectations/consensus are unavailable,
    MUST be marked UNKNOWN. Never inferred from YoY growth alone.
    """
    BEAT = "BEAT"
    MISS = "MISS"
    IN_LINE = "IN_LINE"
    UNKNOWN = "UNKNOWN"


class ReportingBasis(str, Enum):
    """Reporting scope for financial statements and disclosures."""
    CONSOLIDATED = "CONSOLIDATED"
    STANDALONE = "STANDALONE"


class MovementClassification(str, Enum):
    """Deterministic classification of observed price action."""
    IDIOSYNCRATIC_OUTPERFORMANCE = "IDIOSYNCRATIC_OUTPERFORMANCE"
    IDIOSYNCRATIC_UNDERPERFORMANCE = "IDIOSYNCRATIC_UNDERPERFORMANCE"
    SECTOR_SYSTEMATIC_SURGE = "SECTOR_SYSTEMATIC_SURGE"
    SECTOR_SYSTEMATIC_DRAG = "SECTOR_SYSTEMATIC_DRAG"
    MARKET_BETA_DRIVEN = "MARKET_BETA_DRIVEN"
    ANOMALOUS_VOLUME = "ANOMALOUS_VOLUME"
    MUTED_CONSOLIDATION = "MUTED_CONSOLIDATION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNEXPLAINED_MOVEMENT = "UNEXPLAINED_MOVEMENT"


class SectorBenchmarkType(str, Enum):
    """
    Hierarchy of sector-level benchmark comparison.
    1. OFFICIAL_SECTOR_PRI: Dedicated sectoral index (e.g. NIFTY IT, NIFTY BANK).
    2. SYNTHETIC_PEER_BASKET: Equal-weighted basket of >= 3 eligible industry peers.
    3. BROAD_MARKET_NIFTY50_PRI: Broad-market context only (fallback).
    4. SECTOR_BENCHMARK_UNAVAILABLE: When no valid peer or index exists.
    """
    OFFICIAL_SECTOR_PRI = "OFFICIAL_SECTOR_PRI"
    SYNTHETIC_PEER_BASKET = "SYNTHETIC_PEER_BASKET"
    BROAD_MARKET_NIFTY50_PRI = "BROAD_MARKET_NIFTY50_PRI"
    SECTOR_BENCHMARK_UNAVAILABLE = "SECTOR_BENCHMARK_UNAVAILABLE"


@dataclass(frozen=True)
class EvidenceRecord:
    """
    Normalized, immutable representation of a single evidence observation.
    Captures temporal provenance, point-in-time eligibility, verification status,
    and directional alignment.
    """
    evidence_id: str
    symbol: str
    entity_type: str                          # 'STOCK', 'SECTOR', 'BENCHMARK', 'MACRO'
    event_date: str                           # YYYY-MM-DD
    broadcast_timestamp: Optional[str]        # ISO 8601 IST (e.g. '2026-10-23T16:30:00+05:30')
    effective_session_date: str               # YYYY-MM-DD: first trading session market reacted
    tier: EvidenceTier
    category: EvidenceCategory
    direction: EvidenceDirection
    headline: str
    details: Dict[str, Any]
    source_identity: str                      # e.g. 'nse_circular', 'bse_disclosure', 'cfs_table'
    source_reference: Optional[str]           # Circular reference, filing URL, or statement_id
    verification_status: str                  # 'VERIFIED', 'PENDING_VERIFICATION', 'UNVERIFIED'
    is_pit_eligible: bool                     # Point-in-time safety flag
    reporting_basis: Optional[str] = None     # 'CONSOLIDATED' | 'STANDALONE' | None
    expectation_surprise: ExpectationSurprise = ExpectationSurprise.UNKNOWN
    is_contradictory: bool = False            # True if observed return contradicted direction
    retrieval_timestamp: str = ""             # ISO 8601 UTC
    created_at: str = ""                      # ISO 8601 UTC

    def to_dict(self) -> Dict[str, Any]:
        """Serializes dataclass to dictionary with string-serialized enums."""
        d = asdict(self)
        d["tier"] = int(self.tier)
        d["category"] = self.category.value
        d["direction"] = self.direction.value
        d["expectation_surprise"] = self.expectation_surprise.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceRecord":
        """Constructs an EvidenceRecord from dictionary with enum parsing and DB column mapping."""
        d = dict(data)
        
        # Handle database column aliases
        if "evidence_tier" in d and "tier" not in d:
            d["tier"] = d.pop("evidence_tier")
        else:
            d.pop("evidence_tier", None)

        if "evidence_category" in d and "category" not in d:
            d["category"] = d.pop("evidence_category")
        else:
            d.pop("evidence_category", None)

        if "evidence_direction" in d and "direction" not in d:
            d["direction"] = d.pop("evidence_direction")
        else:
            d.pop("evidence_direction", None)

        if "details_json" in d:
            raw_json = d.pop("details_json")
            if "details" not in d and raw_json:
                try:
                    d["details"] = json.loads(raw_json)
                except Exception:
                    d["details"] = {}

        if "details" not in d:
            d["details"] = {}

        d["tier"] = EvidenceTier(int(d["tier"]))
        d["category"] = EvidenceCategory(d["category"])
        d["direction"] = EvidenceDirection(d["direction"])
        d["expectation_surprise"] = ExpectationSurprise(d.get("expectation_surprise", "UNKNOWN"))
        d["is_pit_eligible"] = bool(d.get("is_pit_eligible", True))
        d["is_contradictory"] = bool(d.get("is_contradictory", False))

        # Filter only valid dataclass field names
        valid_fields = {
            "evidence_id", "symbol", "entity_type", "event_date",
            "broadcast_timestamp", "effective_session_date", "tier",
            "category", "direction", "headline", "details",
            "source_identity", "source_reference", "verification_status",
            "is_pit_eligible", "reporting_basis", "expectation_surprise",
            "is_contradictory", "retrieval_timestamp", "created_at"
        }
        filtered = {k: v for k, v in d.items() if k in valid_fields}
        return cls(**filtered)

    def to_json(self) -> str:
        """Returns JSON string representation."""
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


@dataclass
class MovementAnalysisResult:
    """
    Encapsulates complete deterministic decomposition of a stock's price action,
    benchmark alignment, market model regression, volume anomaly, and movement classifications.
    """
    symbol: str
    trading_date: str
    open: float
    high: float
    low: float
    close: float
    prev_close: float
    volume: int

    # Returns & Price Drift
    ret_1d_raw: Optional[float]
    ret_1d_adj: Optional[float]
    ret_1d_total: Optional[float]
    gap_open: Optional[float]
    intraday_drift: float
    intraday_range: float
    ret_5d: Optional[float]
    ret_20d: Optional[float]

    # Benchmark & Sector Benchmark Context
    benchmark_return: Optional[float]  # NIFTY 50 PRI return (None if benchmark unavailable)
    sector_benchmark_type: SectorBenchmarkType
    sector_benchmark_name: str
    sector_return: Optional[float]
    eligible_peers: List[str] = field(default_factory=list)
    peer_returns: Dict[str, float] = field(default_factory=dict)
    is_survivorship_biased_proxy: bool = False
    sector_notes: Optional[str] = None

    # Econometric Market Model & Abnormal Return
    model_status: str = "ESTIMATED"  # 'ESTIMATED', 'INSUFFICIENT_HISTORY', 'ESTIMATION_FAILED'
    alpha: Optional[float] = None
    beta: Optional[float] = None
    r_squared: Optional[float] = None
    residual_std_err: Optional[float] = None
    estimation_sessions_count: int = 0
    expected_return: Optional[float] = None
    abnormal_return: Optional[float] = None
    t_statistic: Optional[float] = None
    sector_adjusted_return: Optional[float] = None

    # Volume & Liquidity Anomalies
    volume_ratio_20d: Optional[float] = None
    volume_log_zscore_50d: Optional[float] = None
    is_volume_spike: bool = False
    is_zero_volume: bool = False

    # Classifications
    primary_classification: MovementClassification = MovementClassification.UNEXPLAINED_MOVEMENT
    classifications: List[MovementClassification] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    # Missing session / calendar gap tracking
    prev_stored_date: Optional[str] = None
    prev_stored_close: Optional[float] = None
    source_prev_close: Optional[float] = None
    source_prev_close_provenance: Optional[str] = None
    has_calendar_gap: bool = False
    missing_intermediate_sessions: List[str] = field(default_factory=list)
    interval_return_raw: Optional[float] = None
    interval_return_adj: Optional[float] = None
    interval_sessions_count: int = 1
    interval_start_date: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["sector_benchmark_type"] = self.sector_benchmark_type.value
        d["primary_classification"] = self.primary_classification.value
        d["classifications"] = [c.value for c in self.classifications]
        return d


@dataclass
class SectorBenchmarkContext:
    """
    Captures the sector-level context for a stock on a specific trading session,
    enforcing the 4-tier benchmark hierarchy.
    """
    symbol: str
    benchmark_type: SectorBenchmarkType
    benchmark_name: str
    peer_symbols: List[str] = field(default_factory=list)
    weighting_method: str = "EQUAL_WEIGHTED"
    is_survivorship_biased_proxy: bool = False
    sector_return: Optional[float] = None
    benchmark_return: Optional[float] = None  # NIFTY 50 PRI return
    excess_over_sector: Optional[float] = None
    excess_over_market: Optional[float] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["benchmark_type"] = self.benchmark_type.value
        return d


@dataclass
class AttributionHypothesis:
    """
    Deterministic hypothesis explaining a stock's movement on date T.
    Enforces that evidence_strength_score is a deterministic heuristic,
    not a calibrated probability.
    """
    hypothesis_id: str
    symbol: str
    target_date: str
    movement_classification: MovementClassification
    primary_evidence_id: Optional[str]
    supporting_evidence_ids: List[str]
    contradicting_evidence_ids: List[str]
    evidence_strength_score: float            # 0.0 to 100.0 (Deterministic heuristic score)
    confidence_level: str                     # 'HIGH_CONFIDENCE', 'MODERATE_CONFIDENCE', 'LOW_CONFIDENCE', etc.
    is_contradicted: bool = False
    contradiction_penalty_applied: float = 0.0
    alternative_hypotheses: List[str] = field(default_factory=list)
    unexplained_residual_pct: Optional[float] = None
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["movement_classification"] = self.movement_classification.value
        return d
