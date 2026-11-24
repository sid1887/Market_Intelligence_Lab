# Market Intelligence Lab (MIL) 2.0 — Phase 3 Execution & Verification Report

**Date:** 2026-11-24  
**Author:** Principal Quantitative Systems Architect & Cloud Infrastructure Auditor  
**Status:** **PHASE 3 COMPLETE (100% Verified)**  

---

## Executive Summary

Phase 3 of Market Intelligence Lab (MIL) 2.0 has been implemented and verified. This phase addresses backtest overfitting, selection bias, and temporal leakage across MIL's quantitative research and machine learning pipeline:

1. **Conservative Daily Triple-Barrier Event Labeler & Path-Aware Net Cost Evaluator:** Replaces fixed-horizon labels with path-dependent volatility-scaled upper ($U$), lower ($L$), and vertical ($T_{\max}$) barriers. Implements a daily double-breach worst-case tie-break rule (conservatively assuming stop-loss was touched first if Open was within the corridor) and deducts exact statutory taxes + ₹23.60 Angel One DP charges via [`fee_engine.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/portfolio/fee_engine.py). Trades failing breakeven net of fees are disqualified from positive labels (`label != 1`).
2. **Combinatorial Purged Cross-Validation (CPCV) & Bailey-López de Prado Deflated Sharpe Ratio (DSR):** Implements `CombinatorialPurgedCV(n_splits=6, n_test_splits=2)` yielding $\binom{6}{2}=15$ combinations and 5 complete out-of-sample paths with $H$-session purging and $\max(H, 5)$ embargoing. Implements the Bailey & López de Prado (2014) Deflated Sharpe Ratio formulation incorporating Fisher excess kurtosis, proven to reduce to $\frac{1 + 0.5\widehat{SR}^2}{T - 1}$ under normality, and penalizing multiple testing selection bias across $M$ model trials.
3. **Two-Stage Meta-Labeling Tournament Engine & Zero-Cost Offload CLI:** Establishes a mandatory deterministic rule-based benchmark (Tactical Momentum + Low Volatility Quality + Structural Trend), a two-stage meta-labeling architecture (Stage 1 directional classifier + Stage 2 calibrated meta-probability with `min_meta_prob = 0.55` abstention gating), strict separation between **Market Alpha** and **Trader DNA**, exclusion of `SECTOR_ESTIMATE` rows, model registry tracking in SQLite, and a CLI runner [`scripts/run_phase3_tournament.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/scripts/run_phase3_tournament.py) designed for zero-cost compute (local CPU, GitHub Actions 16 GB, or Deepnote 5 GiB lake tier).

---

## 1. Conservative Daily Triple-Barrier Event Labeler (Deliverable 1)

**Implementation:** [`src/ml/triple_barrier.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/ml/triple_barrier.py)

### Mathematical Formulation
For each entry signal at session $t$ executed at session $t+1$ Open price ($P_0$):
- **Upper Profit Barrier ($U$):** $U = P_0 \times (1 + k_u \sigma_t)$
- **Lower Stop-Loss Barrier ($L$):** $L = P_0 \times (1 - k_l \sigma_t)$
- **Vertical Holding Horizon ($T_{\max}$):** $t + H$ trading sessions (default $k_u=2.0, k_l=1.5, H=20$)
- **Realized Volatility ($\sigma_t$):** 20-day trailing standard deviation of daily close returns ($\ge 0.005$ floor).

### Daily Double-Breach Worst-Case Tie-Break Invariant
On daily OHLC bars without tick data, if a daily candle breaches both barriers ($\text{High}_s \ge U$ and $\text{Low}_s \le L$):
- If $\text{Open}_s \ge U$: filled at $\text{Open}_s$ (upper gap opening).
- If $\text{Open}_s \le L$: filled at $\text{Open}_s$ (lower gap opening).
- **If $\text{Open}_s \in (L, U)$:** The engine conservatively assumes the stop-loss was touched first ($\text{barrier\_hit} = \text{"LOWER"}$, exit price = $L$, $\text{label} = -1$). This completely prevents optimistic look-ahead backtest bias.

### Net-of-Friction Fee Invariant
Gross returns are converted to net returns using the canonical [`calculate_roundtrip_friction`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/portfolio/fee_engine.py#L112-L185):
- Includes buy/sell turnover costs, exchange charges (0.0030699%), SEBI turnover (0.0001%), STT (0.1%), stamp duty (0.015%), 18% GST on taxable fees, and Angel One DP charges (₹23.60 on delivery sell legs).
- **Label Gating Rule:** $\text{label} = 1$ strictly requires $\text{barrier\_hit} == \text{"UPPER"}$ AND $\text{net\_return} > 0.0$. Micro-gains (e.g. +0.2% on ₹5,000 reference ticket) yielding negative net returns after DP charges are labeled `0` rather than `1`.

---

## 2. Combinatorial Purged Cross-Validation & Deflated Sharpe Ratio (Deliverable 2)

**Implementation:** [`src/quant/validation.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/validation.py)

### Combinatorial Purged Cross-Validation (CPCV)
- **Splits & Paths:** $\text{CPCV}(N=6, k=2)$ partitions chronological observations into 6 equal blocks. Evaluating all combinations of 2 test blocks yields $\binom{6}{2} = 15$ splits. Each block appears in exactly $\binom{5}{1} = 5$ test sets, providing 5 continuous, non-overlapping out-of-sample backtest paths.
- **Purge Window:** For every test block $[t_{\text{start}}, t_{\text{end}})$, all training observations in $[t_{\text{start}} - H, t_{\text{start}})$ are purged to eliminate label look-ahead leakage.
- **Embargo Window:** All training observations in $[t_{\text{end}}, t_{\text{end}} + \max(H, 5))$ are dropped to prevent post-test autoregressive contamination.
- **Holdout Isolation:** [`CombinatorialPurgedCV.split_train_holdout`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/validation.py#L124-L138) isolates the final 252 sessions as an untouched holdout set excluded from CPCV tuning.

### Bailey & López de Prado Deflated Sharpe Ratio (DSR)
The variance of the estimated Sharpe ratio under non-normality (skewness $\gamma_3$, Fisher excess kurtosis $\gamma_4^{\text{ex}}$):
$$\mathbb{V}[\widehat{SR}] = \frac{1}{T - 1} \left( 1 - \gamma_3 \widehat{SR} + \frac{\gamma_4^{\text{ex}} + 2}{4} \widehat{SR}^2 \right)$$

When $\gamma_3 = 0$ and $\gamma_4^{\text{ex}} = 0$ (Normal distribution), the formula simplifies exactly to:
$$\mathbb{V}[\widehat{SR}] = \frac{1 + 0.5\widehat{SR}^2}{T - 1}$$

To correct for data-mining and multiple testing selection bias across $M$ trials, the threshold hurdle $SR^*$ is computed via the extreme value distribution quantile:
$$SR^* = \mathbb{E}\left[\max_{m=1,\dots,M} SR_m\right] \approx \sqrt{\mathbb{V}[\widehat{SR}]} \left( (1 - \gamma_E) \Phi^{-1}\left(1 - \frac{1}{M}\right) + \gamma_E \Phi^{-1}\left(1 - \frac{1}{M e}\right) \right)$$
where $\gamma_E \approx 0.5772156649$ is the Euler-Mascheroni constant. The Deflated Sharpe Ratio is:
$$\text{DSR} = \Phi\left(\frac{\widehat{SR} - SR^*}{\sqrt{\mathbb{V}[\widehat{SR}]}}\right)$$

---

## 3. Two-Stage Tournament Engine & Zero-Cost Offload CLI (Deliverable 3)

**Implementation:** [`src/quant/ml_trainer.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/ml_trainer.py) & [`scripts/run_phase3_tournament.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/scripts/run_phase3_tournament.py)

### Deterministic Rule-Based Baseline
Before any ML candidate is evaluated, the tournament benchmarks a deterministic, rule-based quantitative strategy across the exact same CPCV folds and friction costs:
$$\text{Baseline Score} = 0.40 \times \text{Tactical 20D} + 0.30 \times \text{Low Vol Quality} + 0.30 \times \text{Structural 200D Trend}$$
Long positions are taken on the top 30% of scores. A machine learning candidate can only be promoted if its mean out-of-sample Sharpe strictly exceeds the baseline net of fees.

### Two-Stage Meta-Labeling Architecture
1. **Stage 1 (Primary Directional Classifier):** Predicts trade direction ($\hat{y}_1 \in \{0, 1\}$).
2. **Stage 2 (Meta-Calibrator):** Evaluates whether taking the Stage 1 trade will be profitable after statutory and DP fees:
   $$y_{\text{meta}} = 1 \iff (y_{\text{true}} = 1 \land \hat{y}_1 = 1)$$
   Trained using `CalibratedClassifierCV(HistGradientBoostingClassifier, method="sigmoid")`.
3. **Abstention Gating:** If $P(\text{profitable} \mid X, \hat{y}_1) < \text{min\_meta\_prob}$ (default 0.55), the signal is filtered out (`ABSTAIN`).

### Market Alpha vs. Trader DNA Separation
- `FEATURE_COLUMNS_8` contains **only** instrument and cross-sectional market factors (`tactical_20d`, `trend_60d`, `structural_200d`, `rsi_regime`, `low_vol_quality`, `volume_accumulation`, `relative_strength_nifty`, `news_sentiment_7d`).
- Personal Trader DNA parameters (loss tolerance, revenge trading bias, execution speed) are **strictly isolated** to personal execution sizing and coaching gates; they are completely barred from model training matrices.
- `prepare_dataset_from_df` explicitly filters out all `SECTOR_ESTIMATE` or `is_sector_imputed == 1` rows to maintain Point-in-Time data integrity.

### Model Registry & State Tracking
Upon completion, tournament results are saved to `data/models/tournament_summary.json` and registered in SQLite table `model_registry`. The runner executes `mark_state_dirty()`, queuing the updated state for background synchronization to the private Azure Blob Storage container (`rg-mil-research / milstatearchive74b8`).

---

## 4. Test Verification & Invariant Proofs

The Phase 3 test suite [`tests/test_phase3_validation.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/tests/test_phase3_validation.py) was executed alongside the regression test suite. All tests passed with 100% compliance.

### Test Results Breakdown
```
tests/test_phase3_validation.py::TestTripleBarrierLabeler::test_daily_double_breach_worst_case_tie_break PASSED [  7%]
tests/test_phase3_validation.py::TestTripleBarrierLabeler::test_fee_drag_nullifies_micro_gains PASSED [ 14%]
tests/test_phase3_validation.py::TestTripleBarrierLabeler::test_lower_barrier_hit_triggers_stop_loss PASSED [ 21%]
tests/test_phase3_validation.py::TestTripleBarrierLabeler::test_upper_barrier_hit_with_positive_net_return PASSED [ 28%]
tests/test_phase3_validation.py::TestTripleBarrierLabeler::test_vertical_timeout_barrier PASSED [ 35%]
tests/test_phase3_validation.py::TestCombinatorialPurgedCV::test_cpcv_combinatorics_and_path_reconstruction PASSED [ 42%]
tests/test_phase3_validation.py::TestCombinatorialPurgedCV::test_cpcv_zero_temporal_leakage_and_purging PASSED [ 50%]
tests/test_phase3_validation.py::TestCombinatorialPurgedCV::test_split_train_holdout_untouched_slice PASSED [ 57%]
tests/test_phase3_validation.py::TestDeflatedSharpeRatio::test_analytical_variance_invariant_under_normality PASSED [ 64%]
tests/test_phase3_validation.py::TestDeflatedSharpeRatio::test_dsr_from_sample_returns PASSED [ 71%]
tests/test_phase3_validation.py::TestDeflatedSharpeRatio::test_dsr_penalizes_multiple_trials PASSED [ 78%]
tests/test_phase3_validation.py::TestTwoStageTournamentRunner::test_full_synthetic_tournament_execution PASSED [ 85%]
tests/test_phase3_validation.py::TestTwoStageTournamentRunner::test_market_alpha_separation_from_trader_dna PASSED [ 92%]
tests/test_phase3_validation.py::TestTwoStageTournamentRunner::test_sector_estimate_and_synthetic_rows_excluded PASSED [100%]

============================= 14 passed in 13.57s ==============================
```

### Full Multi-Phase Regression Suite
```
tests/test_fee_engine.py (6 passed)
tests/test_durable_state.py (6 passed)
tests/test_phase2_data_truth.py (7 passed)
tests/test_phase3_validation.py (14 passed)
tests/test_point_in_time_ttm.py (2 passed)
tests/test_truth_invariants.py (8 passed)
tests/test_portfolio_backtester.py (4 passed)

============================= 47 passed in 16.37s ==============================
```

---

## 5. Summary of Files Changed & Created

| File | Status | Description |
| :--- | :--- | :--- |
| [`src/ml/triple_barrier.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/ml/triple_barrier.py) | **Created** | Conservative Daily Triple-Barrier Labeler with volatility scaling, double-breach tie-break, and net-of-fee deductions. |
| [`src/quant/validation.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/validation.py) | **Created** | Combinatorial Purged CV ($\binom{6}{2}=15$), purging/embargoing, and Bailey & López de Prado Deflated Sharpe Ratio. |
| [`src/quant/ml_trainer.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/ml_trainer.py) | **Modified** | Added `TwoStageTournamentRunner`, deterministic baseline evaluation, meta-calibrator abstention, and model registry logging. |
| [`scripts/run_phase3_tournament.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/scripts/run_phase3_tournament.py) | **Created** | CLI runner for local, Deepnote (5 GiB), or GitHub Actions (16 GB) zero-cost tournament execution. |
| [`tests/test_phase3_validation.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/tests/test_phase3_validation.py) | **Created** | 14 comprehensive unit tests verifying all Phase 3 mathematical invariants. |
| [`docs/MIL_PHASE_3_EXECUTION_REPORT.md`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/docs/MIL_PHASE_3_EXECUTION_REPORT.md) | **Created** | Technical documentation and execution verification record. |

---

## 6. Next Steps (Phase 4 Readiness)

With Phase 1 (Azure Guardrails & Fee Engine), Phase 2 (Data-Truth Upgrades), and Phase 3 (Triple-Barrier, CPCV & Deflated Sharpe Tournament) 100% verified and locked down, MIL 2.0 is prepared for **Phase 4: Copilot Deliberation, Adaptive Sizing & Multi-Agent Consensus**:
1. Integration of personal Trader DNA parameters (drawdown pain threshold, loss aversion) strictly inside the position sizing and coaching deliberation layer.
2. 3-Agent consensus voting (Fundamental Analyst, Microstructure/Momentum Analyst, and Risk/Trader Coach) incorporating meta-label probability and friction hurdles.
