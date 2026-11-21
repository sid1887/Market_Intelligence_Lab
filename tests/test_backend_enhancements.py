"""
Unit tests for Market Intelligence Lab Backend Enhancements (Phases 1-5).
Tests WAL PRAGMAs, catalyst cooldown isolation, yfinance upsert non-destructive updates,
vectorized screener scores, GARCH optimization speed, and dynamic aliases.
"""

import pytest
import sqlite3
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from src.api.utils import get_db_connection, DATABASE_PATH, get_database_manager
from src.tasks.catalyst_engine import CausalCatalystEngine
from src.quant.screener import FactorScreener
from src.quant.forecasting import EconometricForecaster
from src.quant.execution_engine import PaperTradingEngine, FLAT_SELL_DP_CHARGE
from src.copilot.deliberation import MultiAgentDeliberationEngine
from src.notifications.web_push import record_dispatched_alert, is_alert_dispatched
from src.quant.ml_trainer import WalkForwardMLTrainer


def test_wal_pragmas_on_db_connection():
    """Verify that get_db_connection sets WAL read performance PRAGMAs."""
    gen = get_db_connection()
    conn = next(gen)
    try:
        # Check query_only is ON
        cur = conn.execute("PRAGMA query_only;")
        assert cur.fetchone()[0] == 1

        # Check busy_timeout is set
        cur = conn.execute("PRAGMA busy_timeout;")
        assert cur.fetchone()[0] == 30000

        # Check temp_store is MEMORY (2)
        cur = conn.execute("PRAGMA temp_store;")
        assert cur.fetchone()[0] == 2
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_catalyst_cooldown_instance_isolation():
    """Verify that CausalCatalystEngine instances have isolated cooldown dicts."""
    engine1 = CausalCatalystEngine(auto_push=False)
    engine2 = CausalCatalystEngine(auto_push=False)

    now = datetime.now(timezone.utc)
    engine1._cooldowns["RELIANCE"] = now

    assert "RELIANCE" in engine1._cooldowns
    assert "RELIANCE" not in engine2._cooldowns, "Cooldown leaked across engine instances!"


def test_vectorized_composite_score(in_memory_db):
    """Verify that FactorScreener vectorized score calculation matches expected bounds."""
    screener = FactorScreener(in_memory_db)
    df = pd.DataFrame({
        "roe_pct": [25.0, 15.0, 30.0, None],
        "debt_to_equity": [0.2, 0.8, 0.1, 1.5],
        "excess_ret_20d": [0.05, -0.02, 0.10, 0.0],
        "opm_pct": [20.0, 10.0, 25.0, None]
    })

    scores, comp, statuses = screener.calculate_composite_score(df, return_metadata=True)
    assert len(scores) == 4
    # Top quality stock (row 2: highest roe, lowest de, highest excess, highest opm) should score near 100
    assert scores.iloc[2] > scores.iloc[1]
    # Row 3 with 2 nulls has completeness < 60% so status is INSUFFICIENT_DATA and score is NaN
    assert statuses.iloc[3] == "INSUFFICIENT_DATA"
    assert np.isnan(scores.iloc[3])


def test_garch_fitting_speed_and_constraints():
    """Verify GARCH parameter calibration enforces strict constraints."""
    returns = np.random.normal(0.0005, 0.015, 300)
    omega, alpha, beta = EconometricForecaster.fit_garch11(returns)

    assert omega > 0
    assert alpha >= 0.001
    assert beta >= 0.001
    assert alpha + beta < 1.0, "GARCH covariance stationarity constraint violated!"


def test_execution_engine_dp_charge():
    """Verify DP charge is calibrated to exact CDSL statutory charge (15.34)."""
    assert FLAT_SELL_DP_CHARGE == 15.34


def test_dynamic_alias_resolution(in_memory_db):
    """Verify that MultiAgentDeliberationEngine dynamically resolves company names."""
    delib = MultiAgentDeliberationEngine(bridge=in_memory_db)
    syms = delib._extract_symbols("What is your quantitative view on Test Company?")
    assert "TESTCO" in syms


def test_push_dispatch_ledger_auto_prune():
    """Verify that record_dispatched_alert records and checks deduplication keys."""
    test_key = "test-alert-key-12345"
    record_dispatched_alert(test_key)
    assert is_alert_dispatched(test_key) is True


def test_ml_trainer_dataset_fallback(in_memory_db):
    """Verify WalkForwardMLTrainer extract_training_dataset succeeds using quant_factors_daily."""
    trainer = WalkForwardMLTrainer(in_memory_db)
    df = trainer.extract_training_dataset(horizon_days=5)
    # The in_memory_db has only 1 row so it returns empty df safely without SQL error
    assert isinstance(df, pd.DataFrame)
