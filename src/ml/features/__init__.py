"""
src/ml/features/__init__.py
Market Intelligence Lab Feature Engineering Suite.
"""

from src.ml.features.builder import (
    PITFeatureExtractor,
    compute_features_hash,
    purge_and_embargo,
    FEATURE_COLUMNS,
)
from src.ml.features.institutional_flow import (
    calculate_institutional_flow_features,
    validate_and_clean_session_dates,
    FLOW_FEATURE_COLUMNS,
)
from src.ml.features.pead_engine import (
    calculate_pead_features,
    resolve_effective_filing_session,
    PEAD_FEATURE_COLUMNS,
)

__all__ = [
    "PITFeatureExtractor",
    "compute_features_hash",
    "purge_and_embargo",
    "FEATURE_COLUMNS",
    "calculate_institutional_flow_features",
    "validate_and_clean_session_dates",
    "FLOW_FEATURE_COLUMNS",
    "calculate_pead_features",
    "resolve_effective_filing_session",
    "PEAD_FEATURE_COLUMNS",
]
