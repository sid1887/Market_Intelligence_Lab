"""
Market Intelligence Lab: Structured Investigation Report Builder.
Assembles quantitative movement analysis, evidence ranking, timelines,
and diagnostic limitations into multi-format, standalone research reports.
"""

import os
import json
import hashlib
from typing import Dict, Any, List, Optional
from src.storage.database import DatabaseManager
from src.attribution.engine import EvidenceRankingEngine, MovementExplanationReport
from src.evidence.models import (
    MovementClassification,
    EvidenceTier,
    EvidenceCategory,
    EvidenceDirection,
    ExpectationSurprise
)
from src.reporting.investigation_schema import (
    InvestigationOverview,
    ExecutiveSummary,
    MarketMovementSection,
    MechanicalAdjustmentContext,
    TimelineItem,
    ExcludedEvidenceItem,
    TimelineSection,
    RankedHypothesisItem,
    ContradictionSection,
    LimitationsSection,
    FinalAssessmentSection,
    StructuredInvestigationReport,
    REPORT_SCHEMA_VERSION,
    FROZEN_DATASET_ID
)
from src.reporting.visualizer import (
    generate_performance_chart_svg,
    generate_drift_decomposition_svg,
    generate_volume_gauge_svg,
    generate_score_breakdown_svg
)


class InvestigationReportBuilder:
    """
    Constructs comprehensive, reproducible, multi-format investigation reports.
    Consumes verified outputs from MarketMovementAnalyzer and EvidenceRankingEngine.
    """

    def __init__(self, db: DatabaseManager, engine: Optional[EvidenceRankingEngine] = None):
        self.db = db
        self.engine = engine or EvidenceRankingEngine(db)

    def build_report(
        self,
        symbol: str,
        trading_date: str,
        as_of_date: Optional[str] = None,
        persist_to_db: bool = False
    ) -> StructuredInvestigationReport:
        """
        Builds a complete StructuredInvestigationReport enclosing sections A through H.
        Defaults to persist_to_db=False to keep report generation read-only and prevent test/run DB pollution.
        """
        # 1. Run deterministic explanation engine (Phase 4)
        exp_report: MovementExplanationReport = self.engine.explain_movement(
            symbol=symbol,
            trading_date=trading_date,
            as_of_date=as_of_date,
            persist_to_db=persist_to_db
        )
        res = exp_report.movement_result
        primary_hyp = exp_report.primary_hypothesis

        # 2. Retrieve security master metadata
        company_name = symbol
        isin = None
        sector = "Unknown"
        industry = "Unknown"
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute("""
                SELECT company_name, isin, sector, industry 
                FROM securities_master WHERE symbol = ? LIMIT 1;
            """, (symbol,)).fetchone()
            if row:
                company_name, isin, sector, industry = row[0], row[1], row[2], row[3]

        # 3. Check for mechanical corporate action on trading date
        mech_adj = self._detect_mechanical_adjustment(symbol, trading_date, res, exp_report.eligible_evidence)
        is_mech_corporate_action = bool(
            mech_adj and mech_adj.has_mechanical_adjustment and
            primary_hyp and primary_hyp.primary_evidence_id and
            ("BONUS" in primary_hyp.primary_evidence_id or "SPLIT" in primary_hyp.primary_evidence_id or "DIVIDEND" in primary_hyp.primary_evidence_id)
        )

        reporting_basis = exp_report.reporting_basis_context.get("reporting_basis", "CONSOLIDATED")
        is_isolated = exp_report.reporting_basis_context.get("is_standalone_isolated", False)

        # If primary hypothesis is a mechanical corporate action, it explains quoted price discontinuity,
        # not the underlying economic return!
        conf_level = "UNEXPLAINED_MOVEMENT" if is_mech_corporate_action else (
            primary_hyp.confidence_level if primary_hyp else "UNEXPLAINED_MOVEMENT"
        )
        final_outcome = "UNEXPLAINED_PRICE_MOVEMENT" if is_mech_corporate_action else self._determine_final_outcome(res, primary_hyp)

        overview = InvestigationOverview(
            investigation_id=exp_report.investigation_id,
            symbol=symbol,
            company_name=company_name,
            isin=isin,
            trading_date=trading_date,
            sector=sector,
            industry=industry,
            reporting_basis=reporting_basis,
            is_standalone_isolated=is_isolated,
            primary_classification=res.primary_classification.value,
            secondary_classifications=[c.value for c in res.classifications if c != res.primary_classification],
            confidence_level=conf_level,
            final_attribution_outcome=final_outcome
        )

        # 4. Section B: Executive Summary
        exec_summary = self._build_executive_summary(
            symbol, company_name, res, primary_hyp, exp_report, mech_adj, is_mech_corporate_action
        )

        # 5. Section C: Market Movement Analysis
        movement_section = MarketMovementSection(
            price_action={
                "open": res.open,
                "high": res.high,
                "low": res.low,
                "close": res.close,
                "prev_close": res.prev_close,
                "volume": res.volume,
                "ret_1d_raw": res.ret_1d_raw,
                "ret_1d_adj": res.ret_1d_adj,
                "gap_open": res.gap_open,
                "intraday_drift": res.intraday_drift,
                "intraday_range": res.intraday_range,
                "ret_5d": res.ret_5d,
                "ret_20d": res.ret_20d,
                "has_calendar_gap": getattr(res, "has_calendar_gap", False),
                "prev_stored_date": getattr(res, "prev_stored_date", None),
                "prev_stored_close": getattr(res, "prev_stored_close", None),
                "source_prev_close": getattr(res, "source_prev_close", None),
                "source_prev_close_provenance": getattr(res, "source_prev_close_provenance", None),
                "missing_intermediate_sessions": getattr(res, "missing_intermediate_sessions", []),
                "interval_return_raw": getattr(res, "interval_return_raw", None),
                "interval_return_adj": getattr(res, "interval_return_adj", None),
                "interval_sessions_count": getattr(res, "interval_sessions_count", 1),
                "interval_start_date": getattr(res, "interval_start_date", None)
            },
            benchmark_comparison={
                "benchmark_name": "NIFTY 50 (PRI)",
                "benchmark_return": res.benchmark_return,
                "sector_benchmark_type": res.sector_benchmark_type.value,
                "sector_benchmark_name": res.sector_benchmark_name,
                "sector_return": res.sector_return,
                "excess_over_market": (res.ret_1d_adj - res.benchmark_return) if (res.ret_1d_adj is not None and res.benchmark_return is not None) else None,
                "excess_over_sector": res.sector_adjusted_return,
                "is_survivorship_biased_proxy": res.is_survivorship_biased_proxy
            },
            market_model={
                "model_status": res.model_status,
                "alpha": res.alpha,
                "beta": res.beta,
                "r_squared": res.r_squared,
                "residual_std_err": res.residual_std_err,
                "estimation_sessions_count": res.estimation_sessions_count,
                "expected_return": res.expected_return,
                "abnormal_return": res.abnormal_return,
                "t_statistic": res.t_statistic,
                "sector_adjusted_return": res.sector_adjusted_return
            },
            volume_liquidity={
                "volume_ratio_20d": res.volume_ratio_20d,
                "volume_log_zscore_50d": res.volume_log_zscore_50d,
                "is_volume_spike": res.is_volume_spike,
                "is_zero_volume": res.is_zero_volume
            },
            mechanical_adjustment=mech_adj
        )

        # 6. Section D: Timeline Section
        eligible_items: List[TimelineItem] = []
        for e in sorted(exp_report.eligible_evidence, key=lambda x: (x.effective_session_date, x.tier.value)):
            tier_labels = {
                1: "Tier 1: Official Exchange Filing",
                2: "Tier 2: Financial Statement / Corporate Action",
                3: "Tier 3: Sector / Market Movement",
                4: "Tier 4: Authorized Macro Event",
                5: "Tier 5: Unverified Disclosure"
            }
            relevance = self._determine_relevance_note(e, primary_hyp, res)
            eligible_items.append(TimelineItem(
                evidence_id=e.evidence_id,
                event_date=e.event_date,
                broadcast_timestamp=e.broadcast_timestamp,
                effective_session_date=e.effective_session_date,
                tier=int(e.tier),
                tier_label=tier_labels.get(int(e.tier), f"Tier {e.tier}"),
                category=e.category.value,
                direction=e.direction.value,
                headline=e.headline,
                source_identity=e.source_identity,
                source_reference=e.source_reference,
                verification_status=e.verification_status,
                is_pit_eligible=e.is_pit_eligible,
                relevance_note=relevance
            ))

        excluded_items: List[ExcludedEvidenceItem] = []
        for ex in exp_report.excluded_evidence:
            excluded_items.append(ExcludedEvidenceItem(
                evidence_id=ex.get("evidence_id", "UNKNOWN"),
                headline=ex.get("headline", ""),
                tier=int(ex.get("tier", 5)),
                effective_session_date=ex.get("effective_session_date", ""),
                exclusion_reason=ex.get("reason", "EXCLUDED_BY_FILTER")
            ))

        timeline_section = TimelineSection(
            eligible_timeline=eligible_items,
            excluded_evidence=excluded_items
        )

        # 7. Section E: Ranked Explanations
        ranked_items: List[RankedHypothesisItem] = []
        rank_idx = 1
        for h in exp_report.ranked_hypotheses:
            # Exclude mechanical corporate actions from economic explanatory ranking
            if mech_adj and mech_adj.has_mechanical_adjustment and h.primary_evidence_id == mech_adj.corporate_action_evidence_id:
                continue

            is_comp = bool(h.primary_evidence_id and ("EV_MKT_" not in h.primary_evidence_id))
            ev_headline = h.primary_evidence_id or "General Market Drift"
            matching_ev = [e for e in exp_report.eligible_evidence if e.evidence_id == h.primary_evidence_id]
            if matching_ev:
                ev_headline = matching_ev[0].headline

            if h.primary_evidence_id and "EV_VOL_" in h.primary_evidence_id:
                item_cat_type = "ACTIVITY_OBSERVATION"
            else:
                item_cat_type = h.movement_classification.value
            item_conf = h.confidence_level
            item_rationale = h.notes

            ranked_items.append(RankedHypothesisItem(
                rank=rank_idx,
                hypothesis_id=h.hypothesis_id,
                primary_evidence_id=h.primary_evidence_id,
                catalyst_type=item_cat_type,
                headline=ev_headline,
                score_breakdown=self._extract_score_breakdown(h),
                final_score=h.evidence_strength_score,
                confidence_level=item_conf,
                is_contradicted=h.is_contradicted,
                contradiction_penalty=h.contradiction_penalty_applied,
                is_company_specific=is_comp,
                ranking_rationale=item_rationale,
                alternative_hypotheses=h.alternative_hypotheses
            ))
            rank_idx += 1

        # 8. Section F: Contradictions & Alternative Evidence
        contradiction_section = ContradictionSection(
            has_contradictions=len(exp_report.contradicting_evidence) > 0,
            contradicting_evidence=exp_report.contradicting_evidence,
            alternative_explanations=primary_hyp.alternative_hypotheses if primary_hyp else []
        )

        # 9. Section G: Limitations & Governance
        limitations_section = LimitationsSection(
            unresolved_questions=exp_report.unresolved_questions,
            limitations=[
                "Frozen offline research dataset; real-time streaming market data is paused.",
                "Zero-LLM deterministic attribution; score measures evidence strength, not causal certainty.",
                "Consensus estimates must be authenticated; unauthenticated surprise remains UNKNOWN."
            ],
            governance_notice=exp_report.governance_notice
        )

        # 10. Section H: Final Assessment
        final_assessment = FinalAssessmentSection(
            final_outcome=overview.final_attribution_outcome,
            conclusion_statement=self._build_conclusion_statement(
                overview, primary_hyp, res, mech_adj, is_mech_corporate_action
            ),
            provenance_audit_hash="",  # Computed below
            reproducibility_token=f"{symbol}_{trading_date}_{FROZEN_DATASET_ID}"
        )

        # Construct full report and stamp hash
        report = StructuredInvestigationReport(
            overview=overview,
            executive_summary=exec_summary,
            movement_analysis=movement_section,
            timeline=timeline_section,
            ranked_explanations=ranked_items,
            contradictions=contradiction_section,
            limitations=limitations_section,
            final_assessment=final_assessment
        )
        report.final_assessment.provenance_audit_hash = report.compute_audit_hash()
        return report

    def _detect_mechanical_adjustment(
        self,
        symbol: str,
        trading_date: str,
        res: Any,
        eligible_evidence: List[Any]
    ) -> Optional[MechanicalAdjustmentContext]:
        """Detects if a mechanical corporate action (bonus, split, dividend) occurred on this session."""
        matching_ca = None
        for e in eligible_evidence:
            if (e.symbol == symbol and 
                e.effective_session_date == trading_date and 
                e.category in {EvidenceCategory.BONUS_SPLIT_EVENT, EvidenceCategory.DIVIDEND_DECLARATION}):
                matching_ca = e
                break

        ca_row = None
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            ca_row = cursor.execute("""
                SELECT action_type, adjustment_factor, purpose 
                FROM corporate_actions 
                WHERE symbol = ? AND ex_date = ? 
                LIMIT 1;
            """, (symbol, trading_date)).fetchone()

        if not matching_ca and not ca_row:
            return None

        ca_type = ca_row[0] if ca_row else (
            "BONUS" if (matching_ca and "BONUS" in matching_ca.headline.upper()) else (
                "SPLIT" if (matching_ca and "SPLIT" in matching_ca.headline.upper()) else "DIVIDEND"
            )
        )
        factor = float(ca_row[1]) if ca_row and ca_row[1] is not None else 1.0
        ev_id = matching_ca.evidence_id if matching_ca else f"EV_CA_{symbol}_{ca_type}_{trading_date.replace('-', '')}"

        raw_ret = res.ret_1d_raw
        adj_ret = res.ret_1d_adj if res.ret_1d_adj is not None else res.ret_1d_raw

        explanation = (
            f"The quoted raw price change of {raw_ret:+.2%} is mechanically explained by the {ca_type} "
            f"corporate action (adjustment factor {factor:.2f}). This mechanical price adjustment does NOT "
            f"establish positive or negative market sentiment."
        )

        return MechanicalAdjustmentContext(
            has_mechanical_adjustment=True,
            corporate_action_type=ca_type,
            adjustment_factor=factor,
            raw_return_pct=raw_ret,
            adjusted_return_pct=adj_ret,
            corporate_action_evidence_id=ev_id,
            mechanical_explanation=explanation
        )

    def _determine_final_outcome(self, res: Any, primary_hyp: Optional[Any]) -> str:
        """Assigns the standardized final outcome string."""
        if not primary_hyp:
            return "UNEXPLAINED_PRICE_MOVEMENT"
        conf = primary_hyp.confidence_level
        if conf == "HIGH_CONFIDENCE":
            return "STRONGLY_SUPPORTED_EXPLANATION"
        elif conf == "MODERATE_CONFIDENCE":
            return "MODERATELY_SUPPORTED_EXPLANATION"
        elif conf == "LOW_CONFIDENCE":
            return "WEAKLY_SUPPORTED_EXPLANATION"
        elif conf == "UNEXPLAINED_MOVEMENT":
            return "UNEXPLAINED_PRICE_MOVEMENT"
        else:
            return "INSUFFICIENT_EVIDENTIAL_SUPPORT"

    def _build_executive_summary(
        self,
        symbol: str,
        company_name: str,
        res: Any,
        primary_hyp: Optional[Any],
        exp_report: Any,
        mech_adj: Optional[MechanicalAdjustmentContext] = None,
        is_mech_corporate_action: bool = False
    ) -> ExecutiveSummary:
        """Constructs concise narrative and relative performance synthesis."""
        ret = res.ret_1d_adj if res.ret_1d_adj is not None else res.ret_1d_raw
        ret_sign = "rose" if ret > 0 else ("declined" if ret < 0 else "remained flat")
        
        # Narrative
        if mech_adj and mech_adj.has_mechanical_adjustment:
            narrative = (
                f"On {res.trading_date}, {company_name} ({symbol}) quoted at ₹{res.close:,.2f} "
                f"with an unadjusted raw price discontinuity of {res.ret_1d_raw:+.2%} and an adjusted economic return "
                f"of {res.ret_1d_adj:+.2%}. The raw price discontinuity is mechanically explained by the "
                f"{mech_adj.corporate_action_type} corporate action (adjustment factor {mech_adj.adjustment_factor:.2f}). "
                f"However, the underlying economic market return of {res.ret_1d_adj:+.2%} had no independent "
                f"explanatory catalyst and is classified as '{res.primary_classification.value}'."
            )
        elif getattr(res, "has_calendar_gap", False):
            raw_str = f"{res.ret_1d_raw:+.2%}" if res.ret_1d_raw is not None else "N/A"
            int_str = f"{res.interval_return_raw:+.2%}" if res.interval_return_raw is not None else "N/A"
            missing_str = ", ".join(res.missing_intermediate_sessions)
            narrative = (
                f"On {res.trading_date}, {company_name} ({symbol}) closed at ₹{res.close:,.2f} with a single-session "
                f"daily return of {raw_str} (vs. exchange previous close ₹{res.prev_close:,.2f}). "
                f"Across the {res.interval_sessions_count}-session calendar gap since {res.prev_stored_date} "
                f"(missing active session: {missing_str}), the cumulative interval return was {int_str} "
                f"(vs. last stored close ₹{res.prev_stored_close:,.2f}). "
                f"The price action was classified as '{res.primary_classification.value}'."
            )
        else:
            narrative = (
                f"On {res.trading_date}, {company_name} ({symbol}) {ret_sign} {abs(ret):.2%} "
                f"(Close: ₹{res.close:,.2f}) with an unadjusted raw return of {res.ret_1d_raw:+.2%}. "
                f"The movement was classified as '{res.primary_classification.value}'."
            )

        # Relative performance
        sec_ret_str = f"{res.sector_return:+.2%}" if res.sector_return is not None else "N/A"
        if res.benchmark_return is not None:
            rel_summary = (
                f"Against broad-market benchmark NIFTY 50 ({res.benchmark_return:+.2%}), the stock exhibited "
                f"an excess return of {(ret - res.benchmark_return):+.2%}. Compared to sector benchmark "
                f"{res.sector_benchmark_name} ({sec_ret_str}), the sector-adjusted return (SAR) was "
                f"{res.sector_adjusted_return:+.2%}." if res.sector_adjusted_return is not None else "SAR was unavailable."
            )
        else:
            rel_summary = (
                f"Broad-market benchmark NIFTY 50 was unavailable for {res.trading_date}. "
                f"Compared to sector benchmark {res.sector_benchmark_name} ({sec_ret_str}), the sector-adjusted return (SAR) was "
                f"{res.sector_adjusted_return:+.2%}." if res.sector_adjusted_return is not None else "SAR was unavailable."
            )

        # Systematic vs idiosyncratic
        if res.primary_classification in {
            MovementClassification.SECTOR_SYSTEMATIC_SURGE,
            MovementClassification.SECTOR_SYSTEMATIC_DRAG
        }:
            sys_idio = f"The price action was predominantly systematic, aligning with broader sectoral momentum in {res.sector_benchmark_name}."
        elif res.primary_classification == MovementClassification.MARKET_BETA_DRIVEN:
            sys_idio = "The price action was broad-market beta driven, closely tracking the NIFTY 50 PRI index."
        elif res.primary_classification in {
            MovementClassification.IDIOSYNCRATIC_OUTPERFORMANCE,
            MovementClassification.IDIOSYNCRATIC_UNDERPERFORMANCE
        }:
            sys_idio = "The price action was predominantly idiosyncratic, showing significant decoupled abnormal performance from peers."
        else:
            sys_idio = "The price action did not exhibit strong systematic coupling; classified as idiosyncratic or routine drift."

        # Strongest hypothesis summary
        if is_mech_corporate_action and mech_adj:
            strongest = (
                f"Mechanical Price Adjustment: {mech_adj.corporate_action_type} Corporate Action ({mech_adj.corporate_action_evidence_id}). "
                f"Underlying Economic Return: No independent market catalyst identified (UNEXPLAINED_MOVEMENT)."
            )
            sufficiency = "Mechanical price adjustment is fully accounted for by corporate action; evidential support for underlying economic return is INSUFFICIENT."
        elif primary_hyp and primary_hyp.primary_evidence_id:
            strongest = (
                f"The highest-ranked explanatory candidate is '{primary_hyp.primary_evidence_id}' "
                f"with an evidence strength score of {primary_hyp.evidence_strength_score:.1f}/100.0 "
                f"({primary_hyp.confidence_level})."
            )
            sufficiency = "Available evidence provides sufficient corroboration for the candidate explanation." if primary_hyp.confidence_level in {"HIGH_CONFIDENCE", "MODERATE_CONFIDENCE"} else "Evidence is weak or uncorroborated."
        else:
            strongest = "No verified explanatory catalyst met the minimum confidence threshold."
            sufficiency = "Available local evidence is INSUFFICIENT to establish a causal explanation for this price movement."

        return ExecutiveSummary(
            narrative=narrative,
            relative_performance_summary=rel_summary,
            systematic_vs_idiosyncratic=sys_idio,
            strongest_hypothesis_summary=strongest,
            evidence_sufficiency=sufficiency,
            key_uncertainties=exp_report.unresolved_questions
        )

    def _determine_relevance_note(self, evidence: Any, primary_hyp: Optional[Any], movement: Any) -> str:
        """Annotates evidence items with diagnostic relevance context."""
        if primary_hyp and evidence.evidence_id == primary_hyp.primary_evidence_id:
            return "Primary explanatory catalyst selected by attribution engine."
        if evidence.category == EvidenceCategory.VOLUME_LIQUIDITY_SURGE:
            return "Secondary market activity observation (anomalous volume indicator)."
        if evidence.category in {EvidenceCategory.DIVIDEND_DECLARATION, EvidenceCategory.BONUS_SPLIT_EVENT}:
            return "Mechanical corporate action adjustment (ex-date alignment; non-directional)."
        if evidence.entity_type in {"SECTOR", "BENCHMARK"}:
            return f"Systematic benchmark reference for {evidence.symbol}."
        return "Coinciding corporate announcement evaluated by attribution engine."

    def _extract_score_breakdown(self, hypothesis: Any) -> Dict[str, Any]:
        """Parses structured score components from notes or defaults."""
        breakdown = {
            "evidence_strength_score": hypothesis.evidence_strength_score,
            "clamped_total": hypothesis.evidence_strength_score,
            "confidence_level": hypothesis.confidence_level,
            "is_contradicted": hypothesis.is_contradicted,
            "contradiction_penalty": hypothesis.contradiction_penalty_applied,
            "base_score": 0.0,
            "temporal_score": 0.0,
            "directional_score": 0.0,
            "abnormal_return_score": 0.0,
            "volume_score": 0.0,
            "corroboration_score": 0.0
        }
        for part in hypothesis.notes.split(";"):
            part = part.strip()
            if "base score:" in part.lower():
                try:
                    breakdown["base_score"] = float(part.split(":")[-1].strip().replace("+", ""))
                except Exception:
                    pass
            elif "same-session" in part.lower() or "announcement:" in part.lower():
                try:
                    breakdown["temporal_score"] = float(part.split(":")[-1].strip().replace("+", ""))
                except Exception:
                    pass
            elif "direction" in part.lower() and ("aligned" in part.lower() or "points" in part.lower() or "award" in part.lower()):
                try:
                    val_str = part.split(":")[-1].strip().replace("+", "")
                    breakdown["directional_score"] = float(val_str)
                except Exception:
                    pass
            elif "abnormal return" in part.lower() and ":" in part:
                try:
                    val_str = part.split(":")[-1].strip().replace("+", "")
                    breakdown["abnormal_return_score"] = float(val_str)
                except Exception:
                    pass
            elif ("volume surge" in part.lower() or "volume confirmation" in part.lower() or "volume activity" in part.lower()) and ":" in part:
                try:
                    val_str = part.split(":")[-1].strip().replace("+", "")
                    breakdown["volume_score"] = float(val_str)
                except Exception:
                    pass
            elif "corroborat" in part.lower() and ":" in part:
                try:
                    val_str = part.split(":")[-1].strip().replace("+", "")
                    breakdown["corroboration_score"] = float(val_str)
                except Exception:
                    pass
        return breakdown

    def _build_conclusion_statement(
        self,
        overview: Any,
        primary_hyp: Optional[Any],
        res: Any,
        mech_adj: Optional[MechanicalAdjustmentContext] = None,
        is_mech_corporate_action: bool = False
    ) -> str:
        """Constructs definitive conclusion with careful non-causal language."""
        if is_mech_corporate_action and mech_adj:
            return (
                f"The quoted price discontinuity of {res.ret_1d_raw:+.2%} is mechanically explained by the "
                f"{mech_adj.corporate_action_type} corporate action (factor {mech_adj.adjustment_factor:.2f}). "
                f"However, the underlying economic market return ({res.ret_1d_adj:+.2%}) remains an UNEXPLAINED MOVEMENT "
                f"as no verified independent market catalyst was identified in the local evidence store."
            )
        elif not primary_hyp or overview.confidence_level == "UNEXPLAINED_MOVEMENT":
            return (
                f"The price action of {overview.symbol} on {overview.trading_date} remains an "
                f"UNEXPLAINED MOVEMENT. While quantitative market metrics were captured, "
                f"no verified explanatory event in the local evidence store met the minimum evidential threshold."
            )
        elif overview.confidence_level == "HIGH_CONFIDENCE":
            return (
                f"The observed price action is STRONGLY SUPPORTED by candidate catalyst "
                f"'{primary_hyp.primary_evidence_id}'. The evidence exhibits consistent directional alignment, "
                f"temporal proximity, and quantitative compatibility with observed market returns."
            )
        elif overview.confidence_level == "MODERATE_CONFIDENCE":
            return (
                f"The observed price action is MODERATELY SUPPORTED by candidate catalyst "
                f"'{primary_hyp.primary_evidence_id}'. While temporally coincident, unverified expectations "
                f"or absence of independent corroboration preclude a definitive high-confidence conclusion."
            )
        else:
            return (
                f"The observed price action has WEAK OR INSUFFICIENT SUPPORT. The candidate explanation "
                f"does not possess enough verified directional conviction to establish explanatory attribution."
            )

    def render_markdown(self, report: StructuredInvestigationReport) -> str:
        """Renders comprehensive, publication-grade GitHub Flavored Markdown report."""
        ov = report.overview
        ex = report.executive_summary
        mv = report.movement_analysis
        pa = mv.price_action
        bm = mv.benchmark_comparison
        mm = mv.market_model
        vl = mv.volume_liquidity

        md: List[str] = []
        md.append(f"# Stock Movement Investigation Report: {ov.company_name} ({ov.symbol})")
        md.append("")
        md.append(f"> **Investigation ID:** `{ov.investigation_id}`  ")
        md.append(f"> **Trading Date:** `{ov.trading_date}` | **Generated At:** `{ov.generation_timestamp}`  ")
        md.append(f"> **Final Outcome:** **{ov.final_attribution_outcome}** (`{ov.confidence_level}`)  ")
        md.append(f"> **Audit Provenance Hash:** `{report.final_assessment.provenance_audit_hash}`  ")
        md.append("")

        # Section A: Investigation Overview
        md.append("## A. Investigation Overview")
        md.append("")
        md.append("| Attribute | Value | Attribute | Value |")
        md.append("| :--- | :--- | :--- | :--- |")
        md.append(f"| **Symbol** | `{ov.symbol}` | **Company Name** | {ov.company_name} |")
        md.append(f"| **ISIN** | `{ov.isin or 'N/A'}` | **Trading Date** | `{ov.trading_date}` |")
        md.append(f"| **Sector** | {ov.sector} | **Industry** | {ov.industry} |")
        md.append(f"| **Reporting Basis** | `{ov.reporting_basis}` | **Standalone Isolated?** | `{'YES' if ov.is_standalone_isolated else 'No'}` |")
        md.append(f"| **Primary Classification** | `{ov.primary_classification}` | **Secondary Tags** | `{', '.join(ov.secondary_classifications) if ov.secondary_classifications else 'None'}` |")
        md.append(f"| **Confidence Level** | **{ov.confidence_level}** | **Dataset Benchmark** | `{ov.dataset_identifier}` |")
        md.append("")

        # Section B: Executive Summary
        md.append("## B. Executive Summary")
        md.append("")
        md.append(f"{ex.narrative}")
        md.append("")
        md.append(f"- **Relative Performance:** {ex.relative_performance_summary}")
        md.append(f"- **Systematic Coupling:** {ex.systematic_vs_idiosyncratic}")
        md.append(f"- **Strongest Hypothesis:** {ex.strongest_hypothesis_summary}")
        md.append(f"- **Evidential Sufficiency:** {ex.evidence_sufficiency}")
        md.append("")
        md.append(f"> [!NOTE]\n> {ex.score_is_heuristic_disclaimer}")
        md.append("")

        # Section C: Market Movement Analysis
        md.append("## C. Quantitative Market Movement Analysis")
        md.append("")
        md.append("### 1. Price Action & Return Structure")
        md.append("")
        md.append("| Metric | Value | Baseline / Context |")
        md.append("| :--- | :---: | :--- |")
        md.append(f"| **Close Price** | `₹{pa['close']:,.2f}` | Open: `₹{pa['open']:,.2f}`, High: `₹{pa['high']:,.2f}`, Low: `₹{pa['low']:,.2f}` |")
        raw_ret_str = f"{pa['ret_1d_raw']:+.2%}" if pa.get('ret_1d_raw') is not None else "N/A"
        adj_ret_str = f"{pa['ret_1d_adj']:+.2%}" if pa.get('ret_1d_adj') is not None else "N/A"
        gap_open_str = f"{pa['gap_open']:+.2%}" if pa.get('gap_open') is not None else "N/A"
        md.append(f"| **Raw 1-Day Return** | `{raw_ret_str}` | Close-to-close unadjusted change |")
        md.append(f"| **Adjusted 1-Day Return** | `{adj_ret_str}` | Corporate-action adjusted price return |")
        md.append(f"| **Overnight Gap Open** | `{gap_open_str}` | Previous close to session open |")
        md.append(f"| **Intraday Drift** | `{pa['intraday_drift']:+.2%}` | Session open to session close |")
        if pa.get('has_calendar_gap'):
            int_raw_str = f"{pa['interval_return_raw']:+.2%}" if pa.get('interval_return_raw') is not None else "N/A"
            int_sessions = pa.get('interval_sessions_count', 1)
            prev_d = pa.get('prev_stored_date', 'N/A')
            prev_c = pa.get('prev_stored_close', 0.0)
            missing = ", ".join(pa.get('missing_intermediate_sessions', []))
            md.append(f"| **Multi-Session Interval Return** | `{int_raw_str}` | Span: {int_sessions} sessions from {prev_d} (Last DB close ₹{prev_c:,.2f}) |")
            md.append(f"| **Exchange Reference Close** | `₹{pa.get('prev_close', 0.0):,.2f}` | Source: {pa.get('source_prev_close_provenance', 'exchange')} (Missing active session: {missing}) |")
        if pa['ret_5d'] is not None:
            md.append(f"| **5-Session Return** | `{pa['ret_5d']:+.2%}` | Preceding 5 trading days momentum |")
        if pa['ret_20d'] is not None:
            md.append(f"| **20-Session Return** | `{pa['ret_20d']:+.2%}` | Preceding 20 trading days momentum |")
        md.append("")

        md.append("### 2. Benchmark & Econometric Market Model")
        md.append("")
        md.append("| Metric | Value | Econometric Interpretation |")
        md.append("| :--- | :---: | :--- |")
        bm_ret_str = f"{bm['benchmark_return']:+.2%}" if bm['benchmark_return'] is not None else "N/A"
        md.append(f"| **NIFTY 50 PRI Return** | `{bm_ret_str}` | Broad-market baseline return ($R_{{m,t}}$) |")
        sec_ret_str = f"{bm['sector_return']:+.2%}" if bm['sector_return'] is not None else "N/A"
        md.append(f"| **Sector Return** | `{sec_ret_str}` | {bm['sector_benchmark_name']} ({bm['sector_benchmark_type']}) |")
        
        ar_str = f"{mm['abnormal_return']:+.2%}" if mm['abnormal_return'] is not None else "Unavailable"
        t_str = f"{mm['t_statistic']:.2f}" if mm['t_statistic'] is not None else "N/A"
        md.append(f"| **Abnormal Return ($AR_t$)** | `{ar_str}` | OLS Market Model excess return ($t = {t_str}$) |")
        
        sar_str = f"{mm['sector_adjusted_return']:+.2%}" if mm['sector_adjusted_return'] is not None else "N/A"
        md.append(f"| **Sector-Adjusted Return ($SAR_t$)** | `{sar_str}` | Net outperformance over sector benchmark |")
        
        alpha_str = f"{mm['alpha']:.5f}" if mm['alpha'] is not None else "N/A"
        beta_str = f"{mm['beta']:.2f}" if mm['beta'] is not None else "N/A"
        md.append(f"| **Market Beta ($\\beta$) & Alpha ($\\alpha$)** | `β={beta_str}, α={alpha_str}` | OLS Market Model coefficients ({mm['estimation_sessions_count']} sessions) |")
        md.append("")

        md.append("### 3. Volume & Liquidity Anomalies")
        md.append("")
        vr_str = f"{vl['volume_ratio_20d']:.2f}x" if vl['volume_ratio_20d'] is not None else "N/A"
        z_str = f"{vl['volume_log_zscore_50d']:+.2f}" if vl['volume_log_zscore_50d'] is not None else "N/A"
        md.append(f"- **Volume Ratio (vs 20d SMA):** `{vr_str}`")
        md.append(f"- **Log Volume Z-Score (vs 50d SMA):** `{z_str}`")
        md.append(f"- **Volume Spike Flag:** `{'YES (ANOMALOUS ACTIVITY)' if vl['is_volume_spike'] else 'No (Normal / Muted Activity)'}`")
        md.append("")

        if mv.mechanical_adjustment and mv.mechanical_adjustment.has_mechanical_adjustment:
            m_adj = mv.mechanical_adjustment
            md.append("### 4. Mechanical Corporate Action Price Adjustment")
            md.append("")
            md.append("| Attribute | Value | Context / Meaning |")
            md.append("| :--- | :--- | :--- |")
            md.append(f"| **Corporate Action Type** | `{m_adj.corporate_action_type}` | Mechanical quoted price adjustment |")
            md.append(f"| **Adjustment Factor** | `{m_adj.adjustment_factor:.2f}` | Recalculation factor applied on ex-date |")
            md.append(f"| **Quoted Raw Price Return** | `{m_adj.raw_return_pct:+.2%}` | Close-to-close unadjusted change |")
            md.append(f"| **Underlying Economic Return** | `{m_adj.adjusted_return_pct:+.2%}` | Corporate-action-adjusted price return |")
            md.append(f"| **Evidence ID** | `{m_adj.corporate_action_evidence_id}` | Verified corporate action record |")
            md.append(f"| **Sentiment / Direction** | `NON-DIRECTIONAL` | Mechanical adjustment does not establish market sentiment |")
            md.append("")
            md.append(f"> [!NOTE]\n> {m_adj.disclaimer}")
            md.append("")

        # Section D: Event and Evidence Timeline
        md.append("## D. Event and Evidence Timeline")
        md.append("")
        md.append("### 1. Eligible Coinciding Evidence (Chronological)")
        md.append("")
        if report.timeline.eligible_timeline:
            md.append("| Date / Session | Evidence ID | Category | Direction | Tier | Headline |")
            md.append("| :--- | :--- | :---: | :---: | :---: | :--- |")
            for item in report.timeline.eligible_timeline:
                md.append(f"| `{item.effective_session_date}` | `{item.evidence_id}` | `{item.category}` | `{item.direction}` | T{item.tier} | {item.headline} |")
        else:
            md.append("*No eligible verified evidence records identified for this event window.*")
        md.append("")

        md.append("### 2. Excluded Candidate Records & Audit Trail")
        md.append("")
        if report.timeline.excluded_evidence:
            md.append("| Evidence ID | Tier | Effective Session | Headline | Exclusion Reason |")
            md.append("| :--- | :---: | :---: | :--- | :--- |")
            for ex_item in report.timeline.excluded_evidence:
                md.append(f"| `{ex_item.evidence_id}` | T{ex_item.tier} | `{ex_item.effective_session_date}` | {ex_item.headline} | `{ex_item.exclusion_reason}` |")
        else:
            md.append("*No candidate records were excluded by filters.*")
        md.append("")

        # Section E: Ranked Candidate Explanations
        md.append("## E. Ranked Candidate Explanations")
        md.append("")
        if report.ranked_explanations:
            md.append("| Rank | Evidence ID / Candidate | Category / Role | Score | Confidence | Type | Contradicted? |")
            md.append("| :---: | :--- | :---: | :---: | :---: | :---: | :---: |")
            for rk in report.ranked_explanations:
                ev_str = rk.primary_evidence_id or "NONE"
                type_str = "Company-Specific" if rk.is_company_specific else "Systematic"
                contra_str = f"YES (-{rk.contradiction_penalty:.0f})" if rk.is_contradicted else "No"
                md.append(f"| **{rk.rank}** | `{ev_str}` | `{rk.catalyst_type}` | `{rk.final_score:.1f}` | **{rk.confidence_level}** | {type_str} | {contra_str} |")
            md.append("")
            md.append("#### Primary Explanation Rationale:")
            md.append(f"{report.ranked_explanations[0].ranking_rationale}")
        else:
            if report.movement_analysis.mechanical_adjustment and report.movement_analysis.mechanical_adjustment.has_mechanical_adjustment:
                md.append("*No independent candidate explanations met the minimum score threshold for the underlying economic return. (Quoted price discontinuity is fully accounted for under Section C.4: Mechanical Corporate Action Price Adjustment).*")
            else:
                md.append("*No candidate explanations met the minimum score threshold.*")
        md.append("")

        # Section F: Contradictions & Alternative Evidence
        md.append("## F. Contradictory Evidence & Alternative Hypotheses")
        md.append("")
        if report.contradictions.has_contradictions:
            md.append("| Conflicting Evidence ID | Direction | Observed Return | Conflict Description | Penalty |")
            md.append("| :--- | :---: | :---: | :--- | :---: |")
            for c in report.contradictions.contradicting_evidence:
                md.append(f"| `{c.get('evidence_id')}` | `{c.get('direction')}` | `{pa['ret_1d_adj']:+.2%}` | {c.get('conflict_reason')} | `-30.0 pts` |")
        else:
            md.append("*No contradictory evidence detected for this session.*")
        md.append("")

        # Section G: Gaps, Limitations & Governance
        md.append("## G. Data Gaps, Methodological Limitations & Governance")
        md.append("")
        if report.limitations.unresolved_questions:
            md.append("### Diagnostic Notes & Data Gaps:")
            for q in report.limitations.unresolved_questions:
                md.append(f"- {q}")
            md.append("")

        md.append("### Methodological Limitations:")
        for lim in report.limitations.limitations:
            md.append(f"- {lim}")
        md.append("")

        # Section H: Final Assessment
        md.append("## H. Final Assessment & Audit Stamp")
        md.append("")
        md.append(f"> **Final Assessment:** **{report.final_assessment.final_outcome}**  ")
        md.append(f"> **Conclusion:** {report.final_assessment.conclusion_statement}  ")
        md.append(f"> **Audit Provenance Hash:** `{report.final_assessment.provenance_audit_hash}`  ")
        md.append(f"> **Dataset / Checkpoint:** `{ov.dataset_identifier}`  ")
        md.append("")
        md.append("> *Note on Provenance Hash:* The SHA-256 audit hash cryptographically protects the canonical structured analytical payload (symbols, timestamps, classifications, price action, and ranked hypothesis scores). It ensures reproducibility and tamper-detection of analytical results across research environments independently of presentation markup or whitespace.")
        md.append("")
        md.append("---")
        md.append(f"*{report.limitations.governance_notice}*")
        md.append("")

        return "\n".join(md)

    def render_html(self, report: StructuredInvestigationReport) -> str:
        """
        Renders a self-contained, publication-grade HTML report with modern CSS styling,
        clean typography, and embedded offline SVG graphics. Zero network dependencies.
        """
        ov = report.overview
        ex = report.executive_summary
        mv = report.movement_analysis
        pa = mv.price_action
        bm = mv.benchmark_comparison
        mm = mv.market_model
        vl = mv.volume_liquidity

        # Generate SVGs
        perf_svg = generate_performance_chart_svg(
            stock_symbol=ov.symbol,
            stock_return=pa["ret_1d_adj"] if pa["ret_1d_adj"] is not None else pa["ret_1d_raw"],
            benchmark_name="NIFTY 50 (PRI)",
            benchmark_return=bm["benchmark_return"],
            sector_name=bm["sector_benchmark_name"],
            sector_return=bm["sector_return"]
        )

        drift_svg = generate_drift_decomposition_svg(
            gap_open=pa["gap_open"],
            intraday_drift=pa["intraday_drift"],
            total_adj_return=pa["ret_1d_adj"] if pa["ret_1d_adj"] is not None else pa["ret_1d_raw"]
        )

        vol_svg = generate_volume_gauge_svg(
            volume_ratio=vl["volume_ratio_20d"],
            z_score=vl["volume_log_zscore_50d"],
            is_spike=vl["is_volume_spike"]
        )

        top_breakdown = report.ranked_explanations[0].score_breakdown if report.ranked_explanations else {}
        score_svg = generate_score_breakdown_svg(top_breakdown)

        # Precompute formatted strings
        bm_ret_str = f"{bm['benchmark_return']:+.2%}" if bm['benchmark_return'] is not None else "N/A"
        sec_ret_str = f"{bm['sector_return']:+.2%}" if bm['sector_return'] is not None else "N/A"
        ar_str = f"{mm['abnormal_return']:+.2%}" if mm['abnormal_return'] is not None else "Unavailable"
        t_str = f"{mm['t_statistic']:.2f}" if mm['t_statistic'] is not None else "N/A"
        sar_str = f"{mm['sector_adjusted_return']:+.2%}" if mm['sector_adjusted_return'] is not None else "N/A"
        vr_str = f"{vl['volume_ratio_20d']:.2f}x" if vl['volume_ratio_20d'] is not None else "N/A"
        z_str = f"{vl['volume_log_zscore_50d']:+.2f}" if vl['volume_log_zscore_50d'] is not None else "N/A"
        ret_1d_adj_str = f"{pa['ret_1d_adj']:+.2%}" if pa.get('ret_1d_adj') is not None else "N/A"
        raw_ret_str = f"{pa['ret_1d_raw']:+.2%}" if pa.get('ret_1d_raw') is not None else "N/A"
        prev_close_str = f"₹{pa['prev_close']:,.2f}" if pa.get('prev_close') is not None else "N/A"

        cal_gap_row = ""
        if pa.get("has_calendar_gap"):
            int_raw_str = f"{pa['interval_return_raw']:+.2%}" if pa.get('interval_return_raw') is not None else "N/A"
            missing = ", ".join(pa.get("missing_intermediate_sessions", []))
            cal_gap_row = f"        <tr><td><strong>Multi-Session Interval Return</strong></td><td><strong>{int_raw_str}</strong></td><td>Across {pa.get('interval_sessions_count', 1)} sessions from {pa.get('prev_stored_date')} (Missing: {missing})</td></tr>\n"

        # Confidence Badge Color
        conf_colors = {
            "HIGH_CONFIDENCE": ("#16a34a", "#dcfce7"),      # Green
            "MODERATE_CONFIDENCE": ("#2563eb", "#dbeafe"),  # Blue
            "LOW_CONFIDENCE": ("#d97706", "#fef3c7"),       # Amber
            "UNEXPLAINED_MOVEMENT": ("#dc2626", "#fee2e2"), # Red
            "INSUFFICIENT_EVIDENCE": ("#475569", "#f1f5f9") # Slate
        }
        text_col, bg_col = conf_colors.get(ov.confidence_level, ("#475569", "#f1f5f9"))

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Investigation Report: {ov.company_name} ({ov.symbol}) - {ov.trading_date}</title>
<style>
  :root {{
    --primary: #0f172a;
    --text: #1e293b;
    --text-muted: #64748b;
    --border: #e2e8f0;
    --card-bg: #ffffff;
    --bg: #f8fafc;
    --accent: #2563eb;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: var(--text);
    background-color: var(--bg);
    line-height: 1.5;
    padding: 32px 16px;
  }}
  .container {{
    max-width: 960px;
    margin: 0 auto;
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
    padding: 36px 44px;
  }}
  header {{
    border-bottom: 2px solid var(--border);
    padding-bottom: 24px;
    margin-bottom: 28px;
  }}
  .badge {{
    display: inline-block;
    padding: 4px 12px;
    border-radius: 9999px;
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  h1 {{ font-size: 26px; color: var(--primary); margin-top: 12px; margin-bottom: 6px; }}
  .meta-sub {{ color: var(--text-muted); font-size: 14px; font-weight: 500; }}
  section {{ margin-bottom: 32px; }}
  h2 {{
    font-size: 18px;
    color: var(--primary);
    border-bottom: 1px solid var(--border);
    padding-bottom: 8px;
    margin-bottom: 16px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  h3 {{ font-size: 15px; color: #334155; margin: 16px 0 8px 0; }}
  p {{ margin-bottom: 12px; font-size: 14.5px; color: #334155; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 18px;
    font-size: 13.5px;
  }}
  th, td {{
    padding: 9px 12px;
    text-align: left;
    border-bottom: 1px solid var(--border);
  }}
  th {{ background-color: #f1f5f9; color: #334155; font-weight: 600; }}
  tr:hover {{ background-color: #f8fafc; }}
  .chart-grid {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 16px;
    margin-bottom: 20px;
  }}
  .callout {{
    background-color: #eff6ff;
    border-left: 4px solid #3b82f6;
    padding: 12px 16px;
    border-radius: 4px;
    margin: 16px 0;
    font-size: 13.5px;
    color: #1e3a8a;
  }}
  .warning-callout {{
    background-color: #fef2f2;
    border-left: 4px solid #ef4444;
    padding: 12px 16px;
    border-radius: 4px;
    margin: 16px 0;
    font-size: 13.5px;
    color: #991b1b;
  }}
  .hash-box {{
    background: #f1f5f9;
    padding: 10px 14px;
    border-radius: 4px;
    font-family: monospace;
    font-size: 12px;
    word-break: break-all;
    color: #475569;
  }}
  footer {{
    border-top: 1px solid var(--border);
    padding-top: 16px;
    font-size: 12px;
    color: var(--text-muted);
    text-align: center;
  }}
</style>
</head>
<body>
<div class="container">
  <header>
    <div style="display:flex; justify-content:space-between; align-items:center;">
      <span class="badge" style="color:{text_col}; background-color:{bg_col};">{ov.confidence_level}</span>
      <span style="font-size:12px; color:var(--text-muted); font-family:monospace;">ID: {ov.investigation_id}</span>
    </div>
    <h1>{ov.company_name} ({ov.symbol})</h1>
    <div class="meta-sub">
      Trading Date: <strong>{ov.trading_date}</strong> | Sector: <strong>{ov.sector}</strong> | Primary Classification: <strong>{ov.primary_classification}</strong>
    </div>
  </header>

  <!-- Section A & B: Executive Summary -->
  <section>
    <h2>Executive Summary</h2>
    <p>{ex.narrative}</p>
    <p><strong>Relative Performance:</strong> {ex.relative_performance_summary}</p>
    <p><strong>Systematic Coupling:</strong> {ex.systematic_vs_idiosyncratic}</p>
    <p><strong>Strongest Hypothesis:</strong> {ex.strongest_hypothesis_summary}</p>
    <div class="callout">
      <strong>Methodological Note:</strong> {ex.score_is_heuristic_disclaimer}
    </div>
  </section>

  <!-- Visual Evidence Charts -->
  <section>
    <h2>Visual Movement Decomposition</h2>
    <div class="chart-grid">
      <div>{perf_svg}</div>
      <div>{drift_svg}</div>
      <div>{vol_svg}</div>
      <div>{score_svg}</div>
    </div>
  </section>

  <!-- Section C: Quantitative Metrics -->
  <section>
    <h2>Market Movement Details</h2>
    <table>
      <thead>
        <tr><th>Metric</th><th>Value</th><th>Context</th></tr>
      </thead>
      <tbody>
        <tr><td><strong>Adjusted Return</strong></td><td><strong>{ret_1d_adj_str}</strong></td><td>Corporate action adjusted</td></tr>
        <tr><td><strong>Raw Price Return</strong></td><td>{raw_ret_str}</td><td>Close: ₹{pa['close']:,.2f} vs Prev: {prev_close_str}</td></tr>
{cal_gap_row}        <tr><td><strong>NIFTY 50 PRI Return</strong></td><td>{bm_ret_str}</td><td>Official Market Benchmark</td></tr>
        <tr><td><strong>Sector Return</strong></td><td>{sec_ret_str}</td><td>{bm['sector_benchmark_name']} ({bm['sector_benchmark_type']})</td></tr>
        <tr><td><strong>Abnormal Return (AR)</strong></td><td>{ar_str}</td><td>OLS Model status: {mm['model_status']} (t = {t_str})</td></tr>
        <tr><td><strong>Sector-Adjusted Return (SAR)</strong></td><td>{sar_str}</td><td>Net excess over sector</td></tr>
        <tr><td><strong>Volume Ratio (20d)</strong></td><td>{vr_str}</td><td>Spike Flag: {'YES' if vl['is_volume_spike'] else 'No'} (Z={z_str})</td></tr>
      </tbody>
    </table>"""

        if mv.mechanical_adjustment and mv.mechanical_adjustment.has_mechanical_adjustment:
            m_adj = mv.mechanical_adjustment
            html += f"""
    <h3 style="margin-top:20px;">Mechanical Corporate Action Price Adjustment</h3>
    <table>
      <thead><tr><th>Attribute</th><th>Value</th><th>Context / Semantic Interpretation</th></tr></thead>
      <tbody>
        <tr><td><strong>Corporate Action Type</strong></td><td>{m_adj.corporate_action_type}</td><td>Mechanical quoted price recalculation</td></tr>
        <tr><td><strong>Adjustment Factor</strong></td><td><strong>{m_adj.adjustment_factor:.2f}</strong></td><td>Exchange ex-date adjustment factor</td></tr>
        <tr><td><strong>Quoted Raw Return</strong></td><td><strong>{m_adj.raw_return_pct:+.2%}</strong></td><td>Unadjusted close-to-close quoted price change</td></tr>
        <tr><td><strong>Underlying Economic Return</strong></td><td><strong>{m_adj.adjusted_return_pct:+.2%}</strong></td><td>Adjusted economic return evaluated by attribution engine</td></tr>
        <tr><td><strong>Evidence ID</strong></td><td><code>{m_adj.corporate_action_evidence_id}</code></td><td>Verified corporate action record</td></tr>
        <tr><td><strong>Sentiment / Direction</strong></td><td><code>NON-DIRECTIONAL</code></td><td>Mechanical corporate action does not establish market sentiment</td></tr>
      </tbody>
    </table>
    <div class="callout" style="background:#f1f5f9; border-left-color:#64748b; color:#334155;">
      <strong>Mechanical Adjustment Notice:</strong> {m_adj.disclaimer}
    </div>"""

        html += """
  </section>

  <!-- Section D: Evidence Timeline -->
  <section>
    <h2>Chronological Evidence Timeline</h2>
    <table>
      <thead>
        <tr><th>Session Date</th><th>Evidence ID</th><th>Category</th><th>Direction</th><th>Tier</th><th>Headline</th></tr>
      </thead>
      <tbody>"""

        for item in report.timeline.eligible_timeline:
            html += f"""
        <tr>
          <td><code>{item.effective_session_date}</code></td>
          <td><code>{item.evidence_id}</code></td>
          <td>{item.category}</td>
          <td><strong>{item.direction}</strong></td>
          <td>T{item.tier}</td>
          <td>{item.headline}</td>
        </tr>"""

        html += """
      </tbody>
    </table>"""

        if report.timeline.excluded_evidence:
            html += """
    <h3>Excluded Evidence Records (Audit Trail)</h3>
    <table>
      <thead><tr><th>Evidence ID</th><th>Tier</th><th>Headline</th><th>Exclusion Reason</th></tr></thead>
      <tbody>"""
            for ex_item in report.timeline.excluded_evidence:
                html += f"""
        <tr>
          <td><code>{ex_item.evidence_id}</code></td>
          <td>T{ex_item.tier}</td>
          <td>{ex_item.headline}</td>
          <td><span style="color:#b91c1c; font-family:monospace; font-size:12px;">{ex_item.exclusion_reason}</span></td>
        </tr>"""
            html += "</tbody></table>"

        html += """
  </section>

  <!-- Section E: Ranked Explanations -->
  <section>
    <h2>Ranked Explanatory Hypotheses</h2>"""

        if report.ranked_explanations:
            html += """
    <table>
      <thead>
        <tr><th>Rank</th><th>Primary Evidence</th><th>Category / Role</th><th>Score</th><th>Confidence</th><th>Type</th><th>Contradicted</th></tr>
      </thead>
      <tbody>"""

            for rk in report.ranked_explanations:
                ev_str = rk.primary_evidence_id or "NONE"
                type_str = "Company-Specific" if rk.is_company_specific else "Systematic"
                contra_str = f"YES (-{rk.contradiction_penalty:.0f})" if rk.is_contradicted else "No"
                html += f"""
        <tr>
          <td><strong>{rk.rank}</strong></td>
          <td><code>{ev_str}</code></td>
          <td>{rk.catalyst_type}</td>
          <td><strong>{rk.final_score:.1f}</strong></td>
          <td><span class="badge" style="font-size:11px; padding:2px 8px;">{rk.confidence_level}</span></td>
          <td>{type_str}</td>
          <td>{contra_str}</td>
        </tr>"""

            html += f"""
      </tbody>
    </table>
    <div class="callout" style="background:#f8fafc; border-left-color:#64748b; color:#334155;">
      <strong>Attribution Rationale:</strong> {report.ranked_explanations[0].ranking_rationale}
    </div>"""
        else:
            no_exp_msg = "No independent candidate explanations met the minimum score threshold for the underlying economic return."
            if report.movement_analysis.mechanical_adjustment and report.movement_analysis.mechanical_adjustment.has_mechanical_adjustment:
                no_exp_msg += " (Quoted price discontinuity is fully accounted for under Section C.4: Mechanical Corporate Action Price Adjustment)."
            html += f"""
    <p style="color:#64748b; font-style:italic; padding:12px 0;">{no_exp_msg}</p>
    <div class="callout" style="background:#f8fafc; border-left-color:#64748b; color:#334155;">
      <strong>Attribution Rationale:</strong> No independent candidate explanation met the evidential threshold for this session.
    </div>"""

        html += """
  </section>"""

        if report.contradictions.has_contradictions:
            html += """
  <!-- Section F: Contradictory Evidence -->
  <section>
    <h2>Contradictory Evidence</h2>
    <div class="warning-callout">
      <strong>Directional Conflict Detected:</strong> Contradictory evidence is retained and penalized (-30.0 pts) under project policy.
    </div>
    <table>
      <thead><tr><th>Evidence ID</th><th>Direction</th><th>Conflict Rationale</th><th>Penalty</th></tr></thead>
      <tbody>"""
            for c in report.contradictions.contradicting_evidence:
                html += f"""
        <tr>
          <td><code>{c.get('evidence_id')}</code></td>
          <td><strong>{c.get('direction')}</strong></td>
          <td>{c.get('conflict_reason')}</td>
          <td>-30.0 pts</td>
        </tr>"""
            html += "</tbody></table></section>"

        html += f"""
  <!-- Section G & H: Limitations & Assessment -->
  <section>
    <h2>Limitations &amp; Final Assessment</h2>
    <div style="margin-bottom:16px;">
      <strong>Final Outcome:</strong> <span style="font-size:16px; font-weight:700; color:{text_col};">{report.final_assessment.final_outcome}</span>
    </div>
    <p>{report.final_assessment.conclusion_statement}</p>
    
    <div style="margin-top:16px;">
      <p style="font-size:12px; color:var(--text-muted); margin-bottom:4px;">AUDIT PROVENANCE HASH (SHA-256):</p>
      <div class="hash-box">{report.final_assessment.provenance_audit_hash}</div>
      <p style="font-size:11px; color:var(--text-muted); margin-top:4px;">Cryptographically protects canonical analytical payload (symbol, date, classifications, price action, ranked scores). Independent of presentation formatting.</p>
    </div>
  </section>

  <footer>
    <p>{report.limitations.governance_notice}</p>
    <p style="margin-top:4px;">Schema Version: {REPORT_SCHEMA_VERSION} | Dataset: {FROZEN_DATASET_ID}</p>
  </footer>
</div>
</body>
</html>"""
        return html

    def export_investigation_bundle(
        self,
        report: StructuredInvestigationReport,
        base_output_dir: str = "reports/investigations"
    ) -> Dict[str, str]:
        """
        Exports JSON, Markdown, and Standalone HTML formats into dedicated folder.
        """
        sub_dir_name = f"{report.overview.symbol}_{report.overview.trading_date.replace('-', '')}"
        target_dir = os.path.join(base_output_dir, sub_dir_name)
        os.makedirs(target_dir, exist_ok=True)

        json_path = os.path.join(target_dir, "report.json")
        md_path = os.path.join(target_dir, "report.md")
        html_path = os.path.join(target_dir, "report.html")

        # 1. JSON
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(report.to_json(indent=2))

        # 2. Markdown
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(self.render_markdown(report))

        # 3. HTML
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(self.render_html(report))

        return {
            "dir": target_dir,
            "json": json_path,
            "md": md_path,
            "html": html_path
        }
