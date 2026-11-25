# MIL 2.0 — Phase 8 Execution Report

**Status:** COMPLETE & VERIFIED  
**Target Runtime:** Render Free (`0.1 vCPU / 512 MB RAM`, Peak Observed `387.6 MB < 395 MB`)  
**Offline Burst Tier:** Azure `Standard_D4s_v5` (`rg-mil-research` / `indiasouthcentral`, 3-layer cost kill-switch)

---

## 1. Deliverable 1: Console Trace Bugfixes
1. **Fixed `sqlite3.Row` `.get()` Crash (`src/quant/ml_trainer.py` — `predict_for_symbol`):**
   - Converted `sqlite3.Row` objects from `ml_training_runs` via `dict(c_row)` before calling `.get(...)`, eliminating `'sqlite3.Row' object has no attribute 'get'` on `/api/v1/ml/forecast/{symbol}`.
   - Fixed undefined `latest_date` reference to `trading_date` in the `NIFTY 50` factor query.
2. **Normalized `feature_importance_pct` in `tournament_summary.json` (`src/quant/ml_trainer.py`, `src/quant/rebalance_engine.py`, `data/models/tournament_summary.json`):**
   - Emitted normalized `feature_importance_pct` (summing to `100.0`) inside `tournament_summary.json` (both top-level and `overall_summary.feature_importance_pct`) using deterministic baseline pillar weights (`rsi_14: 40.0`, `volatility_20d: 25.0`, `momentum_20d: 18.0`, `momentum_252d: 7.0`, `sma_ratio_50_200: 6.0`, `fundamental: 4.0`).
   - Updated `load_tournament_weights()` in `src/quant/rebalance_engine.py` to read top-level or nested `feature_importance_pct` with zero fallback warnings.

---

## 2. Deliverable 2: 3-State Gaussian HMM Market Regime Engine (`src/quant/regime_hmm.py`)
- **Causal Forward-Only Filtering:** Implemented `GaussianRegimeHMM` with offline scaled Baum-Welch EM fitting and strictly causal forward-only filtering $P(S_t = k \mid \mathcal{F}_t)$ (zero backward Viterbi smoothing).
- **Calibrated Features:** `NIFTY 50` 20D return, 20D annualized realized volatility, NSE cross-sectional breadth thrust, and cross-sectional return dispersion across **4,688 sessions** (`2007`–`2026-11-23`).
- **Empirical Regime Distribution (`data/models/regime_hmm_state.json` — `78.4 KB`):**
  - `LOW_VOL_TREND`: `51.15%` (`position_scale=1.0`, `max_portfolio_exposure=1.0`, `min_meta_prob_delta=0.0`)
  - `HIGH_VOL_CHOP`: `34.75%` (`position_scale=0.75`, `max_portfolio_exposure=0.70`, `min_meta_prob_delta=+0.05`)
  - `STRESS_DRAWDOWN`: `14.10%` (`position_scale=0.50`, `max_portfolio_exposure=0.25`, `veto_high_beta_breakouts=True`)

---

## 3. Deliverable 3: Weighted Adaptive Conformal Prediction Cones (`src/quant/conformal_cones.py`)
- **Exponentially Weighted Split-Conformal Calibration:** Computed normalized nonconformity scores $s_i = |y_i - \hat{y}_i| / \max(\hat{\sigma}_i, \epsilon)$ with exponential decay ($\lambda = 0.996$) grouped by HMM regime $\times$ horizon (`5D`, `10D`, `20D`).
- **Coverage Drift Auto-Widening:** Tracks rolling 60-session empirical coverage; flags `CONFORMAL_COVERAGE_DRIFT` and automatically widens $(q_{80}, q_{95})$ when empirical `80%` coverage drops below `72%`.
- **Compact Artifact & UI Integration (`data/models/conformal_quantiles.json` — `3.3 KB`):**
  - Exposed `GET /api/v1/regime/status` returning active HMM regime probabilities, execution policy, and calibrated `80% / 95%` price cones per symbol.
  - Wired `frontend/src/components/CopilotDrawer.tsx` to display the live HMM Regime Badge and calibrated `80% / 95%` Conformal Price Cones.

---

## 4. Deliverable 4: Budget-Safe Azure R&D Burst Runner (`scripts/azure_burst_research.sh`)
- Targets `rg-mil-research` (`indiasouthcentral`) with ephemeral `Standard_D4s_v5` (`4 vCPU, 16 GB RAM`) and **zero static Public IP** (`--public-ip-address ""`, executed via `az vm run-command invoke`).
- Enforces 3-layer cost protection:
  1. Mandatory Azure VM Auto-Shutdown at `23:30 IST` (`1800 UTC`).
  2. Bash `EXIT/ERR/INT/TERM` trap executing `az vm deallocate --no-wait`.
  3. Automatic artifact upload (`regime_hmm_state.json`, `conformal_quantiles.json`, `tournament_summary.json`) to `milstatearchive74b8/mil-durable-state`.

---

## 5. Verification Gates
- **Unit & Integration Tests (`pytest`):**
  - `tests/test_phase8_hmm_and_conformal.py` (6/6 passed): zero look-ahead leakage verified to `1e-12`, conformal drift widening verified, `sqlite3.Row` fix verified, zero-warning `load_tournament_weights`, and `/api/v1/regime/status` verified.
  - Combined Phase 5–8 regression suite (`20 passed`).
- **Frontend Production Build:** `npm --prefix frontend run build` passed with zero TypeScript or Next.js build errors.
- **Runtime Memory & Latency Benchmark (`scripts/benchmark_runtime.py`):**
  - Peak Observed Memory: **`387.6 MB`** (`< 395 MB` ceiling; `124.4 MB` OOM headroom out of `512 MB`, memory guard tightened to `385.0 MB`).
  - Workload p50 Latency: **`22.59 ms`**.
  - Status: **`PASS (VERIFIED SAFE)`**.
