"""
Market Intelligence Lab — Canonical Domain Observation & Metric Result Contracts.
ADR-0006, ADR-0007, P0-01.

Defines the core typed envelopes for observations, financial metrics, and score components.
Guarantees that missing or unverified evidence is never coerced to zero or fabricated numbers.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Tuple, Dict, Any


@dataclass(frozen=True)
class Observation:
    """Standard envelope for raw and ingested data points."""
    value: Any
    unit: str
    source_id: str
    source_record_id: str
    observed_at: str
    available_at: Optional[str] = None
    ingested_at: Optional[str] = None
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    quality_status: str = "VALID"        # VALID / MISSING / STALE / OUTLIER_REJECTED / SYNTHETIC
    freshness_status: str = "CURRENT"    # CURRENT / STALE / UNVERIFIED
    method: str = "SOURCE_REPORTED"
    reason_code: Optional[str] = None
    version: int = 1


@dataclass(frozen=True)
class MetricResult:
    """Typed result for fundamental, technical, and derived quantitative metrics."""
    value: Optional[float]
    unit: str
    status: str                         # VALID / MISSING / STALE / PARTIAL / NOT_MEANINGFUL / NOT_APPLICABLE
    reason_code: Optional[str] = None   # e.g., MISSING_STATEMENT_PERIOD, NEGATIVE_EARNINGS, DEBT_NOT_REPORTED
    source_ids: Tuple[str, ...] = field(default_factory=tuple)
    period_end: Optional[str] = None
    available_at: Optional[str] = None
    accounting_basis: Optional[str] = None  # CONSOLIDATED / STANDALONE
    calculation_version: str = "v2_null_safe"

    @property
    def is_valid(self) -> bool:
        return self.status == "VALID" and self.value is not None


@dataclass(frozen=True)
class ScoreComponent:
    """Factor contribution component within the multi-factor screener model."""
    factor_name: str
    raw_value: Optional[float]
    status: str                         # VALID / MISSING / STALE / NOT_MEANINGFUL / NOT_APPLICABLE
    percentile: Optional[float] = None  # 0.0 to 100.0, None if status != VALID
    nominal_weight: float = 0.0
    effective_weight: float = 0.0
    weighted_contribution: Optional[float] = None
    missing_reason: Optional[str] = None

    @property
    def is_eligible_for_ranking(self) -> bool:
        return self.status == "VALID" and self.raw_value is not None
