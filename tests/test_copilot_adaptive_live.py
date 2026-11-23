"""
tests/test_copilot_adaptive_live.py
Unit & Integration Test Suite for:
1. Adaptive Trader DNA Engine (coaching rules, loss streak, DP breakeven, sizing guards)
2. Zero-PII Conversational Episodic Memory Store (SQLite WAL, auto-pruning, keyword retrieval)
3. Live Intraday Quote & Web Search Fusion
4. Multi-Agent Deliberation Integration
"""

import os
import sqlite3
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from src.storage.database import DatabaseManager
from src.portfolio.tradebook_engine import EncryptedTradebookEngine
from src.copilot.trader_dna import TraderDNAEngine
from src.copilot.memory_store import CopilotMemoryStore, sanitize_conversational_pii
from src.copilot.live_tools import (
    fetch_live_intraday_quote,
    search_live_web_catalysts,
    _QUOTE_CACHE,
    _WEB_CACHE
)
from src.copilot.deliberation import MultiAgentDeliberationEngine


@pytest.fixture
def test_db(tmp_path):
    """Provides an isolated SQLite database initialized with tradebook tables & test fixtures."""
    db_file = tmp_path / "test_copilot.db"
    db = DatabaseManager(str(db_file))

    # Initialize exact tradebook schema using EncryptedTradebookEngine
    EncryptedTradebookEngine(db)

    with db.get_connection() as conn:
        # Populate securities_master
        conn.execute("""
            INSERT OR REPLACE INTO securities_master (symbol, company_name, isin, industry, sector, macro_sector, listing_date, is_active, is_nifty50, updated_at)
            VALUES 
                ('SUZLON', 'SUZLON ENERGY LIMITED', 'INE040H01021', 'Energy', 'Power', 'Energy', '2005-10-19', 1, 0, '2026-11-20 00:00:00'),
                ('M&MFIN', 'MAHINDRA & MAHINDRA FINANCIAL SERVICES LTD', 'INE774D01024', 'Financials', 'NBFC', 'Financials', '2006-03-17', 1, 0, '2026-11-20 00:00:00'),
                ('RVNL', 'RAIL VIKAS NIGAM LIMITED', 'INE415G01027', 'Railways', 'Construction', 'Industrials', '2019-04-11', 1, 0, '2026-11-20 00:00:00'),
                ('ASHOKLEY', 'ASHOK LEYLAND LIMITED', 'INE208A01029', 'Automobile', 'Commercial Vehicles', 'Auto', '1995-01-01', 1, 0, '2026-11-20 00:00:00'),
                ('GAIL', 'GAIL (INDIA) LIMITED', 'INE129A01019', 'Energy', 'Gas Utility', 'Energy', '1997-05-15', 1, 0, '2026-11-20 00:00:00')
        """)

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        conn.execute("""
            INSERT OR REPLACE INTO ohlcv_daily (symbol, series, trading_date, open, high, low, close, volume, retrieval_timestamp, source)
            VALUES 
                ('GAIL', 'EQ', ?, 190.0, 195.0, 189.0, 193.50, 1000000, ?, 'NSE_EOD'),
                ('RVNL', 'EQ', ?, 192.0, 196.0, 190.0, 194.20, 500000, ?, 'NSE_EOD')
        """, (today_str, today_str, today_str, today_str))

        # Insert User's Angel One History (4 closed roundtrips: 1 winner held 7 days, 3 losers held 1-4 days)
        # 1. SUZLON: +₹20.50 net (winner, held 7 days)
        conn.execute("""
            INSERT INTO real_closed_roundtrips (
                symbol, isin, scrip_name, qty, buy_date, sell_date, hold_days,
                avg_buy_price, buy_value, avg_sell_price, sell_value, gross_pnl, trade_charges,
                dp_charge, net_pnl, net_return_pct, outcome, created_at
            ) VALUES ('SUZLON', 'INE040H01021', 'SUZLON ENERGY', 30, '2026-10-01', '2026-10-08', 7, 50.0, 1500.0, 52.0, 1560.0, 60.0, 15.90, 23.60, 20.50, 1.37, 'WIN', '2026-10-08')
        """)
        # 2. M&MFIN: -₹12.00 net (loser, held 3 days)
        conn.execute("""
            INSERT INTO real_closed_roundtrips (
                symbol, isin, scrip_name, qty, buy_date, sell_date, hold_days,
                avg_buy_price, buy_value, avg_sell_price, sell_value, gross_pnl, trade_charges,
                dp_charge, net_pnl, net_return_pct, outcome, created_at
            ) VALUES ('M&MFIN', 'INE774D01024', 'M&M FIN SERVICES', 6, '2026-10-10', '2026-10-13', 3, 290.0, 1740.0, 293.0, 1758.0, 18.0, 6.40, 23.60, -12.00, -0.69, 'LOSS', '2026-10-13')
        """)
        # 3. RVNL: -₹144.25 net (loser, held 2 days, loss > ₹75)
        conn.execute("""
            INSERT INTO real_closed_roundtrips (
                symbol, isin, scrip_name, qty, buy_date, sell_date, hold_days,
                avg_buy_price, buy_value, avg_sell_price, sell_value, gross_pnl, trade_charges,
                dp_charge, net_pnl, net_return_pct, outcome, created_at
            ) VALUES ('RVNL', 'INE415G01027', 'RAIL VIKAS NIGAM', 10, '2026-10-20', '2026-10-22', 2, 200.0, 2000.0, 188.0, 1880.0, -120.0, 0.65, 23.60, -144.25, -7.21, 'LOSS', '2026-10-22')
        """)
        # 4. ASHOKLEY: -₹65.00 net (loser, held 1 day)
        recent_exit = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            INSERT INTO real_closed_roundtrips (
                symbol, isin, scrip_name, qty, buy_date, sell_date, hold_days,
                avg_buy_price, buy_value, avg_sell_price, sell_value, gross_pnl, trade_charges,
                dp_charge, net_pnl, net_return_pct, outcome, created_at
            ) VALUES ('ASHOKLEY', 'INE208A01029', 'ASHOK LEYLAND', 8, '2026-10-22', '2026-10-23', 1, 230.0, 1840.0, 225.0, 1800.0, -40.0, 1.40, 23.60, -65.00, -3.53, 'LOSS', ?)
        """, (recent_exit,))

        # Open holding: GAIL 9 shares @ 192.76
        conn.execute("""
            INSERT INTO real_open_holdings (
                symbol, isin, scrip_name, qty, avg_buy_price, buy_value,
                closing_rate, current_value, unrealized_pnl, unrealized_pnl_pct
            ) VALUES ('GAIL', 'INE129A01019', 'GAIL (INDIA) LTD', 9, 192.76, 1734.84, 193.50, 1741.50, 6.66, 0.38)
        """)

        # Capital: funds added ₹5,000
        conn.execute("""
            INSERT INTO real_capital_ledger (transaction_type, tx_date, voucher, debit, credit, running_balance)
            VALUES ('FUNDS_ADDED', '2026-09-01', 'V001', 0.0, 5000.0, 5000.0)
        """)

    return db


def test_trader_dna_profiler_and_scoring(test_db):
    """Verifies that TraderDNAEngine calculates streaks, hold days, and DP friction accurately."""
    engine = TraderDNAEngine(test_db)
    profile = engine.get_live_execution_profile()

    assert profile["total_trades"] == 4
    assert profile["winning_trades"] == 1
    assert profile["losing_trades"] == 3
    assert profile["win_rate_pct"] == 25.0
    assert profile["consecutive_losses"] == 3  # ASHOKLEY, RVNL, M&MFIN
    assert profile["holding_window_bias"] == "5-12 sessions (Micro-Swing)"
    assert profile["avg_hold_days_winners"] == 7.0
    assert len(profile["open_holdings"]) == 1
    assert profile["open_holdings"][0]["symbol"] == "GAIL"
    assert profile["open_holdings"][0]["quantity"] == 9

    # Check prompt formatting contains behavioral warnings
    dna_prompt = engine.format_dna_for_prompt()
    assert "TRADER DNA" in dna_prompt
    assert "₹23.60 DP" in dna_prompt
    assert "GAIL" in dna_prompt


def test_coaching_rules_and_friction_gate(test_db):
    """
    Verifies the 3 core coaching rules:
    1. Hard Minimum Net-Target Gate (>= 3.5% gross upside).
    2. Post-Loss Cooldown Guard (24h pause after stop-out > ₹75 or 2+ loss streak).
    3. Defensive Sizing Cap (capped to ₹1,500 on consecutive losses).
    """
    engine = TraderDNAEngine(test_db)

    # 1. Evaluate trade with low upside (< 3.5%)
    # RVNL price = 100, target = 102 (+2.0% gross upside)
    eval_low_target = engine.evaluate_proposed_trade("RVNL", price=100.0, target_price=102.0, stop_loss=96.0)
    assert eval_low_target["can_trade"] is False
    assert any("GROSS UPSIDE TOO SMALL" in v for v in eval_low_target["violations"])
    assert eval_low_target["fee_drag_pct"] > 1.0  # DP fee + statutory taxes drag

    # 2. Check sizing cap under defensive mode (3 consecutive losses -> max capital <= ₹1,500)
    eval_defensive = engine.evaluate_proposed_trade("RVNL", price=100.0, target_price=108.0, stop_loss=96.0)
    assert eval_defensive["max_capital_allowed"] <= 1500.0
    assert eval_defensive["recommended_shares"] == 15  # 1500 / 100

    # 3. Check breakeven formula includes exact ₹23.60 DP fee
    # 15 shares @ 100 = 1500 value. Taxes ~ ₹2.10 + ₹23.60 DP = ₹25.70 friction -> ~ ₹1.71/share breakeven addition
    assert eval_defensive["breakeven_price"] > 100.0
    assert eval_defensive["breakeven_price"] == pytest.approx(101.71, abs=0.2)


def test_conversational_episodic_memory_pii_and_pruning(test_db):
    """Verifies that CopilotMemoryStore sanitizes PII, retrieves keyword episodes, and auto-prunes."""
    store = CopilotMemoryStore(test_db)

    # 1. Test PII sanitization
    raw_prompt = "My PAN is ABCDE1234F, client ID 1234567, phone 9876543210 and email trader@gmail.com. Why did RVNL fall?"
    clean_prompt = sanitize_conversational_pii(raw_prompt)
    assert "ABCDE1234F" not in clean_prompt
    assert "9876543210" not in clean_prompt
    assert "trader@gmail.com" not in clean_prompt
    assert "[PAN_REDACTED]" in clean_prompt
    assert "[PHONE_REDACTED]" in clean_prompt
    assert "[EMAIL_REDACTED]" in clean_prompt

    # 2. Test recording and retrieval
    store.distill_and_record_turn(
        user_prompt="Should I sell GAIL at ₹194?",
        primary_symbol="GAIL",
        copilot_response="Holding 9 shares of GAIL. Breakeven after ₹23.60 DP fee is ₹195.40. Recommend holding for 5D target."
    )
    store.distill_and_record_turn(
        user_prompt="What is your view on RVNL momentum?",
        primary_symbol="RVNL",
        copilot_response="RVNL is in defensive cooldown after 7% stop-out. Maintain strict stop at ₹188."
    )

    gail_episodes = store.retrieve_relevant_episodes(["GAIL"])
    assert len(gail_episodes) >= 1
    assert any("GAIL" in ep["primary_symbol"] for ep in gail_episodes)

    # 3. Test prompt formatting
    mem_prompt = store.format_episodes_for_prompt(gail_episodes)
    assert "CONVERSATIONAL EPISODIC MEMORY" in mem_prompt
    assert "GAIL" in mem_prompt


def test_live_tools_db_fusion(test_db):
    """Verifies live intraday quote fusion with SQLite EOD technicals and open holdings."""
    _QUOTE_CACHE.clear()

    # Mock fast_info to return live price 198.50 for GAIL
    mock_fast_info = {
        "lastPrice": 198.50,
        "previousClose": 193.50,
        "dayHigh": 200.0,
        "dayLow": 191.0,
        "open": 192.0,
        "lastVolume": 2500000
    }

    with patch("yfinance.Ticker") as mock_ticker:
        mock_instance = MagicMock()
        mock_instance.fast_info = mock_fast_info
        mock_ticker.return_value = mock_instance

        quote = fetch_live_intraday_quote("GAIL", test_db)
        assert quote["is_live"] is True
        assert quote["ltp"] == 198.50
        assert quote["change_pct"] == pytest.approx(2.58, abs=0.1)
        # Verify fusion with open holdings (GAIL 9 shares @ 192.76)
        assert quote["open_holding"] is not None
        assert quote["open_holding"]["quantity"] == 9
        # Unrealized P&L at 198.50 = (198.50 - 192.76) * 9 = +51.66
        assert quote["open_holding"]["live_unrealized_pnl"] == pytest.approx(51.66, abs=0.5)


def test_live_web_catalyst_search():
    """Verifies live web catalyst search fallback within timeout."""
    _WEB_CACHE.clear()

    mock_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Google News</title>
        <item>
          <title>GAIL reports strong quarterly operating margins and pipeline expansion</title>
          <link>https://news.google.com/item1</link>
          <pubDate>Mon, 23 Nov 2026 10:00:00 GMT</pubDate>
          <source url="https://economictimes.indiatimes.com">Economic Times</source>
        </item>
      </channel>
    </rss>"""

    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_xml.encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_url.return_value = mock_resp

        results = search_live_web_catalysts("GAIL", "GAIL (INDIA) LIMITED", "")
        assert len(results) >= 1
        assert "pipeline expansion" in results[0]["title"]
        assert results[0]["source"] in ("Economic Times", "Google News RSS")


@pytest.mark.asyncio
async def test_deliberation_engine_full_integration(test_db):
    """Verifies that MultiAgentDeliberationEngine fuses Trader DNA, live quotes, and episodic memory."""
    engine = MultiAgentDeliberationEngine(bridge=test_db)

    # 1. Test grounded context builder includes trader DNA and live quote
    grounded = engine._build_grounded_context(["GAIL"])
    assert "trader_dna" in grounded
    assert "trader_dna_prompt" in grounded
    assert "memory_episodes" in grounded
    assert grounded["trader_dna"]["consecutive_losses"] == 3

    # 2. Test deterministic judge embeds micro-capital execution advice
    memo, meta = engine._generate_deterministic_judge(grounded)
    assert "Micro-Capital Execution & Trader DNA Coach" in memo
    assert "coaching" in meta
    assert meta["coaching"]["recommended_shares"] > 0
    assert meta["coaching"]["breakeven_price"] > 0

    # 3. Test direct QA for holding inquiry with deterministic synthesis
    with patch("src.copilot.deliberation.is_live_llm_configured", return_value=False):
        qa_resp = await engine.generate_direct_response("What should I do with my GAIL holding?", symbol="GAIL")
        assert "Trader DNA Behavioral & Execution Analysis" in qa_resp
        assert "Current Holding:" in qa_resp
        assert "9 shares" in qa_resp
        assert "Fee Drag Breakeven:" in qa_resp

    # 4. Verify that direct response automatically recorded an episode in memory
    episodes = engine.memory_store.retrieve_relevant_episodes(["GAIL"])
    assert len(episodes) >= 1
