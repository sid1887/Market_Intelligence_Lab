"""
tests/test_v8_engine_upgrade.py
End-to-End Verification Suite for MIL V8 Engine Upgrades:
1. Dynamic Capital Architecture (₹1,600 seed, zero ₹10L hardcoding, whole-share sizing, residual sweeper)
2. Paper Trading Accounts: paper_alpha_2 (Systematic Quant) and paper_manual_1 (FrontPage Sandbox)
3. Discretionary Trade Lifecycle with FrontPage Analysis Card & Thesis Journaling
4. NSE 1,000+ Universe Expansion Status & Ingestion Tracking
5. Purged Walk-Forward ML Cross-Validation & Telemetry Ledger
6. Financial News Sentiment Engine & Deliberation Enrichment
"""

import os
import json
import sqlite3
import pytest
from datetime import datetime, timezone

from src.storage.database import DatabaseManager
from src.quant.execution_engine import PaperTradingEngine
from src.quant.rebalance_engine import RebalanceEngine
from src.data.universe_expander import UniverseExpander
from src.quant.ml_trainer import WalkForwardMLTrainer
from src.tasks.news_daemon import FinancialSentimentAnalyzer, NewsSentimentDaemon
from src.copilot.deliberation import MultiAgentDeliberationEngine

DATABASE_PATH = "data/market_lab.db"


@pytest.fixture(scope="module")
def db():
    return DatabaseManager(DATABASE_PATH)


@pytest.fixture(scope="module")
def execution_engine(db):
    return PaperTradingEngine(db)


@pytest.fixture(scope="module")
def rebalance_engine(db):
    return RebalanceEngine(db)


def test_variable_capital_1600_metrics_and_pnl(execution_engine, db):
    """
    Verifies that get_account_summary calculates total_pnl and total_pnl_pct
    dynamically from user-defined initial_capital (e.g. ₹1,600), eliminating
    the legacy hardcoded ₹10,00,000 divisor.
    """
    account_id = "paper_alpha_2"
    # Seed account with ₹1,600 starting capital
    summary = execution_engine.set_or_reset_capital(
        account_id=account_id,
        new_capital=1600.0,
        fee_tier="RETAIL_MICRO"
    )

    assert summary["account_id"] == account_id
    assert summary["initial_capital"] == 1600.0
    assert summary["total_nav"] == 1600.0
    assert summary["cash_balance"] == 1600.0
    assert summary["total_pnl"] == 0.0
    assert summary["total_pnl_pct"] == 0.0
    assert summary["fee_tier"] == "RETAIL_MICRO"
    assert summary["account_type"] == "SYSTEMATIC"

    # Verify database persistence
    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT initial_capital, total_nav, fee_tier, account_type FROM portfolio_accounts WHERE account_id = ?",
            (account_id,)
        ).fetchone()
        assert row["initial_capital"] == 1600.0
        assert row["total_nav"] == 1600.0
        assert row["fee_tier"] == "RETAIL_MICRO"
        assert row["account_type"] == "SYSTEMATIC"


def test_paper_alpha_2_micro_capital_rebalance_and_friction(rebalance_engine, execution_engine, db):
    """
    Verifies that paper_alpha_2 on ₹1,600 starting capital:
    1. Computes slot scaling K_eff = 4 (₹400 budget per slot)
    2. Filters out high-priced stocks (e.g. ANANDRATHI > ₹2,000)
    3. Allocates whole shares to affordable compounders (e.g. NHPC, BPCL, etc.)
    4. Applies greedy residual cash sweeper to minimize unallocated drag
    5. Calculates RETAIL_MICRO statutory friction (12 bps + DP charges)
    """
    account_id = "paper_alpha_2"
    execution_engine.set_or_reset_capital(account_id=account_id, new_capital=1600.0, fee_tier="RETAIL_MICRO")

    # Generate daily rebalance proposal for latest session
    proposal = rebalance_engine.generate_daily_rebalance_proposal(
        session_date="2026-11-06",
        account_id=account_id
    )

    assert proposal["proposal_id"].startswith("reb_")
    assert proposal["account_id"] == account_id
    assert "target_holdings" in proposal
    assert len(proposal["target_holdings"]) > 0
    assert len(proposal["orders"]) > 0

    # Ensure all suggested orders are whole shares and affordable
    for order in proposal["orders"]:
        assert isinstance(order["quantity"], int)
        assert order["quantity"] >= 1
        assert order["fill_price"] <= 1600.0

    # Execute the proposal
    exec_result = execution_engine.execute_proposal(
        proposal_id=proposal["proposal_id"],
        account_id=account_id
    )

    assert exec_result["status"] == "EXECUTED"
    assert exec_result["orders_count"] > 0
    assert exec_result["total_friction_paid"] > 0
    # Friction for ₹1,600 under RETAIL_MICRO should be less than ₹10
    assert exec_result["total_friction_paid"] < 10.0

    # Verify positions and account summary
    summary = execution_engine.get_account_summary(account_id)
    assert summary["positions_count"] > 0
    assert summary["invested_value"] > 1000.0  # More than 60% deployed
    assert summary["cash_balance"] >= 0.0      # Solvency preserved


def test_paper_manual_1_frontpage_preview_and_execution(execution_engine, db):
    """
    Verifies discretionary paper trading workflow on paper_manual_1:
    1. Pre-trade preview calculates whole shares, estimated friction, solvency check,
       and FrontPage analysis card with momentum verdict.
    2. Execution persists order, thesis note, and analysis card.
    3. Solvency guard rejects orders exceeding cash balance.
    """
    account_id = "paper_manual_1"
    execution_engine.set_or_reset_capital(account_id=account_id, new_capital=1600.0, fee_tier="RETAIL_MICRO")

    # 1. Preview BUY order for NHPC with ₹400
    preview = execution_engine.preview_manual_order(
        account_id=account_id,
        symbol="NHPC",
        action="BUY",
        amount_inr=400.0
    )

    assert preview["symbol"] == "NHPC"
    assert preview["action"] == "BUY"
    assert preview["calculated_quantity"] > 0
    assert preview["is_solvency_approved"] is True
    assert preview["frontpage_card"]["trend_regime"] in ["ABOVE_200_SMA", "BELOW_200_SMA", "UNKNOWN"]
    assert "signal_summary" in preview["frontpage_card"]

    # 2. Execute the BUY order
    buy_result = execution_engine.execute_manual_order(
        account_id=account_id,
        symbol="NHPC",
        action="BUY",
        amount_inr=400.0,
        thesis_note="Strong base breakout above 200 SMA with volume accumulation"
    )

    assert buy_result["success"] is True
    assert buy_result["action"] == "BUY"
    assert buy_result["quantity"] == preview["calculated_quantity"]
    assert buy_result["thesis_note"] == "Strong base breakout above 200 SMA with volume accumulation"

    # Verify order in portfolio_orders
    with db.get_connection() as conn:
        order_row = conn.execute(
            "SELECT symbol, action, quantity, thesis_note FROM portfolio_orders WHERE order_id = ?",
            (buy_result["order_id"],)
        ).fetchone()
        assert order_row["symbol"] == "NHPC"
        assert order_row["action"] == "BUY"
        assert order_row["thesis_note"] == "Strong base breakout above 200 SMA with volume accumulation"

    # 3. Test Solvency Rejection: Attempting to buy ₹5,000 when balance is ~₹1,200
    with pytest.raises(ValueError, match="Insufficient cash"):
        execution_engine.execute_manual_order(
            account_id=account_id,
            symbol="RELIANCE",
            action="BUY",
            amount_inr=5000.0,
            thesis_note="Will fail solvency check"
        )


def test_universe_expander_status_and_tracking(db):
    """
    Verifies that UniverseExpander accurately tracks the master universe size,
    active OHLCV bars, and historical depth metrics.
    """
    expander = UniverseExpander(db=db)
    status = expander.get_universe_status()

    assert "total_universe_symbols" in status
    assert status["total_universe_symbols"] >= 1000
    assert status["active_ohlcv_symbols"] >= 180
    assert status["total_bars_ingested"] >= 200000
    assert status["target_depth_years"] == 15


def test_walk_forward_ml_trainer_tournament_and_telemetry(db):
    """
    Verifies that WalkForwardMLTrainer:
    1. Extracts multi-asset panel features
    2. Runs purged rolling cross-validation
    3. Persists authentic out-of-sample metrics to ml_training_runs
    4. Updates tournament_summary.json with champion feature weights
    """
    trainer = WalkForwardMLTrainer(db=db, summary_path="data/models/tournament_summary.json")

    # Run tournament across 20D horizon
    results = trainer.run_training_tournament(horizons=[20])

    assert len(results) >= 2  # At least Ridge & HistGradientBoosting
    assert any(r["horizon_days"] == 20 for r in results)

    telemetry = trainer.get_ml_telemetry(limit=5)
    assert telemetry["total_runs_evaluated"] > 0
    assert "20D" in telemetry["active_champions"]

    champ = telemetry["active_champions"]["20D"]
    assert "model_family" in champ
    assert "rank_ic" in champ
    assert "feature_weights" in champ


def test_financial_news_sentiment_analysis_and_negation():
    """
    Verifies deterministic financial sentiment analysis with negation handling.
    """
    # Bullish headline
    res1 = FinancialSentimentAnalyzer.analyze("Reliance reports record profit with EBITDA growth")
    assert res1["score"] > 0.3
    assert res1["label"] == "BULLISH"

    # Bearish headline
    res2 = FinancialSentimentAnalyzer.analyze("SEBI issues notice to company over disclosure violation")
    assert res2["score"] < -0.3
    assert res2["label"] == "BEARISH"

    # Negation handling: "not profit" should invert sentiment
    res3 = FinancialSentimentAnalyzer.analyze("Company did not achieve profit target")
    assert res3["score"] < 0.0


def test_copilot_context_enrichment(db):
    """
    Verifies that MultiAgentDeliberationEngine enriches quant context
    with portfolio account telemetry and news headlines.
    """
    engine = MultiAgentDeliberationEngine()
    ctx = engine._get_quant_context("NHPC")

    assert ctx["symbol"] == "NHPC"
    assert "price" in ctx
    assert "trend" in ctx
    assert "portfolio_telemetry" in ctx
    assert "recent_news" in ctx
    assert "paper_alpha_2" in ctx["portfolio_telemetry"]
    assert "paper_manual_1" in ctx["portfolio_telemetry"]
