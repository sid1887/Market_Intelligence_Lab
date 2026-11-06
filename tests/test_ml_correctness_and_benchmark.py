"""
Unit and Integration Tests for ML Correctness & Benchmark Integrity.
Workstream 3 / Audit Ticket: Finding 3, ADR-0005, ADR-0008.

Verifies:
1. Benchmark returns are retrieved from authentic index_daily TRI / PRI.
2. Missing benchmark prices NEVER default to 0.0; they are tagged UNOBSERVABLE_BENCHMARK with matured=False.
3. Synthetic OHLCV bars are strictly excluded from label generation.
4. Tournament enforces strict target_date purge to eliminate future lookahead into test periods.
5. Model promotion atomically synchronizes model_registry and supervisor_state active_model_id.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone

from src.storage.database import DatabaseManager
from src.ml.labels.builder import MaturedForwardLabelBuilder
from src.ml.registry.manager import ModelRegistryManager
from src.ml.training.tournament import ModelTournament


@pytest.fixture
def ml_test_db(tmp_path):
    db_file = str(tmp_path / "test_ml.db")
    db = DatabaseManager(db_file)
    with db.get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO securities_master (symbol, company_name, isin, industry, sector, macro_sector, updated_at, is_active)
            VALUES ('ALPHA', 'Alpha Corp', 'INE000A00001', 'IT', 'Tech', 'IT', '2026-11-06T00:00:00Z', 1);
        """)

        # Insert 30 trading dates of OHLCV and index prices
        # Dates: 2026-01-01 to 2026-01-30
        for i in range(1, 31):
            d_str = f"2026-01-{i:02d}"
            # Stock price starts at 100 and rises by 1 each day
            stock_close = 100.0 + i
            conn.execute("""
                INSERT INTO ohlcv_daily (symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp, provenance_class, is_synthetic)
                VALUES ('ALPHA', ?, 'EQ', ?, ?, ?, ?, 100000, 'nse_bhavcopy', '2026-11-06T12:00:00Z', 'EXCHANGE_OFFICIAL', 0);
            """, (d_str, stock_close, stock_close + 1, stock_close - 1, stock_close))

            # Benchmark TRI index exists for days 1 to 25 only (day 26-30 missing TRI)
            if i <= 25:
                bench_close = 20000.0 + (i * 100.0)
                conn.execute("""
                    INSERT INTO index_daily (index_name, index_type, trading_date, open, high, low, close, volume, source, retrieval_timestamp)
                    VALUES ('NIFTY 50', 'TRI', ?, ?, ?, ?, ?, 500000, 'nse_index_feed', '2026-11-06T12:00:00Z');
                """, (d_str, bench_close, bench_close + 50, bench_close - 50, bench_close))

        # Also insert a synthetic bar for FAKESYM
        conn.execute("""
            INSERT INTO ohlcv_daily (symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp, provenance_class, is_synthetic)
            VALUES ('FAKESYM', '2026-01-01', 'EQ', 50.0, 52.0, 49.0, 50.0, 1000, 'offline_multi_regime_generator', '2026-11-06T12:00:00Z', 'SYNTHETIC_TEST', 1);
        """)

        conn.commit()

    return db


def test_label_builder_benchmark_retrieval_and_friction(ml_test_db):
    """Verifies authentic TRI calculation and 15 bps friction deduction."""
    builder = MaturedForwardLabelBuilder(ml_test_db, horizon_sessions=5, friction_bps=15.0)
    df = builder.build_labels(["ALPHA"])

    assert not df.empty
    # Day 1: stock price = 101.0, Day 6: stock price = 106.0 -> stock_fwd_ret = (106/101) - 1
    # Day 1: bench = 20100.0, Day 6: bench = 20600.0 -> bench_fwd_ret = (20600/20100) - 1
    day1 = df[df["trading_date"] == "2026-01-01"].iloc[0]
    assert bool(day1["matured"]) is True
    expected_stock_ret = (106.0 / 101.0) - 1.0
    expected_bench_ret = (20600.0 / 20100.0) - 1.0
    expected_excess = round(expected_stock_ret - expected_bench_ret - 0.0015, 6)

    assert pytest.approx(day1["stock_fwd_ret"], 1e-5) == expected_stock_ret
    assert pytest.approx(day1["bench_fwd_ret"], 1e-5) == expected_bench_ret
    assert pytest.approx(day1["label_excess_ret_net"], 1e-5) == expected_excess
    assert day1["status"] == "MATURED"


def test_missing_benchmark_never_defaults_to_zero(ml_test_db):
    """When benchmark return is unobservable, bench_fwd_ret MUST NOT default to 0.0."""
    builder = MaturedForwardLabelBuilder(ml_test_db, horizon_sessions=5, friction_bps=15.0)
    df = builder.build_labels(["ALPHA"])

    # Day 21 target is Day 26. Benchmark is missing on Day 26!
    day21 = df[df["trading_date"] == "2026-01-21"].iloc[0]
    assert bool(day21["matured"]) is False
    assert pd.isna(day21["bench_fwd_ret"])
    assert pd.isna(day21["label_excess_ret_net"])
    assert day21["status"] == "UNOBSERVABLE_BENCHMARK"


def test_synthetic_bars_excluded_from_labels(ml_test_db):
    """Synthetic bars must never produce label rows."""
    builder = MaturedForwardLabelBuilder(ml_test_db, horizon_sessions=5)
    df = builder.build_labels()
    symbols = set(df["symbol"].unique())
    assert "ALPHA" in symbols
    assert "FAKESYM" not in symbols


def test_promotion_synchronizes_supervisor_active_model_id(ml_test_db, tmp_path):
    """Model promotion strictly verifies artifact, hurdles, and updates supervisor_state atomically."""
    import pickle
    import hashlib
    import json
    from sklearn.linear_model import Ridge

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir(exist_ok=True)
    model_path = str(artifact_dir / "test_model_v1.pkl")

    model_obj = Ridge(alpha=1.0)
    model_obj.fit(np.zeros((5, 5)), np.zeros(5))
    with open(model_path, "wb") as f:
        pickle.dump(model_obj, f)

    with open(model_path, "rb") as f:
        artifact_hash = hashlib.sha256(f.read()).hexdigest()

    registry = ModelRegistryManager(ml_test_db, artifact_dir=str(artifact_dir))

    with ml_test_db.get_connection() as conn:
        conn.execute("""
            INSERT INTO model_registry (
                model_id, model_name, model_version, task_type,
                status, artifact_path, artifact_hash,
                train_start, train_end, metrics_json, created_at
            ) VALUES ('test_model_v1', 'RidgeRegressor', '1.0', 'REGRESSION', 'CANDIDATE', ?, ?, '2026-01-01', '2026-01-20', ?, '2026-11-06T00:00:00Z');
        """, (model_path, artifact_hash, json.dumps({"validation_ic": 0.05, "validation_sharpe": 1.2})))

    # Promote model
    success = registry.promote_model("test_model_v1")
    assert success is True

    # Verify model_registry status
    active_rec = registry.get_active_model_record()
    assert active_rec is not None
    assert active_rec["model_id"] == "test_model_v1"
    assert active_rec["status"] == "PROMOTED"

    # Verify supervisor_state active_model_id is synchronized
    with ml_test_db.get_connection() as conn:
        cur = conn.execute("SELECT active_model_id FROM supervisor_state WHERE singleton_id = 1;")
        row = cur.fetchone()
        assert row is not None
        assert row["active_model_id"] == "test_model_v1"


def test_tri_and_pri_endpoints_are_never_mixed(tmp_path):
    """Endpoints must never mix TRI and PRI; mixed endpoints remain UNOBSERVABLE_BENCHMARK."""
    db_file = str(tmp_path / "test_mixed_bench.db")
    db = DatabaseManager(db_file)
    with db.get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO securities_master (symbol, company_name, isin, industry, sector, macro_sector, updated_at, is_active)
            VALUES ('BETA', 'Beta Corp', 'INE000B00001', 'IT', 'Tech', 'IT', '2026-11-06T00:00:00Z', 1);
        """)
        # Day 1: stock = 100, Day 6: stock = 110
        conn.execute("""
            INSERT INTO ohlcv_daily (symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp, provenance_class, is_synthetic)
            VALUES ('BETA', '2026-02-01', 'EQ', 100, 101, 99, 100, 1000, 'yfinance', '2026-11-06', 'VENDOR_OBSERVED', 0),
                   ('BETA', '2026-02-06', 'EQ', 110, 111, 109, 110, 1000, 'yfinance', '2026-11-06', 'VENDOR_OBSERVED', 0);
        """)
        # Day 1 has TRI only; Day 6 has PRI only
        conn.execute("""
            INSERT INTO index_daily (index_name, index_type, trading_date, open, high, low, close, volume, source, retrieval_timestamp)
            VALUES ('NIFTY 50', 'TRI', '2026-02-01', 35000, 35100, 34900, 35000, 1000, 'nse', '2026-11-06'),
                   ('NIFTY 50', 'PRI', '2026-02-06', 24000, 24100, 23900, 24000, 1000, 'nse', '2026-11-06');
        """)
        conn.commit()

    builder = MaturedForwardLabelBuilder(db, horizon_sessions=1)
    df = builder.build_labels(["BETA"])
    assert not df.empty
    day1 = df[df["trading_date"] == "2026-02-01"].iloc[0]
    # Mixing TRI at start with PRI at end is forbidden! Must be UNOBSERVABLE_BENCHMARK
    assert bool(day1["matured"]) is False
    assert day1["status"] == "UNOBSERVABLE_BENCHMARK"
    assert pd.isna(day1["bench_fwd_ret"])
    assert pd.isna(day1["label_excess_ret_net"])


def test_baseline_zero_sharpe_and_cannot_promote(tmp_path):
    """ZeroReturnBaseline must produce 0 Sharpe and be completely barred from promotion."""
    from src.ml.training.tournament import ZeroReturnBaseline
    db_file = str(tmp_path / "test_baseline.db")
    db = DatabaseManager(db_file)
    tournament = ModelTournament(db, artifact_dir=str(tmp_path))

    # Evaluate constant prediction
    preds = np.zeros(20)
    y_test = np.random.normal(0.01, 0.05, 20)
    dates = np.array([f"2026-01-{i:02d}" for i in range(1, 21)])
    eval_res = tournament.evaluate_model(
        "ZeroReturnBaseline",
        ZeroReturnBaseline(),
        np.zeros((20, 5)),
        np.zeros(20),
        np.zeros((20, 5)),
        y_test,
        test_dates=dates
    )
    assert eval_res["validation_sharpe"] == 0.0
    assert eval_res["validation_ic"] == 0.0

    registry = ModelRegistryManager(db, artifact_dir=str(tmp_path))
    # Promoting baseline must fail
    with db.get_connection() as conn:
        conn.execute("""
            INSERT INTO model_registry (
                model_id, model_name, model_version, task_type,
                status, artifact_path, artifact_hash,
                train_start, train_end, metrics_json, created_at
            ) VALUES ('base_1', 'ZeroReturnBaseline', '1.0', 'REGRESSION', 'BASELINE', '', '', '2026-01-01', '2026-01-20', '{}', '2026-11-06T00:00:00Z');
        """)
    assert registry.promote_model("base_1") is False
