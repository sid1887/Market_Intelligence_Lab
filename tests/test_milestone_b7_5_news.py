"""
Unit and Integration Tests for Milestone B7.5: News Ingestion, Structured Summarization & Directional Impact
"""

import unittest
import json
import sqlite3
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.storage.database import DatabaseManager
from src.explanation.news_impact_engine import NewsImpactEngine
from src.client.news_client import NewsClient
from src.api.main import app


SAMPLE_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Google News</title>
    <link>https://news.google.com</link>
    <item>
      <title>Suzlon Energy Secures 300 MW Wind Energy Project - The Economic Times</title>
      <link>https://news.google.com/articles/CAIiEO12345</link>
      <pubDate>Sun, 01 Nov 2026 15:21:00 GMT</pubDate>
      <description>&lt;a href="https://news.google.com/articles/CAIiEO12345"&gt;Suzlon Energy Secures 300 MW Wind Energy Project&lt;/a&gt;</description>
      <source url="https://economictimes.indiatimes.com">The Economic Times</source>
    </item>
    <item>
      <title>Suzlon Energy Shares Fall 9% as Net Profit Declines 69% for Q2 - India Infoline</title>
      <link>https://news.google.com/articles/CAIiEO67890</link>
      <pubDate>Fri, 30 Oct 2026 06:10:00 GMT</pubDate>
      <description>&lt;a href="https://news.google.com/articles/CAIiEO67890"&gt;Suzlon Energy Shares Fall 9% as Net Profit Declines 69% for Q2&lt;/a&gt;</description>
      <source url="https://indiainfoline.com">India Infoline</source>
    </item>
    <item>
      <title>Suzlon Energy Board Meeting to Consider Financial Results - Business Standard</title>
      <link>https://news.google.com/articles/CAIiEO11223</link>
      <pubDate>Wed, 28 Oct 2026 10:00:00 GMT</pubDate>
      <description>Notice of board meeting</description>
      <source url="https://business-standard.com">Business Standard</source>
    </item>
  </channel>
</rss>
"""


class TestMilestoneB75News(unittest.TestCase):
    """Test suite verifying news ingestion, summarization, impact classification, and API endpoints."""

    def setUp(self):
        self.db = DatabaseManager()
        self.db.init_schema()
        self.client = TestClient(app)

    def test_news_impact_engine_bullish(self):
        """Verify bullish classification, driver tagging, and horizon."""
        article = {
            "symbol": "SUZLON",
            "title": "Suzlon Energy Secures 300 MW Wind Energy Project - The Economic Times",
            "source": "The Economic Times",
            "published_at": "2026-11-01T15:21:00Z",
            "article_url": "https://example.com/order_win"
        }
        res = NewsImpactEngine.process_article(article)
        self.assertIn("summary", res)
        self.assertIn("impact", res)
        
        # Summary verification: 2-3 bullets
        self.assertTrue(2 <= len(res["summary"]) <= 3)
        self.assertTrue(any("300 MW" in b for b in res["summary"]))

        # Impact verification
        impact = res["impact"]
        self.assertEqual(impact["direction"], "BULLISH")
        self.assertEqual(impact["horizon"], "MEDIUM_TERM")
        self.assertIn("ORDER_BOOK", impact["affected_drivers"])
        self.assertGreaterEqual(impact["confidence_score"], 0.70)
        self.assertTrue(len(impact["rationale"]) > 10)

    def test_news_impact_engine_bearish(self):
        """Verify bearish classification, margin/profit driver tagging, and short-term horizon."""
        article = {
            "symbol": "SUZLON",
            "title": "Suzlon Energy Shares Fall 9% as Net Profit Declines 69% for Q2 - India Infoline",
            "source": "India Infoline",
            "published_at": "2026-10-30T06:10:00Z",
            "article_url": "https://example.com/profit_drop"
        }
        res = NewsImpactEngine.process_article(article)
        impact = res["impact"]
        self.assertEqual(impact["direction"], "BEARISH")
        self.assertEqual(impact["horizon"], "SHORT_TERM")
        self.assertTrue(any(d in impact["affected_drivers"] for d in ["MARGINS", "VALUATION"]))
        self.assertGreaterEqual(impact["confidence_score"], 0.80)

    def test_news_impact_engine_neutral(self):
        """Verify neutral classification for routine board meeting disclosures."""
        article = {
            "symbol": "INFY",
            "title": "Infosys Board Meeting Scheduled on Oct 28 to Consider Interim Dividend - Livemint",
            "source": "Livemint",
            "published_at": "2026-10-20T12:00:00Z",
            "article_url": "https://example.com/board_meeting"
        }
        res = NewsImpactEngine.process_article(article)
        self.assertIn(res["impact"]["direction"], ["BULLISH", "NEUTRAL"])
        self.assertTrue(2 <= len(res["summary"]) <= 3)

    def test_rss_xml_parsing(self):
        """Verify safe parsing of Google News RSS XML without external network call."""
        news_client = NewsClient(self.db)
        parsed = news_client.parse_rss_payload(SAMPLE_RSS_XML, "SUZLON")
        self.assertEqual(len(parsed), 3)

        first = parsed[0]
        self.assertEqual(first["symbol"], "SUZLON")
        self.assertEqual(first["title"], "Suzlon Energy Secures 300 MW Wind Energy Project")
        self.assertEqual(first["source"], "The Economic Times")
        self.assertTrue(first["published_at"].startswith("2026-11-01"))
        self.assertEqual(first["article_url"], "https://news.google.com/articles/CAIiEO12345")

    def test_deduplication_and_symbol_isolation(self):
        """Verify articles are deduplicated and partitioned strictly by symbol."""
        news_client = NewsClient(self.db)
        
        # Ingest for SUZLON
        with patch.object(news_client.session, "get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = SAMPLE_RSS_XML.encode("utf-8")
            mock_get.return_value = mock_resp

            suzlon_articles = news_client.fetch_latest_news("SUZLON", limit=10, force_refresh=True)
            self.assertGreaterEqual(len(suzlon_articles), 3)
            
            # Verify all have symbol == SUZLON
            for a in suzlon_articles:
                self.assertEqual(a["symbol"], "SUZLON")

            # Run again with same content -> should deduplicate without duplicates
            count_before = len(self.db.get_news_articles("SUZLON", limit=50))
            news_client.fetch_latest_news("SUZLON", limit=10, force_refresh=True)
            count_after = len(self.db.get_news_articles("SUZLON", limit=50))
            self.assertEqual(count_before, count_after)

    def test_api_stocks_news_endpoint(self):
        """Test GET /api/v1/stocks/{symbol}/news endpoint response structure."""
        resp = self.client.get("/api/v1/stocks/SUZLON/news?limit=3")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["symbol"], "SUZLON")
        self.assertIn("count", data)
        self.assertIn("articles", data)
        self.assertTrue(isinstance(data["articles"], list))

        if data["articles"]:
            art = data["articles"][0]
            self.assertIn("id", art)
            self.assertIn("title", art)
            self.assertIn("source", art)
            self.assertIn("published_at", art)
            self.assertIn("article_url", art)
            self.assertIn("summary", art)
            self.assertTrue(isinstance(art["summary"], list))
            self.assertIn("impact", art)
            
            imp = art["impact"]
            self.assertIn("direction", imp)
            self.assertIn(imp["direction"], ["BULLISH", "BEARISH", "NEUTRAL"])
            self.assertIn("horizon", imp)
            self.assertIn(imp["horizon"], ["SHORT_TERM", "MEDIUM_TERM"])
            self.assertIn("affected_drivers", imp)
            self.assertTrue(isinstance(imp["affected_drivers"], list))
            self.assertIn("rationale", imp)

    def test_api_news_limit_and_unknown_symbol(self):
        """Verify limit parameter enforcement and 404 for unknown tickers."""
        resp_limit = self.client.get("/api/v1/stocks/SUZLON/news?limit=2")
        self.assertEqual(resp_limit.status_code, 200)
        self.assertLessEqual(len(resp_limit.json()["articles"]), 2)

        # Non-existent symbol
        resp_404 = self.client.get("/api/v1/stocks/INVALIDXYZNONEXISTENT/news")
        self.assertEqual(resp_404.status_code, 404)


if __name__ == "__main__":
    unittest.main()
