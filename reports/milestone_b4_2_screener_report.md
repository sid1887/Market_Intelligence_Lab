# Market Intelligence Lab — Milestone B4.2 & B4.3 Screener & Watchlist Report

**Screening Date:** `2026-10-28`  
**Execution Timestamp:** `2026-11-04 06:25:40 UTC`  
**Database:** `data/market_lab.db`  

---

## 1. Executive Summary

Milestone B4.2 & B4.3 implement a deterministic, multi-factor screening engine and universe expansion framework. The screener queries `quant_factors_daily` across both authoritative NIFTY 50 constituents and user trading watchlists (`SUZLON`, `TRIDENT`, `DRONACHRYA`, `MOREPENLAB`).

### Screening Directive Filter Criteria:
1. **Debt-to-Equity < 0.5** (Conservative balance sheet discipline)
2. **Exclude Financial Services** (Avoid capital structure distortion in financial leverage)
3. **ROE % > 15.0%** (High capital efficiency)
4. **Price > 200-day SMA** (Established medium-term structural uptrend)

| Metric | Value | Compliance Status |
| :--- | :--- | :--- |
| **Active NIFTY 50 Constituents** | `50` stocks | PASS (Breadth isolated) |
| **User Watchlists Onboarded** | `4` stocks | PASS |
| **Total Universe Evaluated** | `54` stocks | PASS |
| **Securities Passing All Criteria** | `9` stocks | PASS |
| **Total Daily OHLCV Bars** | `27,098` records | PASS |
| **Total Daily Factors Stored** | `27,093` records | PASS |

---

## 2. Multi-Factor Screened & Ranked Portfolio (`2026-10-28`)

Securities passing all technical and fundamental hurdles, sorted descending by **Composite Quality-Momentum Score** (combining ROE %, Low D/E, 20-Day Excess Return vs NIFTY 50, and OPM %):

| Rank | Symbol | Company Name | Sector | Type | Close (₹) | 200 SMA (₹) | D/E | ROE % | OPM % | Excess Ret (20d) | Composite Score |
| :-: | :--- | :--- | :--- | :-: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | **TCS** | Tata Consultancy Services Ltd. | Information Technology | `NIFTY 50` | ₹2,460.00 | ₹2,443.01 | 0.0000 | 50.57% | 24.79% | +21.77% | **88.35** |
| 2 | **HCLTECH** | HCL Technologies Ltd. | Information Technology | `NIFTY 50` | ₹1,400.50 | ₹1,328.60 | 0.0444 | 24.26% | 18.82% | +14.94% | **71.51** |
| 3 | **SUZLON** | Suzlon Energy Ltd | Renewable Energy | `WATCHLIST` | ₹36.85 | ₹34.82 | 0.0322 | 22.44% | 18.57% | +7.47% | **66.98** |
| 4 | **DRREDDY** | Dr. Reddy's Laboratories Ltd. | Healthcare | `NIFTY 50` | ₹1,335.40 | ₹1,243.99 | 0.0247 | 17.53% | 25.71% | +14.80% | **66.79** |
| 5 | **BAJAJ-AUTO** | Bajaj Auto Ltd. | Automobile and Auto Components | `NIFTY 50` | ₹10,485.00 | ₹10,281.48 | 0.0000 | 24.93% | 20.99% | -3.45% | **64.10** |
| 6 | **DRONACHRYA** | Droneacharya Aerial Innovations Ltd | Aerospace / Defense | `WATCHLIST` | ₹156.40 | ₹148.02 | 0.0230 | 17.11% | 27.68% | +6.66% | **63.49** |
| 7 | **TECHM** | Tech Mahindra Ltd. | Information Technology | `NIFTY 50` | ₹1,776.60 | ₹1,523.47 | 0.0456 | 20.18% | 12.10% | +18.38% | **59.91** |
| 8 | **MOREPENLAB** | Morepen Laboratories Ltd | Pharmaceuticals | `WATCHLIST` | ₹52.80 | ₹49.38 | 0.0774 | 15.68% | 15.61% | +7.38% | **48.77** |
| 9 | **APOLLOHOSP** | Apollo Hospitals Enterprise Ltd. | Healthcare | `NIFTY 50` | ₹8,137.00 | ₹8,081.54 | 0.3670 | 20.87% | 13.95% | -4.85% | **39.62** |

---

## 3. Dedicated Constituent Factor Row Audit: `SUZLON`

Complete factor row from `quant_factors_daily` and `user_watchlists` for **SUZLON** as of `2026-10-28`:

```json
{
  "symbol": "SUZLON",
  "trading_date": "2026-10-28",
  "ret_1d": -0.0215,
  "ret_5d": -0.0115,
  "ret_20d": 0.0386,
  "vol_20d_annualized": 0.0877,
  "sma_20": 36.7,
  "sma_50": 34.97,
  "sma_200": 34.82,
  "beta_60d_nifty": -0.0362,
  "volume_ratio_20d": 1.2461,
  "volume_zscore_50d": 1.0,
  "volume_log_zscore_50d": 0.9786,
  "is_volume_spike_ratio": 0,
  "is_volume_spike_zscore": 0,
  "distance_52w_high": -2.8474,
  "distance_52w_low": 17.4689,
  "volatility_annualized": 0.0877,
  "ttm_pe": 36.13,
  "roe_pct": 22.44,
  "debt_to_equity": 0.0322,
  "opm_pct": 18.57,
  "updated_at": "2026-11-04T06:25:21.931903+00:00",
  "open": 36.87,
  "high": 37.07,
  "low": 36.64,
  "close": 36.85,
  "volume": 23248428,
  "target_price": 45.0,
  "stop_loss": 33.0,
  "notes": "Turnaround play in renewable energy wind turbines with significant deleveraging",
  "added_date": "2026-10-01"
}
```

### Key Analytical Observations for `SUZLON`:
- **Debt-to-Equity:** `0.0322` (Substantially below `0.5` threshold; reflects clean deleveraging).
- **Return on Equity (ROE):** `22.44%` (Exceeds `15.0%` hurdle; indicates profitable operational turnaround).
- **Medium-Term Trend:** Close `₹36.85` vs 200 SMA `₹34.82` (Confirmed `Price > 200 SMA` structural uptrend).
- **Watchlist Targets:** Target Price = `₹45.0`, Stop Loss = `₹33.0`.

---

## 4. User Watchlist Inventory Summary

All 4 onboarded watchlist securities across their sectors and screening outcomes:

| Symbol | Company Name | Sector | Target Price | Stop Loss | Notes | Screen Status |
| :--- | :--- | :--- | :---: | :---: | :--- | :---: |
| **SUZLON** | Suzlon Energy Ltd | Renewable Energy | ₹45.00 | ₹33.00 | Turnaround play in wind turbines | **PASSED (Rank #4)** |
| **DRONACHRYA** | Droneacharya Aerial Innovations Ltd | Aerospace / Defense | N/A | N/A | Drone surveying & pilot training | **PASSED (Rank #6)** |
| **MOREPENLAB** | Morepen Laboratories Ltd | Pharmaceuticals | N/A | N/A | API & medical devices manufacturer | **PASSED (Rank #8)** |
| **TRIDENT** | Trident Ltd | Textiles / Paper | N/A | N/A | Textiles & paper manufacturing | *FILTERED (ROE < 15%)* |

---

## 5. Architectural Invariants Verified
1. **NIFTY 50 Index Isolation:** `index_membership_history` was untouched. Market breadth calculations remain strictly bound to the 50 active index constituents.
2. **Point-in-Time Integrity:** Screening on historical dates queries only fundamentals filed strictly on or before `as_of_date`.
3. **Sector Awareness:** Excluding `Financial Services` removes highly levered banks/NBFCs without discarding low-debt manufacturing, healthcare, and technology compounders.
