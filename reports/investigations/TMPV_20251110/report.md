# Stock Movement Investigation Report: Tata Motors Passenger Vehicles Ltd. (TMPV)

> **Investigation ID:** `EXP_TMPV_20251110`  
> **Trading Date:** `2025-11-10` | **Generated At:** `2026-11-01T11:15:30.944544+00:00`  
> **Final Outcome:** **MODERATELY_SUPPORTED_EXPLANATION** (`MODERATE_CONFIDENCE`)  
> **Audit Provenance Hash:** `aa28d1395d599a612391fdfd5108a4f37876fb2f01e2d069429b6e127c7ec8ee`  

## A. Investigation Overview

| Attribute | Value | Attribute | Value |
| :--- | :--- | :--- | :--- |
| **Symbol** | `TMPV` | **Company Name** | Tata Motors Passenger Vehicles Ltd. |
| **ISIN** | `INE155A01022` | **Trading Date** | `2025-11-10` |
| **Sector** | Automobile and Auto Components | **Industry** | Automobile and Auto Components |
| **Reporting Basis** | `CONSOLIDATED` | **Standalone Isolated?** | `No` |
| **Primary Classification** | `INSUFFICIENT_DATA` | **Secondary Tags** | `None` |
| **Confidence Level** | **MODERATE_CONFIDENCE** | **Dataset Benchmark** | `MIL_FROZEN_BENCHMARK_2024_2026_V1` |

## B. Executive Summary

On 2025-11-10, Tata Motors Passenger Vehicles Ltd. (TMPV) rose 1.17% (Close: ₹410.45) with an unadjusted raw return of +1.17%. The movement was classified as 'INSUFFICIENT_DATA'.

- **Relative Performance:** Against broad-market benchmark NIFTY 50 (+0.32%), the stock exhibited an excess return of +0.85%. Compared to sector benchmark NIFTY AUTO (+0.30%), the sector-adjusted return (SAR) was +0.87%.
- **Systematic Coupling:** The price action did not exhibit strong systematic coupling; classified as idiosyncratic or routine drift.
- **Strongest Hypothesis:** The highest-ranked explanatory candidate is 'EV_FS_TMPV_Q2_FY26_CONS_V1' with an evidence strength score of 65.0/100.0 (MODERATE_CONFIDENCE).
- **Evidential Sufficiency:** Available evidence provides sufficient corroboration for the candidate explanation.

> [!NOTE]
> Methodological Note: The evidence strength score (0.0 to 100.0) is a deterministic heuristic measuring evidence quality, temporal proximity, and directional consistency. It is NOT a statistical probability or a calibrated confidence interval.

## C. Quantitative Market Movement Analysis

### 1. Price Action & Return Structure

| Metric | Value | Baseline / Context |
| :--- | :---: | :--- |
| **Close Price** | `₹410.45` | Open: `₹406.00`, High: `₹412.95`, Low: `₹406.00` |
| **Raw 1-Day Return** | `+1.17%` | Close-to-close unadjusted change |
| **Adjusted 1-Day Return** | `+1.17%` | Corporate-action adjusted price return |
| **Overnight Gap Open** | `+0.07%` | Previous close to session open |
| **Intraday Drift** | `+1.10%` | Session open to session close |
| **5-Session Return** | `+0.11%` | Preceding 5 trading days momentum |

### 2. Benchmark & Econometric Market Model

| Metric | Value | Econometric Interpretation |
| :--- | :---: | :--- |
| **NIFTY 50 PRI Return** | `+0.32%` | Broad-market baseline return ($R_{m,t}$) |
| **Sector Return** | `+0.30%` | NIFTY AUTO (OFFICIAL_SECTOR_PRI) |
| **Abnormal Return ($AR_t$)** | `Unavailable` | OLS Market Model excess return ($t = N/A$) |
| **Sector-Adjusted Return ($SAR_t$)** | `+0.87%` | Net outperformance over sector benchmark |
| **Market Beta ($\beta$) & Alpha ($\alpha$)** | `β=N/A, α=N/A` | OLS Market Model coefficients (0 sessions) |

### 3. Volume & Liquidity Anomalies

- **Volume Ratio (vs 20d SMA):** `N/A`
- **Log Volume Z-Score (vs 50d SMA):** `N/A`
- **Volume Spike Flag:** `No (Normal / Muted Activity)`

## D. Event and Evidence Timeline

### 1. Eligible Coinciding Evidence (Chronological)

| Date / Session | Evidence ID | Category | Direction | Tier | Headline |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `2025-11-10` | `EV_FS_TMPV_Q2_FY26_CONS_V1` | `EARNINGS_RELEASE` | `AMBIGUOUS` | T2 | Quarterly Financial Statement (CONSOLIDATED V1): TMPV DISCRETE_QUARTER 2025-09-30 |
| `2025-11-10` | `EV_FS_TMPV_Q1_FY26_CONS_V2_RECAST` | `EARNINGS_REVISION` | `AMBIGUOUS` | T2 | Restated Financial Statement (CONSOLIDATED V2): TMPV DISCRETE_QUARTER 2025-06-30 |

### 2. Excluded Candidate Records & Audit Trail

| Evidence ID | Tier | Effective Session | Headline | Exclusion Reason |
| :--- | :---: | :---: | :--- | :--- |
| `EV_MKT_NIFTY_AUTO_20260120_PRI` | T3 | `2026-01-20` | Significant Index Move: NIFTY AUTO Selloff (-2.48%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-01-20 > 2025-11-10)` |
| `EV_FS_TMPV_Q3_FY26_CONS_V1` | T2 | `2026-01-30` | Quarterly Financial Statement (CONSOLIDATED V1): TMPV DISCRETE_QUARTER 2025-12-31 | `FUTURE_EVENT_LOOKAHEAD (effective 2026-01-30 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260201_PRI` | T3 | `2026-02-01` | Significant Index Move: NIFTY 50 Selloff (-1.96%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-01 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260201_PRI` | T3 | `2026-02-01` | Significant Index Move: NIFTY AUTO Selloff (-2.09%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-01 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260202_PRI` | T3 | `2026-02-02` | Significant Index Move: NIFTY AUTO Surge (+2.13%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-02 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260203_PRI` | T3 | `2026-02-03` | Significant Index Move: NIFTY 50 Surge (+2.55%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-03 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260203_PRI` | T3 | `2026-02-03` | Significant Index Move: NIFTY AUTO Surge (+2.81%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-03 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260219_PRI` | T3 | `2026-02-19` | Significant Index Move: NIFTY AUTO Selloff (-2.10%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-19 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260225_PRI` | T3 | `2026-02-25` | Significant Index Move: NIFTY AUTO Surge (+1.85%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-25 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260227_PRI` | T3 | `2026-02-27` | Significant Index Move: NIFTY AUTO Selloff (-1.86%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-27 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260302_PRI` | T3 | `2026-03-02` | Significant Index Move: NIFTY AUTO Selloff (-2.20%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-02 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260304_PRI` | T3 | `2026-03-04` | Significant Index Move: NIFTY 50 Selloff (-1.55%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-04 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260304_PRI` | T3 | `2026-03-04` | Significant Index Move: NIFTY AUTO Selloff (-2.44%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-04 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260305_PRI` | T3 | `2026-03-05` | Significant Index Move: NIFTY AUTO Surge (+1.86%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-05 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260309_PRI` | T3 | `2026-03-09` | Significant Index Move: NIFTY 50 Selloff (-1.73%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-09 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260309_PRI` | T3 | `2026-03-09` | Significant Index Move: NIFTY AUTO Selloff (-4.10%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-09 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260310_PRI` | T3 | `2026-03-10` | Significant Index Move: NIFTY AUTO Surge (+3.10%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-10 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260311_PRI` | T3 | `2026-03-11` | Significant Index Move: NIFTY 50 Selloff (-1.63%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-11 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260311_PRI` | T3 | `2026-03-11` | Significant Index Move: NIFTY AUTO Selloff (-3.15%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-11 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260312_PRI` | T3 | `2026-03-12` | Significant Index Move: NIFTY AUTO Selloff (-3.19%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-12 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260313_PRI` | T3 | `2026-03-13` | Significant Index Move: NIFTY 50 Selloff (-2.06%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-13 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260313_PRI` | T3 | `2026-03-13` | Significant Index Move: NIFTY AUTO Selloff (-3.60%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-13 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260316_PRI` | T3 | `2026-03-16` | Significant Index Move: NIFTY AUTO Surge (+1.67%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-16 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260317_PRI` | T3 | `2026-03-17` | Significant Index Move: NIFTY AUTO Surge (+2.11%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-17 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260318_PRI` | T3 | `2026-03-18` | Significant Index Move: NIFTY AUTO Surge (+1.92%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-18 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260319_PRI` | T3 | `2026-03-19` | Significant Index Move: NIFTY 50 Selloff (-3.26%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-19 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260319_PRI` | T3 | `2026-03-19` | Significant Index Move: NIFTY AUTO Selloff (-4.25%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-19 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260323_PRI` | T3 | `2026-03-23` | Significant Index Move: NIFTY 50 Selloff (-2.60%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-23 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260323_PRI` | T3 | `2026-03-23` | Significant Index Move: NIFTY AUTO Selloff (-3.16%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-23 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260324_PRI` | T3 | `2026-03-24` | Significant Index Move: NIFTY 50 Surge (+1.78%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-24 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260324_PRI` | T3 | `2026-03-24` | Significant Index Move: NIFTY AUTO Surge (+2.43%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-24 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260325_PRI` | T3 | `2026-03-25` | Significant Index Move: NIFTY 50 Surge (+1.72%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-25 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260325_PRI` | T3 | `2026-03-25` | Significant Index Move: NIFTY AUTO Surge (+2.22%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-25 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260327_PRI` | T3 | `2026-03-27` | Significant Index Move: NIFTY 50 Selloff (-2.09%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-27 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260327_PRI` | T3 | `2026-03-27` | Significant Index Move: NIFTY AUTO Selloff (-2.82%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-27 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260330_PRI` | T3 | `2026-03-30` | Significant Index Move: NIFTY 50 Selloff (-2.14%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-30 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260330_PRI` | T3 | `2026-03-30` | Significant Index Move: NIFTY AUTO Selloff (-2.39%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-30 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260401_PRI` | T3 | `2026-04-01` | Significant Index Move: NIFTY 50 Surge (+1.56%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-01 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260401_PRI` | T3 | `2026-04-01` | Significant Index Move: NIFTY AUTO Surge (+1.97%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-01 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260408_PRI` | T3 | `2026-04-08` | Significant Index Move: NIFTY 50 Surge (+3.78%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-08 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260408_PRI` | T3 | `2026-04-08` | Significant Index Move: NIFTY AUTO Surge (+6.69%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-08 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260410_PRI` | T3 | `2026-04-10` | Significant Index Move: NIFTY AUTO Surge (+2.85%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-10 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260413_PRI` | T3 | `2026-04-13` | Significant Index Move: NIFTY AUTO Selloff (-2.09%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-13 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260415_PRI` | T3 | `2026-04-15` | Significant Index Move: NIFTY 50 Surge (+1.63%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-15 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260415_PRI` | T3 | `2026-04-15` | Significant Index Move: NIFTY AUTO Surge (+1.53%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-15 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260423_PRI` | T3 | `2026-04-23` | Significant Index Move: NIFTY AUTO Selloff (-2.35%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-23 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260427_PRI` | T3 | `2026-04-27` | Significant Index Move: NIFTY AUTO Surge (+1.56%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-27 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260506_PRI` | T3 | `2026-05-06` | Significant Index Move: NIFTY AUTO Surge (+2.41%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-06 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260507_PRI` | T3 | `2026-05-07` | Significant Index Move: NIFTY AUTO Surge (+1.93%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-07 > 2025-11-10)` |
| `EV_FS_TMPV_Q4_FY26_CONS_V1` | T2 | `2026-05-11` | Quarterly Financial Statement (CONSOLIDATED V1): TMPV DISCRETE_QUARTER 2026-03-31 | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-11 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260511_PRI` | T3 | `2026-05-11` | Significant Index Move: NIFTY AUTO Selloff (-1.86%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-11 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260512_PRI` | T3 | `2026-05-12` | Significant Index Move: NIFTY 50 Selloff (-1.83%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-12 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260512_PRI` | T3 | `2026-05-12` | Significant Index Move: NIFTY AUTO Selloff (-2.28%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-12 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260518_PRI` | T3 | `2026-05-18` | Significant Index Move: NIFTY AUTO Selloff (-1.71%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-18 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260525_PRI` | T3 | `2026-05-25` | Significant Index Move: NIFTY AUTO Surge (+1.71%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-25 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260529_PRI` | T3 | `2026-05-29` | Significant Index Move: NIFTY 50 Selloff (-1.50%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-29 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260529_PRI` | T3 | `2026-05-29` | Significant Index Move: NIFTY AUTO Selloff (-1.96%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-29 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260601_PRI` | T3 | `2026-06-01` | Significant Index Move: NIFTY AUTO Selloff (-1.70%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-06-01 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260608_PRI` | T3 | `2026-06-08` | Significant Index Move: NIFTY AUTO Selloff (-1.85%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-06-08 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260612_PRI` | T3 | `2026-06-12` | Significant Index Move: NIFTY 50 Surge (+1.99%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-06-12 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260612_PRI` | T3 | `2026-06-12` | Significant Index Move: NIFTY AUTO Surge (+1.95%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-06-12 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260615_PRI` | T3 | `2026-06-15` | Significant Index Move: NIFTY AUTO Surge (+2.60%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-06-15 > 2025-11-10)` |
| `EV_CA_TMPV_DIVIDEND_20260619_DIVIDEND_RS_3_PER_SHARE` | T2 | `2026-06-19` | Corporate Action Ex-Date: TMPV Dividend - Rs 3 Per Share (Factor: 1.0) | `FUTURE_EVENT_LOOKAHEAD (effective 2026-06-19 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260625_PRI` | T3 | `2026-06-25` | Significant Index Move: NIFTY AUTO Surge (+2.25%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-06-25 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260629_PRI` | T3 | `2026-06-29` | Significant Index Move: NIFTY AUTO Selloff (-2.08%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-06-29 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260708_PRI` | T3 | `2026-07-08` | Significant Index Move: NIFTY 50 Selloff (-2.12%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-07-08 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260708_PRI` | T3 | `2026-07-08` | Significant Index Move: NIFTY AUTO Selloff (-2.23%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-07-08 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260714_PRI` | T3 | `2026-07-14` | Significant Index Move: NIFTY AUTO Selloff (-1.61%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-07-14 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260727_PRI` | T3 | `2026-07-27` | Significant Index Move: NIFTY AUTO Surge (+1.60%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-07-27 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260730_PRI` | T3 | `2026-07-30` | Significant Index Move: NIFTY AUTO Surge (+1.63%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-07-30 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260731_PRI` | T3 | `2026-07-31` | Significant Index Move: NIFTY AUTO Surge (+1.64%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-07-31 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260803_PRI` | T3 | `2026-08-03` | Significant Index Move: NIFTY 50 Surge (+1.60%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-08-03 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260807_PRI` | T3 | `2026-08-07` | Significant Index Move: NIFTY AUTO Surge (+1.84%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-08-07 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260902_PRI` | T3 | `2026-09-02` | Significant Index Move: NIFTY AUTO Selloff (-1.79%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-09-02 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260915_PRI` | T3 | `2026-09-15` | Significant Index Move: NIFTY AUTO Selloff (-2.01%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-09-15 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260924_PRI` | T3 | `2026-09-24` | Significant Index Move: NIFTY 50 Selloff (-1.64%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-09-24 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260924_PRI` | T3 | `2026-09-24` | Significant Index Move: NIFTY AUTO Selloff (-1.57%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-09-24 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20260928_PRI` | T3 | `2026-09-28` | Significant Index Move: NIFTY 50 Selloff (-1.56%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-09-28 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20260928_PRI` | T3 | `2026-09-28` | Significant Index Move: NIFTY AUTO Selloff (-1.64%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-09-28 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20261001_PRI` | T3 | `2026-10-01` | Significant Index Move: NIFTY AUTO Selloff (-3.46%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-01 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20261007_PRI` | T3 | `2026-10-07` | Significant Index Move: NIFTY AUTO Selloff (-1.58%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-07 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20261008_PRI` | T3 | `2026-10-08` | Significant Index Move: NIFTY 50 Selloff (-1.64%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-08 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20261008_PRI` | T3 | `2026-10-08` | Significant Index Move: NIFTY AUTO Selloff (-2.49%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-08 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20261013_PRI` | T3 | `2026-10-13` | Significant Index Move: NIFTY 50 Surge (+1.60%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-13 > 2025-11-10)` |
| `EV_MKT_NIFTY_50_20261015_PRI` | T3 | `2026-10-15` | Significant Index Move: NIFTY 50 Surge (+1.66%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-15 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20261015_PRI` | T3 | `2026-10-15` | Significant Index Move: NIFTY AUTO Surge (+1.67%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-15 > 2025-11-10)` |
| `EV_MKT_NIFTY_AUTO_20261021_PRI` | T3 | `2026-10-21` | Significant Index Move: NIFTY AUTO Selloff (-1.54%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-21 > 2025-11-10)` |

## E. Ranked Candidate Explanations

| Rank | Evidence ID / Candidate | Category / Role | Score | Confidence | Type | Contradicted? |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **1** | `EV_FS_TMPV_Q2_FY26_CONS_V1` | `INSUFFICIENT_DATA` | `65.0` | **MODERATE_CONFIDENCE** | Company-Specific | No |
| **2** | `EV_FS_TMPV_Q1_FY26_CONS_V2_RECAST` | `INSUFFICIENT_DATA` | `65.0` | **MODERATE_CONFIDENCE** | Company-Specific | No |

#### Primary Explanation Rationale:
Tier 2 base score: 50.0; Same-session announcement: +15.0; Financial statement evaluated with ExpectationSurprise.UNKNOWN; PAT sign does NOT award directional points.; Abnormal return unavailable (insufficient history): +0.0

## F. Contradictory Evidence & Alternative Hypotheses

*No contradictory evidence detected for this session.*

## G. Data Gaps, Methodological Limitations & Governance

### Diagnostic Notes & Data Gaps:
- Analyst consensus expectations unavailable in offline archive; quarterly financial statements evaluated under ExpectationSurprise.UNKNOWN.
- Econometric Market Model status is 'INSUFFICIENT_HISTORY' (0 valid sessions). Abnormal return (AR) and Sector-Adjusted Return (SAR) are unestimated.

### Methodological Limitations:
- Frozen offline research dataset; real-time streaming market data is paused.
- Zero-LLM deterministic attribution; score measures evidence strength, not causal certainty.
- Consensus estimates must be authenticated; unauthenticated surprise remains UNKNOWN.

## H. Final Assessment & Audit Stamp

> **Final Assessment:** **MODERATELY_SUPPORTED_EXPLANATION**  
> **Conclusion:** The observed price action is MODERATELY SUPPORTED by candidate catalyst 'EV_FS_TMPV_Q2_FY26_CONS_V1'. While temporally coincident, unverified expectations or absence of independent corroboration preclude a definitive high-confidence conclusion.  
> **Audit Provenance Hash:** `aa28d1395d599a612391fdfd5108a4f37876fb2f01e2d069429b6e127c7ec8ee`  
> **Dataset / Checkpoint:** `MIL_FROZEN_BENCHMARK_2024_2026_V1`  

> *Note on Provenance Hash:* The SHA-256 audit hash cryptographically protects the canonical structured analytical payload (symbols, timestamps, classifications, price action, and ranked hypothesis scores). It ensures reproducibility and tamper-detection of analytical results across research environments independently of presentation markup or whitespace.

---
*DATA GOVERNANCE NOTICE: Market Intelligence Lab operates on a frozen historical research benchmark (October 2024 – October 2026). Automated web scraping is paused in compliance with exchange terms. Commercial deployment or live simulation requires authorized data licensing or academic agreements.*
