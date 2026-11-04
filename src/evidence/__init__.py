"""
Market Intelligence Lab: Evidence & Attribution Framework.
Provides normalized evidence models, constants, adapters, peer validator, and store.
"""

from src.evidence.models import (
    EvidenceTier,
    EvidenceCategory,
    EvidenceDirection,
    ExpectationSurprise,
    ReportingBasis,
    MovementClassification,
    SectorBenchmarkType,
    EvidenceRecord,
    MovementAnalysisResult,
    SectorBenchmarkContext,
    AttributionHypothesis
)

from src.evidence.constants import (
    SECTOR_TO_INDEX_MAP,
    SYNTHETIC_BASKET_DEFINITIONS,
    MINIMUM_SYNTHETIC_PEERS,
    CONTRADICTION_PENALTY_DEFAULT,
    DATA_GOVERNANCE_NOTICE,
    resolve_sector_benchmark
)

from src.evidence.adapters import (
    CorporateDisclosuresAdapter,
    CorporateActionsAdapter,
    FinancialStatementsAdapter,
    MarketIndexMovementsAdapter,
    VolumeAnomaliesAdapter
)

from src.evidence.peer_validator import (
    SyntheticPeerValidator,
    PeerBasketValidationError
)

from src.evidence.store import EvidenceStore

__all__ = [
    "EvidenceTier",
    "EvidenceCategory",
    "EvidenceDirection",
    "ExpectationSurprise",
    "ReportingBasis",
    "MovementClassification",
    "SectorBenchmarkType",
    "EvidenceRecord",
    "MovementAnalysisResult",
    "SectorBenchmarkContext",
    "AttributionHypothesis",
    "SECTOR_TO_INDEX_MAP",
    "SYNTHETIC_BASKET_DEFINITIONS",
    "MINIMUM_SYNTHETIC_PEERS",
    "CONTRADICTION_PENALTY_DEFAULT",
    "DATA_GOVERNANCE_NOTICE",
    "resolve_sector_benchmark",
    "CorporateDisclosuresAdapter",
    "CorporateActionsAdapter",
    "FinancialStatementsAdapter",
    "MarketIndexMovementsAdapter",
    "VolumeAnomaliesAdapter",
    "SyntheticPeerValidator",
    "PeerBasketValidationError",
    "EvidenceStore"
]
