# Stock Movement Investigation Report: State Bank of India (SBIN)

> **Investigation ID:** `EXP_SBIN_20250808`  
> **Trading Date:** `2025-08-08` | **Generated At:** `2026-11-01T11:15:30.930309+00:00`  
> **Final Outcome:** **MODERATELY_SUPPORTED_EXPLANATION** (`MODERATE_CONFIDENCE`)  
> **Audit Provenance Hash:** `0c02098408419a5addd1f4cae2438c53ffa259c7dbc550da673ed6c64f4abb19`  

## A. Investigation Overview

| Attribute | Value | Attribute | Value |
| :--- | :--- | :--- | :--- |
| **Symbol** | `SBIN` | **Company Name** | State Bank of India |
| **ISIN** | `INE062A01020` | **Trading Date** | `2025-08-08` |
| **Sector** | Financial Services | **Industry** | Financial Services |
| **Reporting Basis** | `STANDALONE` | **Standalone Isolated?** | `YES` |
| **Primary Classification** | `MARKET_BETA_DRIVEN` | **Secondary Tags** | `MUTED_CONSOLIDATION` |
| **Confidence Level** | **MODERATE_CONFIDENCE** | **Dataset Benchmark** | `MIL_FROZEN_BENCHMARK_2024_2026_V1` |

## B. Executive Summary

On 2025-08-08, State Bank of India (SBIN) declined 0.11% (Close: ₹804.30) with an unadjusted raw return of -0.11%. The movement was classified as 'MARKET_BETA_DRIVEN'.

- **Relative Performance:** Against broad-market benchmark NIFTY 50 (-0.95%), the stock exhibited an excess return of +0.84%. Compared to sector benchmark NIFTY BANK (-0.93%), the sector-adjusted return (SAR) was +0.82%.
- **Systematic Coupling:** The price action was broad-market beta driven, closely tracking the NIFTY 50 PRI index.
- **Strongest Hypothesis:** The highest-ranked explanatory candidate is 'EV_FS_SBIN_Q1_FY26_STAND_V1' with an evidence strength score of 65.0/100.0 (MODERATE_CONFIDENCE).
- **Evidential Sufficiency:** Available evidence provides sufficient corroboration for the candidate explanation.

> [!NOTE]
> Methodological Note: The evidence strength score (0.0 to 100.0) is a deterministic heuristic measuring evidence quality, temporal proximity, and directional consistency. It is NOT a statistical probability or a calibrated confidence interval.

## C. Quantitative Market Movement Analysis

### 1. Price Action & Return Structure

| Metric | Value | Baseline / Context |
| :--- | :---: | :--- |
| **Close Price** | `₹804.30` | Open: `₹805.00`, High: `₹807.80`, Low: `₹790.00` |
| **Raw 1-Day Return** | `-0.11%` | Close-to-close unadjusted change |
| **Adjusted 1-Day Return** | `-0.11%` | Corporate-action adjusted price return |
| **Overnight Gap Open** | `-0.02%` | Previous close to session open |
| **Intraday Drift** | `-0.09%` | Session open to session close |
| **5-Session Return** | `+1.30%` | Preceding 5 trading days momentum |
| **20-Session Return** | `-0.54%` | Preceding 20 trading days momentum |

### 2. Benchmark & Econometric Market Model

| Metric | Value | Econometric Interpretation |
| :--- | :---: | :--- |
| **NIFTY 50 PRI Return** | `-0.95%` | Broad-market baseline return ($R_{m,t}$) |
| **Sector Return** | `-0.93%` | NIFTY BANK (OFFICIAL_SECTOR_PRI) |
| **Abnormal Return ($AR_t$)** | `+0.88%` | OLS Market Model excess return ($t = 0.79$) |
| **Sector-Adjusted Return ($SAR_t$)** | `+0.82%` | Net outperformance over sector benchmark |
| **Market Beta ($\beta$) & Alpha ($\alpha$)** | `β=1.03, α=-0.00011` | OLS Market Model coefficients (179 sessions) |

### 3. Volume & Liquidity Anomalies

- **Volume Ratio (vs 20d SMA):** `1.51x`
- **Log Volume Z-Score (vs 50d SMA):** `+0.99`
- **Volume Spike Flag:** `No (Normal / Muted Activity)`

## D. Event and Evidence Timeline

### 1. Eligible Coinciding Evidence (Chronological)

| Date / Session | Evidence ID | Category | Direction | Tier | Headline |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `2025-08-08` | `EV_FS_SBIN_Q1_FY26_STAND_V1` | `EARNINGS_RELEASE` | `AMBIGUOUS` | T2 | Quarterly Financial Statement (STANDALONE V1): SBIN DISCRETE_QUARTER 2025-06-30 |

### 2. Excluded Candidate Records & Audit Trail

| Evidence ID | Tier | Effective Session | Headline | Exclusion Reason |
| :--- | :---: | :---: | :--- | :--- |
| `EV_FS_SBIN_Q2_FY26_STAND_V1` | T2 | `2025-11-07` | Quarterly Financial Statement (STANDALONE V1): SBIN DISCRETE_QUARTER 2025-09-30 | `FUTURE_EVENT_LOOKAHEAD (effective 2025-11-07 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260201_PRI` | T3 | `2026-02-01` | Significant Index Move: NIFTY 50 Selloff (-1.96%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-01 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260201_PRI` | T3 | `2026-02-01` | Significant Index Move: NIFTY BANK Selloff (-2.00%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-01 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260203_PRI` | T3 | `2026-02-03` | Significant Index Move: NIFTY 50 Surge (+2.55%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-03 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260203_PRI` | T3 | `2026-02-03` | Significant Index Move: NIFTY BANK Surge (+2.43%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-03 > 2025-08-08)` |
| `EV_FS_SBIN_Q3_FY26_STAND_V1` | T2 | `2026-02-06` | Quarterly Financial Statement (STANDALONE V1): SBIN DISCRETE_QUARTER 2025-12-31 | `FUTURE_EVENT_LOOKAHEAD (effective 2026-02-06 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260304_PRI` | T3 | `2026-03-04` | Significant Index Move: NIFTY 50 Selloff (-1.55%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-04 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260304_PRI` | T3 | `2026-03-04` | Significant Index Move: NIFTY BANK Selloff (-1.81%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-04 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260306_PRI` | T3 | `2026-03-06` | Significant Index Move: NIFTY BANK Selloff (-2.15%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-06 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260309_PRI` | T3 | `2026-03-09` | Significant Index Move: NIFTY 50 Selloff (-1.73%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-09 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260309_PRI` | T3 | `2026-03-09` | Significant Index Move: NIFTY BANK Selloff (-3.05%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-09 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260310_PRI` | T3 | `2026-03-10` | Significant Index Move: NIFTY BANK Surge (+1.66%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-10 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260311_PRI` | T3 | `2026-03-11` | Significant Index Move: NIFTY 50 Selloff (-1.63%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-11 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260311_PRI` | T3 | `2026-03-11` | Significant Index Move: NIFTY BANK Selloff (-2.13%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-11 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260313_PRI` | T3 | `2026-03-13` | Significant Index Move: NIFTY 50 Selloff (-2.06%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-13 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260313_PRI` | T3 | `2026-03-13` | Significant Index Move: NIFTY BANK Selloff (-2.44%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-13 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260319_PRI` | T3 | `2026-03-19` | Significant Index Move: NIFTY 50 Selloff (-3.26%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-19 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260319_PRI` | T3 | `2026-03-19` | Significant Index Move: NIFTY BANK Selloff (-3.39%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-19 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260323_PRI` | T3 | `2026-03-23` | Significant Index Move: NIFTY 50 Selloff (-2.60%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-23 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260323_PRI` | T3 | `2026-03-23` | Significant Index Move: NIFTY BANK Selloff (-3.72%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-23 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260324_PRI` | T3 | `2026-03-24` | Significant Index Move: NIFTY 50 Surge (+1.78%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-24 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260324_PRI` | T3 | `2026-03-24` | Significant Index Move: NIFTY BANK Surge (+2.27%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-24 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260325_PRI` | T3 | `2026-03-25` | Significant Index Move: NIFTY 50 Surge (+1.72%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-25 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260325_PRI` | T3 | `2026-03-25` | Significant Index Move: NIFTY BANK Surge (+2.10%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-25 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260327_PRI` | T3 | `2026-03-27` | Significant Index Move: NIFTY 50 Selloff (-2.09%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-27 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260327_PRI` | T3 | `2026-03-27` | Significant Index Move: NIFTY BANK Selloff (-2.67%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-27 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260330_PRI` | T3 | `2026-03-30` | Significant Index Move: NIFTY 50 Selloff (-2.14%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-30 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260330_PRI` | T3 | `2026-03-30` | Significant Index Move: NIFTY BANK Selloff (-3.82%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-03-30 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260401_PRI` | T3 | `2026-04-01` | Significant Index Move: NIFTY 50 Surge (+1.56%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-01 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260401_PRI` | T3 | `2026-04-01` | Significant Index Move: NIFTY BANK Surge (+2.33%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-01 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260406_PRI` | T3 | `2026-04-06` | Significant Index Move: NIFTY BANK Surge (+2.06%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-06 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260408_PRI` | T3 | `2026-04-08` | Significant Index Move: NIFTY 50 Surge (+3.78%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-08 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260408_PRI` | T3 | `2026-04-08` | Significant Index Move: NIFTY BANK Surge (+5.67%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-08 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260409_PRI` | T3 | `2026-04-09` | Significant Index Move: NIFTY BANK Selloff (-1.58%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-09 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260410_PRI` | T3 | `2026-04-10` | Significant Index Move: NIFTY BANK Surge (+1.99%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-10 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260415_PRI` | T3 | `2026-04-15` | Significant Index Move: NIFTY 50 Surge (+1.63%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-15 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260428_PRI` | T3 | `2026-04-28` | Significant Index Move: NIFTY BANK Selloff (-1.54%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-04-28 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260506_PRI` | T3 | `2026-05-06` | Significant Index Move: NIFTY BANK Surge (+2.63%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-06 > 2025-08-08)` |
| `EV_FS_SBIN_Q4_FY26_STAND_V1` | T2 | `2026-05-08` | Quarterly Financial Statement (STANDALONE V1): SBIN DISCRETE_QUARTER 2026-03-31 | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-08 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260511_PRI` | T3 | `2026-05-11` | Significant Index Move: NIFTY BANK Selloff (-1.57%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-11 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260512_PRI` | T3 | `2026-05-12` | Significant Index Move: NIFTY 50 Selloff (-1.83%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-12 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260512_PRI` | T3 | `2026-05-12` | Significant Index Move: NIFTY BANK Selloff (-1.63%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-12 > 2025-08-08)` |
| `EV_CA_SBIN_DIVIDEND_20260515_DIVIDEND_RS_17_35_PER_SHARE` | T2 | `2026-05-15` | Corporate Action Ex-Date: SBIN Dividend - Rs 17.35 Per Share (Factor: 1.0) | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-15 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260525_PRI` | T3 | `2026-05-25` | Significant Index Move: NIFTY BANK Surge (+2.29%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-25 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260529_PRI` | T3 | `2026-05-29` | Significant Index Move: NIFTY 50 Selloff (-1.50%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-05-29 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260609_PRI` | T3 | `2026-06-09` | Significant Index Move: NIFTY BANK Surge (+2.09%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-06-09 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260612_PRI` | T3 | `2026-06-12` | Significant Index Move: NIFTY 50 Surge (+1.99%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-06-12 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260612_PRI` | T3 | `2026-06-12` | Significant Index Move: NIFTY BANK Surge (+2.97%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-06-12 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260624_PRI` | T3 | `2026-06-24` | Significant Index Move: NIFTY BANK Surge (+1.69%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-06-24 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260708_PRI` | T3 | `2026-07-08` | Significant Index Move: NIFTY 50 Selloff (-2.12%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-07-08 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260708_PRI` | T3 | `2026-07-08` | Significant Index Move: NIFTY BANK Selloff (-2.51%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-07-08 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260717_PRI` | T3 | `2026-07-17` | Significant Index Move: NIFTY BANK Surge (+1.63%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-07-17 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260803_PRI` | T3 | `2026-08-03` | Significant Index Move: NIFTY 50 Surge (+1.60%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-08-03 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260803_PRI` | T3 | `2026-08-03` | Significant Index Move: NIFTY BANK Surge (+1.72%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-08-03 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260924_PRI` | T3 | `2026-09-24` | Significant Index Move: NIFTY 50 Selloff (-1.64%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-09-24 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260924_PRI` | T3 | `2026-09-24` | Significant Index Move: NIFTY BANK Selloff (-1.96%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-09-24 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20260928_PRI` | T3 | `2026-09-28` | Significant Index Move: NIFTY 50 Selloff (-1.56%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-09-28 > 2025-08-08)` |
| `EV_MKT_NIFTY_BANK_20260928_PRI` | T3 | `2026-09-28` | Significant Index Move: NIFTY BANK Selloff (-1.99%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-09-28 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20261008_PRI` | T3 | `2026-10-08` | Significant Index Move: NIFTY 50 Selloff (-1.64%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-08 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20261013_PRI` | T3 | `2026-10-13` | Significant Index Move: NIFTY 50 Surge (+1.60%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-13 > 2025-08-08)` |
| `EV_MKT_NIFTY_50_20261015_PRI` | T3 | `2026-10-15` | Significant Index Move: NIFTY 50 Surge (+1.66%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-15 > 2025-08-08)` |

## E. Ranked Candidate Explanations

| Rank | Evidence ID / Candidate | Category / Role | Score | Confidence | Type | Contradicted? |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **1** | `EV_FS_SBIN_Q1_FY26_STAND_V1` | `MARKET_BETA_DRIVEN` | `65.0` | **MODERATE_CONFIDENCE** | Company-Specific | No |

#### Primary Explanation Rationale:
Tier 2 base score: 50.0; Same-session announcement: +15.0; Financial statement evaluated with ExpectationSurprise.UNKNOWN; PAT sign does NOT award directional points.

## F. Contradictory Evidence & Alternative Hypotheses

*No contradictory evidence detected for this session.*

## G. Data Gaps, Methodological Limitations & Governance

### Diagnostic Notes & Data Gaps:
- Analyst consensus expectations unavailable in offline archive; quarterly financial statements evaluated under ExpectationSurprise.UNKNOWN.
- REPORTING_BASIS_ISOLATION: SBIN operates on a STANDALONE reporting basis; peer valuation multiples and consolidated disclosures are isolated.

### Methodological Limitations:
- Frozen offline research dataset; real-time streaming market data is paused.
- Zero-LLM deterministic attribution; score measures evidence strength, not causal certainty.
- Consensus estimates must be authenticated; unauthenticated surprise remains UNKNOWN.

## H. Final Assessment & Audit Stamp

> **Final Assessment:** **MODERATELY_SUPPORTED_EXPLANATION**  
> **Conclusion:** The observed price action is MODERATELY SUPPORTED by candidate catalyst 'EV_FS_SBIN_Q1_FY26_STAND_V1'. While temporally coincident, unverified expectations or absence of independent corroboration preclude a definitive high-confidence conclusion.  
> **Audit Provenance Hash:** `0c02098408419a5addd1f4cae2438c53ffa259c7dbc550da673ed6c64f4abb19`  
> **Dataset / Checkpoint:** `MIL_FROZEN_BENCHMARK_2024_2026_V1`  

> *Note on Provenance Hash:* The SHA-256 audit hash cryptographically protects the canonical structured analytical payload (symbols, timestamps, classifications, price action, and ranked hypothesis scores). It ensures reproducibility and tamper-detection of analytical results across research environments independently of presentation markup or whitespace.

---
*DATA GOVERNANCE NOTICE: Market Intelligence Lab operates on a frozen historical research benchmark (October 2024 – October 2026). Automated web scraping is paused in compliance with exchange terms. Commercial deployment or live simulation requires authorized data licensing or academic agreements.*
