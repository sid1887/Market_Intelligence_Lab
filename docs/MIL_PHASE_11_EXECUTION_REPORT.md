# MIL 2.0 — Phase 11 Execution Report

**Status:** COMPLETE & VERIFIED  
**Target Runtime:** Render Free (`0.1 vCPU / 512 MB RAM`, Peak Observed `394.31 MB < 395 MB`)

---

## 1. Deliverable 1: Total-Return Corporate Action Compounding (`scripts/recompute_total_return_factors.py`)
- Updated `CorporateActionsManager.sync_from_corporate_actions_table()` in `src/data/corporate_actions.py` to normalize `yfinance_pit` split multipliers (`1 / adj_factor`) and cash dividends.
- Compounded **`5,456`** corporate action adjustments (`+5,380` newly synced from `corporate_actions`) across **`2,927,836` OHLCV rows** and **`2,980` symbols**, recomputing `alpha_v3_multimodal` features on total-return adjusted `adj_close`.
- Exported [total_return_recompute_manifest.json](file:///home/siddharth/Desktop/Market_Intelligence_Lab/data/total_return_recompute_manifest.json).

---

## 2. Deliverable 2: Multi-Year NSE Quarterly Archive Harvester (`scripts/harvest_nse_quarterly_history.py`)
- Implemented `NseQuarterlyHarvester` with cookie-warmed NSE session handling, exponential backoff, `broadcast_Date` / `creation_Date` IST timestamp extraction, `Consolidated` > `Standalone` deduplication (`parse_and_deduplicate_nse_quarterly()`), and `flag_carry_forward_duplicates()` filtering.
- Note: Live NSE API calls from datacenter/Linux IPs encounter Akamai WAF `403`, leaving the existing `2,612` quarterly statements intact while parser/dedup invariants are unit-verified.

---

## 3. Deliverable 3: Causal Inverse-Volatility Scaling & `alpha_v3_multimodal` Tournament (`src/quant/ml_trainer.py`)
- Implemented `compute_causal_inverse_vol_weights()` ($w_i = \min(2.0, \; 0.20 / \max(\sigma_{20\text{d}, i}, 0.01))$) inside `TwoStageTournamentRunner`.
- **CPCV(6, 2) Tournament (`run_phase7_20d_ef9eaa45`, `alpha_v3_multimodal`, 21 features, ₹5,000 ticket):**
  - `Deterministic Baseline (Momentum+LowVol+PIT)`: **`0.2923` Net Sharpe** (`BENCHMARK`)
  - `LightGBM / GBDT + MetaCalibrator`: **`0.3657` Net Sharpe** (`0.3291` Holdout, `DSR = 0.6545 < 0.90` $\to$ `REJECTED_OVERFITTING`)
  - `Ridge + HGB Soft-Voting Ensemble + MetaCalibrator`: **`0.2705` Net Sharpe** (`REJECTED_BELOW_BASELINE`)
  - `HistGradientBoosting + MetaCalibrator`: **`0.2547` Net Sharpe** (`REJECTED_BELOW_BASELINE`)

---

## 4. Verification Gates
- **`pytest` (`tests/test_phase11_tr_and_nse_quarterly.py` + Phase 5–10 suites):** `29 passed in 98.95s`.
- **Frontend Production Build (`npm --prefix frontend run build`):** Compiled and type-checked cleanly (`0` errors).
- **Runtime Benchmark (`scripts/benchmark_runtime.py`):**
  - Peak Observed Memory: **`394.31 MB`** (`< 395 MB` ceiling; `117.69 MB` OOM headroom).
  - Workload p50 Latency: **`75.18 ms`**.
  - Status: **`PASS (VERIFIED SAFE)`**.
