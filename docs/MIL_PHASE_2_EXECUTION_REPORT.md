# Market Intelligence Lab (MIL) 2.0 — Phase 2 Execution & Verification Report

**Date:** 2026-11-24  
**Author:** Principal Quantitative Systems Architect & Cloud Infrastructure Auditor  
**Status:** **PHASE 2 COMPLETE (100% Verified)**  

---

## Executive Summary

Phase 2 of Market Intelligence Lab (MIL) 2.0 has been implemented and verified. This phase resolves fundamental data-truth flaws in historical pricing, corporate event causality, and universe selection:
1. **Total-Return Cash Dividend Backward Adjustments:** Eliminates the historical 1.5%–3.0% annual tracking error against `NIFTY 50 TRI` by compounding cash dividends alongside splits and bonuses without altering raw exchange prints in `ohlcv_daily`. Volume scaling is decoupled so physical share volumes adjust exclusively for splits/bonuses/rights and never for cash dividends.
2. **Timestamp-Exact Point-in-Time (PIT) Gating:** Replaces date-only join ambiguity with strict ISO-8601 IST timestamp causality ($\text{published\_at\_ist} < \text{decision\_timestamp\_ist}$). Standardizes EOD close decisions (`15:30 IST`) and pre-market open decisions (`09:00 IST`), while maintaining SEBI LODR statutory fallback lags (+45d/+60d) with provenance tagging.
3. **Survivorship-Aware Historical Universe Selection:** Implements point-in-time universe queries on `securities_master` (`listing_date <= t` and `(delisting_date IS NULL or delisting_date > t)`) and historical ticker alias resolution, eliminating survivorship bias in quantitative backtesting.

---

## 1. Cash Dividend Total-Return Adjustments (Deliverable 1)

**Implementation:** [`src/data/corporate_actions.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/data/corporate_actions.py)

### Mathematical Formulation
Historical prices in `ohlcv_daily` remain raw and immutable. Point-in-time total-return adjusted prices are computed via backward compounding:
$$\text{AdjClose}_t = P_t \times \prod_{s > t} \left(1 - \frac{D_s}{P_{s-1}}\right) \times \prod_{s > t} \frac{\text{Ratio}_{\text{to}, s}}{\text{Ratio}_{\text{from}, s}}$$
where:
- $D_s$ is the cash dividend per share on ex-dividend date $s$.
- $P_{s-1}$ is the unadjusted close price on the session immediately preceding $s$.
- $\text{Ratio}_{\text{to}, s} / \text{Ratio}_{\text{from}, s}$ is the stock split, bonus, or rights multiplier.

### Core Upgrades & Guardrails
- **Regex Extraction:** [`extract_cash_dividend_amount`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/data/corporate_actions.py#L27-L49) extracts dividends across rupee formats (`Rs`, `Re`, `INR`, hyphenated amounts, multi-component interim + special dividends) and percentage declarations (`100%`, `250%` of face value).
- **Corrupt Record Guardrail:** Rejects or flags corrupt dividend records where $D_s \ge 0.5 \times P_{s-1}$ unless explicitly flagged as a `SPECIAL` dividend.
- **Volume Decoupling:** In [`apply_adjustments_to_ohlcv`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/data/corporate_actions.py#L295-L355), prices (`adj_open`, `adj_high`, `adj_low`, `adj_close`) scale by the total-return multiplier $M(t)$, while `adj_volume` scales strictly by share-count multipliers (`SPLIT`, `BONUS`, `RIGHTS`), preventing cash dividends from distorting traded share volumes.
- **Deterministic Idempotency:** Action IDs are generated deterministically using md5 hashes of purpose text, guaranteeing that synchronizing corporate actions multiple times produces zero duplicate rows.

---

## 2. Timestamp-Exact Point-in-Time Gating (Deliverable 2)

**Implementation:** [`src/storage/temporal_guard.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/temporal_guard.py) & [`src/fundamentals/ttm_builder.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/fundamentals/ttm_builder.py)

### Canonical Decision Timestamps
- **EOD Close Decision (Session $t$):** `YYYY-MM-DDT15:30:00+05:30` ([`get_eod_close_decision_timestamp`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/temporal_guard.py#L55-L58)).
- **Pre-Market Open Decision (Session $t+1$):** `YYYY-MM-DDT09:00:00+05:30` ([`get_pre_market_decision_timestamp`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/temporal_guard.py#L61-L64)).

### Causality Enforcement
[`is_pit_eligible_at(published_at_ist, decision_timestamp_ist)`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/temporal_guard.py#L67-L89) parses offset-aware IST datetimes and enforces strict inequality:
$$\text{published\_at\_ist} < \text{decision\_timestamp\_ist}$$

- **Evening Filings:** A corporate filing published at `19:15 IST` on Day $t$ is strictly blocked at Day $t$ `15:30 IST` close decision, but becomes eligible at Day $t+1$ `09:00 IST` pre-market decision, allowing execution at the 09:15 open without an artificial multi-day delay.
- **Statutory Fallback Lags:** In [`filter_eligible_statements`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/fundamentals/ttm_builder.py#L96-L175), when exchange dissemination timestamps are absent, the system retains conservative SEBI LODR lags (`+45 days` quarterly, `+60 days` annual) and explicitly stamps `pit_provenance = "STATUTORY_FALLBACK_LAG_45D"` or `"STATUTORY_FALLBACK_LAG_60D"`.

---

## 3. Survivorship-Aware Historical Universe (Deliverable 3)

**Implementation:** [`src/storage/database.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/database.py), [`src/client/symbol_resolver.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/client/symbol_resolver.py), [`src/quant/backtest_engine.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/backtest_engine.py), & [`src/quant/portfolio_backtester.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/portfolio_backtester.py)

### Schema & Query Invariants
- Added `delisting_date TEXT DEFAULT NULL` to `securities_master` with backward-compatible additive migration in [`_migrate_schema()`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/database.py#L256-L260).
- Implemented [`get_pit_active_universe(as_of_date)`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/database.py#L749-L781) and [`get_pit_active_symbols(as_of_date)`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/database.py#L783-L786):
  ```sql
  SELECT symbol, company_name, isin, industry, sector, macro_sector, listing_date, delisting_date, is_active
  FROM securities_master
  WHERE (listing_date IS NULL OR listing_date <= :as_of_date)
    AND (delisting_date IS NULL OR delisting_date > :as_of_date)
  ORDER BY symbol ASC;
  ```
- Added [`resolve_pit_symbol(symbol, as_of_date)`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/client/symbol_resolver.py#L55-L68) with historical corporate restructuring dates (e.g. `HDFC` before 2023-07-13 vs `HDFCBANK`, `LTI`/`MINDTREE` before late 2022 vs `LTIM`).
- Integrated universe filtering into [`run_backtest`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/backtest_engine.py#L237-L244) and [`_get_strategy_scores`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/portfolio_backtester.py#L282-L287), ensuring backtests cannot allocate to delisted or unlisted securities on historical rebalance dates.

---

## 4. Verification & Test Suite

All tests in [`tests/test_phase2_data_truth.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/tests/test_phase2_data_truth.py) pass 100%:

```
tests/test_phase2_data_truth.py::test_extract_cash_dividend_amounts PASSED [ 14%]
tests/test_phase2_data_truth.py::test_total_return_adjustment_math_and_continuity PASSED [ 28%]
tests/test_phase2_data_truth.py::test_corporate_action_idempotency_and_guard_rail PASSED [ 42%]
tests/test_phase2_data_truth.py::test_evening_filing_timestamp_pit_gating PASSED [ 57%]
tests/test_phase2_data_truth.py::test_statutory_fallback_lag_when_timestamp_missing PASSED [ 71%]
tests/test_phase2_data_truth.py::test_survivorship_universe_inclusion_and_delisting PASSED [ 85%]
tests/test_phase2_data_truth.py::test_historical_ticker_alias_resolution PASSED [100%]
============================== 7 passed in 3.49s ===============================
```

### Regression Verification Across Core Subsystems
- `tests/test_fee_engine.py` (6/6 PASSED)
- `tests/test_durable_state.py` (6/6 PASSED)
- `tests/test_point_in_time_ttm.py` (2/2 PASSED)
- `tests/test_truth_invariants.py` (8/8 PASSED)
- `tests/test_portfolio_backtester.py` (4/4 PASSED)
- `tests/test_copilot_adaptive_live.py` (6/6 PASSED)
- `tests/test_corporate_disclosure_audit.py` (7/7 PASSED)
- `tests/test_historical_backfill_and_corporate_actions.py` (8/8 PASSED)
- `tests/test_advanced_backtest_and_comparison.py` (7/7 PASSED)
- `tests/test_milestone_b8_backtest.py` (4/4 PASSED)
