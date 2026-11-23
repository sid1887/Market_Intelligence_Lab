"""
src/data/corporate_disclosures.py
Universal Corporate Disclosures & Regulatory Announcement Ingestion Engine.

Features:
1. Scraping and ingestion of official NSE announcements (Board Meetings, Earnings, Orders, Exits).
2. Canonical exchange PDF link resolution (https://nsearchives.nseindia.com/corporate/...).
3. Materiality Tagging Engine: Separates price-sensitive material disclosures from routine compliance filings.
4. Point-in-time session alignment ensuring zero look-ahead bias (15:30 IST market close cutoff).
"""

import re
import json
import random
import logging
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union
import requests

from src.storage.database import DatabaseManager
from src.quant.disclosures import CorporateDisclosuresHandler
from src.data.nse_archive_fetcher import USER_AGENT_POOL

logger = logging.getLogger("MIL.DisclosuresHarvester")

ROUTINE_PATTERNS = [
    r"\btrading window (?:closure|closed)\b",
    r"\bloss of share certificate\b",
    r"\bduplicate share certificate\b",
    r"\bcompliance certificate\b",
    r"\bregulation 7\s*\(\s*3\s*\)\b",
    r"\bregulation 74\s*\(\s*5\s*\)\b",
    r"\bregulation 40\s*\(\s*9\s*\)\b",
    r"\bnewspaper publication\b",
    r"\bnewspaper advertisement\b",
    r"\bdispatch of (?:annual report|postal ballot)\b",
    r"\bclosure of register of members\b",
]

HIGH_MATERIAL_PATTERNS = [
    r"\b(?:un-?audited|audited)?\s*financial results\b",
    r"\bboard meeting outcome\b",
    r"\bdeclaration of dividend\b",
    r"\brecommendation of dividend\b",
    r"\bbonus issue\b",
    r"\bstock split\b",
    r"\bsub-division of shares\b",
    r"\bmerger|demerger|amalgamation|acquisition|takeover\b",
    r"\bresignation of (?:managing director|ceo|cfo|executive director|auditor)\b",
    r"\bcessation of (?:managing director|ceo|cfo|director)\b",
    r"\baward of (?:order|contract|project)\b",
    r"\bcommercial agreement\b",
    r"\bcredit rating (?:downgrade|revised downwards)\b",
    r"\bdefault in payment\b",
    r"\bsebi (?:notice|order|inquiry)|cbi|ed investigation\b",
]


class CorporateDisclosuresHarvester:
    """
    Harvests, normalizes, scores materiality, and persists official exchange disclosures.
    """

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        session: Optional[requests.Session] = None,
        timeout: int = 15
    ):
        self.db = db or DatabaseManager()
        self.handler = CorporateDisclosuresHandler()
        self.session = session or requests.Session()
        self.timeout = timeout

    @staticmethod
    def normalize_pdf_url(raw_url: Optional[str]) -> Optional[str]:
        """
        Normalizes raw exchange attachment filename/URL to absolute exchange archive URL.
        Example: 'INFY_15012024.pdf' -> 'https://nsearchives.nseindia.com/corporate/INFY_15012024.pdf'
        """
        if not raw_url:
            return None
        cleaned = str(raw_url).strip()
        if cleaned in ("-", "", "None", "null", "#"):
            return None

        if cleaned.startswith("http://") or cleaned.startswith("https://"):
            return cleaned

        # Strip leading slashes
        filename = cleaned.lstrip("/")
        return f"https://nsearchives.nseindia.com/corporate/{filename}"

    @classmethod
    def classify_materiality(
        cls,
        subject: str,
        details_summary: str,
        category: str
    ) -> Tuple[str, float]:
        """
        Tags disclosure as HIGHLY_MATERIAL, MATERIAL, or ROUTINE with confidence score.
        """
        text = f"{subject} {details_summary}".lower()

        for pat in ROUTINE_PATTERNS:
            if re.search(pat, text):
                return "ROUTINE", 0.15

        for pat in HIGH_MATERIAL_PATTERNS:
            if re.search(pat, text):
                return "HIGHLY_MATERIAL", 0.95

        if category in ("EARNINGS", "CONTRACT_AWARD", "RESIGNATION", "DIVIDEND"):
            return "MATERIAL", 0.80

        if category == "BOARD_MEETING":
            return "MATERIAL", 0.70

        return "ROUTINE", 0.30

    def fetch_announcements(
        self,
        symbol: Optional[str] = None,
        index: str = "equities"
    ) -> List[Dict[str, Any]]:
        """
        Fetches live corporate announcements from official NSE endpoint.
        Returns list of raw announcement payloads.
        """
        url = "https://www.nseindia.com/api/corporate-announcements"
        params = {"index": index}
        if symbol:
            params["symbol"] = symbol.strip().upper()

        headers = {
            "User-Agent": random.choice(USER_AGENT_POOL),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements"
        }

        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "data" in data:
                    return data["data"]
            logger.warning(f"Failed to fetch announcements: HTTP {resp.status_code}")
        except Exception as err:
            logger.warning(f"Network error fetching corporate announcements: {err}")

        return []

    def process_and_store_disclosures(
        self,
        raw_items: List[Dict[str, Any]],
        symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Processes raw announcements, normalizes PDF URLs, assigns materiality,
        and persists them idempotently into corporate_disclosures table.
        """
        if not raw_items:
            return {"accepted": 0, "rejected": 0, "status": "EMPTY"}

        normalized_disclosures: List[Dict[str, Any]] = []
        rejected = 0

        for item in raw_items:
            sym = (item.get("symbol") or symbol or "").strip().upper()
            if not sym:
                rejected += 1
                continue

            parsed = self.handler.parse_disclosure(item, sym)
            if not parsed:
                rejected += 1
                continue

            # Normalize PDF link
            raw_file = item.get("attchmntFile") or item.get("source_url") or parsed.get("source_url")
            parsed["source_url"] = self.normalize_pdf_url(raw_file)

            # Classify materiality
            mat_class, mat_score = self.classify_materiality(
                parsed["subject"],
                parsed.get("details_summary") or "",
                parsed["category"]
            )
            parsed["materiality_class"] = mat_class
            parsed["materiality_score"] = mat_score

            normalized_disclosures.append(parsed)

        accepted = 0
        if normalized_disclosures:
            accepted = self.db.upsert_corporate_disclosures(normalized_disclosures)

        logger.info(f"Processed {len(raw_items)} announcements: {accepted} accepted, {rejected} rejected.")
        return {
            "accepted": accepted,
            "rejected": rejected,
            "total": len(raw_items),
            "status": "SUCCESS" if rejected == 0 else "PARTIAL"
        }
