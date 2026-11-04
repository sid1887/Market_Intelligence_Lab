"""
Market Intelligence Lab: Deterministic Evidence Attribution & Confidence Ranking.
Provides configurable scoring algorithms, contradiction detection, and confidence
classification for market movement explanations.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from src.evidence.models import (
    EvidenceRecord,
    EvidenceTier,
    EvidenceCategory,
    EvidenceDirection,
    ExpectationSurprise,
    MovementAnalysisResult,
    MovementClassification
)
from src.evidence.constants import (
    BASE_TIER_SCORES,
    VOLUME_SCORE_DELTAS,
    ABNORMAL_RETURN_SCORE_DELTAS,
    CONTRADICTION_PENALTY_DEFAULT
)


@dataclass(frozen=True)
class ScoringConfig:
    """
    Centralized, configurable weights, bonuses, penalties, and thresholds
    for deterministic evidence scoring.
    """
    base_tier_scores: Dict[int, float] = field(default_factory=lambda: dict(BASE_TIER_SCORES))
    temporal_same_session: float = 15.0     # Event on session t
    temporal_lag_1d: float = 5.0            # Event on session t-1
    temporal_lag_multi_day: float = 0.0     # Event on session t-2 to t-5
    time_decay_per_day: float = 5.0         # Penalty per trading day lag after t-1
    directional_aligned_bonus: float = 15.0 # Direction matches price return sign
    directional_neutral_flat: float = 10.0  # Direction is NEUTRAL on flat day (|ret| <= 0.5%)
    contradiction_penalty: float = CONTRADICTION_PENALTY_DEFAULT  # 30.0 pts provisional penalty
    abnormal_large_bonus: float = 15.0      # |AR| >= 3.0% and aligned
    abnormal_moderate_bonus: float = 10.0   # 1.5% <= |AR| < 3.0% and aligned
    volume_extreme_bonus: float = 15.0      # VR >= 3.0 or Z >= 3.0
    volume_high_bonus: float = 10.0         # VR >= 2.0 or Z >= 2.0
    volume_muted_penalty: float = 10.0      # VR < 0.8 when |ret| >= 1.5%
    corroboration_bonus: float = 10.0       # Secondary independent evidence supports hypothesis
    high_confidence_threshold: float = 75.0
    moderate_confidence_threshold: float = 50.0
    low_confidence_threshold: float = 30.0
    unexplained_ar_threshold: float = 2.0   # If |AR| >= 2.0% and best score < low threshold -> UNEXPLAINED


@dataclass
class ScoringBreakdown:
    """
    Detailed, auditable decomposition of an evidence score.
    """
    base_score: float
    temporal_score: float
    directional_score: float
    abnormal_return_score: float
    volume_score: float
    corroboration_score: float
    contradiction_penalty: float
    time_decay_penalty: float
    raw_total: float
    clamped_total: float                    # Clamped to [0.0, 100.0]
    is_contradicted: bool
    contradiction_reason: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base_score": round(self.base_score, 2),
            "temporal_score": round(self.temporal_score, 2),
            "directional_score": round(self.directional_score, 2),
            "abnormal_return_score": round(self.abnormal_return_score, 2),
            "volume_score": round(self.volume_score, 2),
            "corroboration_score": round(self.corroboration_score, 2),
            "contradiction_penalty": round(self.contradiction_penalty, 2),
            "time_decay_penalty": round(self.time_decay_penalty, 2),
            "raw_total": round(self.raw_total, 2),
            "clamped_total": round(self.clamped_total, 2),
            "is_contradicted": self.is_contradicted,
            "contradiction_reason": self.contradiction_reason,
            "notes": self.notes
        }


def is_independently_corroborating(primary_record: EvidenceRecord, candidate_record: EvidenceRecord) -> bool:
    """
    Rigorously determines if candidate_record is a genuinely independent corroborating
    observation for primary_record.
    
    Enforces strict independence rules:
    1. Candidate cannot be the same record ID.
    2. Candidate must be VERIFIED.
    3. Volume anomalies cannot corroborate other volume anomalies or company filings (volume is market activity).
    4. Records sharing the same filing/circular reference or (source_identity, event_date, category)
       represent the same underlying event and do not count as independent corroboration.
    5. Sector index returns used in quantitative movement calculations cannot be double-counted
       as corroboration for company-specific news filings.
    6. Candidate direction must align with primary record's direction (must be POSITIVE or NEGATIVE).
    """
    if candidate_record.evidence_id == primary_record.evidence_id:
        return False

    if candidate_record.verification_status != "VERIFIED":
        return False

    # Volume anomalies represent trading activity, not independent narrative catalysts
    if candidate_record.category == EvidenceCategory.VOLUME_LIQUIDITY_SURGE or primary_record.category == EvidenceCategory.VOLUME_LIQUIDITY_SURGE:
        return False

    # Same filing / source document / circular check
    if primary_record.source_reference and candidate_record.source_reference:
        if primary_record.source_reference == candidate_record.source_reference:
            return False

    # Same event channel, date, and category (e.g. recast or duplicate disclosures)
    if (
        primary_record.source_identity == candidate_record.source_identity
        and primary_record.event_date == candidate_record.event_date
        and primary_record.category == candidate_record.category
    ):
        return False

    # Sector index movement vs company filing:
    # Sector index return is already incorporated in quantitative market model / SAR_t.
    # It must NOT be double-counted as independent corroboration of a company news filing.
    # Similarly, market index movements from index_daily (broad market NIFTY 50 or sector indices)
    # are already inputs to the econometric market model (alpha, beta, abnormal return)
    # and sector-adjusted return calculations. They CANNOT corroborate each other or company filings.
    if primary_record.source_identity == "index_daily" or candidate_record.source_identity == "index_daily":
        return False

    if primary_record.entity_type in {"SECTOR", "BENCHMARK"} or candidate_record.entity_type in {"SECTOR", "BENCHMARK"}:
        return False

    # Directional alignment: must share verified non-neutral, non-ambiguous direction
    if primary_record.direction not in {EvidenceDirection.POSITIVE, EvidenceDirection.NEGATIVE}:
        return False

    if candidate_record.direction != primary_record.direction:
        return False

    return True


def score_evidence_item(
    evidence: EvidenceRecord,
    movement: MovementAnalysisResult,
    config: Optional[ScoringConfig] = None,
    corroborating_count: int = 0,
    session_lag_days: int = 0
) -> ScoringBreakdown:
    """
    Deterministically scores a single eligible evidence item against an observed stock movement.
    Enforces all critical safeguards:
    - Financial statement profitability alone (PAT > 0 or PAT < 0) NEVER awards directional catalyst points.
    - ExpectationSurprise.UNKNOWN remains neutral/ambiguous without authenticated consensus.
    - Neutral corporate actions do not award directional points on trending sessions.
    - Contradictory evidence receives a provisional -30 point penalty and cannot exceed 49.9 points.
    - Missing quantitative variables (AR, SAR) contribute 0.0 bonus without fabricating values.
    """
    cfg = config or ScoringConfig()
    notes: List[str] = []

    # 1. Base Tier Score
    base_score = float(cfg.base_tier_scores.get(int(evidence.tier), 10.0))
    notes.append(f"Tier {evidence.tier.value} base score: {base_score:.1f}")

    # 2. Temporal Score & Time Decay
    if session_lag_days == 0:
        temporal_score = cfg.temporal_same_session
        time_decay = 0.0
        notes.append(f"Same-session announcement: +{temporal_score:.1f}")
    elif session_lag_days == 1:
        temporal_score = cfg.temporal_lag_1d
        time_decay = 0.0
        notes.append(f"Pre-market / previous-session announcement (1-day lag): +{temporal_score:.1f}")
    else:
        temporal_score = cfg.temporal_lag_multi_day
        time_decay = min(25.0, (session_lag_days - 1) * cfg.time_decay_per_day)
        notes.append(f"Multi-day lag ({session_lag_days} days): +{temporal_score:.1f}, decay: -{time_decay:.1f}")

    # 3. Directional Alignment & Contradiction Evaluation
    directional_score = 0.0
    contradiction_penalty = 0.0
    is_contradicted = False
    contradiction_reason = None

    # Determine movement direction from corporate-action-adjusted return
    ret = movement.ret_1d_adj if movement.ret_1d_adj is not None else movement.ret_1d_raw
    if ret >= 0.005:
        move_dir = EvidenceDirection.POSITIVE
    elif ret <= -0.005:
        move_dir = EvidenceDirection.NEGATIVE
    else:
        move_dir = EvidenceDirection.NEUTRAL

    # Financial Statements & Consensus Safeguard
    if evidence.category == EvidenceCategory.EARNINGS_RELEASE or evidence.source_identity == "company_financial_statements":
        if evidence.expectation_surprise == ExpectationSurprise.UNKNOWN:
            # Strict safeguard: PAT sign alone NEVER grants directional catalyst points
            directional_score = 0.0
            is_contradicted = False
            notes.append("Financial statement evaluated with ExpectationSurprise.UNKNOWN; PAT sign does NOT award directional points.")
        elif evidence.expectation_surprise == ExpectationSurprise.BEAT:
            if move_dir == EvidenceDirection.POSITIVE:
                directional_score = cfg.directional_aligned_bonus
                notes.append(f"Authenticated consensus BEAT aligned with positive price return: +{directional_score:.1f}")
            elif move_dir == EvidenceDirection.NEGATIVE:
                is_contradicted = True
                contradiction_penalty = cfg.contradiction_penalty
                contradiction_reason = "Authenticated earnings BEAT contradicted by observed stock price decline."
                notes.append(f"CONTRADICTION: Earnings BEAT on negative day: -{contradiction_penalty:.1f}")
        elif evidence.expectation_surprise == ExpectationSurprise.MISS:
            if move_dir == EvidenceDirection.NEGATIVE:
                directional_score = cfg.directional_aligned_bonus
                notes.append(f"Authenticated consensus MISS aligned with negative price return: +{directional_score:.1f}")
            elif move_dir == EvidenceDirection.POSITIVE:
                is_contradicted = True
                contradiction_penalty = cfg.contradiction_penalty
                contradiction_reason = "Authenticated earnings MISS contradicted by observed stock price surge."
                notes.append(f"CONTRADICTION: Earnings MISS on positive day: -{contradiction_penalty:.1f}")
        elif evidence.expectation_surprise == ExpectationSurprise.IN_LINE:
            if move_dir == EvidenceDirection.NEUTRAL:
                directional_score = cfg.directional_neutral_flat
                notes.append(f"Authenticated IN_LINE results aligned with flat session: +{directional_score:.1f}")
            else:
                directional_score = 0.0
                notes.append("Authenticated IN_LINE results on trending day: +0.0")

    # Corporate Actions (Dividends, Splits, Bonus issues)
    elif evidence.category in {EvidenceCategory.DIVIDEND_DECLARATION, EvidenceCategory.BONUS_SPLIT_EVENT} or evidence.direction == EvidenceDirection.NEUTRAL:
        if move_dir == EvidenceDirection.NEUTRAL:
            directional_score = cfg.directional_neutral_flat
            notes.append(f"Neutral corporate action on flat session: +{directional_score:.1f}")
        else:
            # Mechanical adjustment does not award directional catalyst bonus
            directional_score = 0.0
            is_contradicted = False
            notes.append("Mechanical corporate action on trending day: +0.0 (neutral adjustment, non-directional)")

    # Volume Anomalies as standalone evidence items
    elif evidence.category == EvidenceCategory.VOLUME_LIQUIDITY_SURGE or evidence.source_identity == "quant_factors_daily":
        directional_score = 0.0
        is_contradicted = False
        notes.append("Volume anomaly is a market activity observation, not a directional causal explanation (+0.0 directional).")

    # Standard Directional Evidence (Disclosures, Sector Moves, Macro)
    else:
        if evidence.direction == EvidenceDirection.AMBIGUOUS:
            directional_score = 0.0
            is_contradicted = False
            notes.append("Ambiguous evidence direction: +0.0")
        elif evidence.direction == move_dir:
            directional_score = cfg.directional_aligned_bonus
            notes.append(f"Evidence direction {evidence.direction.value} aligned with market move: +{directional_score:.1f}")
        elif (evidence.direction == EvidenceDirection.POSITIVE and move_dir == EvidenceDirection.NEGATIVE) or \
             (evidence.direction == EvidenceDirection.NEGATIVE and move_dir == EvidenceDirection.POSITIVE):
            is_contradicted = True
            contradiction_penalty = cfg.contradiction_penalty
            contradiction_reason = f"Evidence direction {evidence.direction.value} conflicts with price move {move_dir.value} (ret: {ret:.2%})."
            notes.append(f"CONTRADICTION: Direction {evidence.direction.value} vs move {move_dir.value}: -{contradiction_penalty:.1f}")
        elif move_dir == EvidenceDirection.NEUTRAL and evidence.direction in {EvidenceDirection.POSITIVE, EvidenceDirection.NEGATIVE}:
            is_contradicted = True
            contradiction_penalty = cfg.contradiction_penalty
            contradiction_reason = f"Expected directional catalyst {evidence.direction.value} failed to move stock (return: {ret:.2%})."
            notes.append(f"CONTRADICTION: Directional catalyst on flat session: -{contradiction_penalty:.1f}")

    # 4. Abnormal Return Corroboration
    abnormal_return_score = 0.0
    if movement.abnormal_return is not None:
        ar = movement.abnormal_return
        # Check alignment with evidence direction
        if evidence.direction == EvidenceDirection.POSITIVE and ar > 0:
            if ar >= 0.03:
                abnormal_return_score = cfg.abnormal_large_bonus
                notes.append(f"Large positive abnormal return (AR: {ar:.2%}): +{abnormal_return_score:.1f}")
            elif ar >= 0.015:
                abnormal_return_score = cfg.abnormal_moderate_bonus
                notes.append(f"Moderate positive abnormal return (AR: {ar:.2%}): +{abnormal_return_score:.1f}")
        elif evidence.direction == EvidenceDirection.NEGATIVE and ar < 0:
            if ar <= -0.03:
                abnormal_return_score = cfg.abnormal_large_bonus
                notes.append(f"Large negative abnormal return (AR: {ar:.2%}): +{abnormal_return_score:.1f}")
            elif ar <= -0.015:
                abnormal_return_score = cfg.abnormal_moderate_bonus
                notes.append(f"Moderate negative abnormal return (AR: {ar:.2%}): +{abnormal_return_score:.1f}")
    else:
        notes.append("Abnormal return unavailable (insufficient history): +0.0")

    # 5. Volume Corroboration (for non-volume items)
    volume_score = 0.0
    if evidence.category != EvidenceCategory.VOLUME_LIQUIDITY_SURGE:
        if movement.volume_ratio_20d is not None and not movement.is_zero_volume:
            vr = movement.volume_ratio_20d
            z = movement.volume_log_zscore_50d
            if vr >= 3.0 or (z is not None and z >= 3.0):
                volume_score = cfg.volume_extreme_bonus
                notes.append(f"Extreme volume surge (VR: {vr:.2f}x): +{volume_score:.1f}")
            elif vr >= 2.0 or (z is not None and z >= 2.0):
                volume_score = cfg.volume_high_bonus
                notes.append(f"High volume surge (VR: {vr:.2f}x): +{volume_score:.1f}")
            elif vr < 0.8 and abs(ret) >= 0.015:
                volume_score = -cfg.volume_muted_penalty
                notes.append(f"Muted volume on large move (VR: {vr:.2f}x): -{cfg.volume_muted_penalty:.1f}")
        elif movement.is_zero_volume:
            notes.append("Zero trading volume recorded: +0.0")

    # 6. Independent Corroboration
    corroboration_score = 0.0
    if corroborating_count > 0 and not is_contradicted:
        corroboration_score = cfg.corroboration_bonus
        notes.append(f"Supported by {corroborating_count} independent corroborating evidence item(s): +{corroboration_score:.1f}")

    # 7. Total Score & Guards
    raw_total = (
        base_score
        + temporal_score
        + directional_score
        + abnormal_return_score
        + volume_score
        + corroboration_score
        - contradiction_penalty
        - time_decay
    )

    clamped_total = max(0.0, min(100.0, raw_total))

    # CRITICAL GUARD 1: Contradictory evidence alone can NEVER attain HIGH_CONFIDENCE
    if is_contradicted:
        clamped_total = min(clamped_total, 49.9)
        notes.append("Contradicted evidence guard applied: capped at 49.9 (cannot achieve HIGH_CONFIDENCE).")

    # CRITICAL GUARD 2: Volume activity observation cannot inflate explanatory score
    # Volume measures market trading activity, not causal price explanation.
    # Its effective explanatory score is capped at 49.9 to strictly harmonize with the LOW_CONFIDENCE taxonomy range (30.0-49.9).
    if evidence.category == EvidenceCategory.VOLUME_LIQUIDITY_SURGE or evidence.source_identity == "quant_factors_daily":
        clamped_total = min(clamped_total, 49.9)
        notes.append("Volume activity observation guard applied: explanatory score capped at 49.9 (LOW_CONFIDENCE) as volume measures market activity, not causal explanation.")

    return ScoringBreakdown(
        base_score=base_score,
        temporal_score=temporal_score,
        directional_score=directional_score,
        abnormal_return_score=abnormal_return_score,
        volume_score=volume_score,
        corroboration_score=corroboration_score,
        contradiction_penalty=contradiction_penalty,
        time_decay_penalty=time_decay,
        raw_total=raw_total,
        clamped_total=clamped_total,
        is_contradicted=is_contradicted,
        contradiction_reason=contradiction_reason,
        notes=notes
    )


def determine_confidence_level(
    score: float,
    evidence: Any = None,
    movement: Any = None,
    breakdown: Optional[ScoringBreakdown] = None,
    is_contradicted: bool = False,
    tier: Optional[EvidenceTier] = None,
    is_unexplained: bool = False,
    config: Optional[ScoringConfig] = None
) -> str:
    """
    Deterministically maps a heuristic score and rigorous explanatory gates to an auditable confidence level:
    - 'HIGH_CONFIDENCE'
    - 'MODERATE_CONFIDENCE'
    - 'LOW_CONFIDENCE'
    - 'INSUFFICIENT_EVIDENCE'
    - 'UNEXPLAINED_MOVEMENT'

    Enforces critical architectural gates:
    1. High-quality evidence != High explanatory confidence.
    2. Volume anomalies alone can NEVER achieve MODERATE_CONFIDENCE or HIGH_CONFIDENCE as price explanations.
    3. Official financial results with UNKNOWN consensus cannot reach HIGH_CONFIDENCE solely through timing.
    4. Contradicted evidence is strictly capped at <= MODERATE_CONFIDENCE (score <= 49.9).
    """
    cfg = config or ScoringConfig()

    if is_unexplained:
        return "UNEXPLAINED_MOVEMENT"

    # Handle legacy / alternate positional calling: determine_confidence_level(score, is_contradicted, tier)
    if isinstance(evidence, bool):
        is_contradicted = evidence
        if isinstance(movement, (EvidenceTier, int)):
            tier = EvidenceTier(int(movement))
        evidence = None
        movement = None

    contra = is_contradicted or (breakdown.is_contradicted if breakdown else False)
    ev_tier = evidence.tier if isinstance(evidence, EvidenceRecord) else (tier or EvidenceTier.TIER_5_UNVERIFIED)

    # 1. Volume Anomaly Gate
    # A volume anomaly establishes unusual trading activity, not the cause or direction of that activity.
    # It can NEVER independently generate MODERATE_CONFIDENCE or HIGH_CONFIDENCE as a price-movement explanation.
    if evidence and (evidence.category == EvidenceCategory.VOLUME_LIQUIDITY_SURGE or evidence.source_identity == "quant_factors_daily"):
        if score >= cfg.low_confidence_threshold:
            return "LOW_CONFIDENCE"
        return "INSUFFICIENT_EVIDENCE"

    # 2. Contradiction Gate
    # Contradicted evidence can NEVER attain HIGH_CONFIDENCE
    if contra:
        if score >= cfg.low_confidence_threshold:
            return "MODERATE_CONFIDENCE" if score >= 45.0 else "LOW_CONFIDENCE"
        return "INSUFFICIENT_EVIDENCE"

    # 3. HIGH_CONFIDENCE Explanatory Relevance Gates
    if score >= cfg.high_confidence_threshold and ev_tier in {
        EvidenceTier.TIER_1_OFFICIAL_FILING,
        EvidenceTier.TIER_2_FINANCIAL_ACTION,
        EvidenceTier.TIER_3_SECTOR_BENCHMARK
    }:
        # Check explanatory relevance if evidence is provided:
        if evidence:
            # A. Company Filing Gate (STOCK)
            if evidence.entity_type == "STOCK":
                # Must have verified directional alignment (breakdown.directional_score > 0)
                # UNKNOWN consensus or AMBIGUOUS direction is explicitly barred from HIGH_CONFIDENCE!
                if evidence.expectation_surprise == ExpectationSurprise.UNKNOWN and evidence.category == EvidenceCategory.EARNINGS_RELEASE:
                    # Direction is unauthenticated: capped at MODERATE_CONFIDENCE
                    return "MODERATE_CONFIDENCE"
                if evidence.direction == EvidenceDirection.AMBIGUOUS:
                    return "MODERATE_CONFIDENCE"
                if evidence.direction == EvidenceDirection.NEUTRAL:
                    # Mechanical corporate actions do not explain directional price movements
                    return "MODERATE_CONFIDENCE"
                if breakdown and breakdown.directional_score <= 0.0:
                    return "MODERATE_CONFIDENCE"

            # B. Sector / Benchmark Index Gate
            elif evidence.entity_type in {"SECTOR", "BENCHMARK"}:
                # Must be consistent with systematic movement classification
                if movement and movement.primary_classification not in {
                    MovementClassification.SECTOR_SYSTEMATIC_SURGE,
                    MovementClassification.SECTOR_SYSTEMATIC_DRAG,
                    MovementClassification.MARKET_BETA_DRIVEN
                }:
                    # If stock move was idiosyncratic, sector move is not high-confidence explanation
                    return "MODERATE_CONFIDENCE"
                if breakdown and breakdown.directional_score <= 0.0:
                    return "MODERATE_CONFIDENCE"

        return "HIGH_CONFIDENCE"

    elif score >= cfg.moderate_confidence_threshold:
        return "MODERATE_CONFIDENCE"
    elif score >= cfg.low_confidence_threshold:
        return "LOW_CONFIDENCE"
    else:
        return "INSUFFICIENT_EVIDENCE"
