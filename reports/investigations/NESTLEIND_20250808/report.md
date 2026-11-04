# Stock Movement Investigation Report: Nestle India Ltd. (NESTLEIND)

> **Investigation ID:** `EXP_NESTLEIND_20250808`  
> **Trading Date:** `2025-08-08` | **Generated At:** `2026-11-01T11:15:30.912335+00:00`  
> **Final Outcome:** **UNEXPLAINED_PRICE_MOVEMENT** (`UNEXPLAINED_MOVEMENT`)  
> **Audit Provenance Hash:** `c36f4714642aadc57d42366507a8e8b65aaed6cf893819e99b01437232b53817`  

## A. Investigation Overview

| Attribute | Value | Attribute | Value |
| :--- | :--- | :--- | :--- |
| **Symbol** | `NESTLEIND` | **Company Name** | Nestle India Ltd. |
| **ISIN** | `INE239A01024` | **Trading Date** | `2025-08-08` |
| **Sector** | Fast Moving Consumer Goods | **Industry** | Fast Moving Consumer Goods |
| **Reporting Basis** | `CONSOLIDATED` | **Standalone Isolated?** | `No` |
| **Primary Classification** | `UNEXPLAINED_MOVEMENT` | **Secondary Tags** | `None` |
| **Confidence Level** | **UNEXPLAINED_MOVEMENT** | **Dataset Benchmark** | `MIL_FROZEN_BENCHMARK_2024_2026_V1` |

## B. Executive Summary

On 2025-08-08, Nestle India Ltd. (NESTLEIND) quoted at ₹1,096.50 with an unadjusted raw price discontinuity of -50.93% and an adjusted economic return of -1.86%. The raw price discontinuity is mechanically explained by the BONUS corporate action (adjustment factor 0.50). However, the underlying economic market return of -1.86% had no independent explanatory catalyst and is classified as 'UNEXPLAINED_MOVEMENT'.

- **Relative Performance:** Against broad-market benchmark NIFTY 50 (-0.95%), the stock exhibited an excess return of -0.91%. Compared to sector benchmark NIFTY FMCG (-0.72%), the sector-adjusted return (SAR) was -1.14%.
- **Systematic Coupling:** The price action did not exhibit strong systematic coupling; classified as idiosyncratic or routine drift.
- **Strongest Hypothesis:** Mechanical Price Adjustment: BONUS Corporate Action (EV_CA_NESTLEIND_BONUS_20250808_BONUS_1_1). Underlying Economic Return: No independent market catalyst identified (UNEXPLAINED_MOVEMENT).
- **Evidential Sufficiency:** Mechanical price adjustment is fully accounted for by corporate action; evidential support for underlying economic return is INSUFFICIENT.

> [!NOTE]
> Methodological Note: The evidence strength score (0.0 to 100.0) is a deterministic heuristic measuring evidence quality, temporal proximity, and directional consistency. It is NOT a statistical probability or a calibrated confidence interval.

## C. Quantitative Market Movement Analysis

### 1. Price Action & Return Structure

| Metric | Value | Baseline / Context |
| :--- | :---: | :--- |
| **Close Price** | `₹1,096.50` | Open: `₹1,122.00`, High: `₹1,126.40`, Low: `₹1,093.40` |
| **Raw 1-Day Return** | `-50.93%` | Close-to-close unadjusted change |
| **Adjusted 1-Day Return** | `-1.86%` | Corporate-action adjusted price return |
| **Overnight Gap Open** | `-49.79%` | Previous close to session open |
| **Intraday Drift** | `-2.27%` | Session open to session close |
| **5-Session Return** | `-51.83%` | Preceding 5 trading days momentum |
| **20-Session Return** | `-54.38%` | Preceding 20 trading days momentum |

### 2. Benchmark & Econometric Market Model

| Metric | Value | Econometric Interpretation |
| :--- | :---: | :--- |
| **NIFTY 50 PRI Return** | `-0.95%` | Broad-market baseline return ($R_{m,t}$) |
| **Sector Return** | `-0.72%` | NIFTY FMCG (OFFICIAL_SECTOR_PRI) |
| **Abnormal Return ($AR_t$)** | `-1.30%` | OLS Market Model excess return ($t = -1.25$) |
| **Sector-Adjusted Return ($SAR_t$)** | `-1.14%` | Net outperformance over sector benchmark |
| **Market Beta ($\beta$) & Alpha ($\alpha$)** | `β=0.61, α=0.00008` | OLS Market Model coefficients (179 sessions) |

### 3. Volume & Liquidity Anomalies

- **Volume Ratio (vs 20d SMA):** `0.84x`
- **Log Volume Z-Score (vs 50d SMA):** `-0.10`
- **Volume Spike Flag:** `No (Normal / Muted Activity)`

### 4. Mechanical Corporate Action Price Adjustment

| Attribute | Value | Context / Meaning |
| :--- | :--- | :--- |
| **Corporate Action Type** | `BONUS` | Mechanical quoted price adjustment |
| **Adjustment Factor** | `0.50` | Recalculation factor applied on ex-date |
| **Quoted Raw Price Return** | `-50.93%` | Close-to-close unadjusted change |
| **Underlying Economic Return** | `-1.86%` | Corporate-action-adjusted price return |
| **Evidence ID** | `EV_CA_NESTLEIND_BONUS_20250808_BONUS_1_1` | Verified corporate action record |
| **Sentiment / Direction** | `NON-DIRECTIONAL` | Mechanical adjustment does not establish market sentiment |

> [!NOTE]
> Mechanical Adjustment Notice: Quoted price adjustments resulting from corporate actions (bonus issues, stock splits, cash dividends) are purely mechanical arithmetic recalculations. They do NOT establish positive or negative market sentiment, nor do they explain the underlying economic market return.

## D. Event and Evidence Timeline

### 1. Eligible Coinciding Evidence (Chronological)

| Date / Session | Evidence ID | Category | Direction | Tier | Headline |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `2025-08-08` | `EV_CA_NESTLEIND_BONUS_20250808_BONUS_1_1` | `BONUS_SPLIT_EVENT` | `NEUTRAL` | T2 | Corporate Action Ex-Date: NESTLEIND Bonus 1:1 (Factor: 0.5) |

### 2. Excluded Candidate Records & Audit Trail

| Evidence ID | Tier | Effective Session | Headline | Exclusion Reason |
| :--- | :---: | :---: | :--- | :--- |
| `EV_FS_NESTLEIND_Q2_FY26_CONS_V1` | T2 | `2025-10-16` | Quarterly Financial Statement (CONSOLIDATED V1): NESTLEIND DISCRETE_QUARTER 2025-09-30 | `FUTURE_EVENT_LOOKAHEAD (effective 2025-10-16 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20251016_PRI` | T3 | `2025-10-16` | Significant Index Move: NIFTY FMCG Surge (+2.02%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2025-10-16 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260101_PRI` | T3 | `2026-01-01` | Significant Index Move: NIFTY FMCG Selloff (-3.17%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-01-01 > 2025-08-08)` |
| `EV_FS_NESTLEIND_Q3_FY26_CONS_V1` | T2 | `2026-01-15` | Quarterly Financial Statement (CONSOLIDATED V1): NESTLEIND DISCRETE_QUARTER 2025-12-31 | `FUTURE_EVENT_LOOKAHEAD (effective 2026-01-15 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260201_PRI` | T3 | `2026-02-01` | Significant Index Move: NIFTY 50 Selloff (-1.96%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-01 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260201_PRI` | T3 | `2026-02-01` | Significant Index Move: NIFTY FMCG Selloff (-2.29%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-01 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260203_PRI` | T3 | `2026-02-03` | Significant Index Move: NIFTY 50 Surge (+2.55%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-03 > 2025-08-08)` |
| `EV_CA_NESTLEIND_DIVIDEND_20260206_INTERIM_DIVIDEND_RS_7_PER_SHAR` | T2 | `2026-02-06` | Corporate Action Ex-Date: NESTLEIND Interim Dividend - Rs 7 Per Share (Factor: 1.0) | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-06 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260206_PRI` | T3 | `2026-02-06` | Significant Index Move: NIFTY FMCG Surge (+2.27%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-06 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260213_PRI` | T3 | `2026-02-13` | Significant Index Move: NIFTY FMCG Selloff (-1.90%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-13 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260219_PRI` | T3 | `2026-02-19` | Significant Index Move: NIFTY FMCG Selloff (-1.76%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-19 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260227_PRI` | T3 | `2026-02-27` | Significant Index Move: NIFTY FMCG Selloff (-1.69%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-27 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260304_PRI` | T3 | `2026-03-04` | Significant Index Move: NIFTY 50 Selloff (-1.55%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-04 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260304_PRI` | T3 | `2026-03-04` | Significant Index Move: NIFTY FMCG Selloff (-1.88%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-04 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260309_PRI` | T3 | `2026-03-09` | Significant Index Move: NIFTY 50 Selloff (-1.73%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-09 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260309_PRI` | T3 | `2026-03-09` | Significant Index Move: NIFTY FMCG Selloff (-1.56%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-09 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260311_PRI` | T3 | `2026-03-11` | Significant Index Move: NIFTY 50 Selloff (-1.63%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-11 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260312_PRI` | T3 | `2026-03-12` | Significant Index Move: NIFTY FMCG Selloff (-1.77%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-12 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260313_PRI` | T3 | `2026-03-13` | Significant Index Move: NIFTY 50 Selloff (-2.06%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-13 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260319_PRI` | T3 | `2026-03-19` | Significant Index Move: NIFTY 50 Selloff (-3.26%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-19 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260319_PRI` | T3 | `2026-03-19` | Significant Index Move: NIFTY FMCG Selloff (-2.53%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-19 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260323_PRI` | T3 | `2026-03-23` | Significant Index Move: NIFTY 50 Selloff (-2.60%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-23 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260323_PRI` | T3 | `2026-03-23` | Significant Index Move: NIFTY FMCG Selloff (-2.49%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-23 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260324_PRI` | T3 | `2026-03-24` | Significant Index Move: NIFTY 50 Surge (+1.78%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-24 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260325_PRI` | T3 | `2026-03-25` | Significant Index Move: NIFTY 50 Surge (+1.72%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-25 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260325_PRI` | T3 | `2026-03-25` | Significant Index Move: NIFTY FMCG Surge (+1.89%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-25 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260327_PRI` | T3 | `2026-03-27` | Significant Index Move: NIFTY 50 Selloff (-2.09%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-27 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260327_PRI` | T3 | `2026-03-27` | Significant Index Move: NIFTY FMCG Selloff (-1.81%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-27 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260330_PRI` | T3 | `2026-03-30` | Significant Index Move: NIFTY 50 Selloff (-2.14%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-30 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260330_PRI` | T3 | `2026-03-30` | Significant Index Move: NIFTY FMCG Selloff (-1.91%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-30 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260401_PRI` | T3 | `2026-04-01` | Significant Index Move: NIFTY 50 Surge (+1.56%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-01 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260408_PRI` | T3 | `2026-04-08` | Significant Index Move: NIFTY 50 Surge (+3.78%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-08 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260408_PRI` | T3 | `2026-04-08` | Significant Index Move: NIFTY FMCG Surge (+1.54%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-08 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260415_PRI` | T3 | `2026-04-15` | Significant Index Move: NIFTY 50 Surge (+1.63%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-15 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260415_PRI` | T3 | `2026-04-15` | Significant Index Move: NIFTY FMCG Surge (+1.51%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-15 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260417_PRI` | T3 | `2026-04-17` | Significant Index Move: NIFTY FMCG Surge (+2.65%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-17 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260421_PRI` | T3 | `2026-04-21` | Significant Index Move: NIFTY FMCG Surge (+2.55%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-21 > 2025-08-08)` |
| `EV_FS_NESTLEIND_Q4_FY26_CONS_V1` | T2 | `2026-04-23` | Quarterly Financial Statement (CONSOLIDATED V1): NESTLEIND DISCRETE_QUARTER 2026-03-31 | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-23 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260429_PRI` | T3 | `2026-04-29` | Significant Index Move: NIFTY FMCG Surge (+1.75%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-29 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260512_PRI` | T3 | `2026-05-12` | Significant Index Move: NIFTY 50 Selloff (-1.83%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-12 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260529_PRI` | T3 | `2026-05-29` | Significant Index Move: NIFTY 50 Selloff (-1.50%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-29 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260529_PRI` | T3 | `2026-05-29` | Significant Index Move: NIFTY FMCG Selloff (-1.51%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-29 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260601_PRI` | T3 | `2026-06-01` | Significant Index Move: NIFTY FMCG Selloff (-2.30%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-06-01 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260612_PRI` | T3 | `2026-06-12` | Significant Index Move: NIFTY 50 Surge (+1.99%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-06-12 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260701_PRI` | T3 | `2026-07-01` | Significant Index Move: NIFTY FMCG Surge (+2.08%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-07-01 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260708_PRI` | T3 | `2026-07-08` | Significant Index Move: NIFTY 50 Selloff (-2.12%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-07-08 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260708_PRI` | T3 | `2026-07-08` | Significant Index Move: NIFTY FMCG Selloff (-2.49%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-07-08 > 2025-08-08)` |
| `EV_CA_NESTLEIND_DIVIDEND_20260710_DIVIDEND_RS_5_PER_SHARE` | T2 | `2026-07-10` | Corporate Action Ex-Date: NESTLEIND Dividend - Rs 5 Per Share (Factor: 1.0) | `FUTURE_EVENT_LOOKAHEAD (effective 2026-07-10 > 2025-08-08)` |
| `EV_CA_NESTLEIND_DIVIDEND_20260710_SPECIAL_DIVIDEND_RS_2_PER_SHAR` | T2 | `2026-07-10` | Corporate Action Ex-Date: NESTLEIND Special Dividend - Rs 2 Per Share (Factor: 1.0) | `FUTURE_EVENT_LOOKAHEAD (effective 2026-07-10 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260729_PRI` | T3 | `2026-07-29` | Significant Index Move: NIFTY FMCG Surge (+1.66%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-07-29 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260803_PRI` | T3 | `2026-08-03` | Significant Index Move: NIFTY 50 Surge (+1.60%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-08-03 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260803_PRI` | T3 | `2026-08-03` | Significant Index Move: NIFTY FMCG Surge (+1.72%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-08-03 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260831_PRI` | T3 | `2026-08-31` | Significant Index Move: NIFTY FMCG Selloff (-1.69%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-08-31 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20260916_PRI` | T3 | `2026-09-16` | Significant Index Move: NIFTY FMCG Surge (+1.63%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-09-16 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260924_PRI` | T3 | `2026-09-24` | Significant Index Move: NIFTY 50 Selloff (-1.64%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-09-24 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260928_PRI` | T3 | `2026-09-28` | Significant Index Move: NIFTY 50 Selloff (-1.56%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-09-28 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20261001_PRI` | T3 | `2026-10-01` | Significant Index Move: NIFTY FMCG Selloff (-1.61%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-01 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20261005_PRI` | T3 | `2026-10-05` | Significant Index Move: NIFTY FMCG Surge (+1.80%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-05 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20261008_PRI` | T3 | `2026-10-08` | Significant Index Move: NIFTY 50 Selloff (-1.64%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-08 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20261008_PRI` | T3 | `2026-10-08` | Significant Index Move: NIFTY FMCG Selloff (-2.02%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-08 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20261009_PRI` | T3 | `2026-10-09` | Significant Index Move: NIFTY FMCG Surge (+2.20%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-09 > 2025-08-08)` |
| `EV_MKT_NIFTY_FMCG_20261012_PRI` | T3 | `2026-10-12` | Significant Index Move: NIFTY FMCG Selloff (-1.67%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-12 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20261013_PRI` | T3 | `2026-10-13` | Significant Index Move: NIFTY 50 Surge (+1.60%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-13 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20261015_PRI` | T3 | `2026-10-15` | Significant Index Move: NIFTY 50 Surge (+1.66%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-15 > 2025-08-08)` |

## E. Ranked Candidate Explanations

*No independent candidate explanations met the minimum score threshold for the underlying economic return. (Quoted price discontinuity is fully accounted for under Section C.4: Mechanical Corporate Action Price Adjustment).*

## F. Contradictory Evidence & Alternative Hypotheses

*No contradictory evidence detected for this session.*

## G. Data Gaps, Methodological Limitations & Governance

### Methodological Limitations:
- Frozen offline research dataset; real-time streaming market data is paused.
- Zero-LLM deterministic attribution; score measures evidence strength, not causal certainty.
- Consensus estimates must be authenticated; unauthenticated surprise remains UNKNOWN.

## H. Final Assessment & Audit Stamp

> **Final Assessment:** **UNEXPLAINED_PRICE_MOVEMENT**  
> **Conclusion:** The quoted price discontinuity of -50.93% is mechanically explained by the BONUS corporate action (factor 0.50). However, the underlying economic market return (-1.86%) remains an UNEXPLAINED MOVEMENT as no verified independent market catalyst was identified in the local evidence store.  
> **Audit Provenance Hash:** `c36f4714642aadc57d42366507a8e8b65aaed6cf893819e99b01437232b53817`  
> **Dataset / Checkpoint:** `MIL_FROZEN_BENCHMARK_2024_2026_V1`  

> *Note on Provenance Hash:* The SHA-256 audit hash cryptographically protects the canonical structured analytical payload (symbols, timestamps, classifications, price action, and ranked hypothesis scores). It ensures reproducibility and tamper-detection of analytical results across research environments independently of presentation markup or whitespace.

---
*DATA GOVERNANCE NOTICE: Market Intelligence Lab operates on a frozen historical research benchmark (October 2024 – October 2026). Automated web scraping is paused in compliance with exchange terms. Commercial deployment or live simulation requires authorized data licensing or academic agreements.*
