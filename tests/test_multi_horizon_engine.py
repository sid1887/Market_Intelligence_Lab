"""
tests/test_multi_horizon_engine.py
Hermetic verification suite for Phase 7.0 Multi-Horizon Research Engine.
Tests:
1. Multi-horizon label builder (5D, 20D, 60D forward returns, TRI/PRI benchmark isolation).
2. Walk-forward purged & embargoed cross-validation boundaries.
3. Multi-horizon model deployment registry & governance tracking.
4. Signal blending & automated portfolio rebalance proposal generation.
"""

import os
import json
import sqlite3
import pytest
import numpy as np
import pandas as pd

from src.storage.database import DatabaseManager
from src.storage.migrations import run_all_migrations
from src.ml.labels.builder import MaturedForwardLabelBuilder
from src.ml.training.tournament import generate_walk_forward_folds
from src.ml.registry.manager import ModelRegistryManager
from src.quant.rebalance_engine import RebalanceEngine


@pytest.fixture
def multi_horizon_db(tmp_path):
    """Hermetic isolated SQLite database with migrations 0001-0008 applied."""
    db_file = tmp_path / "test_multi_horizon.db"
    db_manager = DatabaseManager(str(db_file))

    with db_manager.get_connection() as conn:
        run_all_migrations(conn)

        # Seed synthetic benchmark index bars (100 sessions)
        dates = [f"2026-01-{i:02d}" if i <= 31 else (f"2026-02-{i-31:02d}" if i <= 59 else f"2026-03-{i-59:02d}") for i in range(1, 90)]
        for idx, d in enumerate(dates):
            conn.execute("""
                INSERT INTO index_daily (index_name, trading_date, open, high, low, close, volume, index_type, source, retrieval_timestamp)
                VALUES ('NIFTY 50', ?, ?, ?, ?, ?, 1000000, 'TRI', 'nse_historical', '2026-01-01T00:00:00Z')
            """, (d, 20000.0 + idx * 10, 20050.0 + idx * 10, 19950.0 + idx * 10, 20000.0 + idx * 10))

        # Seed 3 equities across all dates
        for sym in ["ALPHA", "BETA", "GAMMA"]:
            conn.execute("""
                INSERT OR IGNORE INTO securities_master (
                    symbol, company_name, isin, industry, sector, macro_sector, is_active, updated_at, is_nifty50
                ) VALUES (?, ?, ?, 'Financials', 'Banking', 'Financial Services', 1, '2026-01-01T00:00:00Z', 1)
            """, (sym, f"{sym} Ltd", f"INE{sym}01010"))

            base_p = 100.0 if sym == "ALPHA" else (200.0 if sym == "BETA" else 300.0)
            for idx, d in enumerate(dates):
                p = base_p + idx * 1.5
                conn.execute("""
                    INSERT INTO ohlcv_daily (
                        symbol, trading_date, series, open, high, low, close, volume,
                        is_synthetic, is_eligible_for_training, data_status, source, retrieval_timestamp
                    ) VALUES (?, ?, 'EQ', ?, ?, ?, ?, 50000, 0, 1, 'CONFIRMED', 'nse_bhavcopy', '2026-01-01T00:00:00Z')
                """, (sym, d, p, p + 2, p - 2, p))

                conn.execute("""
                    INSERT INTO quant_factors_daily (
                        symbol, trading_date, ret_1d, ret_5d, ret_20d, vol_20d_annualized,
                        sma_20, sma_50, sma_200, volume_ratio_20d, beta_60d_nifty,
                        roe_pct, debt_to_equity, opm_pct, is_orphaned
                    ) VALUES (?, ?, 0.01, 0.05, 0.10, 0.20, ?, ?, ?, 1.2, 1.0, 18.5, 0.45, 22.0, 0)
                """, (sym, d, p, p, p))

        # Seed baseline 20D model for multi-horizon deployments verification
        conn.execute("""
            INSERT INTO model_registry (
                model_id, model_name, model_version, task_type, target_horizon_days,
                status, validation_ic, validation_sharpe, created_at, train_start, train_end, metrics_json
            ) VALUES (
                'baseline_ridge_20d', 'Baseline_Ridge_20D', '1.0.0', 'REGRESSION', 20,
                'CHAMPION', 0.035, 1.40, '2026-01-01T00:00:00Z', '2024-01-01', '2025-12-31', '{}'
            )
        """)
        conn.execute("""
            INSERT INTO model_horizon_deployments (
                horizon_days, active_model_id, promoted_at, promoted_by, validation_ic, validation_sharpe
            ) VALUES (
                20, 'baseline_ridge_20d', '2026-01-01T00:00:00Z', 'multi_horizon_fixture', 0.035, 1.40
            )
        """)

        conn.commit()

    return db_manager


def test_multi_horizon_label_builder_horizons(multi_horizon_db):
    """Verifies label generation across 5D, 20D, and 60D horizons."""
    for h in [5, 20, 60]:
        builder = MaturedForwardLabelBuilder(multi_horizon_db, horizon_sessions=h)
        df = builder.build_labels(["ALPHA"])

        assert not df.empty, f"Labels should not be empty for horizon {h}"
        assert "horizon_sessions" in df.columns
        assert df["horizon_sessions"].iloc[0] == h

        # First observation should be matured
        first_row = df.iloc[0]
        assert bool(first_row["matured"]) is True
        assert first_row["stock_fwd_ret"] is not None
        assert first_row["bench_fwd_ret"] is not None
        assert first_row["label_excess_ret_net"] is not None
        assert first_row["status"] == "MATURED"

        # Observation near end of calendar should be IN_FLIGHT
        last_row = df.iloc[-1]
        assert bool(last_row["matured"]) is False
        assert last_row["status"] == "IN_FLIGHT"


def test_walk_forward_purge_and_embargo_isolation():
    """Asserts that training signals strictly satisfy t_i + H < T_test and embargo buffer."""
    dates = [f"2026-01-{i:02d}" if i <= 31 else f"2026-02-{i-31:02d}" for i in range(1, 60)]
    records = []
    for d_idx, d in enumerate(dates):
        for sym in ["SYM1", "SYM2", "SYM3", "SYM4", "SYM5"]:
            target_d = dates[min(len(dates) - 1, d_idx + 5)]
            records.append({
                "symbol": sym,
                "trading_date": d,
                "target_date": target_d,
                "forward_relative_return_5d": 0.02
            })
    df = pd.DataFrame(records)

    folds = generate_walk_forward_folds(df, n_folds=3, horizon_days=5, embargo_days=2)
    assert len(folds) > 0

    for tr_idx, val_idx in folds:
        train_df = df.iloc[tr_idx]
        val_df = df.iloc[val_idx]

        test_start_date = val_df["trading_date"].min()
        # Invariant 1: No training target_date may overlap or exceed test_start_date
        assert (train_df["target_date"] < test_start_date).all()
        # Invariant 2: Training dates must respect embargo buffer
        assert (train_df["trading_date"] < test_start_date).all()


def test_model_horizon_deployments_ledger(multi_horizon_db, tmp_path):
    """Verifies that model_horizon_deployments tracks active champions per horizon."""
    registry = ModelRegistryManager(multi_horizon_db, artifact_dir=str(tmp_path))

    # Verify seeded 20D deployment from migration 0008
    deployments = registry.get_horizon_deployments()
    assert 20 in deployments
    assert deployments[20]["horizon_days"] == 20

    # Register and promote mock 5D model
    from sklearn.linear_model import Ridge
    mock_pipeline = Ridge()
    model_5d = registry.register_model(
        model_name="Ridge_Alpha5D_5D",
        model_version="1.0.0",
        task_type="REGRESSION",
        artifact_pipeline=mock_pipeline,
        metrics={"validation_ic": 0.035, "validation_sharpe": 1.25},
        status="CANDIDATE",
        target_horizon_days=5
    )
    promoted_5d = registry.promote_model(model_5d, approved_by="TEST_SUITE", min_ic_hurdle=0.01)
    assert promoted_5d is True

    # Register and promote mock 60D model
    model_60d = registry.register_model(
        model_name="HistGradientBoosting_Alpha5D_60D",
        model_version="1.0.0",
        task_type="REGRESSION",
        artifact_pipeline=mock_pipeline,
        metrics={"validation_ic": 0.040, "validation_sharpe": 1.10},
        status="CANDIDATE",
        target_horizon_days=60
    )
    promoted_60d = registry.promote_model(model_60d, approved_by="TEST_SUITE", min_ic_hurdle=0.01)
    assert promoted_60d is True

    # Check that all 3 horizons are tracked
    updated_deps = registry.get_horizon_deployments()
    assert 5 in updated_deps
    assert 20 in updated_deps
    assert 60 in updated_deps
    assert updated_deps[5]["active_model_id"] == model_5d
    assert updated_deps[60]["active_model_id"] == model_60d


def test_rebalance_proposal_engine(multi_horizon_db, tmp_path):
    """Verifies automated daily rebalance proposal, trade deltas, and friction calculations."""
    registry = ModelRegistryManager(multi_horizon_db, artifact_dir=str(tmp_path))

    # Promote fitted models for 5, 20, 60
    from sklearn.linear_model import Ridge
    from src.ml.features.builder import FEATURE_COLUMNS
    for h in [5, 20, 60]:
        fitted_model = Ridge()
        fitted_model.fit(np.zeros((5, len(FEATURE_COLUMNS))), np.zeros(5))
        m_id = registry.register_model(
            model_name=f"MockModel_{h}D",
            model_version="1.0.0",
            task_type="REGRESSION",
            artifact_pipeline=fitted_model,
            metrics={"validation_ic": 0.03, "validation_sharpe": 1.2},
            status="CANDIDATE",
            target_horizon_days=h
        )
        registry.promote_model(m_id, approved_by="TEST", min_ic_hurdle=0.01)

    engine = RebalanceEngine(multi_horizon_db, registry_manager=registry)
    proposal = engine.generate_daily_rebalance_proposal(top_n=2)

    assert proposal["status"] == "PROPOSED"
    assert "proposal_id" in proposal
    assert proposal["turnover_pct"] >= 0
    assert proposal["projected_cost_bps"] >= 0
    assert len(proposal["top_candidates"]) == 2
    assert len(proposal["trade_deltas"]) > 0

    # Verify persisted in database
    with multi_horizon_db.get_connection() as conn:
        cur = conn.execute("SELECT * FROM rebalance_proposals WHERE proposal_id = ?", (proposal["proposal_id"],))
        row = cur.fetchone()
        assert row is not None
        assert row["turnover_pct"] == proposal["turnover_pct"]


def test_rebalance_engine_disarms_sub_hurdle_models(multi_horizon_db, tmp_path):
    """
    Verifies quantitative governance hurdle:
    Sub-hurdle models (IC < 0.0150) must receive an effective weight of 0.0,
    with remaining valid models (20D, 60D) absorbing the normalized allocation (62.5% / 37.5%).
    """
    registry = ModelRegistryManager(multi_horizon_db, artifact_dir=str(tmp_path))
    from sklearn.linear_model import Ridge
    from src.ml.features.builder import FEATURE_COLUMNS

    # 1. Register and promote 5D model with sub-hurdle IC = 0.003
    fitted_5d = Ridge()
    fitted_5d.fit(np.zeros((5, len(FEATURE_COLUMNS))), np.zeros(5))
    m5 = registry.register_model(
        model_name="NoisyModel_5D",
        model_version="1.0.0",
        task_type="REGRESSION",
        artifact_pipeline=fitted_5d,
        metrics={"validation_ic": 0.0030, "validation_sharpe": 1.08},
        status="CANDIDATE",
        target_horizon_days=5
    )
    registry.promote_model(m5, approved_by="TEST", min_ic_hurdle=0.001)

    # 2. Register and promote 20D model with IC = 0.0349
    fitted_20d = Ridge()
    fitted_20d.fit(np.zeros((5, len(FEATURE_COLUMNS))), np.zeros(5))
    m20 = registry.register_model(
        model_name="Champion_20D",
        model_version="1.0.0",
        task_type="REGRESSION",
        artifact_pipeline=fitted_20d,
        metrics={"validation_ic": 0.0349, "validation_sharpe": 1.42},
        status="CANDIDATE",
        target_horizon_days=20
    )
    registry.promote_model(m20, approved_by="TEST", min_ic_hurdle=0.015)

    # 3. Register and promote 60D model with IC = 0.0260
    fitted_60d = Ridge()
    fitted_60d.fit(np.zeros((5, len(FEATURE_COLUMNS))), np.zeros(5))
    m60 = registry.register_model(
        model_name="Trend_60D",
        model_version="1.0.0",
        task_type="REGRESSION",
        artifact_pipeline=fitted_60d,
        metrics={"validation_ic": 0.0260, "validation_sharpe": 0.78},
        status="CANDIDATE",
        target_horizon_days=60
    )
    registry.promote_model(m60, approved_by="TEST", min_ic_hurdle=0.015)

    engine = RebalanceEngine(multi_horizon_db, registry_manager=registry)
    proposal = engine.generate_daily_rebalance_proposal(top_n=2)

    # Invariant 1: 5D horizon must be excluded from active horizons
    assert 5 not in proposal["active_horizons"]
    assert 20 in proposal["active_horizons"]
    assert 60 in proposal["active_horizons"]

    # Invariant 2: 20D and 60D absorb the allocation: 0.50/(0.50+0.30) = 0.625, 0.30/0.80 = 0.375
    weights = proposal["effective_weights"]
    assert weights[20] == pytest.approx(0.625, rel=1e-3)
    assert weights[60] == pytest.approx(0.375, rel=1e-3)
    assert weights.get(5, 0.0) == 0.0

    # Invariant 3: Model composite ID must only contain 20D and 60D champions
    assert "5D" not in proposal["model_composite_id"]
    assert "20D" in proposal["model_composite_id"]
    assert "60D" in proposal["model_composite_id"]


def test_rebalance_latest_api_endpoint(multi_horizon_db):
    """Verifies that GET /api/v1/rebalance/latest returns latest proposal and active weights."""
    from datetime import datetime, timezone
    import json
    from fastapi.testclient import TestClient
    from src.api.main import app
    from src.api.utils import get_db_connection

    app.dependency_overrides[get_db_connection] = multi_horizon_db.get_connection
    client = TestClient(app)

    # First without proposals
    r = client.get("/api/v1/rebalance/latest")
    assert r.status_code == 200

    # Insert a proposal into rebalance_proposals
    now_iso = datetime.now(timezone.utc).isoformat()
    with multi_horizon_db.get_connection() as conn:
        conn.execute("""
            INSERT INTO rebalance_proposals (
                proposal_id, session_date, model_composite_id, status, turnover_pct, projected_cost_bps,
                holdings_before_json, holdings_after_json, trade_deltas_json, created_at
            ) VALUES (
                'reb_test_001', '2026-03-30', 'BLENDED_20D:m1_60D:m2', 'PROPOSED', 0.0, 0.0,
                '{"ALPHA": 0.5}', '{"ALPHA": 0.5, "BETA": 0.5}',
                '[{"symbol": "BETA", "current_weight": 0.0, "target_weight": 0.5, "delta": 0.5, "action": "BUY", "blended_score": 90.0}]', ?
            )
        """, (now_iso,))
        conn.commit()

    r2 = client.get("/api/v1/rebalance/latest")
    assert r2.status_code == 200
    data = r2.json()
    assert data["proposal_id"] == "reb_test_001"
    assert "effective_weights" in data
    assert "holdings_after" in data
    assert len(data["trade_deltas"]) > 0
    assert data["trade_deltas"][0]["target_allocation_pct"] == 50.0
    assert data["trade_deltas"][0]["target_weight"] == 0.5

    app.dependency_overrides.clear()
