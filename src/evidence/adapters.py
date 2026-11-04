"""
Market Intelligence Lab: Unified Evidence Source Adapters.
Transforms local SQLite tables (disclosures, corporate actions, financial statements,
index movements, and volume anomalies) into normalized EvidenceRecord objects.

Strict Compliance & Governance:
- Operates exclusively against local SQLite database and authorized local files.
- Zero network scraping, external polling, or unverified synthesis.
- Preserves distinct identities (e.g. multiple dividends on same ex-date, restatements).
- Enforces verification_status controls and point-in-time eligibility.
- Classifies mechanical ex-date price changes as NEUTRAL.
"""

import re
import json
import datetime
from typing import List, Dict, Any, Optional, Tuple, Set

from src.storage.database import DatabaseManager
from src.evidence.models import (
    EvidenceTier,
    EvidenceCategory,
    EvidenceDirection,
    ExpectationSurprise,
    ReportingBasis,
    EvidenceRecord
)


class CorporateDisclosuresAdapter:
    """
    Adapts corporate_disclosures into Tier 1 (or Tier 5 if unverified) EvidenceRecords.
    Preserves exact broadcast timestamps, effective session alignment, and SEBI categories.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    def extract_evidence(
        self,
        symbol: Optional[str] = None,
        as_of_date: Optional[str] = None
    ) -> List[EvidenceRecord]:
        disclosures = self.db.get_corporate_disclosures(symbol=symbol)
        records: List[EvidenceRecord] = []

        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        for d in disclosures:
            disc_id = d["disclosure_id"]
            sym = d["symbol"]
            eff_session = d["effective_session_date"]
            b_ts = d.get("broadcast_timestamp")
            cat_raw = d.get("category", "OTHER").upper()
            ver_status = d.get("verification_status", "PENDING_VERIFICATION").upper()
            subject = d.get("subject", "")
            summary = d.get("details_summary", "")

            # PIT filtering: if as_of_date is provided, ignore disclosures effective after as_of_date
            if as_of_date and eff_session > as_of_date:
                continue

            # Tier assignment: VERIFIED -> Tier 1; PENDING / SOURCE_UNVERIFIED -> Tier 5
            if ver_status == "VERIFIED":
                tier = EvidenceTier.TIER_1_OFFICIAL_FILING
            else:
                tier = EvidenceTier.TIER_5_UNVERIFIED

            # Category mapping
            if "EARNING" in cat_raw or "RESULT" in cat_raw:
                category = EvidenceCategory.EARNINGS_RELEASE
            elif "DIVIDEND" in cat_raw:
                category = EvidenceCategory.DIVIDEND_DECLARATION
            elif any(term in cat_raw for term in ["BONUS", "SPLIT"]):
                category = EvidenceCategory.BONUS_SPLIT_EVENT
            else:
                category = EvidenceCategory.BOARD_MEETING_OUTCOME

            # Directional evaluation
            # Routine meeting notices/schedules are strictly NEUTRAL
            if any(term in subject.upper() for term in ["SCHEDULE", "INTIMATION OF BOARD MEETING"]):
                direction = EvidenceDirection.NEUTRAL
            elif category == EvidenceCategory.EARNINGS_RELEASE:
                # If operating margin or cc growth is verified and strongly positive
                qoq = d.get("revenue_growth_qoq_cc")
                op_margin = d.get("operating_margin_pct")
                if qoq is not None and qoq > 1.5:
                    direction = EvidenceDirection.POSITIVE
                elif qoq is not None and qoq < -1.5:
                    direction = EvidenceDirection.NEGATIVE
                else:
                    direction = EvidenceDirection.NEUTRAL
            else:
                direction = EvidenceDirection.NEUTRAL

            # Event date extraction (YYYY-MM-DD)
            event_d = b_ts[:10] if b_ts and len(b_ts) >= 10 else eff_session

            details_dict = {
                "disclosure_id": disc_id,
                "category": cat_raw,
                "subject": subject,
                "details_summary": summary,
                "audit_status": d.get("audit_status"),
                "dividend_declared": d.get("dividend_declared"),
                "operating_margin_pct": d.get("operating_margin_pct"),
                "revenue_inr_crore": d.get("revenue_inr_crore"),
                "revenue_growth_yoy_cc": d.get("revenue_growth_yoy_cc"),
                "revenue_growth_qoq_cc": d.get("revenue_growth_qoq_cc"),
                "revenue_growth_yoy_reported": d.get("revenue_growth_yoy_reported"),
                "source_url": d.get("source_url"),
                "source_timestamp_basis": d.get("source_timestamp_basis")
            }

            rec = EvidenceRecord(
                evidence_id=f"EV_DISC_{disc_id}",
                symbol=sym,
                entity_type="STOCK",
                event_date=event_d,
                broadcast_timestamp=b_ts,
                effective_session_date=eff_session,
                tier=tier,
                category=category,
                direction=direction,
                headline=f"Exchange Disclosure: {subject}",
                details=details_dict,
                source_identity="corporate_disclosures",
                source_reference=d.get("source_url") or disc_id,
                verification_status=ver_status,
                is_pit_eligible=(ver_status == "VERIFIED"),
                reporting_basis=None,
                expectation_surprise=ExpectationSurprise.UNKNOWN,  # Strict Requirement: Never infer surprise without consensus
                is_contradictory=False,
                retrieval_timestamp=d.get("retrieval_timestamp", now_utc),
                created_at=now_utc
            )
            records.append(rec)

        return records


class CorporateActionsAdapter:
    """
    Adapts corporate_actions into Tier 2 EvidenceRecords.
    Preserves multiple distinct events on the same ex-date (e.g. Nestlé ₹5 dividend + ₹2 special dividend).
    Classifies mechanical ex-date price changes as NEUTRAL to prevent confusing mechanical
    drops with investor sentiment shifts.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    def extract_evidence(
        self,
        symbol: Optional[str] = None,
        as_of_date: Optional[str] = None
    ) -> List[EvidenceRecord]:
        actions = self.db.get_corporate_actions(symbol=symbol)
        records: List[EvidenceRecord] = []
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        for ca in actions:
            sym = ca["symbol"]
            act_type = ca["action_type"].upper()
            ex_d = ca["ex_date"]
            purpose = ca["purpose"]
            factor = float(ca.get("adjustment_factor", 1.0))
            ann_date = ca.get("announcement_date")

            if as_of_date and ex_d > as_of_date:
                continue

            # Deterministic slug for unique natural key: (symbol, action_type, ex_date, purpose)
            slug = re.sub(r"[^A-Za-z0-9]+", "_", purpose).strip("_").upper()[:30]
            ev_id = f"EV_CA_{sym}_{act_type}_{ex_d.replace('-', '')}_{slug}"

            # Category mapping
            if "DIVIDEND" in act_type:
                category = EvidenceCategory.DIVIDEND_DECLARATION
            elif any(t in act_type for t in ["BONUS", "SPLIT"]):
                category = EvidenceCategory.BONUS_SPLIT_EVENT
            else:
                category = EvidenceCategory.BOARD_MEETING_OUTCOME

            # Requirement 3: Corporate actions must not be misclassified as positive catalysts.
            # A bonus or split is primarily a mechanical price/share adjustment.
            # On ex-date, price movement is mechanical adjustment. Direction is NEUTRAL.
            direction = EvidenceDirection.NEUTRAL

            headline = f"Corporate Action Ex-Date: {sym} {purpose} (Factor: {factor})"

            details_dict = {
                "action_type": act_type,
                "purpose": purpose,
                "ex_date": ex_d,
                "record_date": ca.get("record_date"),
                "announcement_date": ann_date,
                "effective_date": ca.get("effective_date"),
                "adjustment_factor": factor,
                "is_mechanical_adjustment": True,
                "mechanical_note": (
                    "Ex-date price adjustment is mechanical. Does not reflect "
                    "a change in underlying investor sentiment."
                )
            }

            rec = EvidenceRecord(
                evidence_id=ev_id,
                symbol=sym,
                entity_type="STOCK",
                event_date=ex_d,
                broadcast_timestamp=None,
                effective_session_date=ex_d,  # Market reacts on ex-date
                tier=EvidenceTier.TIER_2_FINANCIAL_ACTION,
                category=category,
                direction=direction,
                headline=headline,
                details=details_dict,
                source_identity="corporate_actions",
                source_reference=ca.get("source"),
                verification_status="VERIFIED",
                is_pit_eligible=True,
                reporting_basis=None,
                expectation_surprise=ExpectationSurprise.UNKNOWN,
                is_contradictory=False,
                retrieval_timestamp=ca.get("retrieval_timestamp", now_utc),
                created_at=now_utc
            )
            records.append(rec)

        return records


class FinancialStatementsAdapter:
    """
    Adapts company_financial_statements into Tier 2 (or Tier 5 if unverified) EvidenceRecords.
    Preserves statement versions, restatements, publication dates, and reporting basis (STANDALONE vs CONSOLIDATED).
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    def extract_evidence(
        self,
        symbol: Optional[str] = None,
        as_of_date: Optional[str] = None
    ) -> List[EvidenceRecord]:
        statements = self.db.get_financial_statements(symbol=symbol)
        records: List[EvidenceRecord] = []
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        for s in statements:
            stmt_id = s["statement_id"]
            sym = s["symbol"]
            eff_session = s["effective_session_date"]
            pub_date = s.get("publication_date") or eff_session
            b_ts = s.get("broadcast_timestamp")
            rep_basis = s["reporting_basis"]
            version = s.get("statement_version", 1)
            is_restated = s.get("is_restated", 0)
            restat_reason = s.get("restatement_reason")
            ver_status = s.get("verification_status", "VERIFIED").upper()
            is_pit = bool(s.get("is_pit_eligible", 1))

            if as_of_date and eff_session > as_of_date:
                continue

            tier = EvidenceTier.TIER_2_FINANCIAL_ACTION if ver_status == "VERIFIED" else EvidenceTier.TIER_5_UNVERIFIED

            if is_restated == 1:
                category = EvidenceCategory.EARNINGS_REVISION
                headline = f"Restated Financial Statement ({rep_basis} V{version}): {sym} {s['period_nature']} {s['period_end_date']}"
            else:
                category = EvidenceCategory.EARNINGS_RELEASE
                headline = f"Quarterly Financial Statement ({rep_basis} V{version}): {sym} {s['period_nature']} {s['period_end_date']}"

            # Evaluate reported revenue and net profit
            rev = s.get("revenue_operations")
            pat = s.get("net_profit")
            eps = s.get("basic_eps")

            # Absolute profitability attribute (PROFITABLE / LOSS_MAKING / BREAK_EVEN)
            if pat is not None:
                if pat > 0:
                    profitability_status = "PROFITABLE"
                elif pat < 0:
                    profitability_status = "LOSS_MAKING"
                else:
                    profitability_status = "BREAK_EVEN"
            else:
                profitability_status = "UNKNOWN"

            # Market-impact direction:
            # Per User Requirement 0: Absolute profitability is NOT market news direction.
            # Without authenticated consensus expectation benchmarks, the market sentiment
            # direction of an earnings release MUST be classified as AMBIGUOUS.
            direction = EvidenceDirection.AMBIGUOUS

            details_dict = {
                "statement_id": stmt_id,
                "profitability_status": profitability_status,
                "market_impact_note": (
                    "Direction is AMBIGUOUS because authenticated consensus expectations are unavailable. "
                    "Absolute profitability alone does not constitute positive market news."
                ),
                "reporting_basis": rep_basis,
                "statement_version": version,
                "is_restated": is_restated,
                "restatement_reason": restat_reason,
                "period_start_date": s["period_start_date"],
                "period_end_date": s["period_end_date"],
                "fiscal_year": s["fiscal_year"],
                "fiscal_quarter": s.get("fiscal_quarter"),
                "audit_status": s.get("audit_status"),
                "revenue_operations": rev,
                "net_profit": pat,
                "basic_eps": eps,
                "total_equity": s.get("total_equity"),
                "shares_outstanding": s.get("shares_outstanding"),
                "source_timestamp_basis": s.get("source_timestamp_basis")
            }

            rec = EvidenceRecord(
                evidence_id=f"EV_FS_{stmt_id}",
                symbol=sym,
                entity_type="STOCK",
                event_date=pub_date,
                broadcast_timestamp=b_ts,
                effective_session_date=eff_session,
                tier=tier,
                category=category,
                direction=direction,
                headline=headline,
                details=details_dict,
                source_identity="company_financial_statements",
                source_reference=s.get("source_url") or stmt_id,
                verification_status=ver_status,
                is_pit_eligible=is_pit,
                reporting_basis=rep_basis,
                expectation_surprise=ExpectationSurprise.UNKNOWN,  # Strict: surprise is unknown without consensus
                is_contradictory=False,
                retrieval_timestamp=s.get("retrieval_timestamp", now_utc),
                created_at=now_utc
            )
            records.append(rec)

        return records


class MarketIndexMovementsAdapter:
    """
    Adapts significant daily market and sector index movements (|Return| >= 1.5%) into Tier 3 EvidenceRecords.
    CRITICAL: Strictly filters index_type = 'PRI' to prevent double-counting with TRI representations.
    """

    MOMENTUM_THRESHOLD: float = 0.015  # 1.5% daily move threshold

    def __init__(self, db: DatabaseManager):
        self.db = db

    def extract_evidence(
        self,
        as_of_date: Optional[str] = None
    ) -> List[EvidenceRecord]:
        records: List[EvidenceRecord] = []
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Strict PRI-only query with window LAG to compute daily returns
        sql = """
        WITH pri_series AS (
            SELECT index_name, trading_date, close,
                   LAG(close) OVER (PARTITION BY index_name ORDER BY trading_date) as prev_close
            FROM index_daily
            WHERE index_type = 'PRI'
        )
        SELECT index_name, trading_date, close, prev_close,
               ((close - prev_close) / prev_close) as ret_1d
        FROM pri_series
        WHERE prev_close IS NOT NULL
        ORDER BY trading_date ASC, index_name ASC;
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute(sql)
            rows = cursor.fetchall()

        for r in rows:
            idx_name = r["index_name"]
            t_date = r["trading_date"]
            ret_1d = float(r["ret_1d"])

            if as_of_date and t_date > as_of_date:
                continue

            if abs(ret_1d) >= self.MOMENTUM_THRESHOLD:
                direction = EvidenceDirection.POSITIVE if ret_1d > 0 else EvidenceDirection.NEGATIVE
                entity_type = "BENCHMARK" if idx_name == "NIFTY 50" else "SECTOR"
                dir_label = "Surge" if ret_1d > 0 else "Selloff"

                ev_id = f"EV_MKT_{idx_name.replace(' ', '_')}_{t_date.replace('-', '')}_PRI"
                headline = f"Significant Index Move: {idx_name} {dir_label} ({ret_1d * 100:+.2f}%) [PRI]"

                details_dict = {
                    "index_name": idx_name,
                    "trading_date": t_date,
                    "index_type": "PRI",
                    "ret_1d": ret_1d,
                    "close": float(r["close"]),
                    "prev_close": float(r["prev_close"]),
                    "deduplication_rule": "PRI_EXCLUSIVE_FILTER"
                }

                rec = EvidenceRecord(
                    evidence_id=ev_id,
                    symbol=idx_name,
                    entity_type=entity_type,
                    event_date=t_date,
                    broadcast_timestamp=None,
                    effective_session_date=t_date,
                    tier=EvidenceTier.TIER_3_SECTOR_BENCHMARK,
                    category=EvidenceCategory.SECTOR_MOMENTUM,
                    direction=direction,
                    headline=headline,
                    details=details_dict,
                    source_identity="index_daily",
                    source_reference=f"{idx_name}_PRI_{t_date}",
                    verification_status="VERIFIED",
                    is_pit_eligible=True,
                    reporting_basis=None,
                    expectation_surprise=ExpectationSurprise.UNKNOWN,
                    is_contradictory=False,
                    retrieval_timestamp=now_utc,
                    created_at=now_utc
                )
                records.append(rec)

        return records


class VolumeAnomaliesAdapter:
    """
    Adapts volume and liquidity surges (Volume Ratio >= 2.5 or Z-Score >= 2.5) into Tier 3 EvidenceRecords.
    Volume indicates trading conviction/activity; direction is strictly NEUTRAL.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    def extract_evidence(
        self,
        symbol: Optional[str] = None,
        as_of_date: Optional[str] = None
    ) -> List[EvidenceRecord]:
        records: List[EvidenceRecord] = []
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        sql = """
        SELECT symbol, trading_date, ret_1d, volume_ratio_20d, volume_log_zscore_50d,
               is_volume_spike_ratio, is_volume_spike_zscore
        FROM quant_factors_daily
        WHERE (is_volume_spike_ratio = 1 OR is_volume_spike_zscore = 1)
        """
        params: List[Any] = []
        if symbol:
            sql += " AND symbol = ?"
            params.append(symbol)
        if as_of_date:
            sql += " AND trading_date <= ?"
            params.append(as_of_date)
        sql += " ORDER BY trading_date ASC, symbol ASC;"

        with self.db.get_connection() as conn:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()

        for r in rows:
            sym = r["symbol"]
            t_date = r["trading_date"]
            vr = r["volume_ratio_20d"]
            z = r["volume_log_zscore_50d"]

            ev_id = f"EV_VOL_{sym}_{t_date.replace('-', '')}"
            vr_str = f"{vr:.2f}x" if vr is not None else "N/A"
            z_str = f"{z:.2f}" if z is not None else "N/A"
            headline = f"Volume Anomaly: {sym} Volume Ratio={vr_str}, Log Z={z_str}"

            details_dict = {
                "symbol": sym,
                "trading_date": t_date,
                "volume_ratio_20d": vr,
                "volume_log_zscore_50d": z,
                "is_volume_spike_ratio": r["is_volume_spike_ratio"],
                "is_volume_spike_zscore": r["is_volume_spike_zscore"],
                "ret_1d": r["ret_1d"]
            }

            rec = EvidenceRecord(
                evidence_id=ev_id,
                symbol=sym,
                entity_type="STOCK",
                event_date=t_date,
                broadcast_timestamp=None,
                effective_session_date=t_date,
                tier=EvidenceTier.TIER_3_SECTOR_BENCHMARK,
                category=EvidenceCategory.VOLUME_LIQUIDITY_SURGE,
                direction=EvidenceDirection.NEUTRAL,  # Volume reflects intensity, not sentiment direction
                headline=headline,
                details=details_dict,
                source_identity="quant_factors_daily",
                source_reference=f"{sym}_VOL_{t_date}",
                verification_status="VERIFIED",
                is_pit_eligible=True,
                reporting_basis=None,
                expectation_surprise=ExpectationSurprise.UNKNOWN,
                is_contradictory=False,
                retrieval_timestamp=now_utc,
                created_at=now_utc
            )
            records.append(rec)

        return records
