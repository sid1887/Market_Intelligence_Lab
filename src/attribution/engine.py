"""
Market Intelligence Lab: Evidence Attribution & Confidence Ranking Engine.
Connects the deterministic evidence store with quantitative movement analysis
to produce transparent, reproducible, evidence-ranked explanations.
"""

import json
import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Set, Tuple

from src.storage.database import DatabaseManager
from src.evidence.models import (
    EvidenceRecord,
    EvidenceTier,
    EvidenceCategory,
    EvidenceDirection,
    ExpectationSurprise,
    MovementAnalysisResult,
    MovementClassification,
    AttributionHypothesis
)
from src.evidence.constants import (
    DATA_GOVERNANCE_NOTICE,
    resolve_sector_benchmark
)
from src.evidence.store import EvidenceStore
from src.quant.movement_analyzer import MarketMovementAnalyzer
from src.quant.calendar import count_trading_sessions_between
from src.attribution.ranking import (
    ScoringConfig,
    ScoringBreakdown,
    score_evidence_item,
    determine_confidence_level,
    is_independently_corroborating
)


@dataclass
class MovementExplanationReport:
    """
    Structured, fully reproducible investigation result for a stock's
    price movement on a given trading date.
    """
    investigation_id: str
    symbol: str
    trading_date: str
    movement_result: MovementAnalysisResult
    primary_hypothesis: Optional[AttributionHypothesis]
    ranked_hypotheses: List[AttributionHypothesis]
    eligible_evidence: List[EvidenceRecord]
    excluded_evidence: List[Dict[str, Any]]
    contradicting_evidence: List[Dict[str, Any]]
    unresolved_questions: List[str]
    reporting_basis_context: Dict[str, Any]
    governance_notice: str = DATA_GOVERNANCE_NOTICE
    generated_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Serializes report to structured dictionary."""
        return {
            "investigation_id": self.investigation_id,
            "symbol": self.symbol,
            "trading_date": self.trading_date,
            "movement_result": self.movement_result.to_dict(),
            "primary_hypothesis": self.primary_hypothesis.to_dict() if self.primary_hypothesis else None,
            "ranked_hypotheses": [h.to_dict() for h in self.ranked_hypotheses],
            "eligible_evidence": [e.to_dict() for e in self.eligible_evidence],
            "excluded_evidence": self.excluded_evidence,
            "contradicting_evidence": self.contradicting_evidence,
            "unresolved_questions": self.unresolved_questions,
            "reporting_basis_context": self.reporting_basis_context,
            "governance_notice": self.governance_notice,
            "generated_at": self.generated_at
        }

    def to_json(self, indent: int = 2) -> str:
        """Serializes report to JSON formatted string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        """Generates an executive, human-readable Markdown investigation report."""
        res = self.movement_result
        hyp = self.primary_hypothesis

        md: List[str] = []
        md.append(f"# Market Explanation Report: {self.symbol} ({self.trading_date})")
        md.append("")
        md.append(f"> **Investigation ID:** `{self.investigation_id}`  ")
        md.append(f"> **Generated At:** `{self.generated_at}`  ")
        md.append(f"> **Classification:** `{res.primary_classification.value}`  ")
        md.append("")

        # 1. Executive Summary & Movement Decomposition
        md.append("## 1. Executive Movement Decomposition")
        md.append("")
        md.append("| Metric | Value | Description |")
        md.append("| :--- | :---: | :--- |")
        md.append(f"| **Raw 1-Day Return** | `{res.ret_1d_raw:+.2%}` | Close-to-close unadjusted change |")
        md.append(f"| **Adjusted 1-Day Return** | `{res.ret_1d_adj:+.2%}` | Corporate-action adjusted return |")
        md.append(f"| **Gap Open** | `{res.gap_open:+.2%}` | Overnight market price adjustment |")
        md.append(f"| **Intraday Drift** | `{res.intraday_drift:+.2%}` | Open-to-close regular hours drift |")
        bench_ret_str = f"{res.benchmark_return:+.2%}" if res.benchmark_return is not None else "N/A"
        md.append(f"| **NIFTY 50 PRI Return** | `{bench_ret_str}` | Official broad-market benchmark return |")
        
        sec_ret_str = f"{res.sector_return:+.2%}" if res.sector_return is not None else "N/A"
        md.append(f"| **Sector Return** | `{sec_ret_str}` | {res.sector_benchmark_name} ({res.sector_benchmark_type.value}) |")

        ar_str = f"{res.abnormal_return:+.2%}" if res.abnormal_return is not None else "Unavailable (Insufficient History)"
        md.append(f"| **Econometric AR ($AR_t$)** | `{ar_str}` | OLS Market Model abnormal return |")

        sar_str = f"{res.sector_adjusted_return:+.2%}" if res.sector_adjusted_return is not None else "N/A"
        md.append(f"| **Sector-Adjusted Return ($SAR_t$)** | `{sar_str}` | Excess return over sector benchmark |")

        vr_str = f"{res.volume_ratio_20d:.2f}x" if res.volume_ratio_20d is not None else "N/A"
        md.append(f"| **20-Day Volume Ratio** | `{vr_str}` | Adjusted volume relative to 20-day SMA |")
        md.append("")

        # 2. Primary Explanation & Confidence
        md.append("## 2. Evidence Attribution & Primary Explanation")
        md.append("")
        if hyp:
            conf_badge = f"**{hyp.confidence_level}**"
            md.append(f"- **Confidence Level:** {conf_badge}")
            md.append(f"- **Evidence Strength Score:** `{hyp.evidence_strength_score:.1f} / 100.0` (Deterministic Heuristic)")
            if hyp.primary_evidence_id:
                md.append(f"- **Primary Catalyst Record:** `{hyp.primary_evidence_id}`")
            else:
                md.append("- **Primary Catalyst Record:** *None (No eligible catalyst met minimum score threshold)*")
            md.append(f"- **Assessment Rationale:** {hyp.notes}")
        else:
            md.append("- **Confidence Level:** `UNEXPLAINED_MOVEMENT`")
            md.append("- **Assessment Rationale:** No candidate hypothesis could be formed.")
        md.append("")

        # 3. Ranked Candidate Hypotheses
        md.append("## 3. Ranked Candidate Explanations")
        md.append("")
        if self.ranked_hypotheses:
            md.append("| Rank | Primary Evidence ID | Catalyst Category | Score | Confidence Level | Contradicted? |")
            md.append("| :---: | :--- | :---: | :---: | :---: | :---: |")
            for i, h in enumerate(self.ranked_hypotheses, start=1):
                ev_id = h.primary_evidence_id or "NONE"
                contra_str = "YES (-30.0)" if h.is_contradicted else "No"
                md.append(f"| {i} | `{ev_id}` | `{h.movement_classification.value}` | `{h.evidence_strength_score:.1f}` | `{h.confidence_level}` | {contra_str} |")
        else:
            md.append("*No eligible candidate hypotheses met the criteria.*")
        md.append("")

        # 4. Contradictory Evidence & Penalties
        md.append("## 4. Contradictory Evidence & Penalties")
        md.append("")
        if self.contradicting_evidence:
            md.append("| Evidence ID | Headline | Direction | Conflict Reason | Penalty Applied |")
            md.append("| :--- | :--- | :---: | :--- | :---: |")
            for c in self.contradicting_evidence:
                md.append(f"| `{c.get('evidence_id')}` | {c.get('headline')} | `{c.get('direction')}` | {c.get('conflict_reason')} | `-30.0 pts` |")
        else:
            md.append("*No contradictory evidence detected for this session.*")
        md.append("")

        # 5. Excluded Evidence Records
        md.append("## 5. Excluded Evidence & Audit Trail")
        md.append("")
        if self.excluded_evidence:
            md.append("| Evidence ID | Headline | Tier | Exclusion Reason |")
            md.append("| :--- | :--- | :---: | :--- |")
            for ex in self.excluded_evidence:
                md.append(f"| `{ex.get('evidence_id')}` | {ex.get('headline')} | Tier {ex.get('tier')} | `{ex.get('reason')}` |")
        else:
            md.append("*No candidate records were excluded.*")
        md.append("")

        # 6. Unresolved Questions & Diagnostic Limitations
        md.append("## 6. Unresolved Questions & Missing Information")
        md.append("")
        if self.unresolved_questions:
            for q in self.unresolved_questions:
                md.append(f"- {q}")
        else:
            md.append("- *All diagnostic parameters satisfied without unresolved data gaps.*")
        md.append("")

        # 7. Compliance Notice
        md.append("---")
        md.append(f"> **{self.governance_notice}**")
        md.append("")

        return "\n".join(md)


class EvidenceRankingEngine:
    """
    Deterministic Evidence Attribution & Confidence Ranking Engine.
    Evaluates evidence eligibility, calculates deterministic heuristic scores,
    enforces contradiction penalties, and produces structured investigation reports.
    """

    def __init__(
        self,
        db: DatabaseManager,
        store: Optional[EvidenceStore] = None,
        analyzer: Optional[MarketMovementAnalyzer] = None,
        config: Optional[ScoringConfig] = None
    ):
        self.db = db
        self.store = store or EvidenceStore(db)
        self.analyzer = analyzer or MarketMovementAnalyzer(db)
        self.config = config or ScoringConfig()

    def _get_recent_trading_sessions(self, symbol: str, target_date: str, count: int = 6) -> List[str]:
        """Returns up to `count` completed trading sessions ending on target_date."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute("""
                SELECT trading_date FROM ohlcv_daily 
                WHERE symbol = ? AND trading_date <= ?
                ORDER BY trading_date DESC LIMIT ?;
            """, (symbol, target_date, count)).fetchall()

            if not rows:
                # Fallback to NIFTY 50 trading calendar
                rows = cursor.execute("""
                    SELECT trading_date FROM index_daily 
                    WHERE index_name = 'NIFTY 50' AND index_type = 'PRI' AND trading_date <= ?
                    ORDER BY trading_date DESC LIMIT ?;
                """, (target_date, count)).fetchall()

        dates = [r[0] for r in rows]
        dates.sort()  # Ascending order
        return dates

    def explain_movement(
        self,
        symbol: str,
        trading_date: str,
        as_of_date: Optional[str] = None,
        persist_to_db: bool = False
    ) -> MovementExplanationReport:
        """
        Executes a complete deterministic attribution investigation for a stock movement.
        Enforces point-in-time isolation, verification gates, contradiction penalties,
        and multi-hypothesis ranking.
        """
        # Step 1: Perform quantitative movement decomposition (Phase 3)
        movement = self.analyzer.analyze_session_movement(symbol, trading_date)

        # Step 2: Establish recent session window [t-5, t]
        recent_sessions = self._get_recent_trading_sessions(symbol, trading_date, count=6)
        earliest_session = recent_sessions[0] if recent_sessions else trading_date
        target_session_idx = recent_sessions.index(trading_date) if trading_date in recent_sessions else (len(recent_sessions) - 1)

        # Step 3: Identify relevant symbols for evidence gathering
        relevant_symbols: Set[str] = {symbol, "NIFTY 50"}
        if movement.sector_benchmark_name and movement.sector_benchmark_name != "NIFTY 50":
            relevant_symbols.add(movement.sector_benchmark_name)
        
        # Account for predecessor lineage (e.g. TMPV predecessor TATAMOTORS)
        if symbol == "TMPV":
            relevant_symbols.add("TATAMOTORS")

        # Step 4: Query candidate evidence records in window
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" for _ in relevant_symbols)
            # Retrieve all records up to target_date (and also inspect same date future hours)
            query = f"""
                SELECT * FROM evidence_records
                WHERE symbol IN ({placeholders})
                  AND effective_session_date >= ?
                ORDER BY effective_session_date ASC, evidence_tier ASC;
            """
            params = list(relevant_symbols) + [earliest_session]
            cursor.execute(query, params)
            candidate_rows = [dict(r) for r in cursor.fetchall()]

        # Step 5: Screen eligibility, point-in-time availability, and verification status
        effective_as_of = as_of_date or trading_date
        eligible_verified_records: List[EvidenceRecord] = []
        excluded_evidence: List[Dict[str, Any]] = []

        for row in candidate_rows:
            r = EvidenceRecord.from_dict(row)
            ev_dict = {
                "evidence_id": r.evidence_id,
                "headline": r.headline,
                "tier": int(r.tier),
                "symbol": r.symbol,
                "effective_session_date": r.effective_session_date,
                "verification_status": r.verification_status
            }

            # 1. Point-in-time / Future Event Exclusion
            if r.effective_session_date > trading_date or r.event_date > trading_date:
                ev_dict["reason"] = f"FUTURE_EVENT_LOOKAHEAD (effective {r.effective_session_date} > {trading_date})"
                excluded_evidence.append(ev_dict)
                continue

            if as_of_date and r.effective_session_date > as_of_date:
                ev_dict["reason"] = f"AS_OF_DATE_LOOKAHEAD (effective {r.effective_session_date} > {as_of_date})"
                excluded_evidence.append(ev_dict)
                continue

            if not r.is_pit_eligible:
                ev_dict["reason"] = "PIT_INELIGIBLE (look-ahead or untimed hazard)"
                excluded_evidence.append(ev_dict)
                continue

            # 2. Same-day broadcast timestamp check:
            # If broadcast timestamp occurred after market close (15:30 IST) on trading_date,
            # it was published after today's session closed and cannot explain today's trading.
            if r.broadcast_timestamp:
                try:
                    ts_dt = datetime.datetime.fromisoformat(r.broadcast_timestamp)
                    ts_date_str = ts_dt.strftime("%Y-%m-%d")
                    # If announced on trading_date after 15:30 IST:
                    if ts_date_str == trading_date and (ts_dt.hour > 15 or (ts_dt.hour == 15 and ts_dt.minute >= 30)):
                        ev_dict["reason"] = f"POST_MARKET_BROADCAST_ON_EVENT_DATE ({r.broadcast_timestamp})"
                        excluded_evidence.append(ev_dict)
                        continue
                except Exception:
                    pass

            # 3. Verification Gate:
            # Only VERIFIED records enter candidate hypothesis ranking
            if r.verification_status != "VERIFIED":
                ev_dict["reason"] = f"UNVERIFIED_STATUS ({r.verification_status})"
                excluded_evidence.append(ev_dict)
                continue

            # Passed all filters
            eligible_verified_records.append(r)

        # Step 6: Multi-Hypothesis Scoring & Directional Evaluation
        candidate_hypotheses: List[AttributionHypothesis] = []
        contradicting_evidence: List[Dict[str, Any]] = []

        for record in eligible_verified_records:
            # Calculate session lag days using official exchange trading calendar
            rec_session = record.effective_session_date
            lag_days = count_trading_sessions_between(rec_session, movement.trading_date)

            # Count independent corroborating evidence using rigorous independence rules
            corrob_count = sum(
                1 for other in eligible_verified_records
                if is_independently_corroborating(record, other)
            )

            # Score item
            breakdown = score_evidence_item(
                evidence=record,
                movement=movement,
                config=self.config,
                corroborating_count=corrob_count,
                session_lag_days=lag_days
            )

            # Determine confidence level with explanatory relevance gates
            conf_level = determine_confidence_level(
                score=breakdown.clamped_total,
                evidence=record,
                movement=movement,
                breakdown=breakdown,
                is_contradicted=breakdown.is_contradicted,
                tier=record.tier,
                is_unexplained=False,
                config=self.config
            )

            # Identify supporting and contradicting peer evidence IDs
            aligned_ids = [
                o.evidence_id for o in eligible_verified_records
                if o.evidence_id != record.evidence_id and o.direction == record.direction
            ]
            contra_ids = [
                o.evidence_id for o in eligible_verified_records
                if o.evidence_id != record.evidence_id and (
                    (record.direction == EvidenceDirection.POSITIVE and o.direction == EvidenceDirection.NEGATIVE) or
                    (record.direction == EvidenceDirection.NEGATIVE and o.direction == EvidenceDirection.POSITIVE)
                )
            ]

            if breakdown.is_contradicted:
                contra_dict = {
                    "evidence_id": record.evidence_id,
                    "headline": record.headline,
                    "direction": record.direction.value,
                    "conflict_reason": breakdown.contradiction_reason,
                    "penalty_applied": breakdown.contradiction_penalty
                }
                contradicting_evidence.append(contra_dict)

            hyp = AttributionHypothesis(
                hypothesis_id=f"HYP_{symbol}_{trading_date.replace('-', '')}_{record.evidence_id}",
                symbol=symbol,
                target_date=trading_date,
                movement_classification=movement.primary_classification,
                primary_evidence_id=record.evidence_id,
                supporting_evidence_ids=aligned_ids,
                contradicting_evidence_ids=contra_ids,
                evidence_strength_score=breakdown.clamped_total,
                confidence_level=conf_level,
                is_contradicted=breakdown.is_contradicted,
                contradiction_penalty_applied=breakdown.contradiction_penalty,
                alternative_hypotheses=[],
                unexplained_residual_pct=round(abs(movement.ret_1d_adj) * 100, 2) if breakdown.clamped_total < self.config.low_confidence_threshold else None,
                notes="; ".join(breakdown.notes)
            )
            candidate_hypotheses.append(hyp)

        # Step 7: Multi-Hypothesis Ranking & Synthesis
        # Sort descending by evidence_strength_score
        candidate_hypotheses.sort(key=lambda h: h.evidence_strength_score, reverse=True)

        # Check special systematic classifications (Sector Surge / Market Beta)
        # If the market movement analyzer identified a systematic movement,
        # prioritize systematic explanations if available.
        if movement.primary_classification in {
            MovementClassification.SECTOR_SYSTEMATIC_SURGE,
            MovementClassification.SECTOR_SYSTEMATIC_DRAG
        }:
            # Find sector hypothesis if present
            sec_hyps = [h for h in candidate_hypotheses if h.primary_evidence_id and "NIFTY" in h.primary_evidence_id]
            if sec_hyps:
                # Prioritize sector hypothesis to top
                candidate_hypotheses.remove(sec_hyps[0])
                candidate_hypotheses.insert(0, sec_hyps[0])

        # Step 8: Select Primary Hypothesis and Populate Alternative Hypotheses
        # CRITICAL SAFEGUARD: Volume anomalies represent market trading activity,
        # NOT the causal reason or explanation for price movement.
        # A volume anomaly cannot become the sole primary explanatory hypothesis,
        # nor can it independently generate MODERATE_CONFIDENCE or HIGH_CONFIDENCE.
        catalyst_hypotheses = [
            h for h in candidate_hypotheses
            if not (
                h.primary_evidence_id and (
                    "_VOL_" in h.primary_evidence_id
                    or any(e.evidence_id == h.primary_evidence_id and e.category == EvidenceCategory.VOLUME_LIQUIDITY_SURGE for e in eligible_verified_records)
                )
            )
        ]
        volume_hypotheses = [
            h for h in candidate_hypotheses
            if h not in catalyst_hypotheses
        ]

        primary_hypothesis: Optional[AttributionHypothesis] = None

        if catalyst_hypotheses and catalyst_hypotheses[0].evidence_strength_score >= self.config.low_confidence_threshold:
            primary_hypothesis = catalyst_hypotheses[0]
            # Link other hypotheses as alternatives
            all_alternatives = [h for h in candidate_hypotheses if h.hypothesis_id != primary_hypothesis.hypothesis_id]
            primary_hypothesis.alternative_hypotheses = [
                f"{h.hypothesis_id} ({h.confidence_level}, Score: {h.evidence_strength_score:.1f})"
                for h in all_alternatives
            ]
        else:
            # No genuine explanatory catalyst achieved score >= 30.0!
            # If a volume anomaly exists, it is recorded as a secondary market activity observation,
            # but CANNOT become the primary price-movement explanation.
            ret_abs = abs(movement.ret_1d_adj) if movement.ret_1d_adj is not None else abs(movement.ret_1d_raw)
            ar_abs = abs(movement.abnormal_return) if movement.abnormal_return is not None else 0.0

            has_volume_anomaly = len(volume_hypotheses) > 0 or movement.is_volume_spike
            vol_str = f"Anomalous trading volume observed (VR: {movement.volume_ratio_20d:.2f}x), but unusual volume alone establishes trading activity, not the cause or direction of price movement. " if has_volume_anomaly else ""

            if ret_abs >= 0.015 or ar_abs >= 0.02 or has_volume_anomaly:
                # Unexplained move (or significant volume without catalyst)
                primary_hypothesis = AttributionHypothesis(
                    hypothesis_id=f"HYP_{symbol}_{trading_date.replace('-', '')}_UNEXPLAINED",
                    symbol=symbol,
                    target_date=trading_date,
                    movement_classification=MovementClassification.UNEXPLAINED_MOVEMENT,
                    primary_evidence_id=None,
                    supporting_evidence_ids=[vh.primary_evidence_id for vh in volume_hypotheses if vh.primary_evidence_id],
                    contradicting_evidence_ids=[c["evidence_id"] for c in contradicting_evidence],
                    evidence_strength_score=0.0,
                    confidence_level="UNEXPLAINED_MOVEMENT",
                    is_contradicted=False,
                    contradiction_penalty_applied=0.0,
                    alternative_hypotheses=[f"{h.hypothesis_id} ({h.confidence_level}, Score: {h.evidence_strength_score:.1f})" for h in candidate_hypotheses],
                    unexplained_residual_pct=round(ret_abs * 100, 2),
                    notes=f"{vol_str}No verified explanatory catalyst met the minimum score threshold (30.0); price movement remains unexplained."
                )
            else:
                # Flat/routine drift without catalyst
                primary_hypothesis = AttributionHypothesis(
                    hypothesis_id=f"HYP_{symbol}_{trading_date.replace('-', '')}_INSUFFICIENT",
                    symbol=symbol,
                    target_date=trading_date,
                    movement_classification=movement.primary_classification,
                    primary_evidence_id=None,
                    supporting_evidence_ids=[],
                    contradicting_evidence_ids=[c["evidence_id"] for c in contradicting_evidence],
                    evidence_strength_score=0.0,
                    confidence_level="INSUFFICIENT_EVIDENCE",
                    is_contradicted=False,
                    contradiction_penalty_applied=0.0,
                    alternative_hypotheses=[f"{h.hypothesis_id} ({h.confidence_level}, Score: {h.evidence_strength_score:.1f})" for h in candidate_hypotheses],
                    unexplained_residual_pct=None,
                    notes=f"Routine price action ({movement.ret_1d_adj:+.2%}); no candidate evidence scored >= 30.0."
                )

        # Step 9: Compile Unresolved Questions and Context
        unresolved_questions: List[str] = []

        # Consensus check
        has_earnings_release = any(
            e.category == EvidenceCategory.EARNINGS_RELEASE
            for e in eligible_verified_records
        )
        if has_earnings_release:
            unknown_surprises = [
                e for e in eligible_verified_records
                if e.category == EvidenceCategory.EARNINGS_RELEASE and e.expectation_surprise == ExpectationSurprise.UNKNOWN
            ]
            if unknown_surprises:
                unresolved_questions.append(
                    "Analyst consensus expectations unavailable in offline archive; "
                    "quarterly financial statements evaluated under ExpectationSurprise.UNKNOWN."
                )

        # Econometric OLS Model check
        if movement.model_status != "ESTIMATED":
            unresolved_questions.append(
                f"Econometric Market Model status is '{movement.model_status}' ({movement.estimation_sessions_count} valid sessions). "
                "Abnormal return (AR) and Sector-Adjusted Return (SAR) are unestimated."
            )

        # Synthetic proxy survivorship bias check
        if movement.is_survivorship_biased_proxy:
            unresolved_questions.append(
                f"Sector context evaluated using {movement.sector_benchmark_name}; "
                "survivorship bias flagged due to historical peer attrition."
            )

        # Calendar gap check
        if getattr(movement, "has_calendar_gap", False):
            missing_str = ", ".join(movement.missing_intermediate_sessions)
            unresolved_questions.append(
                f"TRADING_CALENDAR_GAP: Missing intermediate exchange trading session(s) [{missing_str}] "
                f"detected between previous stored observation ({movement.prev_stored_date}) and target date ({movement.trading_date}). "
                f"Reaction lag was determined using official NSE trading calendar from announcement effective date."
            )

        # Step 10: Compile Reporting Basis Context (SBIN isolation, etc.)
        reporting_basis_context: Dict[str, Any] = {
            "symbol": symbol,
            "is_standalone_isolated": (symbol == "SBIN"),
            "reporting_basis": "STANDALONE" if symbol == "SBIN" else "CONSOLIDATED"
        }
        if symbol == "SBIN":
            unresolved_questions.append(
                "REPORTING_BASIS_ISOLATION: SBIN operates on a STANDALONE reporting basis; "
                "peer valuation multiples and consolidated disclosures are isolated."
            )

        # Step 11: Build Report Object
        investigation_id = f"EXP_{symbol}_{trading_date.replace('-', '')}"
        report = MovementExplanationReport(
            investigation_id=investigation_id,
            symbol=symbol,
            trading_date=trading_date,
            movement_result=movement,
            primary_hypothesis=primary_hypothesis,
            ranked_hypotheses=candidate_hypotheses,
            eligible_evidence=eligible_verified_records,
            excluded_evidence=excluded_evidence,
            contradicting_evidence=contradicting_evidence,
            unresolved_questions=unresolved_questions,
            reporting_basis_context=reporting_basis_context,
            governance_notice=DATA_GOVERNANCE_NOTICE
        )

        # Step 12: Optional Persistence to SQLite
        if persist_to_db:
            explanation_row = {
                "explanation_id": report.investigation_id,
                "symbol": symbol,
                "trading_date": trading_date,
                "movement_classification": movement.primary_classification.value,
                "stock_return_1d": movement.ret_1d_raw,
                "benchmark_return_1d": movement.benchmark_return,
                "sector_return_1d": movement.sector_return,
                "sector_benchmark_type": movement.sector_benchmark_type.value,
                "sector_benchmark_name": movement.sector_benchmark_name,
                "abnormal_return": movement.abnormal_return,
                "sector_adjusted_return": movement.sector_adjusted_return,
                "volume_ratio": movement.volume_ratio_20d,
                "primary_evidence_id": primary_hypothesis.primary_evidence_id if primary_hypothesis else None,
                "evidence_strength_score": primary_hypothesis.evidence_strength_score if primary_hypothesis else 0.0,
                "confidence_level": primary_hypothesis.confidence_level if primary_hypothesis else "INSUFFICIENT_EVIDENCE",
                "is_contradicted": 1 if (primary_hypothesis and primary_hypothesis.is_contradicted) else 0,
                "contradiction_penalty": primary_hypothesis.contradiction_penalty_applied if primary_hypothesis else 0.0,
                "unexplained_residual_pct": primary_hypothesis.unexplained_residual_pct if primary_hypothesis else None,
                "full_report_json": report.to_json(),
                "generated_at": report.generated_at
            }
            self.db.record_movement_explanation(explanation_row)

        return report
