# Market Intelligence Lab — Milestone B4.1 Factor Persistence Audit

**Execution Timestamp:** `2026-11-03 17:31:46 UTC`  
**Target Table:** `quant_factors_daily`  
**Database Location:** `data/market_lab.db`  

---

## 1. Executive Summary

Milestone B4.1 has successfully populated the unified `quant_factors_daily` table deterministically across the 50-stock active universe defined in `securities_master`. The pipeline bridges quantitative market mechanics (20/50/200-day SMAs, annualized volatility, 60-day rolling beta vs NIFTY 50 PRI, volume liquidity metrics) and fundamental point-in-time valuation ratios (TTM P/E, ROE %, Debt-to-Equity, Operating Margin %) into a single queryable table.

| Metric | Result | Compliance Status |
| :--- | :--- | :--- |
| **Active Universe Stocks Processed** | `50` stocks | PASS |
| **Total Factor Records Populated** | `25,101` records | PASS |
| **Distinct Symbols in Factor Store** | `50` symbols | PASS |
| **Historical Trading Date Range** | `2023-04-10` to `2026-10-28` | PASS |
| **Pipeline Execution Duration** | `3.60` seconds | PASS |
| **SQLite Integrity Check** | `ok` | PASS |
| **Foreign Key Violations** | `0` errors | PASS |

---

## 2. Schema Audit (`quant_factors_daily`)

The table schema strictly adheres to the directive requirements. All 14 mandated columns are present, properly typed, and indexed for high-performance point-in-time cross-sectional and time-series queries.

| # | Column Name | Data Type | Nullable | Default | Role / Description |
| :-: | :--- | :--- | :-: | :-: | :--- |
| 0 | `symbol` | `TEXT` | `No` | `NULL` | PRIMARY KEY |
| 1 | `trading_date` | `TEXT` | `No` | `NULL` | PRIMARY KEY |
| 2 | `ret_1d` | `REAL` | `No` | `NULL` | MANDATORY FACTOR |
| 3 | `ret_5d` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 4 | `ret_20d` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 5 | `vol_20d_annualized` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 6 | `sma_20` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 7 | `sma_50` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 8 | `sma_200` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 9 | `beta_60d_nifty` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 10 | `volume_ratio_20d` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 11 | `volume_zscore_50d` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 12 | `volume_log_zscore_50d` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 13 | `is_volume_spike_ratio` | `INTEGER` | `No` | `0` | MANDATORY FACTOR |
| 14 | `is_volume_spike_zscore` | `INTEGER` | `No` | `0` | MANDATORY FACTOR |
| 15 | `distance_52w_high` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 16 | `distance_52w_low` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 17 | `volatility_annualized` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 18 | `ttm_pe` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 19 | `roe_pct` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 20 | `debt_to_equity` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 21 | `opm_pct` | `REAL` | `Yes` | `NULL` | OPTIONAL / WARMUP |
| 22 | `updated_at` | `TEXT` | `Yes` | `NULL` | OPTIONAL / WARMUP |

---

## 3. Representative Constituent Factor Walkthrough: `INFY`

Below is the chronological evolution of daily quantitative factors and fundamental ratios for **Infosys Ltd (INFY)** across early warm-up, mid-horizon mature history, and the latest trading session.

### A. Early Warm-Up Phase (`2024-10-28`)
Proves strict compliance with warm-up NULL handling. 6 trading sessions are insufficient for 20-day SMA, 20-day volatility, 50-day SMA, or 60-day beta; balance-sheet snapshot yields Debt-to-Equity while incomplete trailing quarters return NULL for TTM P/E and OPM.

```json
{
  "symbol": "INFY",
  "trading_date": "2024-10-28",
  "ret_1d": 0.0018,
  "ret_5d": 0.0068,
  "ret_20d": null,
  "vol_20d_annualized": null,
  "sma_20": null,
  "sma_50": null,
  "sma_200": null,
  "beta_60d_nifty": null,
  "volume_ratio_20d": null,
  "volume_zscore_50d": null,
  "volume_log_zscore_50d": null,
  "is_volume_spike_ratio": 0,
  "is_volume_spike_zscore": 0,
  "distance_52w_high": -1.7616,
  "distance_52w_low": 1.488,
  "volatility_annualized": null,
  "ttm_pe": null,
  "roe_pct": null,
  "debt_to_equity": 0.0,
  "opm_pct": null,
  "updated_at": "2026-11-03T17:31:44.717124+00:00"
}
```

### B. Mid-Horizon Mature History (`2025-10-27`)
All technical warm-up windows (including 200-day SMA and 60-day rolling beta) are fully populated. 4 trailing discrete quarters are filed, enabling accurate TTM P/E, ROE, and OPM.

```json
{
  "symbol": "INFY",
  "trading_date": "2025-10-27",
  "ret_1d": -0.0137,
  "ret_5d": 0.0204,
  "ret_20d": 0.0047,
  "vol_20d_annualized": 0.2483,
  "sma_20": 1476.52,
  "sma_50": 1483.08,
  "sma_200": 1603.46,
  "beta_60d_nifty": 0.9918,
  "volume_ratio_20d": 1.0141,
  "volume_zscore_50d": -0.19,
  "volume_log_zscore_50d": 0.0125,
  "is_volume_spike_ratio": 0,
  "is_volume_spike_zscore": 0,
  "distance_52w_high": -25.0168,
  "distance_52w_low": 15.1109,
  "volatility_annualized": 0.2483,
  "ttm_pe": 22.62,
  "roe_pct": 30.84,
  "debt_to_equity": 0.0,
  "opm_pct": 21.15,
  "updated_at": "2026-11-03T17:31:44.717124+00:00"
}
```

### C. Latest Historical Trading Session (`2026-10-28`)
Full cross-sectional factor state as of the latest trading session in the historical dataset.

```json
{
  "symbol": "INFY",
  "trading_date": "2026-10-28",
  "ret_1d": -0.0343,
  "ret_5d": -0.0067,
  "ret_20d": 0.1229,
  "vol_20d_annualized": 0.3819,
  "sma_20": 1071.39,
  "sma_50": 1083.81,
  "sma_200": 1222.12,
  "beta_60d_nifty": 1.0733,
  "volume_ratio_20d": 0.9984,
  "volume_zscore_50d": 0.7178,
  "volume_log_zscore_50d": 0.9418,
  "is_volume_spike_ratio": 0,
  "is_volume_spike_zscore": 0,
  "distance_52w_high": -35.0029,
  "distance_52w_low": 14.5604,
  "volatility_annualized": 0.3819,
  "ttm_pe": 16.21,
  "roe_pct": 32.24,
  "debt_to_equity": 0.0,
  "opm_pct": 21.03,
  "updated_at": "2026-11-03T17:31:44.717124+00:00"
}
```

---

## 4. Watchlist Symbol Assessment: `SUZLON`

> [!NOTE] Watchlist Status: `SUZLON`
> `SUZLON` is **not** an active constituent of the authoritative 50-stock NIFTY 50 universe in `securities_master`, nor does it possess historical OHLCV or financial filings in the current local database.
> As per directive instruction (*"displaying a sample factor row for INFY and SUZLON (if watchlist data is present)"*), its absence is formally recorded here. All 50 active universe constituents are 100% populated.

---

## 5. Active Constituent Peer Basket Audit (`2026-10-23`)

Cross-sectional snapshot across diverse sectors (IT, Energy, Banking, Consumer, NBFC) confirming uniform multi-factor integration:

| Symbol | Close (₹) | SMA 20 | SMA 50 | SMA 200 | Ann. Vol | Beta (60d) | Vol Ratio (20d) | Vol Z-Score | TTM P/E | ROE % | D/E | OPM % |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **BAJFINANCE** | ₹928.95 | 962.85 | 1,020.94 | 973.70 | 0.3323 | 1.4230 | 0.71 | -0.07 | 27.26 | 18.74% | 3.2301 | 31.95% |
| **HDFCBANK** | ₹692.80 | 712.29 | 716.12 | 796.77 | 0.2400 | 0.9768 | 0.60 | -0.78 | 10.84 | 14.37% | 0.0000 | 42.06% |
| **RELIANCE** | ₹1,190.00 | 1,192.59 | 1,250.00 | 1,339.25 | 0.2585 | 1.1717 | 1.00 | 0.49 | 16.82 | 10.64% | 0.3222 | 17.68% |
| **TCS** | ₹2,530.00 | 2,223.27 | 2,248.22 | 2,450.62 | 0.3535 | 1.1190 | 1.21 | 0.99 | 17.75 | 50.57% | 0.0000 | 24.79% |
| **TITAN** | ₹4,299.70 | 4,513.83 | 4,816.51 | 4,437.72 | 0.2230 | 0.8616 | 0.79 | -0.12 | 89.61 | 23.28% | 0.5027 | 9.54% |

---

## 6. Point-in-Time Governance & Mathematical Verification

1. **No Look-Ahead Bias:** Every fundamental ratio joined into `quant_factors_daily` strictly satisfies `filing_date <= trading_date`. Financial filings published after `trading_date` are completely invisible to earlier dates.
2. **Warm-Up Period Safety:** The engine enforces window requirements ($N \ge 20$ for SMA-20 and Volatility; $N \ge 50$ for SMA-50 and Volume Z-Score; $N \ge 200$ for SMA-200; $N \ge 60$ aligned sessions for Beta). Insufficient observations return `NULL` without throwing exceptions.
3. **Idempotency:** Re-executing `compute_daily_factors.py` performs safe upserts via SQLite `ON CONFLICT(symbol, trading_date) DO UPDATE SET ...`, guaranteeing zero duplicate rows.
