"""
Market Intelligence Lab — Corporate Disclosures Processing Module (B3.2).

Extracts, tags, normalizes, and ingests official regulatory disclosures and board
announcements from official NSE payloads into SQLite.
Extracts direct official PDF URLs, accurately extracts exchange broadcast timestamps,
aligns effective trading sessions (15:30 IST cutoff), deterministically tags categories,
and strictly enforces default verification_status = 'PENDING_VERIFICATION'.
"""

import os
import re
import json
import datetime
from typing import Dict, Any, List, Optional, Tuple

from src.storage.database import DatabaseManager
from src.quant.calendar import is_trading_session


class CorporateDisclosuresHandler:
    """
    Parser, taxonomical classifier, and persistence engine for official corporate disclosures.
    """

    def __init__(self, source_name: str = "nse_corporate_announcements"):
        self.source_name = source_name

    @staticmethod
    def parse_broadcast_timestamp(raw_item: Dict[str, Any]) -> Tuple[Optional[str], Optional[datetime.datetime]]:
        """
        Extracts and converts the exact exchange submission timestamp into ISO-8601 with IST offset (+05:30).
        Priority: sort_date -> an_dt -> exchdisstime. Does NOT use PDF file creation dates.
        """
        raw_ts = (
            raw_item.get("sort_date")
            or raw_item.get("an_dt")
            or raw_item.get("exchdisstime")
            or raw_item.get("broadcast_timestamp")
        )
        if not raw_ts or str(raw_ts).strip() in ("-", "", "None", "null"):
            return None, None

        cleaned = str(raw_ts).strip()

        # If already formatted with timezone
        if "T" in cleaned and ("+" in cleaned or "Z" in cleaned):
            try:
                # Replace Z with +00:00 for fromisoformat if needed
                dt = datetime.datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
                return cleaned, dt
            except Exception:
                pass

        # Try various NSE timestamp formats
        # e.g. "2026-10-30 18:50:50", "30-Oct-2026 18:50:50", "30-OCT-2026 18:50:50"
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%d-%b-%Y %H:%M:%S",
            "%d-%B-%Y %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d-%b-%Y %H:%M",
            "%Y-%m-%d"
        ):
            try:
                dt_naive = datetime.datetime.strptime(cleaned, fmt)
                # Assign IST timezone (+05:30)
                ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
                dt_ist = dt_naive.replace(tzinfo=ist_tz)
                iso_str = dt_ist.isoformat()
                return iso_str, dt_ist
            except ValueError:
                continue

        return None, None

    @staticmethod
    def get_effective_session(dt_ist: Optional[datetime.datetime]) -> str:
        """
        Determines the earliest trading session (t=0) when the market could react.
        - Disseminated <= 15:30:00 IST on a trading session -> same day.
        - Disseminated > 15:30:00 IST, on weekend, or on exchange holiday -> next trading day.
        """
        if dt_ist is None:
            return datetime.date.today().strftime("%Y-%m-%d")

        market_close = datetime.time(15, 30, 0)
        curr_date = dt_ist.date()
        date_str = curr_date.strftime("%Y-%m-%d")

        is_open, _ = is_trading_session(date_str)
        if is_open and dt_ist.time() <= market_close:
            return date_str

        # Advance to next open trading session
        next_d = curr_date + datetime.timedelta(days=1)
        for _ in range(30):
            next_date_str = next_d.strftime("%Y-%m-%d")
            is_open, _ = is_trading_session(next_date_str)
            if is_open:
                return next_date_str
            next_d += datetime.timedelta(days=1)

        return date_str

    @staticmethod
    def classify_category(desc: str, attchmnt_text: str) -> str:
        """
        Deterministic regex and keyword taxonomy classifier for corporate disclosures.
        """
        combined = f"{desc} {attchmnt_text}".lower()

        # 1. Earnings & Financial Results
        if re.search(r"\b(financial results?|quarterly financial|un-?audited financial|audited financial|balance sheet|earnings)\b|\bq[1-4]\s*(?:results?|financials)?\b", combined):
            return "EARNINGS"

        # 2. Board Meetings
        if re.search(r"\b(board meeting|outcome of board)\b", combined):
            return "BOARD_MEETING"

        # 3. Contract Awards & Orders
        if re.search(r"\b(order|contract|award|agreement|deal|procurement|bagged|commercial agreement)\b", combined):
            return "CONTRACT_AWARD"

        # 4. Resignations & Key Executive Exits
        if re.search(r"\b(resignation|cessation|relinquish)\b", combined):
            return "RESIGNATION"

        # 5. Executive & Board Appointments
        if re.search(r"\b(appointment|re-appointment|designated|induction)\b", combined):
            return "APPOINTMENT"

        # 6. Cash Dividends & Corporate Actions Announced in Board Notes
        if re.search(r"\b(dividend|record date for dividend)\b", combined):
            return "DIVIDEND"

        # 7. Investor Presentations & Earnings Call Transcripts
        if re.search(r"\b(investor presentation|analyst meet|concall|conference call)\b", combined):
            return "INVESTOR_PRESENTATION"

        # 8. General Regulatory Notices
        return "GENERAL_ANNOUNCEMENT"

    def parse_disclosure(
        self,
        raw_item: Dict[str, Any],
        symbol: str
    ) -> Optional[Dict[str, Any]]:
        """
        Parses a single raw corporate announcement dictionary from NSE.
        Extracts direct PDF filing URL, exact timestamp, effective session,
        and assigns verification_status = 'PENDING_VERIFICATION'.
        """
        sym = raw_item.get("symbol") or symbol
        seq_id = str(raw_item.get("seq_id") or raw_item.get("dt") or "").strip()
        if not seq_id:
            # Fallback surrogate hash if seq_id missing
            raw_summary = str(raw_item.get("attchmntText") or raw_item.get("desc") or "")
            import hashlib
            seq_id = hashlib.md5(raw_summary.encode("utf-8")).hexdigest()[:12]

        disc_id = f"DISC_{sym}_{seq_id}"

        # Extract timestamps
        broadcast_iso, dt_ist = self.parse_broadcast_timestamp(raw_item)
        if not broadcast_iso:
            return None

        effective_session = self.get_effective_session(dt_ist)

        desc = str(raw_item.get("desc") or "").strip()
        attchmnt_text = str(raw_item.get("attchmntText") or "").strip()
        subject = desc if desc else (attchmnt_text[:120] if attchmnt_text else "Exchange Notification")
        details_summary = attchmnt_text if attchmnt_text else desc

        # Document URL extraction: official PDF filing
        source_url = raw_item.get("attchmntFile") or raw_item.get("source_url")
        if source_url and str(source_url).strip() in ("-", "", "None", "null"):
            source_url = None

        category = self.classify_category(desc, attchmnt_text)
        now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "id": disc_id,
            "disclosure_id": disc_id,
            "symbol": sym,
            "broadcast_timestamp": broadcast_iso,
            "effective_session_date": effective_session,
            "category": category,
            "subject": subject,
            "details_summary": details_summary,
            "source_url": source_url,
            "retrieval_timestamp": now_utc,
            "verification_status": "PENDING_VERIFICATION",
            "source_timestamp_basis": "exchange_submission_metadata"
        }

    def ingest_disclosures(
        self,
        db: DatabaseManager,
        symbol: str,
        raw_disclosures: List[Dict[str, Any]],
        raw_path: str = ""
    ) -> Dict[str, Any]:
        """
        Parses and persists corporate disclosures for a symbol into SQLite.
        Guarantees idempotent UPSERT and audit log tracking.
        """
        now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not raw_disclosures or len(raw_disclosures) == 0:
            db.record_audit_log(
                source=self.source_name,
                endpoint="https://www.nseindia.com/api/corporate-announcements",
                symbol=symbol,
                date_range_start=None,
                date_range_end=None,
                records_retrieved=0,
                records_accepted=0,
                records_rejected=0,
                validation_summary=json.dumps({"info": "No disclosures found for symbol"}),
                raw_payload_path=raw_path,
                status="NO_DISCLOSURES_FOUND",
                created_at=now_iso
            )
            return {
                "status": "NO_DISCLOSURES_FOUND",
                "retrieved": 0,
                "accepted": 0,
                "rejected": 0,
                "symbol": symbol
            }

        parsed_disclosures: List[Dict[str, Any]] = []
        rejected_count = 0
        rejection_details: List[str] = []

        for item in raw_disclosures:
            parsed = self.parse_disclosure(item, symbol)
            if parsed is not None:
                parsed_disclosures.append(parsed)
            else:
                rejected_count += 1
                rejection_details.append(f"Invalid disclosure: {str(item)[:80]}")

        accepted_count = 0
        if parsed_disclosures:
            accepted_count = db.upsert_corporate_disclosures(parsed_disclosures)

        status = "SUCCESS" if rejected_count == 0 else ("PARTIAL" if accepted_count > 0 else "FAILED")

        db.record_audit_log(
            source=self.source_name,
            endpoint="https://www.nseindia.com/api/corporate-announcements",
            symbol=symbol,
            date_range_start=None,
            date_range_end=None,
            records_retrieved=len(raw_disclosures),
            records_accepted=len(parsed_disclosures),
            records_rejected=rejected_count,
            validation_summary=json.dumps({
                "accepted": len(parsed_disclosures),
                "rejected": rejected_count,
                "rejection_reasons": rejection_details[:10]
            }),
            raw_payload_path=raw_path,
            status=status,
            created_at=now_iso
        )

        return {
            "status": status,
            "retrieved": len(raw_disclosures),
            "accepted": len(parsed_disclosures),
            "rejected": rejected_count,
            "symbol": symbol
        }
