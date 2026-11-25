"""
tests/test_phase11_tr_and_nse_quarterly.py
Verification suite for MIL 2.0 Phase 11:
1. Total-return adj_close continuity across newly harvested dividends/splits.
2. NSE quarterly JSON parser standalone/consolidated deduplication & broadcast_Date IST extraction.
3. Causal inverse-volatility return scaling & kurtosis control.
"""

import numpy as np
import pandas as pd

from scripts.harvest_nse_quarterly_history import parse_and_deduplicate_nse_quarterly
from src.data.corporate_actions import CorporateActionsManager
from src.quant.ml_trainer import compute_causal_inverse_vol_weights
from src.storage.database import DatabaseManager


def test_total_return_adj_close_continuity_across_split_and_dividend(tmp_path):
    """
    Verifies CorporateActionsManager.apply_adjustments_to_ohlcv() preserves
    total-return adj_close continuity across a 2:1 split and cash dividend.
    """
    db = DatabaseManager(str(tmp_path / "test_tr.db"))
    db.init_schema()
    ca = CorporateActionsManager(db)
    # Record 2:1 split (ratio 2.0 -> 1.0, multiplier 0.5) on 2024-06-10 and Rs 10 dividend on 2024-06-15
    ca.record_action("TESTTR", "2024-06-10", "SPLIT", ratio_from=2.0, ratio_to=1.0)
    ca.record_dividend_action("TESTTR", "2024-06-15", dividend_amount=10.0, cum_close_price=500.0)

    df_raw = pd.DataFrame({
        "symbol": ["TESTTR"] * 4,
        "trading_date": ["2024-06-07", "2024-06-10", "2024-06-14", "2024-06-17"],
        "open": [1000.0, 500.0, 500.0, 490.0],
        "high": [1010.0, 505.0, 505.0, 495.0],
        "low": [990.0, 495.0, 495.0, 485.0],
        "close": [1000.0, 500.0, 500.0, 490.0],
        "volume": [10000, 20000, 20000, 20000],
    })
    adj = ca.apply_adjustments_to_ohlcv(df_raw, include_dividends=True)
    # 2024-06-07 close (1000) * 0.5 (split) * 0.98 (div) = 490.0 == 2024-06-17 adj_close!
    assert abs(float(adj.loc[0, "adj_close"]) - float(adj.loc[3, "adj_close"])) < 0.05
    # Volume on 2024-06-07 scaled by 1/0.5 = 20000 (excluding dividend)
    assert int(adj.loc[0, "adj_volume"]) == 20000


def test_nse_quarterly_parser_consolidated_dedup_and_ist_timestamp():
    """
    Verifies parse_and_deduplicate_nse_quarterly() prefers Consolidated over
    Standalone for the same period_end_date and preserves broadcast_Date IST timestamps.
    """
    raw_records = [
        {
            "toDate": "31-Mar-2025",
            "consolidated": "Standalone",
            "broadcast_Date": "20-May-2025 16:45:00",
            "re_net_sale": "1000.0",
            "re_net_profit": "100.0",
            "re_diluted_eps": "5.0",
        },
        {
            "toDate": "31-Mar-2025",
            "consolidated": "Consolidated",
            "broadcast_Date": "20-May-2025 17:15:00",
            "re_net_sale": "2500.0",
            "re_net_profit": "280.0",
            "re_diluted_eps": "14.0",
        },
        {
            "toDate": "30-Jun-2025",
            "consolidated": "Consolidated",
            "broadcast_Date": "28-Jul-2025 14:20:00",
            "re_net_sale": "2700.0",
            "re_net_profit": "310.0",
            "re_diluted_eps": "15.5",
        },
    ]
    parsed = parse_and_deduplicate_nse_quarterly(raw_records, "RELIANCE")
    assert len(parsed) == 2
    q_mar = parsed[0]
    assert q_mar["period_end_date"] == "2025-03-31"
    assert q_mar["reporting_basis"] == "CONSOLIDATED"
    assert q_mar["revenue"] == 2500.0
    assert q_mar["published_at_ist"] == "2025-05-20 17:15:00"
    assert not q_mar.get("is_carry_forward_duplicate", False)


def test_causal_inverse_vol_weights_causality_and_kurtosis_reduction():
    """
    Verifies compute_causal_inverse_vol_weights() is strictly causal and reduces
    excess kurtosis when high-volatility tail prints are down-weighted.
    """
    rng = np.random.default_rng(77)
    n = 200
    vols = np.concatenate([np.full(160, 0.15), np.full(40, 0.80)])
    w_prefix = compute_causal_inverse_vol_weights(vols[:160], target_vol=0.20, max_weight=2.0)
    w_full = compute_causal_inverse_vol_weights(vols, target_vol=0.20, max_weight=2.0)
    assert np.allclose(w_prefix, w_full[:160], atol=1e-12)
    assert np.all(w_full <= 2.0)
    assert w_full[-1] < w_full[0]

    # High-vol regime tail returns should see lower kurtosis after inverse-vol scaling
    rets = np.concatenate([rng.normal(0.0, 0.015, 160), rng.normal(0.0, 0.12, 40)])
    scaled_rets = rets * w_full
    kurt_raw = float(pd.Series(rets).kurtosis())
    kurt_scaled = float(pd.Series(scaled_rets).kurtosis())
    assert kurt_scaled < kurt_raw
