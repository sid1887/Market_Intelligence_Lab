# MARKET INTELLIGENCE LAB (MIL) 2.0
## PHASE 7 EXECUTION REPORT: ALPHA RESEARCH TRACK 1 — NSE DELIVERY FLOW & PIT PEAD EARNINGS SURPRISE

**Date:** 2026-11-24  
**Git Commit Target:** `feat(mil-2.0): phase 7 nse delivery flow, pit pead engine, deepnote ml-book, and fee-adjusted cpcv tournament`  
**Status:** COMPLETE & FULLY VERIFIED  

---

### EXECUTIVE SUMMARY

In Phase 7 (Alpha Research Track 1 — Stage B), MIL 2.0 expanded from its baseline 8-factor feature suite to **`alpha_v2_flow_pead` (18 features)**, introducing verified point-in-time microstructure accumulation signals and fundamental post-earnings announcement drift (PEAD) surprises. Concurrently, the quantitative validation engine was upgraded to replace the naive flat 15 bps (0.0015) hurdle approximation with the **canonical Angel One retail cash delivery friction schedule (0.70% / 70 bps roundtrip drag at ₹5,000 ticket size)**, accounting for the statutory ₹23.60 sell DP fee, STT, turnover charges, and 18% GST.

A dedicated cloud research notebook was constructed and verified via the `mil-deepnote` MCP in Deepnote project `ml-book`, mirrored locally at `notebooks/phase7_flow_pead_research.ipynb`. The full 10-year Bhavcopy tournament across 18 features was executed locally using zero-cost compute: the deterministic baseline achieved **0.2923 Net Sharpe**, while all 3 ML candidates were automatically rejected (`REJECTED_BELOW_BASELINE`) by the Bailey & López de Prado Deflated Sharpe Ratio (DSR) promotion gate.

---

### DELIVERABLE 1: NSE DELIVERY FLOW & MICROSTRUCTURE ACCUMULATION FEATURES (`src/ml/features/institutional_flow.py`)

1. **Exchange Session-Date Integrity:**
   - Validates that daily observations follow official exchange trading session dates using `src.quant.calendar::is_trading_session`.
   - Cleanly drops weekend carryover rows, official exchange holidays, and duplicate `(symbol, trading_date)` records (retaining verified final records).

2. **Mathematical Formulations & Bounded Invariants:**
   - **`deliv_zscore_60d`:** Rolling 60-trading-session Z-score of deliverable volume percentage ($D_t \in [0, 100]$):
     $$Z_{\text{deliv}, t} = \frac{D_t - \mu_{60}}{\max(\sigma_{60}, 1\text{e}-4)}$$
     Winsorized strictly to $[-4.0, +4.0]$. Degenerate / zero-variance series default gracefully to $0.0$.
   - **`clv_1d` (Close Location Value):**
     $$\text{CLV}_t = \begin{cases} 0.5 & \text{if } \text{High}_t - \text{Low}_t \le 1\text{e}-5 \\ \text{clip}\left(\frac{\text{Close}_t - \text{Low}_t}{\text{High}_t - \text{Low}_t}, 0.0, 1.0\right) & \text{otherwise} \end{cases}$$
     Upper/lower circuit-locked candles ($\text{High} == \text{Low}$) default to neutral $0.5$.
   - **`deliv_clv_impulse`:**
     $$\text{deliv\_clv\_impulse}_t = \text{deliv\_zscore\_60d}_t \times (2.0 \times \text{clv\_1d}_t - 1.0)$$
     Bounded strictly to $[-8.0, +8.0]$. High delivery volume closing near the day's high produces positive accumulation impulse ($+1.0$ multiplier); high delivery volume closing near the low produces negative distribution impulse ($-1.0$ multiplier).
   - **`atpt_zscore_60d`:** Rolling 60-session Z-score of Average Rupee Turnover per Reported Trade:
     $$\text{ATPT}_t = \frac{\text{turnover}_t}{\max(\text{trades\_count}_t, 1)}$$
     Winsorized strictly to $[-4.0, +4.0]$. Resilient to missing/zero trade counts.
   - **`fii_dii_delta_qoq` & `promoter_pledge_delta`:**
     Point-in-time merge of shareholding pattern filings strictly as of `eligible_from_date <= trading_date`. Calculates quarterly delta in institutional ownership ($\Delta(\text{FII} + \text{DII})$) and promoter pledge percentage ($\Delta \text{pledged\_pct}$). Pre-filing periods safely default to $0.0$ with zero lookahead bias.

---

### DELIVERABLE 2: POINT-IN-TIME PEAD ENGINE (`src/ml/features/pead_engine.py`)

1. **Surprise Formulations:**
   - **`sue_eps` (Standardized Unexpected Earnings):**
     $$\text{sue\_eps}_q = \frac{\text{EPS}_q - \text{EPS}_{q-4}}{\max(\sigma_{\text{EPS}}, 0.01)}$$
     Seasonal YoY quarterly EPS surprise winsorized strictly to $[-5.0, +5.0]$.
   - **`opm_surprise_bps`:** YoY operating profit margin change in basis points:
     $$\text{opm\_surprise\_bps}_q = (\text{OPM}_q - \text{OPM}_{q-4}) \times 10,000$$
     Winsorized to $[-5000.0, +5000.0]$ bps.

2. **Strict Provenance & Timestamp Gating:**
   - Broadcast timestamp evaluation: filings disseminated after 15:30:00 IST or on non-trading days roll forward to the next open session ($t=0$).
   - **CRITICAL DATA-TRUTH INVARIANT:**
     - Rows with `pit_provenance == "OBSERVED_TIMESTAMP"` set `is_observed_pead = 1`.
     - Rows with `STATUTORY_FALLBACK_LAG_45D`, `STATUTORY_FALLBACK_LAG_60D`, or unobserved filing dates set `is_observed_pead = 0` AND MUST FORCIBLY HAVE `pead_reaction_score = 0.0`.
     - This guarantees that artificial statutory lag boundaries (+45d/+60d) never generate spurious post-earnings drift momentum signals.

3. **20-Session Exponential Decay:**
   - For observed filings (`is_observed_pead == 1`), across sessions $0 \le \Delta t \le 20$:
     $$\text{pead\_reaction\_score} = \text{clip}(\text{sue\_eps}, -3.0, 3.0) \times \exp\left(-\frac{\Delta t}{10.0}\right)$$
   - Beyond 20 sessions ($\Delta t > 20$), or when unobserved, reaction score decays strictly to $0.0$.

---

### DELIVERABLE 3: DEEPNOTE CLOUD RESEARCH ENVIRONMENT (`mil-deepnote` MCP)

1. **Workspace & Project Integration:**
   - Integrated with Deepnote project `ml-book` (Project ID: `f4289f19-b4ef-45f1-bfc3-a3851d10af2e`).
   - Created research notebook `phase7_flow_pead_research.ipynb` (Notebook ID: `8348f077d8684f448683175cab44f0ff`).
   - Created and structured 4 interactive cells:
     - Cell 1 (Markdown): Research objectives and hypothesis.
     - Cell 2 (Code): Alpha v2 feature definitions (`baseline_8` + `flow_6` + `pead_4` = 18 features).
     - Cell 3 (Code): Spearman Rank Information Coefficient (IC) & t-statistic calculation vs forward 20-day returns.
     - Cell 4 (Code): Feature cross-correlation matrix and friction-adjusted return simulation.
2. **Local Counterpart:**
   - Saved reproducible local Jupyter notebook at `notebooks/phase7_flow_pead_research.ipynb`.

---

### DELIVERABLE 4: UPGRADED CPCV(6, 2) TOURNAMENT & CANONICAL FRICTION HURDLE

1. **Elimination of 15 bps Approximation:**
   - In `src/quant/ml_trainer.py`, the previous flat `DEFAULT_HURDLE_RATE = 0.0015` (15 bps) approximation was replaced with `get_canonical_roundtrip_friction_rate(ticket=5000.0)`.
   - On a ₹5,000 reference delivery ticket, the Angel One statutory schedule (₹23.60 sell DP fee + STT + turnover + GST) imposes **0.70% (70 bps) drag**, 4.6x higher than the flat 15 bps approximation!

2. **10-Year Bhavcopy Tournament Results (`alpha_v2_flow_pead`, 18 Features):**
   - Combinatorial Purged Cross-Validation: $\binom{6}{2} = 15$ splits $\implies 5$ complete out-of-sample paths.
   - Reference Ticket: ₹5,000.00 (Friction Drag: 0.70%).
   - Candidates evaluated: 3 models (`RidgeClassifier`, `HistGradientBoosting`, `ExtraTreesClassifier`) with Stage 2 MetaCalibrator.

```
================================================================================
MIL 2.0 TOURNAMENT EXECUTION REPORT SUMMARY
================================================================================
Run ID:                run_phase7_20d_f70e7a1c
Feature Set:           alpha_v2_flow_pead (18 features)
Friction Drag:         0.70% (Angel One delivery schedule @ ₹5,000)
CPCV Combinations:     15 splits (5 complete out-of-sample paths)
Holdout Net Sharpe:    0.1506
Promotion Verdict:     REJECTED_BELOW_BASELINE
--------------------------------------------------------------------------------
Model Name                          | Net Sharpe  | DSR     | SR* Hurdle  | Abstention | Status
--------------------------------------------------------------------------------
Deterministic Baseline (Mom+LowVol) | 0.2923      | N/A     | N/A         | 0.0%       | BENCHMARK
RidgeClassifier + MetaCalibrator    | 0.0416      | 0.1842  | 0.5233      | 85.5%      | REJECTED_BELOW_BASELINE
HistGradientBoosting + MetaCalibrator | 0.1673      | 0.0000  | 0.3205      | 0.1%       | REJECTED_BELOW_BASELINE
ExtraTreesClassifier + MetaCalibrator | 0.0000      | 0.0000  | 0.2923      | 100.0%     | REJECTED_BELOW_BASELINE
================================================================================
Champion Selected:     HistGradientBoosting + MetaCalibrator (REJECTED_BELOW_BASELINE)
Summary Written:       data/models/tournament_summary.json (4.8 KB)
================================================================================
```

3. **Key Quantitative Insights:**
   - When exact statutory + DP friction (₹34.98 on ₹5,000) is deducted, the Deterministic Baseline delivers **0.2923 Net Sharpe** (down from 0.4322 under the understated 15 bps hurdle).
   - `RidgeClassifier + MetaCalibrator` achieves **0.0416 Net Sharpe** with an 85.5% abstention rate.
   - `HistGradientBoosting + MetaCalibrator` achieves **0.1673 Net Sharpe** with an 0.1% abstention rate.
   - `ExtraTreesClassifier + MetaCalibrator` achieves **0.0000 Net Sharpe** with 100% abstention (its meta-calibrator probability consistently remained below 0.55 on the test folds, vetoing every trade setup).
   - Because no candidate exceeded the 0.2923 benchmark or cleared the $DSR \ge 0.50$ hurdle on the holdout, the promotion gate properly assigned `REJECTED_BELOW_BASELINE`.
   - `data/models/tournament_summary.json` is stored compactly with return moments (mean, std, skewness, excess kurtosis, percentiles) at **4.8 KB** (well within the 15 KB limit).

---

### DELIVERABLE 5: VERIFICATION & REGRESSION TEST SUITE

1. **Phase 7 Test Suite (`tests/test_phase7_flow_and_pead.py`):**
   - `test_session_date_deduplication_and_sorting`: PASSED.
   - `test_clv_and_deliv_impulse_bounds_and_circuit_locks`: PASSED.
   - `test_deliv_zscore_and_atpt_zscore_bounds`: PASSED.
   - `test_pit_shareholding_delta_isolation`: PASSED.
   - `test_effective_filing_session_rolls_after_1530`: PASSED.
   - `test_strict_provenance_gating_statutory_fallback_isolation`: PASSED.
   - `test_observed_pead_exponential_decay_window`: PASSED.
   - `test_canonical_friction_rate_computation`: PASSED.
   - `test_tournament_runner_with_alpha_v2_features`: PASSED.

2. **Full Phase 2–7 Regression Test Suite:**
   - 47 passed in 138.42s across:
     - `tests/test_phase2_data_truth.py` (7/7 passed)
     - `tests/test_phase3_validation.py` (14/14 passed)
     - `tests/test_phase4_execution_and_copilot.py` (9/9 passed)
     - `tests/test_phase5_hardening.py` (5/5 passed)
     - `tests/test_phase6_ui_endpoints.py` (3/3 passed)
     - `tests/test_phase7_flow_and_pead.py` (9/9 passed)

3. **Frontend Production Build:**
   - `npm --prefix frontend run build`: Compiled with 0 errors across all 8 static and dynamic routes.
