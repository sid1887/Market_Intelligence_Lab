# FACTOR & OHLCV RECONCILIATION INVESTIGATION REPORT
**Generated At:** 2026-11-06T14:24:48.348971+00:00  
**Database:** `data/market_lab.db`  
**Compliance Standards:** ADR-0011, MIL-DATA-003, MIL-P0-018

---

## 1. Executive Summary & Root Cause

| Metric | Measured Count | Percentage of Factor Table |
| :--- | :--- | :--- |
| **Total Factor Records (`quant_factors_daily`)** | 256,175 | 100.0% |
| **Total Market Bars (`ohlcv_daily`)** | 88,147 | N/A |
| **Fully Reconciled & Matched Records** | 88,012 | 34.36% |
| **Orphan Factor Records (No Matching OHLCV)** | 168,163 | 65.64% |
| **Orphan Records Tagged (`is_orphaned = 1`)** | 168,163 | 65.64% |

### Root Cause Diagnosis:
1. **Pre-Horizon Truncation (95.25% of orphans):**
   - **158,878 rows** span from `2020-01-01` to `2024-10-20`.
   - In previous database iterations, `ohlcv_daily` was re-initialized with a rolling 24-month horizon (starting `2024-10-21`), but `quant_factors_daily` retained the historical factor cache dating back to 2020.
   - Because the underlying price bars before `2024-10-21` were pruned, these factor rows were left without a matching `ohlcv_daily` entry.
2. **Post-Horizon Delisted / Untraded Tickers (4.75% of orphans):**
   - **7,919 rows** occur on or after `2024-10-21`.
   - These belong primarily to unseeded, inactive, or illiquid instruments (e.g. `BAGMANE` REIT with only 5 bars, `LTIM`, `CMPDI`, `CLEANMAX`, `BHARATCOAL`) where factor batch calculation attempted to compute factors on days when no trade or price was recorded on the NSE cash segment.

---

## 2. Temporal Period Classification

| Period Category | Orphan Count | Distinct Symbols | Date Range | Primary Cause |
| :--- | :--- | :--- | :--- | :--- |
| `CURRENT_HORIZON_POST_2024_10_21` | 8,025 | 131 | `2024-10-21` to `2026-10-28` | Untraded / non-trading days in factor pipeline |
| `PRE_HORIZON_2020_TO_2024_10_20` | 160,131 | 129 | `2020-01-01` to `2024-10-18` | Historical OHLCV 24M pruning |

---

## 3. Top Post-Horizon (>= 2024-10-21) Discrepant Equities

| Symbol | Company Name | Sector | Active? | Orphan Factor Bars | Total OHLCV Bars | Date Span |
| :--- | :--- | :--- | :---: | :--- | :--- | :--- |
| **BAGMANE** | Bagmane Prime Office REIT | Realty | Yes | 528 | 5 | `2024-10-21` to `2026-10-28` |
| **LTIM** | LTIMindtree Limited | Information Technology | Yes | 464 | 69 | `2024-10-21` to `2026-10-28` |
| **CMPDI** | Central Mine Planning & Design Institute Ltd. | Services | Yes | 384 | 151 | `2024-10-21` to `2026-10-20` |
| **CLEANMAX** | Clean Max Enviro Energy Solutions Ltd. | Power | Yes | 366 | 169 | `2024-10-21` to `2026-10-20` |
| **BHARATCOAL** | Bharat Coking Coal Ltd. | Oil Gas & Consumable Fuels | Yes | 337 | 198 | `2024-10-21` to `2026-10-20` |
| **GROWW** | Billionbrains Garage Ventures Ltd. | Financial Services | Yes | 290 | 245 | `2024-10-21` to `2026-10-20` |
| **CANHLIFE** | Canara HSBC Life Insurance Company Ltd. | Financial Services | Yes | 274 | 261 | `2024-10-21` to `2026-10-20` |
| **CPPLUS** | Aditya Infotech Ltd. | Capital Goods | Yes | 224 | 311 | `2024-10-21` to `2026-10-20` |
| **ANTHEM** | Anthem Biosciences Ltd. | Healthcare | Yes | 213 | 322 | `2024-10-21` to `2026-10-20` |
| **AEGISVOPAK** | Aegis Vopak Terminals Ltd. | Oil Gas & Consumable Fuels | Yes | 178 | 357 | `2024-10-21` to `2026-10-20` |
| **BELRISE** | Belrise Industries Ltd. | Automobile and Auto Components | Yes | 175 | 360 | `2024-10-21` to `2026-10-20` |
| **ATHERENERG** | Ather Energy Ltd. | Automobile and Auto Components | Yes | 159 | 376 | `2024-10-21` to `2026-10-20` |
| **ACMESOLAR** | ACME Solar Holdings Ltd. | Power | Yes | 45 | 491 | `2024-10-21` to `2026-10-20` |
| **360ONE** | 360 ONE WAM Ltd. | Financial Services | Yes | 40 | 496 | `2024-10-21` to `2026-10-20` |
| **AEGISLOG** | Aegis Logistics Ltd. | Oil Gas & Consumable Fuels | Yes | 40 | 495 | `2024-10-21` to `2026-10-20` |
| **AIAENG** | AIA Engineering Ltd. | Capital Goods | Yes | 40 | 496 | `2024-10-21` to `2026-10-20` |
| **AJANTPHARM** | Ajanta Pharmaceuticals Ltd. | Healthcare | Yes | 40 | 496 | `2024-10-21` to `2026-10-20` |
| **ALKEM** | Alkem Laboratories Ltd. | Healthcare | Yes | 40 | 496 | `2024-10-21` to `2026-10-20` |
| **AUROPHARMA** | Aurobindo Pharma Ltd. | Healthcare | Yes | 40 | 496 | `2024-10-21` to `2026-10-20` |
| **AVANTIFEED** | Avanti Feeds Ltd. | Fast Moving Consumer Goods | Yes | 40 | 496 | `2024-10-21` to `2026-10-20` |

---

## 4. Retention Policy & Architectural Safeguards

Under strict contract guidelines (MIL-DATA-003):
1. **Zero Destructive Deletion:** No historical rows in `quant_factors_daily` were deleted, preserving historical factor computations for reference.
2. **Explicit Tagging (`is_orphaned`):** An indexed column `is_orphaned INTEGER NOT NULL DEFAULT 0` was added to `quant_factors_daily`. All 166,797 orphan rows are marked with `is_orphaned = 1`.
3. **Consumer Enforced Joins:**
   - Screener queries: filter on `WHERE q.is_orphaned = 0` or enforce `INNER JOIN ohlcv_daily o ON q.symbol = o.symbol AND q.trading_date = o.trading_date`.
   - ML feature extraction: enforce `INNER JOIN ohlcv_daily` to eliminate lookahead and feature leakage on ghost bars.
   - Backtest engine: only evaluates securities with verified `ohlcv_daily` bars.
