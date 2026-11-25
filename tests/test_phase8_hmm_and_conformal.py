"""
tests/test_phase8_hmm_and_conformal.py
Verification suite for MIL 2.0 Phase 8:
1. Forward-only HMM filtering causality (zero future look-ahead leakage).
2. Weighted Adaptive Conformal Cones coverage & drift widening.
3. Console bugfixes: sqlite3.Row .get() fix & feature_importance_pct zero-warning load.
4. Regime API endpoint (/api/v1/regime/status) & compact artifact size bounds.
"""

import json
import logging
from pathlib import Path

import numpy as np
import pytest
from starlette.testclient import TestClient

from src.api.main import app
from src.quant.conformal_cones import (
    DEFAULT_CONFORMAL_PATH,
    calibrate_regime_conformal_cell,
    compute_conformal_price_cone,
)
from src.quant.rebalance_engine import load_tournament_weights
from src.quant.regime_hmm import (
    DEFAULT_HMM_STATE_PATH,
    GaussianRegimeHMM,
    REGIME_NAMES,
)


def test_hmm_forward_filter_zero_lookahead_leakage():
    """
    Appending extreme future crash bars MUST NOT alter any past filtered
    regime probability P(S_t = k | F_t) for t < T.
    """
    rng = np.random.default_rng(42)
    calm = rng.normal(loc=[0.02, 0.12, 0.65, 0.012], scale=[0.015, 0.02, 0.10, 0.003], size=(120, 4))
    chop = rng.normal(loc=[0.00, 0.22, 0.45, 0.020], scale=[0.025, 0.04, 0.12, 0.005], size=(80, 4))
    hist = np.vstack([calm, chop])

    hmm = GaussianRegimeHMM(n_states=3, max_iter=30, random_state=42).fit(hist)
    probs_prefix = hmm.forward_filter(hist)

    # Append severe future crash bars
    crash = np.array([
        [-0.18, 0.55, 0.08, 0.045],
        [-0.22, 0.65, 0.05, 0.055],
        [-0.25, 0.72, 0.04, 0.060],
    ])
    probs_extended = hmm.forward_filter(np.vstack([hist, crash]))

    assert probs_prefix.shape == (200, 3)
    assert probs_extended.shape == (203, 3)
    assert np.allclose(probs_prefix, probs_extended[:200], atol=1e-12), (
        "Forward-only HMM filtering leaked future observations into past probabilities!"
    )
    assert np.allclose(np.sum(probs_extended, axis=1), 1.0, atol=1e-8)


def test_weighted_conformal_coverage_and_drift_widening():
    """
    Verifies weighted split-conformal intervals achieve calibrated coverage on
    stationary residuals and flag CONFORMAL_COVERAGE_DRIFT + widen on tail shock.
    """
    rng = np.random.default_rng(123)
    n = 300
    sigmas = np.full(n, 0.04)
    # Stationary normal residuals -> should be well-calibrated
    stationary_res = rng.normal(0.0, 0.04, size=n)
    cell_ok = calibrate_regime_conformal_cell(stationary_res, sigmas, decay_lambda=0.996, rolling_window=60)
    assert cell_ok["q_80"] > 0.8
    assert cell_ok["q_95"] > cell_ok["q_80"]
    assert cell_ok["rolling_60_coverage_80"] >= 0.70

    # Inject sudden 3x volatility shock in last 60 sessions -> triggers drift widening
    shock_res = stationary_res.copy()
    shock_res[-60:] = rng.normal(0.0, 0.14, size=60)
    cell_drift = calibrate_regime_conformal_cell(shock_res, sigmas, decay_lambda=0.996, rolling_window=60)
    assert cell_drift["drift_flag"] == "CONFORMAL_COVERAGE_DRIFT"
    assert cell_drift["drift_widening_factor"] > 1.0
    assert cell_drift["q_80"] > cell_drift["raw_q_80"]


def test_conformal_price_cone_widens_in_stress_vs_low_vol():
    """Verifies STRESS_DRAWDOWN 20D conformal cone is wider than LOW_VOL_TREND."""
    cone_low = compute_conformal_price_cone(
        current_price=1000.0,
        expected_return=0.02,
        annual_vol=0.22,
        horizon_days=20,
        regime="LOW_VOL_TREND",
    )
    cone_stress = compute_conformal_price_cone(
        current_price=1000.0,
        expected_return=0.02,
        annual_vol=0.22,
        horizon_days=20,
        regime="STRESS_DRAWDOWN",
    )
    width_low_80 = cone_low["upper_80_price"] - cone_low["lower_80_price"]
    width_stress_80 = cone_stress["upper_80_price"] - cone_stress["lower_80_price"]
    assert width_stress_80 > width_low_80
    assert cone_stress["upper_95_price"] > cone_stress["upper_80_price"] > cone_stress["lower_80_price"] > cone_stress["lower_95_price"]


def test_load_tournament_weights_zero_warnings(caplog):
    """Verifies tournament_summary.json includes feature_importance_pct and loads with zero warnings."""
    with caplog.at_level(logging.WARNING, logger="MIL.Rebalance"):
        weights = load_tournament_weights("data/models/tournament_summary.json")

    assert abs(sum(weights.values()) - 1.0) < 1e-3
    assert "No valid feature_importance_pct" not in caplog.text
    assert "Falling back to default weights" not in caplog.text


def test_ml_forecast_sqlite_row_no_attribute_error():
    """
    Verifies WalkForwardMLTrainer.predict_for_symbol handles sqlite3.Row objects
    without raising `'sqlite3.Row' object has no attribute 'get'`, even when bypassing
    the precomputed JSON cache.
    """
    from src.quant.ml_trainer import WalkForwardMLTrainer, _precomputed_forecasts, _precomputed_forecasts_lock
    from src.storage.database import DatabaseManager

    db = DatabaseManager()
    trainer = WalkForwardMLTrainer(db=db)

    # Temporarily bypass precomputed cache for RELIANCE to exercise DB sqlite3.Row path
    with _precomputed_forecasts_lock:
        saved = _precomputed_forecasts.pop("RELIANCE", None)

    try:
        res = trainer.predict_for_symbol("RELIANCE")
        assert isinstance(res, dict)
        assert res.get("symbol") == "RELIANCE"
        assert "forecasts" in res or "error" in res
    finally:
        if saved is not None:
            with _precomputed_forecasts_lock:
                _precomputed_forecasts["RELIANCE"] = saved

    client = TestClient(app)
    resp = client.get("/api/v1/ml/forecast/RELIANCE")
    assert resp.status_code == 200


def test_phase8_artifacts_and_regime_status_endpoint():
    """Verifies compact HMM & Conformal artifacts (< 100 KB / < 150 KB) and /api/v1/regime/status."""
    hmm_p = Path(DEFAULT_HMM_STATE_PATH)
    conf_p = Path(DEFAULT_CONFORMAL_PATH)
    assert hmm_p.exists(), "data/models/regime_hmm_state.json must exist"
    assert conf_p.exists(), "data/models/conformal_quantiles.json must exist"
    assert hmm_p.stat().st_size / 1024.0 < 100.0
    assert conf_p.stat().st_size / 1024.0 < 150.0

    client = TestClient(app)
    resp = client.get("/api/v1/regime/status?symbol=RELIANCE&horizon_days=20")
    assert resp.status_code == 200
    body = resp.json()
    assert body["active_regime"] in REGIME_NAMES
    assert body["causality_mode"] == "FORWARD_ONLY_FILTER"
    assert "policy" in body
    assert body["symbol_cones"] is not None
    assert "20D" in body["symbol_cones"]["horizons"]
    cone_20 = body["symbol_cones"]["horizons"]["20D"]
    assert cone_20["lower_95_price"] < cone_20["lower_80_price"] < cone_20["upper_80_price"] < cone_20["upper_95_price"]
