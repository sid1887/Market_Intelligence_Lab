"""
Market Intelligence Lab: Structured Investigation Report Schema.
Defines immutable, strictly typed schemas and serializable data structures
for multi-format stock movement investigation reports.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
import datetime
import hashlib
import json

REPORT_SCHEMA_VERSION = "1.0.0"
ANALYZER_VERSION = "1.0.0"
ATTRIBUTION_ENGINE_VERSION = "1.0.0"
SCORING_CONFIG_VERSION = "1.0.0"
FROZEN_DATASET_ID = "MIL_FROZEN_BENCHMARK_2024_2026_V1"


@dataclass
class InvestigationOverview:
    """Section A: Header and Metadata Overview."""
    investigation_id: str
    symbol: str
    company_name: str
    isin: Optional[str]
    trading_date: str
    sector: str
    industry: str
    reporting_basis: str
    is_standalone_isolated: bool
    primary_classification: str
    secondary_classifications: List[str]
    confidence_level: str
    final_attribution_outcome: str
    dataset_identifier: str = FROZEN_DATASET_ID
    schema_version: str = REPORT_SCHEMA_VERSION
    analyzer_version: str = ANALYZER_VERSION
    attribution_engine_version: str = ATTRIBUTION_ENGINE_VERSION
    scoring_config_version: str = SCORING_CONFIG_VERSION
    generation_timestamp: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


@dataclass
class ExecutiveSummary:
    """Section B: Executive Summary & Narrative."""
    narrative: str
    relative_performance_summary: str
    systematic_vs_idiosyncratic: str
    strongest_hypothesis_summary: str
    evidence_sufficiency: str
    key_uncertainties: List[str]
    score_is_heuristic_disclaimer: str = (
        "Methodological Note: The evidence strength score (0.0 to 100.0) is a deterministic "
        "heuristic measuring evidence quality, temporal proximity, and directional consistency. "
        "It is NOT a statistical probability or a calibrated confidence interval."
    )


@dataclass
class MechanicalAdjustmentContext:
    """Mechanical corporate action price adjustment context."""
    has_mechanical_adjustment: bool = False
    corporate_action_type: Optional[str] = None           # "BONUS", "SPLIT", "DIVIDEND"
    adjustment_factor: Optional[float] = None              # e.g., 0.5 for 1:1 bonus
    raw_return_pct: Optional[float] = None                 # e.g., -50.93%
    adjusted_return_pct: Optional[float] = None            # e.g., -1.86%
    corporate_action_evidence_id: Optional[str] = None
    mechanical_explanation: Optional[str] = None
    disclaimer: str = (
        "Mechanical Adjustment Notice: Quoted price adjustments resulting from corporate actions "
        "(bonus issues, stock splits, cash dividends) are purely mechanical arithmetic recalculations. "
        "They do NOT establish positive or negative market sentiment, nor do they explain the underlying "
        "economic market return."
    )


@dataclass
class MarketMovementSection:
    """Section C: Quantitative Movement Analysis."""
    price_action: Dict[str, Any]
    benchmark_comparison: Dict[str, Any]
    market_model: Dict[str, Any]
    volume_liquidity: Dict[str, Any]
    mechanical_adjustment: Optional[MechanicalAdjustmentContext] = None


@dataclass
class TimelineItem:
    """Single item in the chronological evidence timeline."""
    evidence_id: str
    event_date: str
    broadcast_timestamp: Optional[str]
    effective_session_date: str
    tier: int
    tier_label: str
    category: str
    direction: str
    headline: str
    source_identity: str
    source_reference: Optional[str]
    verification_status: str
    is_pit_eligible: bool
    relevance_note: str


@dataclass
class ExcludedEvidenceItem:
    """Excluded evidence record with explicit rationale."""
    evidence_id: str
    headline: str
    tier: int
    effective_session_date: str
    exclusion_reason: str


@dataclass
class TimelineSection:
    """Section D: Event and Evidence Timeline."""
    eligible_timeline: List[TimelineItem]
    excluded_evidence: List[ExcludedEvidenceItem]


@dataclass
class RankedHypothesisItem:
    """Section E Item: Single ranked candidate explanation."""
    rank: int
    hypothesis_id: str
    primary_evidence_id: Optional[str]
    catalyst_type: str
    headline: str
    score_breakdown: Dict[str, Any]
    final_score: float
    confidence_level: str
    is_contradicted: bool
    contradiction_penalty: float
    is_company_specific: bool
    ranking_rationale: str
    alternative_hypotheses: List[str] = field(default_factory=list)


@dataclass
class ContradictionSection:
    """Section F: Contradictory Evidence & Alternative Hypotheses."""
    has_contradictions: bool
    contradicting_evidence: List[Dict[str, Any]]
    alternative_explanations: List[str]


@dataclass
class LimitationsSection:
    """Section G: Gaps, Limitations & Governance."""
    unresolved_questions: List[str]
    limitations: List[str]
    governance_notice: str


@dataclass
class FinalAssessmentSection:
    """Section H: Final Assessment & Audit Stamp."""
    final_outcome: str
    conclusion_statement: str
    provenance_audit_hash: str
    reproducibility_token: str


@dataclass
class StructuredInvestigationReport:
    """
    Complete structured investigation report enclosing sections A through H.
    Fully serializable to JSON, Markdown, and Standalone HTML.
    """
    overview: InvestigationOverview
    executive_summary: ExecutiveSummary
    movement_analysis: MarketMovementSection
    timeline: TimelineSection
    ranked_explanations: List[RankedHypothesisItem]
    contradictions: ContradictionSection
    limitations: LimitationsSection
    final_assessment: FinalAssessmentSection

    def to_dict(self) -> Dict[str, Any]:
        """Serializes report to dictionary with nested dataclasses converted."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serializes report to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    def compute_audit_hash(self) -> str:
        """Computes deterministic SHA-256 hash of core quantitative and attribution payload."""
        payload = {
            "symbol": self.overview.symbol,
            "trading_date": self.overview.trading_date,
            "primary_classification": self.overview.primary_classification,
            "final_outcome": self.final_assessment.final_outcome,
            "price_action": self.movement_analysis.price_action,
            "ranked_hypotheses": [
                (h.hypothesis_id, h.final_score, h.confidence_level)
                for h in self.ranked_explanations
            ]
        }
        raw_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(raw_bytes).hexdigest()
