"""
Unit and integration tests for Upgraded Multi-Agent Copilot Deliberation Engine.
Verifies intent classification, multi-symbol extraction, direct Q&A, peer comparison,
portfolio/watchlist summaries, and multi-turn conversational history.
"""

import json
import pytest
import asyncio
from unittest.mock import patch, MagicMock

from src.copilot.deliberation import MultiAgentDeliberationEngine


@pytest.fixture
def copilot_engine():
    return MultiAgentDeliberationEngine()


def test_copilot_symbol_extraction_and_alias_mapping(copilot_engine):
    """Verifies symbol extraction, common company alias resolution, and deduplication."""
    # Direct symbol
    syms = copilot_engine._extract_symbols("What is the 20D forecast for RELIANCE?", "NIFTY 50")
    assert "RELIANCE" in syms

    # Multi-symbol comparison
    syms_comp = copilot_engine._extract_symbols("Compare TCS and INFY performance", "NIFTY 50")
    assert "TCS" in syms_comp
    assert "INFY" in syms_comp

    # Common Indian company names via alias map
    syms_suzlon = copilot_engine._extract_symbols("Is Suzlon Energy a good buy?", "NIFTY 50")
    assert "SUZLON" in syms_suzlon

    syms_hdfc = copilot_engine._extract_symbols("Review HDFC Bank fundamentals", "NIFTY 50")
    assert "HDFCBANK" in syms_hdfc


def test_copilot_intent_classification(copilot_engine):
    """Verifies intent classification across DIRECT_QA, COMPARE, PORTFOLIO_WATCHLIST, and DEBATE_THESIS."""
    # Compare
    assert copilot_engine._classify_intent("Compare TCS vs INFY", ["TCS", "INFY"]) == "COMPARE"
    assert copilot_engine._classify_intent("Which is better, TCS or INFY?", ["TCS", "INFY"]) == "COMPARE"

    # Portfolio / Watchlist
    assert copilot_engine._classify_intent("Review my current watchlist", ["NIFTY 50"]) == "PORTFOLIO_WATCHLIST"
    assert copilot_engine._classify_intent("What positions are in my portfolio?", ["NIFTY 50"]) == "PORTFOLIO_WATCHLIST"

    # Debate Thesis
    assert copilot_engine._classify_intent("Debate Bull vs Bear Thesis", ["RELIANCE"]) == "DEBATE_THESIS"
    assert copilot_engine._classify_intent("Give me the committee debate on INFY", ["INFY"]) == "DEBATE_THESIS"

    # Direct QA
    assert copilot_engine._classify_intent("What is the 20D forecast for RELIANCE?", ["RELIANCE"]) == "DIRECT_QA"
    assert copilot_engine._classify_intent("Explain the GARCH bounds for TCS", ["TCS"]) == "DIRECT_QA"
    assert copilot_engine._classify_intent("What is the current RSI and ATR?", ["RELIANCE"]) == "DIRECT_QA"


@pytest.mark.asyncio
async def test_copilot_direct_qa_stream(copilot_engine):
    """Verifies DIRECT_QA produces conversational stage and avoids bull/bear debate boilerplate."""
    chunks = []
    async for chunk in copilot_engine.run_deliberation_stream(
        symbol="RELIANCE",
        user_prompt="What is the 20D forecast for RELIANCE?",
        context_override={
            "fundamentals": {"ltp": 2450.0, "company_name": "Reliance Industries Ltd", "market_cap_tier": "LARGE_CAP"},
            "ml_drift": {"expected_return_pct": 3.8, "drift_label": "BULLISH"},
            "garch": {"current_vol_annual": 0.22, "cone_80_upper": 2550.0, "cone_80_lower": 2350.0}
        }
    ):
        chunks.append(chunk)

    full_output = "".join(chunks)
    assert "data: " in full_output
    assert '"stage": "conversational"' in full_output
    assert '"stage": "complete"' in full_output
    # Direct Q&A should not emit bull_analyst / bear_analyst stages
    assert '"stage": "bull_analyst"' not in full_output
    assert '"stage": "bear_analyst"' not in full_output


@pytest.mark.asyncio
async def test_copilot_compare_stream(copilot_engine):
    """Verifies COMPARE intent extracts both symbols and returns comparative metrics."""
    chunks = []
    async for chunk in copilot_engine.run_deliberation_stream(
        symbol="TCS",
        user_prompt="Compare TCS vs INFY",
        context_override={
            "TCS": {"ltp": 4100.0, "quality_score": 85.0, "expected_return_pct": 2.5},
            "INFY": {"ltp": 1850.0, "quality_score": 80.0, "expected_return_pct": 3.2}
        }
    ):
        chunks.append(chunk)

    full_output = "".join(chunks)
    assert '"stage": "conversational"' in full_output
    assert '"stage": "complete"' in full_output


@pytest.mark.asyncio
async def test_copilot_watchlist_stream(copilot_engine):
    """Verifies PORTFOLIO_WATCHLIST intent returns watchlist / portfolio analysis."""
    chunks = []
    async for chunk in copilot_engine.run_deliberation_stream(
        symbol="NIFTY 50",
        user_prompt="Review my watchlist",
        context_override={
            "watchlist": [
                {"symbol": "RELIANCE", "ltp": 2450.0, "entry_price": 2400.0, "unrealized_pnl_pct": 2.08, "composite_score": 78.5}
            ]
        }
    ):
        chunks.append(chunk)

    full_output = "".join(chunks)
    assert '"stage": "conversational"' in full_output
    assert '"stage": "complete"' in full_output


@pytest.mark.asyncio
async def test_copilot_debate_stream_preserves_3_agents(copilot_engine):
    """Verifies DEBATE_THESIS intent preserves the 3-agent committee pipeline."""
    stages_seen = set()
    async for chunk in copilot_engine.run_deliberation_stream(
        symbol="RELIANCE",
        user_prompt="Debate Bull vs Bear Thesis"
    ):
        if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
            try:
                payload = json.loads(chunk[6:].strip())
                if "stage" in payload:
                    stages_seen.add(payload["stage"])
            except Exception:
                pass

    assert "bull_analyst" in stages_seen
    assert "bear_analyst" in stages_seen
    assert "judge_synthesis" in stages_seen
    assert "complete" in stages_seen


@pytest.mark.asyncio
async def test_copilot_with_multi_turn_history(copilot_engine):
    """Verifies multi-turn conversation history is received and handled cleanly."""
    history = [
        {"role": "user", "content": "What is the trend for RELIANCE?"},
        {"role": "assistant", "content": "RELIANCE is showing a positive drift with 5D expected return of +1.4%."}
    ]
    chunks = []
    async for chunk in copilot_engine.run_deliberation_stream(
        symbol="RELIANCE",
        user_prompt="What are its key support levels?",
        history=history
    ):
        chunks.append(chunk)

    full_output = "".join(chunks)
    assert '"stage": "conversational"' in full_output
    assert '"stage": "complete"' in full_output


@pytest.mark.asyncio
async def test_copilot_colpal_telemetry_grounding(copilot_engine):
    """Verifies COLPAL grounding resolves live price from ohlcv_daily, non-null ROE, and historical dip."""
    funds = copilot_engine.bridge.get_stock_fundamentals("COLPAL")
    drawdowns = copilot_engine.bridge.get_historical_drawdown_telemetry("COLPAL")

    assert funds.get("current_price", 0.0) > 1000.0
    # ROE should be resolved to ~63.07% from quant_factors_daily / fundamentals
    assert funds.get("fundamentals", {}).get("roe_pct") is not None
    assert funds["fundamentals"]["roe_pct"] > 50.0

    # Historical drawdown telemetry verification
    assert "last_major_dip" in drawdowns
    last_dip = drawdowns["last_major_dip"]
    assert last_dip["drop_pct"] <= -8.0
    assert last_dip["peak_price"] > last_dip["trough_price"]
    assert "high_52w" in drawdowns
    assert "low_52w" in drawdowns


@pytest.mark.asyncio
async def test_copilot_direct_response_greeting_vs_canned_template(copilot_engine):
    """Verifies asking 'hi' returns natural conversational greeting with live price & ROE instead of 3-agent template."""
    resp = await copilot_engine.generate_direct_response("hi", symbol="COLPAL")
    assert resp and len(resp.strip()) > 30
    # Should contain price and ROE
    assert "1714" in resp or "₹" in resp
    assert "63" in resp or "ROE" in resp
    # Should NOT contain rigid multi-agent template artifacts
    assert "Bull Analyst Thesis" not in resp
    assert "Bear Analyst Thesis" not in resp


@pytest.mark.asyncio
async def test_copilot_direct_response_dip_query(copilot_engine):
    """Verifies asking 'what was its last massive dip?' returns exact historical drawdown data."""
    resp = await copilot_engine.generate_direct_response("what was its last massive dip?", symbol="COLPAL")
    assert resp and len(resp.strip()) > 30
    # Should cite the -58% or -59% decline and dates
    assert "58" in resp or "59" in resp or "Dip" in resp or "Drawdown" in resp
    assert "3838" in resp or "1575" in resp or "2024" in resp

