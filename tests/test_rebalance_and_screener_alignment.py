"""
tests/test_rebalance_and_screener_alignment.py
Hermetic Unit & Integration Tests for Rebalance Proposal Order Generation
and Tournament-Calibrated Screener Alignment (Ticket MIL-P1-050).
"""

from pathlib import Path
import pytest
from src.storage.database import DatabaseManager
from src.quant.rebalance_engine import RebalanceEngine
from src.quant.screener import FactorScreener

DB_PATH = Path("data/market_lab.db")


@pytest.fixture
def db_manager():
    return DatabaseManager(str(DB_PATH))


@pytest.fixture
def rebalance_engine(db_manager):
    return RebalanceEngine(db_manager)


@pytest.fixture
def factor_screener(db_manager):
    return FactorScreener(db_manager)


def test_screener_sorting_and_parameters(factor_screener):
    """
    Verifies that FactorScreener.screen accepts trading_date and limit,
    returns exactly limit rows, and sorts monotonically non-increasing by score.
    """
    trading_date = "2026-11-06"
    limit = 10
    df = factor_screener.screen(trading_date=trading_date, limit=limit)

    assert len(df) == limit, f"Expected exactly {limit} candidates, got {len(df)}"

    # Determine sorting column
    sort_col = "blended_score" if ("blended_score" in df.columns and df["blended_score"].notna().any()) else "composite_score"
    scores = df[sort_col].tolist()

    # Monotonic non-increasing invariant: S_i >= S_{i+1}
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1], (
            f"Ordering violation at rank {i+1} vs {i+2}: {scores[i]} < {scores[i+1]}"
        )

    # Required telemetry columns present
    for col in ["symbol", "close", "rsi_14", "volatility_20d", sort_col]:
        assert col in df.columns, f"Missing expected column: {col}"


def test_generate_daily_rebalance_proposal_emits_executable_orders(rebalance_engine, db_manager):
    """
    Verifies that generate_daily_rebalance_proposal computes authentic market breadth,
    dynamic cash allocation, inspects real portfolio positions, and emits concrete executable orders.
    """
    session_date = "2026-11-06"
    test_account_id = "test_hermetic_rebal_acc"

    with db_manager.get_connection() as conn:
        conn.execute("DELETE FROM portfolio_positions WHERE account_id = ?", (test_account_id,))
        conn.execute("DELETE FROM portfolio_accounts WHERE account_id = ?", (test_account_id,))
        conn.execute(
            "INSERT INTO portfolio_accounts (account_id, cash_balance, total_nav, updated_at) VALUES (?, ?, ?, ?)",
            (test_account_id, 950000.0, 1000000.0, "2026-11-06T00:00:00Z")
        )
        conn.execute(
            "INSERT INTO portfolio_positions (position_id, account_id, symbol, quantity, average_entry_price, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (f"{test_account_id}_Z_EJECT", test_account_id, "Z_EJECT_TEST", 1000, 50.0, "2026-11-06T00:00:00Z")
        )

    try:
        proposal = rebalance_engine.generate_daily_rebalance_proposal(
            session_date=session_date,
            account_id=test_account_id,
            top_n=15,
            hysteresis_buffer=5.0
        )

        # Top-level proposal invariants
        assert proposal["status"] == "PROPOSED"
        assert proposal["session_date"] == session_date
        assert proposal["account_id"] == test_account_id
        assert proposal["market_breadth_pct"] > 0.0
        assert 0.0 <= proposal["target_cash_pct"] <= 100.0
        assert proposal["estimated_friction_inr"] > 0.0
        assert len(proposal["top_candidates"]) == 15

        orders = proposal["orders"]
        assert len(orders) > 0, "Expected non-empty list of executable orders"

        required_order_keys = [
            "action", "symbol", "quantity", "ref_price",
            "order_value", "estimated_friction", "reason"
        ]

        actions_seen = set()
        for o in orders:
            for k in required_order_keys:
                assert k in o, f"Missing key '{k}' in order: {o}"

            assert o["action"] in ("BUY", "SELL"), f"Invalid order action: {o['action']}"
            actions_seen.add(o["action"])

            assert isinstance(o["quantity"], int), f"Quantity must be integer: {o['quantity']}"
            assert o["quantity"] > 0, f"Quantity must be positive: {o['quantity']}"
            assert o["ref_price"] > 0, f"Price must be positive: {o['ref_price']}"
            assert o["order_value"] > 0, f"Order value must be positive: {o['order_value']}"
            assert o["estimated_friction"] > 0, f"Friction must be positive: {o['estimated_friction']}"
            assert isinstance(o["reason"], str) and len(o["reason"]) > 0

        # Ensure both SELL (departures/trims) and BUY (new entries/expansions) are represented
        assert "SELL" in actions_seen, "Expected SELL orders for ejected holdings"
        assert "BUY" in actions_seen, "Expected BUY orders for new entries"
    finally:
        with db_manager.get_connection() as conn:
            conn.execute("DELETE FROM portfolio_positions WHERE account_id = ?", (test_account_id,))
            conn.execute("DELETE FROM portfolio_accounts WHERE account_id = ?", (test_account_id,))
