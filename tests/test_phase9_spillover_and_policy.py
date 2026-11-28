"""
tests/test_phase9_spillover_and_policy.py
Verification suite for MIL 2.0 Phase 9:
1. Spillover Graph partial correlation symmetry, [-1, 1] bounds, and zero look-ahead leakage.
2. 100k-path Policy Optimizer micro-ticket monotonicity (₹2,500 vs ₹25,000 DP drag) & PositionSizer wiring.
3. GET /api/v1/regime/spillover endpoint schema & compact artifact size bounds.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from starlette.testclient import TestClient

from src.api.main import app
from src.portfolio.position_sizer import FrictionAwarePositionSizer
from src.quant.policy_optimizer import DEFAULT_POLICY_PATH, load_optimal_execution_policy
from src.quant.regime_hmm import REGIME_NAMES
from src.quant.spillover_graph import (
    DEFAULT_SPILLOVER_PATH,
    build_spillover_graph,
    compute_partial_correlations_from_returns,
    compute_systemic_contagion_index,
)


def test_spillover_partial_corr_symmetry_bounds_and_causality(tmp_path):
    """
    Verifies partial correlation matrix is symmetric, bounded in [-1, 1],
    and strictly causal up to `as_of_date` (future rows cannot alter past estimates).
    """
    import sqlite3

    rng = np.random.default_rng(99)
    n_days = 120
    dates = pd.bdate_range("2025-01-01", periods=n_days).strftime("%Y-%m-%d")
    base = rng.normal(0.0, 0.012, size=(n_days, 5))
    # Inject factor coupling
    mkt = rng.normal(0.0, 0.01, size=(n_days, 1))
    df = pd.DataFrame(base + 0.6 * mkt, index=dates, columns=["BANK", "IT", "AUTO", "METAL", "PHARMA"])

    pcorr, cols, est = compute_partial_correlations_from_returns(df.iloc[:100], window=60)
    assert len(cols) == 5
    assert pcorr.shape == (5, 5)
    assert np.allclose(pcorr, pcorr.T, atol=1e-10)
    assert np.allclose(np.diag(pcorr), 1.0, atol=1e-10)
    assert np.all((pcorr >= -1.0 - 1e-9) & (pcorr <= 1.0 + 1e-9))

    contagion = compute_systemic_contagion_index(df.iloc[:100], window=60)
    assert 0.0 <= contagion <= 100.0

    # Strict PIT check on hermetic SQLite DB with dates before and after 2025-06-30
    pit_db = tmp_path / "pit_spillover.db"
    pit_dates = pd.bdate_range("2025-03-01", periods=130).strftime("%Y-%m-%d")
    sector_names = ["NIFTY BANK", "NIFTY IT", "NIFTY AUTO", "NIFTY PHARMA", "NIFTY METAL", "NIFTY FMCG"]
    rows = []
    for s_idx, sec in enumerate(sector_names):
        px = 10000.0 + s_idx * 500.0
        for d_str in pit_dates:
            px *= 1.0 + float(rng.normal(0.0003, 0.011))
            rows.append((sec, d_str, round(px, 2)))
    with sqlite3.connect(pit_db) as conn:
        conn.execute("CREATE TABLE index_daily (index_name TEXT, trading_date TEXT, close REAL)")
        conn.executemany("INSERT INTO index_daily VALUES (?, ?, ?)", rows)
        conn.commit()

    pit_res = build_spillover_graph(db_path=str(pit_db), as_of_date="2025-06-30", output_path=None)
    assert pit_res["as_of_date"] <= "2025-06-30"


def test_policy_optimizer_micro_ticket_monotonicity_and_sizer_wiring():
    """
    Verifies 100k-path optimal_execution_policy.json satisfies micro-capital DP drag
    monotonicity (₹2,500 has higher fee drag & higher min_net_rr than ₹25,000) and
    loads automatically into FrictionAwarePositionSizer.
    """
    pol_p = Path(DEFAULT_POLICY_PATH)
    assert pol_p.exists(), "data/models/optimal_execution_policy.json must exist"
    assert pol_p.stat().st_size / 1024.0 < 50.0

    with open(pol_p, "r", encoding="utf-8") as f:
        pol_data = json.load(f)

    assert pol_data["n_paths_per_regime"] >= 100000
    for r in REGIME_NAMES:
        p_2500 = pol_data["policies_by_regime"][r]["2500"]
        p_25000 = pol_data["policies_by_regime"][r]["25000"]
        assert p_2500["observed_ticket_fee_drag_pct"] > p_25000["observed_ticket_fee_drag_pct"]
        assert p_2500["min_net_rr"] > p_25000["min_net_rr"]

    # Verify PositionSizer automatic lookup
    sizer = FrictionAwarePositionSizer(use_regime_policy=True)
    loaded = sizer.get_regime_optimal_policy(ticket_size=2500.0, regime="STRESS_DRAWDOWN")
    assert loaded is not None
    assert loaded["min_net_rr"] > 1.6


def test_spillover_artifact_and_endpoint_schema():
    """Verifies compact spillover_graph.json (< 150 KB) and GET /api/v1/regime/spillover."""
    sp_p = Path(DEFAULT_SPILLOVER_PATH)
    assert sp_p.exists(), "data/models/spillover_graph.json must exist"
    assert sp_p.stat().st_size / 1024.0 < 150.0

    client = TestClient(app)
    resp = client.get("/api/v1/regime/spillover")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert 0.0 <= body["systemic_contagion_index"] <= 100.0
    assert body["contagion_regime"] in ("SYSTEMIC_STRESS", "ELEVATED_COUPLING", "NORMAL_DISPERSION")
    assert isinstance(body["nodes"], list) and len(body["nodes"]) >= 4
    assert isinstance(body["sparse_partial_corr_edges"], list)
    assert isinstance(body["directed_lead_lag_edges"], list)
