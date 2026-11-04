"""
Market Intelligence Lab: Attribution Package.
Exports EvidenceRankingEngine, ScoringConfig, ScoringBreakdown, and MovementExplanationReport.
"""

from src.attribution.ranking import (
    ScoringConfig,
    ScoringBreakdown,
    score_evidence_item,
    determine_confidence_level,
    is_independently_corroborating
)
from src.attribution.engine import (
    EvidenceRankingEngine,
    MovementExplanationReport
)
from src.explanation.attribution_engine import (
    MovementAttributionEngine,
    AttributionResult
)

__all__ = [
    "ScoringConfig",
    "ScoringBreakdown",
    "score_evidence_item",
    "determine_confidence_level",
    "is_independently_corroborating",
    "EvidenceRankingEngine",
    "MovementExplanationReport",
    "MovementAttributionEngine",
    "AttributionResult"
]
