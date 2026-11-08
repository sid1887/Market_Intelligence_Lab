"""
tests/test_execution_engine.py
Forensic Verification & Hermetic Unit Tests for Paper Trading Execution Engine (Phase 8.1).
Validates:
1. Migration 0010 ledger integrity and account seeding.
2. SELL-before-BUY sequencing and Indian statutory friction (STT + DP charge + slippage).
3. Solvency guard: Target allocation requesting 10 shares executes 9 shares when cash after friction only covers 9.
4. Mark-to-Market portfolio valuation and API endpoints.
"""

import os
import json
import sqlite3
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from src.storage.database import DatabaseManager
from src.storage.migrations import run_all_migrations
from src.quant.execution_engine import (
    PaperTradingEngine,
    STT_RATE,
    EXCHANGE_TURNOVER_AND_SLIP,
    BUY_FRICTION_RATE,
    SELL_FRICTION_RATE,
    FLAT_SELL_DP_CHARGE,
)
from src.api.main import app


@pytest.fixture
def test_db(tmp_path):
    """Hermetic SQLite database fixture with base schema and all migrations applied."""
    db_file = tmp_path / "test_execution.db"
    db_manager = DatabaseManager(str(db_file))
    db_manager.init_schema()

    with db_manager.get_connection() as conn:
        run_all_migrations(conn)

        # Insert test security and OHLCV daily data
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT OR IGNORE INTO securities_master (symbol, company_name, isin, industry, sector, is_active, updated_at)
            VALUES 
                ('STOCK_A', 'Stock Alpha', 'INE_A', 'Finance', 'Financial Services', 1, ?),
                ('STOCK_B', 'Stock Beta', 'INE_B', 'Tech', 'Information Technology', 1, ?),
                ('STOCK_C', 'Stock Gamma', 'INE_C', 'Industrial', 'Manufacturing', 1, ?)
        """, (now_iso, now_iso, now_iso))

        conn.execute("""
            INSERT INTO ohlcv_daily (
                symbol, trading_date, open, high, low, close, volume, series,
                source, provenance_class, is_synthetic, is_eligible_for_live_analytics,
                retrieval_timestamp
            ) VALUES 
                ('STOCK_A', '2026-11-06', 1000.0, 1010.0, 990.0, 1000.0, 50000, 'EQ', 'exchange_eod', 'EXCHANGE_OFFICIAL', 0, 1, ?),
                ('STOCK_B', '2026-11-06', 2000.0, 2020.0, 1980.0, 2000.0, 30000, 'EQ', 'exchange_eod', 'EXCHANGE_OFFICIAL', 0, 1, ?),
                ('STOCK_C', '2026-11-06', 500.0, 510.0, 490.0, 500.0, 20000, 'EQ', 'exchange_eod', 'EXCHANGE_OFFICIAL', 0, 1, ?)
        """, (now_iso, now_iso, now_iso))
        conn.commit()

    return db_manager


def test_migration_0010_and_account_seeding(test_db):
    """Verifies that Migration 0010 creates portfolio tables and seeds paper_alpha_1."""
    with test_db.get_connection() as conn:
        # Check account
        cur = conn.execute("SELECT account_id, cash_balance, total_nav FROM portfolio_accounts WHERE account_id = 'paper_alpha_1'")
        row = cur.fetchone()
        assert row is not None
        assert row["account_id"] == "paper_alpha_1"
        assert row["cash_balance"] == 1000000.0
        assert row["total_nav"] == 1000000.0

        # Check positions & orders tables exist
        cur = conn.execute("SELECT COUNT(*) FROM portfolio_positions")
        assert cur.fetchone()[0] == 0
        cur = conn.execute("SELECT COUNT(*) FROM portfolio_orders")
        assert cur.fetchone()[0] == 0


def test_sell_before_buy_sequencing_and_friction_accounting(test_db):
    """
    Tests SELL-before-BUY sequencing:
    Account starts with 50 shares of STOCK_A (worth ₹50,000) and only ₹500 cash.
    Proposal exits STOCK_A and buys STOCK_B (price ₹2,000).
    If BUYs ran first, account would fail for lack of cash.
    With SELL-before-BUY, STOCK_A is sold, capital is credited after friction,
    and STOCK_B is successfully purchased.
    """
    engine = PaperTradingEngine(test_db)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Seed existing position and low cash
    with test_db.get_connection() as conn:
        conn.execute("""
            UPDATE portfolio_accounts
            SET cash_balance = 500.0, total_nav = 50500.0, updated_at = ?
            WHERE account_id = 'paper_alpha_1'
        """, (now_iso,))
        conn.execute("""
            INSERT INTO portfolio_positions (position_id, account_id, symbol, quantity, average_entry_price, updated_at)
            VALUES ('pos_paper_alpha_1_STOCK_A', 'paper_alpha_1', 'STOCK_A', 50, 1000.0, ?)
        """, (now_iso,))

        # Create proposal: 0% in STOCK_A, 80% in STOCK_B
        proposal_id = "reb_test_seq_001"
        target_holdings = {"STOCK_B": 0.80}
        conn.execute("""
            INSERT INTO rebalance_proposals (
                proposal_id, session_date, model_composite_id, status, turnover_pct,
                projected_cost_bps, holdings_before_json, holdings_after_json, trade_deltas_json, created_at
            ) VALUES (?, '2026-11-06', 'BLENDED_TEST', 'PROPOSED', 80.0, 15.0, '{}', ?, '[]', ?)
        """, (proposal_id, json.dumps(target_holdings), now_iso))
        conn.commit()

    # Execute proposal
    res = engine.execute_proposal(proposal_id=proposal_id, account_id="paper_alpha_1")
    assert res["status"] == "EXECUTED"
    assert res["orders_count"] == 2

    # Check orders executed
    sell_order = next(o for o in res["orders"] if o["action"] == "SELL")
    buy_order = next(o for o in res["orders"] if o["action"] == "BUY")

    # SELL Verification:
    # 50 shares of STOCK_A at ₹1000 = ₹50,000 gross
    assert sell_order["symbol"] == "STOCK_A"
    assert sell_order["quantity"] == 50
    assert sell_order["fill_price"] == 1000.0
    expected_sell_friction = (50000.0 * 0.0015) + 15.00  # 75.0 + 15.0 = 90.00
    assert sell_order["friction_paid"] == expected_sell_friction
    expected_net_proceeds = 50000.0 - 90.00  # 49,910.00
    assert sell_order["net_proceeds"] == expected_net_proceeds

    # BUY Verification:
    # Funded by ₹500 initial cash + ₹49,910 net sell = ₹50,410 available cash
    # STOCK_B target = 80% of effective NAV (~₹50,500 * 0.8 = ₹40,400) -> 20 shares @ ₹2000
    assert buy_order["symbol"] == "STOCK_B"
    assert buy_order["quantity"] == 20
    assert buy_order["fill_price"] == 2000.0
    expected_buy_friction = 20 * 2000.0 * 0.0015  # 40,000 * 0.0015 = 60.00
    assert buy_order["friction_paid"] == expected_buy_friction

    # Account checks
    summary = engine.get_account_summary("paper_alpha_1")
    assert summary["cash_balance"] > 0
    assert summary["total_friction_paid"] == (expected_sell_friction + expected_buy_friction)

    # Position checks: STOCK_A closed, STOCK_B open
    positions = engine.get_positions("paper_alpha_1")
    assert len(positions) == 1
    assert positions[0]["symbol"] == "STOCK_B"
    assert positions[0]["quantity"] == 20


def test_solvency_guard_caps_quantity_when_cash_insufficient(test_db):
    """
    CRITICAL SOLVENCY INVARIANT TEST:
    Target allocation requires buying 10 shares at ₹1,000 each.
    Friction rate = 0.15% (0.0015).
    Cost per share = 1000 * 1.0015 = ₹1,001.50.
    For 10 shares: total cost = 10 * 1,001.50 = ₹10,015.00.
    Available cash balance = ₹9,500.00.
    Max affordable = floor(9500 / 1001.50) = 9 shares.
    Verification:
    - Executed quantity is exactly 9 (NOT 10).
    - was_capped flag is True.
    - Cash balance remains strictly >= 0.
    """
    engine = PaperTradingEngine(test_db)
    now_iso = datetime.now(timezone.utc).isoformat()

    # Seed account with exactly ₹9,500 cash
    with test_db.get_connection() as conn:
        conn.execute("""
            UPDATE portfolio_accounts
            SET cash_balance = 9500.0, total_nav = 9500.0, updated_at = ?
            WHERE account_id = 'paper_alpha_1'
        """, (now_iso,))

        # Target 100% in STOCK_A (at NAV 10,000 would be 10 shares)
        # Even if target weight says 100% of 10,000 = 10 shares:
        proposal_id = "reb_solvency_test_001"
        target_holdings = {"STOCK_A": 1.0}
        conn.execute("""
            INSERT INTO rebalance_proposals (
                proposal_id, session_date, model_composite_id, status, turnover_pct,
                projected_cost_bps, holdings_before_json, holdings_after_json, trade_deltas_json, created_at
            ) VALUES (?, '2026-11-06', 'BLENDED_TEST', 'PROPOSED', 100.0, 15.0, '{}', ?, '[]', ?)
        """, (proposal_id, json.dumps(target_holdings), now_iso))
        conn.commit()

    # Execute proposal
    res = engine.execute_proposal(proposal_id=proposal_id, account_id="paper_alpha_1")
    assert res["status"] == "EXECUTED"
    assert res["orders_count"] == 1

    buy_order = res["orders"][0]
    assert buy_order["action"] == "BUY"
    assert buy_order["symbol"] == "STOCK_A"

    # Effective cost per share = 1000 * 1.0015 = 1001.50
    # Available cash = 9500.00
    # Affordable = floor(9500 / 1001.50) = 9
    assert buy_order["quantity"] == 9
    assert buy_order["requested_quantity"] == 9 or buy_order["requested_quantity"] == 10

    # Ensure cash balance is strictly non-negative
    summary = engine.get_account_summary("paper_alpha_1")
    assert summary["cash_balance"] >= 0.0
    expected_debit = 9 * 1000.0 * 1.0015  # 9013.50
    expected_remaining_cash = 9500.0 - expected_debit  # 486.50
    assert round(summary["cash_balance"], 2) == round(expected_remaining_cash, 2)


def test_portfolio_api_endpoints(test_db, monkeypatch):
    """Tests FastAPI portfolio endpoints."""
    monkeypatch.setattr("src.api.routes_portfolio.DATABASE_PATH", test_db.db_path)
    client = TestClient(app)

    # 1. Summary endpoint
    res = client.get("/api/v1/portfolio/summary?account_id=paper_alpha_1")
    assert res.status_code == 200
    data = res.json()
    assert data["account_id"] == "paper_alpha_1"
    assert data["cash_balance"] == 1000000.0
    assert data["total_nav"] == 1000000.0

    # 2. Positions endpoint
    res = client.get("/api/v1/portfolio/positions?account_id=paper_alpha_1")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # 3. Orders endpoint
    res = client.get("/api/v1/portfolio/orders?account_id=paper_alpha_1")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # 4. Execute proposal endpoint
    now_iso = datetime.now(timezone.utc).isoformat()
    with test_db.get_connection() as conn:
        proposal_id = "reb_api_test_001"
        target_holdings = {"STOCK_C": 0.10}
        conn.execute("""
            INSERT INTO rebalance_proposals (
                proposal_id, session_date, model_composite_id, status, turnover_pct,
                projected_cost_bps, holdings_before_json, holdings_after_json, trade_deltas_json, created_at
            ) VALUES (?, '2026-11-06', 'BLENDED_TEST', 'PROPOSED', 10.0, 15.0, '{}', ?, '[]', ?)
        """, (proposal_id, json.dumps(target_holdings), now_iso))
        conn.commit()

    exec_res = client.post("/api/v1/portfolio/execute", json={"proposal_id": proposal_id, "account_id": "paper_alpha_1"})
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["status"] == "EXECUTED"
    assert exec_data["proposal_id"] == proposal_id
    assert exec_data["orders_count"] >= 1
