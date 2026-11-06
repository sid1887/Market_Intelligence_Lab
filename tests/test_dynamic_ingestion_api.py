"""
tests/test_dynamic_ingestion_api.py

Verifies Phase 1 to Phase 4 endpoints:
1. Universal Dynamic Ingestion route (POST /api/v1/system/ingest).
2. Live News route (GET /api/v1/news/{symbol} and GET /news/{symbol}).
3. Conversational Copilot routing (casual queries return conversational guidance with live metrics; analytical queries trigger multi-agent committee).
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.api.main import app
from src.copilot.deliberation import MultiAgentDeliberationEngine

client = TestClient(app)


def test_system_ingest_endpoint():
    """Verify POST /api/v1/system/ingest returns success status and updates settled date without test DB contamination."""
    with patch("src.pipeline.universe_ingestion.UniverseIngestionManager.execute_universe_ingestion") as mock_ingest:
        mock_ingest.return_value = {
            "status": "SUCCESS",
            "settled_date": "2026-11-06",
            "symbols_updated": 181,
            "records_ingested": 181,
            "factors_computed": 181,
            "duration_seconds": 1.2,
            "message": "Successfully ingested live session data."
        }
        res = client.post("/api/v1/system/ingest?background=false")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert "settled_date" in data
        assert data["symbols_updated"] > 100
        assert data["factors_computed"] > 100


def test_live_news_routes():
    """Verify GET /api/v1/news/{symbol} and GET /news/{symbol} return structured news with impact analysis."""
    for path in ["/api/v1/news/SUZLON", "/news/SUZLON"]:
        res = client.get(path)
        assert res.status_code == 200
        data = res.json()
        assert data["symbol"] == "SUZLON"
        assert "articles" in data
        assert len(data["articles"]) > 0
        art = data["articles"][0]
        assert "title" in art
        assert "impact" in art
        assert "direction" in art["impact"]


@pytest.mark.asyncio
async def test_copilot_conversational_routing():
    """Verify copilot routes conversational queries to direct conversational guidance with live metrics."""
    engine = MultiAgentDeliberationEngine()

    stages = []
    conversational_text = ""
    async for event in engine.run_deliberation_stream("SUZLON", user_prompt="hello"):
        if "conversational" in event:
            import json
            data = json.loads(event.replace("data: ", "").strip())
            stages.append(data.get("stage"))
            if data.get("conversational_response"):
                conversational_text = data["conversational_response"]

    assert "conversational" in stages
    assert "SUZLON" in conversational_text
    assert "Settled Price" in conversational_text


@pytest.mark.asyncio
async def test_copilot_analytical_deliberation():
    """Verify copilot routes analytical queries to 3-agent committee."""
    engine = MultiAgentDeliberationEngine()

    stages = []
    async for event in engine.run_deliberation_stream("SUZLON", user_prompt="Debate Bull vs Bear Thesis"):
        if "stage" in event:
            import json
            data = json.loads(event.replace("data: ", "").strip())
            st = data.get("stage")
            if st and st not in stages:
                stages.append(st)

    assert "bull_analyst" in stages
    assert "bear_analyst" in stages
    assert "judge_synthesis" in stages
    assert "complete" in stages
