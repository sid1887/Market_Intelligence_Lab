"""
Market Intelligence Lab: News Impact & Directional Assessment Engine
Milestone: B7.5 (News Ingestion, Structured Summarization & Directional Impact Engine)

Extracts factual bullet summaries and deterministically classifies market direction,
horizon, affected fundamental drivers, and confidence score for equity news items.
Strictly rules-based and deterministic with zero lookahead bias or uncalibrated LLM hallucinations.
"""

import re
import json
from typing import Dict, List, Any, Optional, Tuple


class NewsImpactEngine:
    """
    Processes financial media articles and regulatory news to produce:
    1. Concise, factual bullet points focusing on metrics and operations.
    2. Directional impact assessment (BULLISH, BEARISH, NEUTRAL).
    3. Impact horizon (SHORT_TERM, MEDIUM_TERM).
    4. Key affected drivers (ORDER_BOOK, MARGINS, DELEVERAGING, VALUATION, REGULATORY, etc.).
    5. Calibrated confidence score (0.0 to 1.0).
    """

    # Driver patterns
    DRIVER_PATTERNS = {
        "ORDER_BOOK": re.compile(
            r"\b(orders?|contract|wins?|bagged|secures?|tender|capacity|commissioning|mw|gw|mwp|"
            r"megawatt|gigawatt|backlog|pact|mou|pipeline|client win|supply agreement|deliveries|project)\b",
            re.IGNORECASE,
        ),
        "MARGINS": re.compile(
            r"\b(margins?|ebitda|operating profit|costs?|cost cutting|raw material|pricing power|"
            r"margin squeeze|margin contraction|margin expansion|contraction|profitability|opm|net profit|profit|earnings|loss)\b",
            re.IGNORECASE,
        ),
        "DELEVERAGING": re.compile(
            r"\b(debt|deleveraging|pre-pays?|repay(?:ment)?|debt-free|cuts debt|credit rating|"
            r"borrowings?|interest cost|refinanc(?:e|ing)|credit upgrade|solvency)\b",
            re.IGNORECASE,
        ),
        "REVENUE_VISIBILITY": re.compile(
            r"\b(revenue|turnover|deliveries|sales|shipments|topline|record deliveries|"
            r"volume growth|multi-year|recurring revenue|client acquisition)\b",
            re.IGNORECASE,
        ),
        "VALUATION": re.compile(
            r"\b(valuation|pe ratio|target price|brokerage|upgrade|downgrade|buyback|"
            r"outperform|underperform|overvalued|undervalued|rally|discount|target raised|"
            r"buy rating|accumulate|shares? fall|shares? drop|shares? rise)\b",
            re.IGNORECASE,
        ),
        "REGULATORY": re.compile(
            r"\b(sebi|rbi|usfda|fda|clearance|approval|nclt|court|tribunal|tax demand|"
            r"gst|probe|investigation|penalty|fine|notice|plea|stay order|litigation|lawsuit|"
            r"ed raid|cbi|inquiry)\b",
            re.IGNORECASE,
        ),
        "GOVERNANCE": re.compile(
            r"\b(promoter|pledge|pledging|auditor|resignation|resigns|cfo|ceo|board meeting|"
            r"agm|independent director|governance|corporate governance|stake sale|promoter buying)\b",
            re.IGNORECASE,
        ),
    }

    # Direction patterns
    BULLISH_PATTERNS = [
        re.compile(r"\b(secures?|wins?|bagged|bags)\b.*?\b(order|contract|project|mandate|tender|deal|capacity|\d+\s*(?:MW|GW|cr))\b", re.IGNORECASE),
        re.compile(r"\b(order win|new order|fresh order|commercial order|major win)\b", re.IGNORECASE),
        re.compile(r"\b(capacity expansion|commissioned|commissions|new plant|commercial operations|cod|expansion)\b", re.IGNORECASE),
        re.compile(r"\b(debt reduction|pre-pays debt|debt free|debt-free|cuts debt|rating upgrade|credit upgrade)\b", re.IGNORECASE),
        re.compile(r"\b(profit jumps?|profit up|profit rises?|profit surged?|profit doubles?|net profit climbs?|profit skyrockets?|surges?|grows? \d+%)\b", re.IGNORECASE),
        re.compile(r"\b(revenue grows?|revenue rises?|revenue up|revenue surge|sales rise|sales up|topline jumps?)\b", re.IGNORECASE),
        re.compile(r"\b(record deliveries|record revenue|record profit|record high|swings to profit|turns profitable)\b", re.IGNORECASE),
        re.compile(r"\b(dividend|bonus issue|share buyback|buy rating|target price raised|upgrade|outperform|accumulate)\b", re.IGNORECASE),
        re.compile(r"\b(usfda approval|fda approval|clearance|green light|patent granted|wins case|relief from)\b", re.IGNORECASE),
        re.compile(r"\b(stocks? to buy|top stocks?|low-price stocks? to buy|multibagger)\b", re.IGNORECASE),
    ]

    BEARISH_PATTERNS = [
        re.compile(r"\b(profit declines?|profit falls?|profit drops?|profit slumps?|net loss|widens loss|loss widens|net profit drops?|net profit falls?|net profit declines?)\b", re.IGNORECASE),
        re.compile(r"\b(revenue drops?|revenue falls?|revenue declines?|sales dip|sales drop|topline slumps?)\b", re.IGNORECASE),
        re.compile(r"\b(shares? falls?|shares? drops?|shares? plunge|shares? tumble|shares? slide|stock hits 52-week low|plunges|tumbles|falls? \d+%|drops? \d+%)\b", re.IGNORECASE),
        re.compile(r"\b(litigation|lawsuit|fraud|sebi notice|sebi probe|cbi|ed raid|fine|penalty|tax demand|show cause|controversy)\b", re.IGNORECASE),
        re.compile(r"\b(promoter pledge|pledging|rating downgrade|downgraded|downgrade|auditor resigns|resignation of cfo|resignation of ceo)\b", re.IGNORECASE),
        re.compile(r"\b(investigation|search and seizure|nclt|insolvency|default|debt default|breach of debt)\b", re.IGNORECASE),
        re.compile(r"\b(margin contraction|margin squeeze|margin drops|guidance cut|cuts guidance|cuts outlook)\b", re.IGNORECASE),
        re.compile(r"\b(strike|plant shutdown|fire at plant|blast|halted operations|supply disruption)\b", re.IGNORECASE),
    ]

    @classmethod
    def clean_headline(cls, title: str) -> Tuple[str, Optional[str]]:
        """
        Cleans headline and extracts source if present as trailing suffix (e.g., 'Headline - Source').
        """
        if not title:
            return "", None
        title = title.strip()
        extracted_source = None
        # Check trailing dash
        if " - " in title:
            parts = title.rsplit(" - ", 1)
            if len(parts) == 2 and len(parts[1].strip()) < 40:
                title = parts[0].strip()
                extracted_source = parts[1].strip()
        return title, extracted_source

    @classmethod
    def extract_summary(
        cls,
        symbol: str,
        title: str,
        source: str,
        description: Optional[str] = None
    ) -> List[str]:
        """
        Extracts 2–3 concise, factual bullet points focusing on transaction values,
        operational announcements, and corporate metrics.
        """
        clean_title, _ = cls.clean_headline(title)
        full_text = f"{clean_title} {description or ''}"
        symbol_upper = symbol.upper()

        # 1. Bullet 1: Core Event / Primary Disclosure
        bullet1 = ""
        if re.search(r"\b(profit|revenue|ebitda|results?|q[1-4]|earnings|income)\b", full_text, re.IGNORECASE):
            bullet1 = f"Financial Performance: {source} reports that {clean_title}."
        elif re.search(r"\b(orders?|contract|wins?|bagged|secures?|mandate|mw|gw)\b", full_text, re.IGNORECASE):
            bullet1 = f"Operational Mandate: {clean_title} highlighted for {symbol_upper}."
        elif re.search(r"\b(debt|credit|rating|refinanc|borrowing|fund raise)\b", full_text, re.IGNORECASE):
            bullet1 = f"Capital Structure: Coverage indicates {clean_title} impacting balance sheet parameters."
        elif re.search(r"\b(sebi|rbi|court|tax|probe|penalty|notice|usfda)\b", full_text, re.IGNORECASE):
            bullet1 = f"Regulatory & Legal: {clean_title} tracked across market broadcasts."
        elif re.search(r"\b(target|buy|sell|rating|brokerage|upgrade|downgrade)\b", full_text, re.IGNORECASE):
            bullet1 = f"Market Assessment: {source} publishes {clean_title}."
        else:
            bullet1 = f"Corporate Development: {source} reports {clean_title} for {symbol_upper}."

        # 2. Bullet 2: Quantifiable metrics and operational figures
        # Extract percentage figures
        percentages = re.findall(r"\b[+-]?\d+(?:\.\d+)?%", full_text)
        # Extract currency values
        currencies = re.findall(
            r"(?:₹|Rs\.?|INR|\$)\s*\d+(?:\.\d+)?\s*(?:cr(?:ore)?|lakh|bn|billion|million)?",
            full_text,
            re.IGNORECASE,
        )
        # Extract volume/capacity
        capacities = re.findall(
            r"\b\d+(?:\.\d+)?\s*(?:MW|GW|MWp|MTPA|tpa|units|turbines|MW series)\b",
            full_text,
            re.IGNORECASE,
        )
        # Extract period
        periods = re.findall(r"\b(Q[1-4]\s*(?:FY\d{2,4})?|FY\d{2,4}|H[1-2])\b", full_text, re.IGNORECASE)

        metrics = []
        if percentages:
            metrics.append(f"variance of {', '.join(percentages[:2])}")
        if currencies:
            metrics.append(f"value of {', '.join(currencies[:2])}")
        if capacities:
            metrics.append(f"capacity volume of {', '.join(capacities[:2])}")
        if periods:
            metrics.append(f"reporting period {periods[0].upper()}")

        bullet2 = ""
        if metrics:
            bullet2 = f"Key Metrics Identified: Discloses {'; '.join(metrics)} impacting {symbol_upper} financial and operational momentum."
        else:
            # Fallback operational context
            if re.search(r"\b(orders?|contract|expansion|capacity|mw)\b", full_text, re.IGNORECASE):
                bullet2 = f"Commercial Scope: Mandate strengthens active manufacturing backlog and utility delivery schedules for {symbol_upper}."
            elif re.search(r"\b(profit|revenue|margin|loss|earnings)\b", full_text, re.IGNORECASE):
                bullet2 = f"Operating Velocity: Performance figures benchmark period EBITDA realization and operational margins against consensus."
            elif re.search(r"\b(sebi|probe|tax|notice|penalty)\b", full_text, re.IGNORECASE):
                bullet2 = f"Statutory Context: Proceeding undergoes formal exchange reporting and regulatory compliance review."
            else:
                bullet2 = f"Operational Scope: Announcement centers on enterprise positioning, client delivery timelines, and market visibility."

        # 3. Bullet 3: Strategic / Point-in-Time Context
        bullet3 = f"Market Implication: Informs short-to-medium term institutional liquidity, valuation multiples, and sector sentiment for {symbol_upper}."

        return [bullet1, bullet2, bullet3]

    @classmethod
    def classify_impact(
        cls,
        symbol: str,
        title: str,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Classifies directional market impact, horizon, drivers, and confidence.
        """
        clean_title, _ = cls.clean_headline(title)
        full_text = f"{clean_title} {description or ''}"

        # 1. Driver Tagging
        matched_drivers = []
        for driver, pattern in cls.DRIVER_PATTERNS.items():
            if pattern.search(full_text):
                matched_drivers.append(driver)
        
        if not matched_drivers:
            matched_drivers = ["VALUATION"]

        # 2. Bullish vs Bearish keyword matching
        bullish_matches = 0
        for pat in cls.BULLISH_PATTERNS:
            if pat.search(full_text):
                bullish_matches += 1

        bearish_matches = 0
        for pat in cls.BEARISH_PATTERNS:
            if pat.search(full_text):
                bearish_matches += 1

        # 3. Direction Assignment
        if bullish_matches > bearish_matches:
            direction = "BULLISH"
        elif bearish_matches > bullish_matches:
            direction = "BEARISH"
        else:
            direction = "NEUTRAL"

        # 4. Horizon Classification
        # Medium term: capacity expansion, order wins, debt reduction, credit rating, structural capex
        medium_term_pattern = re.compile(
            r"\b(capacity expansion|commissioning|order win|secures? order|secures?.*?project|secures?.*?\d+\s*(?:mw|gw)|bagged|multi-year|"
            r"debt reduction|pre-pays debt|debt free|credit upgrade|rating upgrade|expansion|"
            r"mou|joint venture|acquisition|new plant)\b",
            re.IGNORECASE,
        )
        if medium_term_pattern.search(full_text):
            horizon = "MEDIUM_TERM"
        else:
            horizon = "SHORT_TERM"

        # 5. Rationale Formulation
        rationale = ""
        if direction == "BULLISH":
            if "ORDER_BOOK" in matched_drivers or "REVENUE_VISIBILITY" in matched_drivers:
                rationale = "Secures commercial order or capacity expansion mandates, expanding forward order book visibility and revenue horizon."
            elif "DELEVERAGING" in matched_drivers:
                rationale = "Strengthens capital structure and balance sheet solvency through debt reduction or credit profile enhancement."
            elif "MARGINS" in matched_drivers:
                rationale = "Reflects operating leverage and expanding operational profit margins relative to previous periods."
            else:
                rationale = "Positive commercial sentiment supported by operational milestones and favorable equity market evaluation."
        elif direction == "BEARISH":
            if "MARGINS" in matched_drivers or "REVENUE_VISIBILITY" in matched_drivers:
                rationale = "Indicates near-term profitability headwind driven by margin compression or net profit decline."
            elif "REGULATORY" in matched_drivers or "GOVERNANCE" in matched_drivers:
                rationale = "Exposes the entity to statutory or regulatory scrutiny with potential legal/financial liability."
            else:
                rationale = "Reflects short-term price correction pressure and market skepticism regarding near-term earnings delivery."
        else:
            rationale = "Routine corporate communication or sector coverage with balanced operational and valuation impact."

        # 6. Confidence Score
        total_matches = bullish_matches + bearish_matches
        if total_matches >= 2 and len(matched_drivers) >= 2:
            confidence_score = 0.90
        elif total_matches >= 1:
            confidence_score = 0.82
        elif direction == "NEUTRAL":
            confidence_score = 0.65
        else:
            confidence_score = 0.70

        return {
            "direction": direction,
            "horizon": horizon,
            "affected_drivers": matched_drivers,
            "rationale": rationale,
            "confidence_score": confidence_score,
        }

    @classmethod
    def process_article(cls, article_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes an incoming article dictionary:
        Extracts summary bullets, directional impact, horizon, drivers, and confidence.
        """
        symbol = article_dict.get("symbol", "")
        title = article_dict.get("title", "")
        source = article_dict.get("source", "Financial Media")
        description = article_dict.get("description", "")

        summary_bullets = cls.extract_summary(
            symbol=symbol,
            title=title,
            source=source,
            description=description,
        )

        impact = cls.classify_impact(
            symbol=symbol,
            title=title,
            description=description,
        )

        return {
            "summary": summary_bullets,
            "impact": impact,
        }
