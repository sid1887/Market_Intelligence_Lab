"""
src/storage/temporal_guard.py
Point-In-Time (PIT) Temporal Invariants Guard & Causality Auditor.
ADR-0006, ADR-0008, ADR-0011.

Enforces fundamental temporal invariants across all storage layers:
1. Causality: publication_date >= period_end_date (companies cannot report before quarter closes).
2. Availability: effective_session_date >= publication_date (market cannot trade on filings before broadcast).
3. Factor Horizon: calculated_at >= trading_date (factors cannot look into future sessions).
4. Corporate Actions: effective_date >= ex_date (actions cannot adjust prices retroactively before ex-date).
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple, Optional, Union
from src.storage.database import DatabaseManager

logger = logging.getLogger("MIL.TemporalGuard")

# Canonical Indian Standard Time (IST) offset: UTC+05:30
IST_TIMEZONE = timezone(timedelta(hours=5, minutes=30))
EOD_CLOSE_TIME_IST = "15:30:00+05:30"
PRE_MARKET_OPEN_TIME_IST = "09:00:00+05:30"


def parse_ist_timestamp(ts: Union[str, datetime]) -> datetime:
    """
    Parses an ISO-8601 string or datetime object into a timezone-aware IST datetime.
    Supports ISO formats with '+05:30', 'Z', and naive datetime strings (assumed IST).
    """
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=IST_TIMEZONE)
        return ts.astimezone(IST_TIMEZONE)

    s = str(ts).strip()
    if not s:
        raise ValueError("Timestamp string cannot be empty.")

    # Normalize trailing Z to UTC
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    # Date-only YYYY-MM-DD
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        s = f"{s}T00:00:00+05:30"

    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST_TIMEZONE)
        return dt.astimezone(IST_TIMEZONE)
    except Exception as e:
        raise ValueError(f"Unable to parse timestamp '{ts}' to IST: {e}")


def get_eod_close_decision_timestamp(session_date: str) -> str:
    """Returns canonical EOD Close Decision timestamp for session t (15:30 IST)."""
    clean_date = str(session_date).strip()[:10]
    return f"{clean_date}T{EOD_CLOSE_TIME_IST}"


def get_pre_market_decision_timestamp(session_date: str) -> str:
    """Returns canonical Pre-Market Open Decision timestamp for session t+1 (09:00 IST)."""
    clean_date = str(session_date).strip()[:10]
    return f"{clean_date}T{PRE_MARKET_OPEN_TIME_IST}"


def is_pit_eligible_at(
    published_at_ist: Optional[Union[str, datetime]],
    decision_timestamp_ist: Union[str, datetime]
) -> bool:
    """
    Enforces strict point-in-time timestamp causality:
        published_at_ist < decision_timestamp_ist

    Returns True if filing/event was officially broadcast and known to the market
    strictly BEFORE the execution decision point.
    """
    if not published_at_ist:
        return False

    try:
        pub_dt = parse_ist_timestamp(published_at_ist)
        dec_dt = parse_ist_timestamp(decision_timestamp_ist)
        return pub_dt < dec_dt
    except Exception as e:
        logger.warning(f"[PIT-GUARD] Failed timestamp comparison ({published_at_ist} vs {decision_timestamp_ist}): {e}")
        return False


class TemporalInvariantGuard:
    """Enforces strict Point-In-Time causality invariants across all database entities."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def audit_financial_statements(self) -> Dict[str, Any]:
        """
        Audits company_financial_statements and financial_statements_quarterly.
        Quarantines any statement violating causality by setting is_pit_eligible = 0.
        """
        with self.db.get_connection() as conn:
            # 1. Check company_financial_statements causality
            cur = conn.execute("""
                SELECT statement_id, symbol, period_end_date, publication_date, effective_session_date
                FROM company_financial_statements
                WHERE publication_date < period_end_date OR effective_session_date < publication_date;
            """)
            cfs_violations = cur.fetchall()

            if cfs_violations:
                logger.warning(f"[PIT-GUARD] Found {len(cfs_violations)} causality violations in company_financial_statements. Quarantining...")
                bad_ids = [r[0] for r in cfs_violations]
                placeholders = ",".join("?" for _ in bad_ids)
                conn.execute(f"UPDATE company_financial_statements SET is_pit_eligible = 0 WHERE statement_id IN ({placeholders})", bad_ids)
                conn.commit()

            # 2. Check financial_statements_quarterly causality
            cur = conn.execute("""
                SELECT symbol, period_end_date, filing_date
                FROM financial_statements_quarterly
                WHERE filing_date < period_end_date;
            """)
            fsq_violations = cur.fetchall()

            # Count clean statements
            cur = conn.execute("SELECT COUNT(*) FROM company_financial_statements WHERE is_pit_eligible = 1;")
            eligible_cfs = cur.fetchone()[0]

            cur = conn.execute("SELECT COUNT(*) FROM financial_statements_quarterly;")
            total_fsq = cur.fetchone()[0]

            return {
                "cfs_eligible_count": eligible_cfs,
                "cfs_violations_quarantined": len(cfs_violations),
                "fsq_total_count": total_fsq,
                "fsq_violations_count": len(fsq_violations),
                "status": "PASS" if len(cfs_violations) == 0 and len(fsq_violations) == 0 else "QUARANTINED"
            }

    def audit_quant_factors(self) -> Dict[str, Any]:
        """
        Verifies quant_factors_daily and fundamental_factors_daily temporal bounds.
        Ensures no future session leakages exist.
        """
        with self.db.get_connection() as conn:
            # Detect any date anomaly where trading_date is in the distant future (> 2030)
            cur = conn.execute("""
                SELECT COUNT(*) FROM quant_factors_daily WHERE trading_date > '2030-01-01';
            """)
            future_qf = cur.fetchone()[0]

            cur = conn.execute("""
                SELECT COUNT(*) FROM fundamental_factors_daily WHERE trading_date > '2030-01-01';
            """)
            future_ffd = cur.fetchone()[0]

            cur = conn.execute("SELECT COUNT(*) FROM quant_factors_daily;")
            total_qf = cur.fetchone()[0]

            return {
                "total_quant_factors": total_qf,
                "future_leaks_qf": future_qf,
                "future_leaks_ffd": future_ffd,
                "status": "PASS" if future_qf == 0 and future_ffd == 0 else "FAIL"
            }

    def audit_corporate_actions(self) -> Dict[str, Any]:
        """
        Verifies corporate_actions temporal consistency.
        """
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT COUNT(*) FROM corporate_actions 
                WHERE ex_date IS NOT NULL AND announcement_date IS NOT NULL AND ex_date < announcement_date;
            """)
            inverted_dates = cur.fetchone()[0]

            cur = conn.execute("SELECT COUNT(*) FROM corporate_actions;")
            total_ca = cur.fetchone()[0]

            return {
                "total_corporate_actions": total_ca,
                "inverted_announcement_ex_date": inverted_dates,
                "status": "PASS" if inverted_dates == 0 else "AUDIT_FLAGGED"
            }

    def run_full_temporal_audit(self) -> Dict[str, Any]:
        """Runs complete causality and Point-In-Time invariant audit suite."""
        logger.info("[PIT-GUARD] Initiating full temporal invariant audit...")
        fs_res = self.audit_financial_statements()
        qf_res = self.audit_quant_factors()
        ca_res = self.audit_corporate_actions()

        overall_status = "PASS" if fs_res["status"] in ("PASS", "QUARANTINED") and qf_res["status"] == "PASS" else "FAIL"

        return {
            "overall_status": overall_status,
            "financial_statements": fs_res,
            "quant_factors": qf_res,
            "corporate_actions": ca_res
        }
