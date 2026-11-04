"""
Market Intelligence Lab — Corporate Actions Processing Module (B3.2).

Extracts, normalizes, validates, and ingests official corporate actions
(dividends, stock splits, bonus share issues, rights issues) from official NSE payloads.
Enforces idempotent upserts on surrogate ID, computes historical price adjustment ratios,
and gracefully logs stocks with zero actions as NO_ACTIONS_FOUND in the audit log.
"""

import os
import re
import json
import hashlib
import datetime
from typing import Dict, Any, List, Optional, Tuple

from src.storage.database import DatabaseManager


class CorporateActionsHandler:
    """
    Normalizer and database persistence handler for official corporate actions.
    """

    def __init__(self, source_name: str = "nse_corp_actions"):
        self.source_name = source_name

    @staticmethod
    def _parse_nse_date(date_str: Optional[str]) -> Optional[str]:
        """Parses NSE date format '03-Nov-2026' into ISO '2026-11-03'."""
        if not date_str or date_str.strip() in ("-", "", "None", "null"):
            return None
        cleaned = date_str.strip()
        # Already ISO YYYY-MM-DD
        if re.match(r"^\d{4}-\d{2}-\d{2}$", cleaned):
            return cleaned
        for fmt in ("%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                dt = datetime.datetime.strptime(cleaned, fmt).date()
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    @staticmethod
    def classify_action_type(purpose: str) -> str:
        """Classifies corporate action type based on declaration text."""
        p_up = purpose.upper()
        if "DIVIDEND" in p_up:
            return "DIVIDEND"
        if "BONUS" in p_up:
            return "BONUS"
        if "SPLIT" in p_up or "SUB-DIVISION" in p_up or "SUB DIVISION" in p_up:
            return "SPLIT"
        if "RIGHTS" in p_up:
            return "RIGHTS"
        return "OTHER"

    @classmethod
    def compute_adjustment_ratio(
        cls,
        action_type: str,
        purpose: str,
        face_val: Optional[float] = None
    ) -> float:
        """
        Computes the historical-price scaling multiplier M_hist <= 1.0.
        - DIVIDEND: 1.0 (cash dividends do not compress historical prices in this milestone).
        - BONUS A:B: ratio = B / (A + B).
        - SPLIT old:new: ratio = new_fv / old_fv.
        """
        p_up = purpose.upper()

        if action_type == "DIVIDEND":
            return 1.0

        if action_type == "BONUS":
            # Matches 'Bonus 1:1', 'Bonus Issue 1:2', '1:1', etc.
            m = re.search(r'(?:BONUS[A-Z\s]*)?(\d+)\s*:\s*(\d+)', p_up)
            if m:
                bonus = float(m.group(1))
                existing = float(m.group(2))
                if existing + bonus > 0:
                    ratio = existing / (existing + bonus)
                    return round(ratio, 4)
            return 1.0

        if action_type == "SPLIT":
            # Matches 'From Rs 5/- Per Share To Re 1/- Per Share', 'Rs 10 to Rs 2', '10 to 1', 'From Rs. 10/- to Rs. 2/-'
            m = re.search(
                r'(?:FROM\s+)?(?:RS\.?|RE\.?|INR)?\s*(\d+(?:\.\d+)?)(?:/-)?\s*(?:PER\s+SHARE)?\s*(?:TO|-)\s*(?:RS\.?|RE\.?|INR)?\s*(\d+(?:\.\d+)?)',
                p_up
            )
            if m:
                old_fv = float(m.group(1))
                new_fv = float(m.group(2))
                if old_fv > 0 and new_fv <= old_fv:
                    return round(new_fv / old_fv, 4)
            if face_val and face_val > 0:
                # If current face value is lower than nominal 10
                if face_val < 10.0:
                    return round(face_val / 10.0, 4)
            return 1.0

        return 1.0

    def parse_action(
        self,
        raw_item: Dict[str, Any],
        symbol: str
    ) -> Optional[Dict[str, Any]]:
        """
        Parses a single raw corporate action dictionary from NSE.
        Returns a normalized dictionary with schema-aligned attributes.
        """
        sym = raw_item.get("symbol") or symbol
        purpose = (raw_item.get("subject") or raw_item.get("purpose") or "").strip()
        if not purpose:
            return None

        ex_date = self._parse_nse_date(raw_item.get("exDate") or raw_item.get("ex_date"))
        if not ex_date:
            return None

        record_date = self._parse_nse_date(raw_item.get("recDate") or raw_item.get("record_date"))
        announcement_date = self._parse_nse_date(raw_item.get("caBroadcastDate") or raw_item.get("announcement_date"))

        # Parse face value
        face_val_raw = raw_item.get("faceVal") or raw_item.get("face_value")
        face_value: Optional[float] = None
        if face_val_raw and str(face_val_raw).strip() not in ("-", "", "None"):
            try:
                face_value = float(face_val_raw)
            except (ValueError, TypeError):
                face_value = None

        action_type = raw_item.get("action_type") or self.classify_action_type(purpose)
        adjustment_ratio = self.compute_adjustment_ratio(action_type, purpose, face_value)

        # Deterministic surrogate key
        purp_hash = hashlib.md5(purpose.encode("utf-8")).hexdigest()[:8]
        action_id = f"{sym}_{action_type}_{ex_date}_{purp_hash}"

        now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return {
            "id": action_id,
            "symbol": sym,
            "action_type": action_type,
            "ex_date": ex_date,
            "record_date": record_date,
            "announcement_date": announcement_date,
            "effective_date": ex_date,
            "face_value": face_value,
            "adjustment_ratio": adjustment_ratio,
            "adjustment_factor": adjustment_ratio,
            "purpose": purpose,
            "source": self.source_name,
            "retrieval_timestamp": now_iso
        }

    def ingest_actions(
        self,
        db: DatabaseManager,
        symbol: str,
        raw_actions: List[Dict[str, Any]],
        raw_path: str = ""
    ) -> Dict[str, Any]:
        """
        Parses and persists corporate actions for a symbol into SQLite.
        Handles zero actions gracefully by logging NO_ACTIONS_FOUND in ingestion_audit_log.
        """
        now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not raw_actions or len(raw_actions) == 0:
            db.record_audit_log(
                source=self.source_name,
                endpoint="https://www.nseindia.com/api/corporates-corporateActions",
                symbol=symbol,
                date_range_start=None,
                date_range_end=None,
                records_retrieved=0,
                records_accepted=0,
                records_rejected=0,
                validation_summary=json.dumps({"info": "No corporate actions found for symbol in timeframe"}),
                raw_payload_path=raw_path,
                status="NO_ACTIONS_FOUND",
                created_at=now_iso
            )
            return {
                "status": "NO_ACTIONS_FOUND",
                "retrieved": 0,
                "accepted": 0,
                "rejected": 0,
                "symbol": symbol
            }

        parsed_actions: List[Dict[str, Any]] = []
        rejected_count = 0
        rejection_details: List[str] = []

        for item in raw_actions:
            parsed = self.parse_action(item, symbol)
            if parsed is not None:
                parsed_actions.append(parsed)
            else:
                rejected_count += 1
                rejection_details.append(f"Invalid record: {str(item)[:80]}")

        # Idempotent upsert via DatabaseManager
        accepted_count = 0
        if parsed_actions:
            accepted_count = db.upsert_corporate_actions(parsed_actions)

        status = "SUCCESS" if rejected_count == 0 else ("PARTIAL" if accepted_count > 0 else "FAILED")

        db.record_audit_log(
            source=self.source_name,
            endpoint="https://www.nseindia.com/api/corporates-corporateActions",
            symbol=symbol,
            date_range_start=None,
            date_range_end=None,
            records_retrieved=len(raw_actions),
            records_accepted=len(parsed_actions),
            records_rejected=rejected_count,
            validation_summary=json.dumps({
                "accepted": len(parsed_actions),
                "rejected": rejected_count,
                "rejection_reasons": rejection_details[:10]
            }),
            raw_payload_path=raw_path,
            status=status,
            created_at=now_iso
        )

        return {
            "status": status,
            "retrieved": len(raw_actions),
            "accepted": len(parsed_actions),
            "rejected": rejected_count,
            "symbol": symbol
        }
