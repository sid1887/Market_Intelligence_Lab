"""
tests/test_phase10_multimodal_alpha.py
Verification suite for MIL 2.0 Phase 10:
1. Causal fixed-width fractional differentiation (fracdiff) weights & zero look-ahead leakage.
2. alpha_v3_multimodal exclusion of SECTOR_ESTIMATE / CARRY_FORWARD_DUPLICATE & Trader DNA isolation.
3. End-to-end alpha_v3_multimodal tournament execution & compact tournament_summary.json (< 15 KB, 100% weights).
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.ml.features.alpha_v3_multimodal import (
    FEATURE_COLUMNS_ALPHA_V3,
    TRADER_DNA_FORBIDDEN_COLUMNS,
    build_alpha_v3_multimodal_features,
    causal_fracdiff_series,
    get_fracdiff_weights,
)
from src.quant.ml_trainer import TwoStageTournamentRunner


def test_fracdiff_weights_and_zero_lookahead_leakage():
    """
    Verifies fixed-width window fracdiff weights decay cleanly and appending
    extreme future bars leaves all past fracdiff values identical to 1e-12.
    """
    w35 = get_fracdiff_weights(d=0.35, threshold=1e-4)
    assert w35[0] == 1.0
    assert len(w35) > 5
    assert abs(w35[-1]) >= 1e-4

    rng = np.random.default_rng(7)
    log_px = np.cumsum(rng.normal(0.0005, 0.015, size=120)) + 5.0
    fd_prefix = causal_fracdiff_series(log_px, d=0.35, threshold=1e-4)

    crash_future = np.array([2.5, 2.0, 1.5, 1.0, 0.5])
    fd_extended = causal_fracdiff_series(np.concatenate([log_px, crash_future]), d=0.35, threshold=1e-4)

    assert np.allclose(fd_prefix, fd_extended[:120], atol=1e-12), (
        "FracDiff leaked future observations into past series values!"
    )


def test_alpha_v3_excludes_non_pit_rows_and_trader_dna():
    """
    Verifies alpha_v3_multimodal excludes SECTOR_ESTIMATE and CARRY_FORWARD_DUPLICATE
    rows and strips all Trader DNA columns.
    """
    dates = pd.bdate_range("2025-01-01", periods=10).strftime("%Y-%m-%d")
    df = pd.DataFrame({
        "symbol": ["RELIANCE"] * 10,
        "trading_date": dates,
        "close": np.linspace(100.0, 110.0, 10),
        "volume": np.full(10, 100000.0),
        "sector": ["ENERGY"] * 10,
        "data_status": ["OBSERVED"] * 8 + ["SECTOR_ESTIMATE", "CARRY_FORWARD_DUPLICATE"],
        "is_carry_forward_duplicate": [False] * 9 + [True],
        "trader_dna_score": np.full(10, 88.0),
        "cooldown_active": [0] * 10,
    })

    out = build_alpha_v3_multimodal_features(df)
    assert len(out) == 8
    for dna_col in TRADER_DNA_FORBIDDEN_COLUMNS:
        assert dna_col not in out.columns
    for feat in FEATURE_COLUMNS_ALPHA_V3:
        assert feat in out.columns
        assert feat not in TRADER_DNA_FORBIDDEN_COLUMNS


def test_alpha_v3_tournament_end_to_end_and_summary_artifact(tmp_path):
    """
    Verifies end-to-end alpha_v3_multimodal tournament execution on synthetic panel
    and validates the live data/models/tournament_summary.json (< 15 KB, weights sum to 100.0).
    """
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2023-01-02", periods=320).strftime("%Y-%m-%d")
    rows = []
    for sym in ("RELIANCE", "TCS", "HDFCBANK", "INFY"):
        px = 100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, size=len(dates))))
        for i, d in enumerate(dates):
            rows.append({
                "symbol": sym,
                "trading_date": d,
                "close": float(px[i]),
                "adj_close": float(px[i]),
                "volume": float(rng.integers(50000, 200000)),
                "ret_20d": float(rng.normal(0.01, 0.05)),
                "volatility_20d": 0.20,
                "rsi_14": float(rng.uniform(35.0, 68.0)),
                "forward_return": float(rng.normal(0.008, 0.04)),
                "data_status": "OBSERVED",
                "is_sector_imputed": 0,
            })
    df = pd.DataFrame(rows)

    tmp_summary = tmp_path / "tournament_summary_tmp.json"
    runner = TwoStageTournamentRunner(
        horizon_days=20,
        n_splits=6,
        n_test_splits=2,
        holdout_sessions=40,
        summary_path=str(tmp_summary),
        feature_set="alpha_v3_multimodal",
    )
    res = runner.run_full_tournament(df=df)
    assert res["feature_set"] == "alpha_v3_multimodal"
    assert len(res["candidates"]) == 3
    assert tmp_summary.exists()
    assert abs(sum(res["feature_importance_pct"].values()) - 100.0) < 1e-3

    # Also validate the live Phase 10 artifact on disk
    live_p = Path("data/models/tournament_summary.json")
    assert live_p.exists()
    assert live_p.stat().st_size / 1024.0 < 15.0
    with open(live_p, "r", encoding="utf-8") as f:
        live = json.load(f)
    assert live["feature_set"] == "alpha_v3_multimodal"
    assert abs(sum(live["feature_importance_pct"].values()) - 100.0) < 1e-3
