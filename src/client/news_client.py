"""
Market Intelligence Lab: Structured News Aggregator & RSS Ingestion Client
Milestone: B7.5 (News Ingestion, Structured Summarization & Directional Impact Engine)

Ingests live, ticker-specific financial media articles via structured Google News RSS
and exchange-linked public feeds. Uses standard xml.etree.ElementTree for safe,
unbreakable XML parsing (no brittle HTML scraping).
Integrates with NewsImpactEngine and DatabaseManager.
"""

import os
import re
import hashlib
import urllib.parse
import email.utils
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import xml.etree.ElementTree as ET
import requests

from src.storage.database import DatabaseManager
from src.explanation.news_impact_engine import NewsImpactEngine
from src.config import is_network_allowed


class NewsClient:
    """
    Ingests, deduplicates, and structures equity news from verified RSS feeds.
    """

    GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    }

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)

    def _resolve_company_name(self, symbol: str) -> str:
        """
        Resolves company name from securities_master or user_watchlists,
        cleaning corporate entity suffixes (Ltd, Limited, etc.).
        """
        symbol_upper = symbol.upper()
        # 1. Check user watchlists
        watchlists = self.db.get_user_watchlists(symbol_upper)
        company_name = ""
        if watchlists and watchlists[0].get("company_name"):
            company_name = watchlists[0]["company_name"]
        else:
            # 2. Check securities master
            secs = self.db.get_securities_master(symbol_upper)
            if secs and secs[0].get("company_name"):
                company_name = secs[0]["company_name"]

        if not company_name:
            return symbol_upper

        # Clean corporate suffixes for optimal search query recall
        cleaned = re.sub(r"\b(Limited|Ltd\.?|Corp\.?|Corporation|Inc\.?|Enterprise|Holdings?)\b", "", company_name, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or symbol_upper

    def build_rss_url(self, symbol: str, days: int = 7) -> str:
        """
        Constructs the structured Google News RSS query URL.
        """
        company_name = self._resolve_company_name(symbol)
        query = f"{company_name} {symbol.upper()} NSE India when:{days}d"
        params = {
            "q": query,
            "hl": "en-IN",
            "gl": "IN",
            "ceid": "IN:en",
        }
        return f"{self.GOOGLE_NEWS_RSS_URL}?{urllib.parse.urlencode(params)}"

    def parse_rss_payload(self, xml_content: str or bytes, symbol: str) -> List[Dict[str, Any]]:
        """
        Parses Google News RSS XML safely using xml.etree.ElementTree.
        Extracts title, clean source, publication timestamp, and link.
        """
        if isinstance(xml_content, str):
            xml_bytes = xml_content.encode("utf-8")
        else:
            xml_bytes = xml_content

        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as e:
            # Handle possible XML parse error
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        items = channel.findall("item")
        parsed_articles = []
        symbol_upper = symbol.upper()

        for item in items:
            raw_title = item.findtext("title") or ""
            link = item.findtext("link") or ""
            pub_date_str = item.findtext("pubDate") or ""
            description = item.findtext("description") or ""

            # Extract source tag
            source_elem = item.find("source")
            if source_elem is not None and source_elem.text:
                source_name = source_elem.text.strip()
            else:
                _, extracted_src = NewsImpactEngine.clean_headline(raw_title)
                source_name = extracted_src or "Financial Media"

            # Clean headline
            title, extracted_src = NewsImpactEngine.clean_headline(raw_title)
            if not source_name or source_name == "Financial Media":
                source_name = extracted_src or "Financial Media"

            if not title or not link:
                continue

            # Parse RFC 2822 date to ISO-8601 UTC (P0-10: Unknown published_at remains None)
            published_at = None
            if pub_date_str:
                try:
                    dt = email.utils.parsedate_to_datetime(pub_date_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.astimezone(timezone.utc)
                    published_at = dt.isoformat()
                except Exception:
                    published_at = None

            parsed_articles.append({
                "symbol": symbol_upper,
                "title": title,
                "source": source_name,
                "published_at": published_at,
                "article_url": link,
                "description": description,
            })

        return parsed_articles

    @staticmethod
    def _generate_article_id(symbol: str, published_at: str, article_url: str) -> str:
        """
        Generates a deterministic ID: NEWS_{symbol}_{YYYYMMDD}_{hash[:8]}
        """
        date_str = published_at[:10].replace("-", "") if len(published_at) >= 10 else "RECENT"
        url_hash = hashlib.sha256(article_url.encode("utf-8")).hexdigest()[:8]
        return f"NEWS_{symbol.upper()}_{date_str}_{url_hash}"

    def fetch_latest_news(
        self,
        symbol: str,
        limit: int = 10,
        days: int = 7,
        force_refresh: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Fetches live RSS news, deduplicates against existing records,
        runs impact & summary processing, and stores in equity_news_feed.
        Returns the combined/ordered list of articles for this symbol.
        """
        symbol_upper = symbol.upper()

        # 1. If not forcing refresh, check if we have fresh cached articles (within 4 hours)
        if not force_refresh:
            latest_fetch = self.db.get_latest_news_timestamp(symbol_upper)
            if latest_fetch:
                try:
                    fetch_dt = datetime.fromisoformat(latest_fetch)
                    if fetch_dt.tzinfo is None:
                        fetch_dt = fetch_dt.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) - fetch_dt < timedelta(hours=4):
                        cached = self.db.get_news_articles(symbol_upper, limit=limit)
                        if cached:
                            return cached
                except Exception:
                    pass

        # 2. Fetch external RSS feed (P0-10: Guarded by network governance or explicit force_refresh)
        raw_items: List[Dict[str, Any]] = []
        if is_network_allowed() or force_refresh or os.getenv("ENABLE_LIVE_INGESTION") == "1":
            url = self.build_rss_url(symbol_upper, days=days)
            try:
                resp = self.session.get(url, timeout=10)
                if resp.status_code == 200:
                    raw_items = self.parse_rss_payload(resp.content, symbol_upper)
            except Exception as e:
                # Graceful network error fallback
                pass

        # 3. Process, deduplicate, and persist new items
        new_records = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for item in raw_items:
            # Check deduplication by URL and normalized title
            norm_title = re.sub(r"[^a-zA-Z0-9]", "", item["title"].lower())
            if self.db.article_exists(symbol_upper, item["article_url"], norm_title):
                continue

            # Process summary & impact
            processed = NewsImpactEngine.process_article(item)
            summary_bullets = processed["summary"]
            impact = processed["impact"]

            article_id = self._generate_article_id(
                symbol=symbol_upper,
                published_at=item["published_at"],
                article_url=item["article_url"]
            )

            new_record = {
                "id": article_id,
                "symbol": symbol_upper,
                "title": item["title"],
                "source": item["source"],
                "published_at": item["published_at"],
                "article_url": item["article_url"],
                "summary_bullets": summary_bullets,
                "impact_direction": impact["direction"],
                "impact_horizon": impact["horizon"],
                "impact_drivers": impact.get("affected_drivers", []),
                "impact_rationale": impact.get("rationale", ""),
                "confidence_score": impact.get("confidence_score", 1.0),
                "fetched_at": now_iso,
            }
            new_records.append(new_record)

        if new_records:
            self.db.insert_news_articles(new_records)

        # 4. Return top articles from database ordered by published_at DESC
        return self.db.get_news_articles(symbol_upper, limit=limit)
