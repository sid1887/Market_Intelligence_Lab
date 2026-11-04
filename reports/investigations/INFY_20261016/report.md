# Stock Movement Investigation Report: Infosys Ltd. (INFY)

> **Investigation ID:** `EXP_INFY_20261016`  
> **Trading Date:** `2026-10-16` | **Generated At:** `2026-11-01T11:15:30.837410+00:00`  
> **Final Outcome:** **STRONGLY_SUPPORTED_EXPLANATION** (`HIGH_CONFIDENCE`)  
> **Audit Provenance Hash:** `f284cf4ea14488b4268425a0d00c5591ebea0d7f6f03760fcc3e2bfb5ccfa76d`  

## A. Investigation Overview

| Attribute | Value | Attribute | Value |
| :--- | :--- | :--- | :--- |
| **Symbol** | `INFY` | **Company Name** | Infosys Ltd. |
| **ISIN** | `INE009A01021` | **Trading Date** | `2026-10-16` |
| **Sector** | Information Technology | **Industry** | Information Technology |
| **Reporting Basis** | `CONSOLIDATED` | **Standalone Isolated?** | `No` |
| **Primary Classification** | `SECTOR_SYSTEMATIC_SURGE` | **Secondary Tags** | `ANOMALOUS_VOLUME` |
| **Confidence Level** | **HIGH_CONFIDENCE** | **Dataset Benchmark** | `MIL_FROZEN_BENCHMARK_2024_2026_V1` |

## B. Executive Summary

On 2026-10-16, Infosys Ltd. (INFY) rose 4.61% (Close: ₹1,161.20) with an unadjusted raw return of +4.61%. The movement was classified as 'SECTOR_SYSTEMATIC_SURGE'.

- **Relative Performance:** Against broad-market benchmark NIFTY 50 (+0.65%), the stock exhibited an excess return of +3.97%. Compared to sector benchmark NIFTY IT (+3.92%), the sector-adjusted return (SAR) was +0.69%.
- **Systematic Coupling:** The price action was predominantly systematic, aligning with broader sectoral momentum in NIFTY IT.
- **Strongest Hypothesis:** The highest-ranked explanatory candidate is 'EV_MKT_NIFTY_IT_20261016_PRI' with an evidence strength score of 90.0/100.0 (HIGH_CONFIDENCE).
- **Evidential Sufficiency:** Available evidence provides sufficient corroboration for the candidate explanation.

> [!NOTE]
> Methodological Note: The evidence strength score (0.0 to 100.0) is a deterministic heuristic measuring evidence quality, temporal proximity, and directional consistency. It is NOT a statistical probability or a calibrated confidence interval.

## C. Quantitative Market Movement Analysis

### 1. Price Action & Return Structure

| Metric | Value | Baseline / Context |
| :--- | :---: | :--- |
| **Close Price** | `₹1,161.20` | Open: `₹1,127.50`, High: `₹1,167.85`, Low: `₹1,122.00` |
| **Raw 1-Day Return** | `+4.61%` | Close-to-close unadjusted change |
| **Adjusted 1-Day Return** | `+4.61%` | Corporate-action adjusted price return |
| **Overnight Gap Open** | `+1.58%` | Previous close to session open |
| **Intraday Drift** | `+2.99%` | Session open to session close |
| **5-Session Return** | `+13.46%` | Preceding 5 trading days momentum |
| **20-Session Return** | `+9.69%` | Preceding 20 trading days momentum |

### 2. Benchmark & Econometric Market Model

| Metric | Value | Econometric Interpretation |
| :--- | :---: | :--- |
| **NIFTY 50 PRI Return** | `+0.65%` | Broad-market baseline return ($R_{m,t}$) |
| **Sector Return** | `+3.92%` | NIFTY IT (OFFICIAL_SECTOR_PRI) |
| **Abnormal Return ($AR_t$)** | `+4.29%` | OLS Market Model excess return ($t = 2.30$) |
| **Sector-Adjusted Return ($SAR_t$)** | `+0.69%` | Net outperformance over sector benchmark |
| **Market Beta ($\beta$) & Alpha ($\alpha$)** | `β=0.69, α=-0.00123` | OLS Market Model coefficients (229 sessions) |

### 3. Volume & Liquidity Anomalies

- **Volume Ratio (vs 20d SMA):** `2.12x`
- **Log Volume Z-Score (vs 50d SMA):** `+2.73`
- **Volume Spike Flag:** `YES (ANOMALOUS ACTIVITY)`

## D. Event and Evidence Timeline

### 1. Eligible Coinciding Evidence (Chronological)

| Date / Session | Evidence ID | Category | Direction | Tier | Headline |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `2026-10-09` | `EV_MKT_NIFTY_IT_20261009_PRI` | `SECTOR_MOMENTUM` | `POSITIVE` | T3 | Significant Index Move: NIFTY IT Surge (+3.02%) [PRI] |
| `2026-10-13` | `EV_MKT_NIFTY_50_20261013_PRI` | `SECTOR_MOMENTUM` | `POSITIVE` | T3 | Significant Index Move: NIFTY 50 Surge (+1.60%) [PRI] |
| `2026-10-13` | `EV_MKT_NIFTY_IT_20261013_PRI` | `SECTOR_MOMENTUM` | `POSITIVE` | T3 | Significant Index Move: NIFTY IT Surge (+5.22%) [PRI] |
| `2026-10-15` | `EV_MKT_NIFTY_50_20261015_PRI` | `SECTOR_MOMENTUM` | `POSITIVE` | T3 | Significant Index Move: NIFTY 50 Surge (+1.66%) [PRI] |
| `2026-10-15` | `EV_MKT_NIFTY_IT_20261015_PRI` | `SECTOR_MOMENTUM` | `POSITIVE` | T3 | Significant Index Move: NIFTY IT Surge (+1.82%) [PRI] |
| `2026-10-16` | `EV_MKT_NIFTY_IT_20261016_PRI` | `SECTOR_MOMENTUM` | `POSITIVE` | T3 | Significant Index Move: NIFTY IT Surge (+3.92%) [PRI] |

### 2. Excluded Candidate Records & Audit Trail

| Evidence ID | Tier | Effective Session | Headline | Exclusion Reason |
| :--- | :---: | :---: | :--- | :--- |
| `EV_DISC_INFY_DISC_20261015_SCHED` | T5 | `2026-10-16` | Exchange Disclosure: Claimed Intimation of Board Meeting (Unverified Schedule Notice) | `PIT_INELIGIBLE (look-ahead or untimed hazard)` |
| `EV_MKT_NIFTY_IT_20261021_PRI` | T3 | `2026-10-21` | Significant Index Move: NIFTY IT Surge (+2.88%) [PRI] | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-21 > 2026-10-16)` |
| `EV_VOL_INFY_20261023` | T3 | `2026-10-23` | Volume Anomaly: INFY Volume Ratio=2.43x, Log Z=2.89 | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-23 > 2026-10-16)` |
| `EV_DISC_INFY_DISC_20261023_Q2` | T1 | `2026-10-26` | Exchange Disclosure: Outcome of Board Meeting: Audited Standalone & Consolidated Financial Results for Q2 FY2027 and Declaration of Interim Dividend | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-26 > 2026-10-16)` |
| `EV_FS_INFY_Q2_FY27_CONS_V1` | T2 | `2026-10-26` | Quarterly Financial Statement (CONSOLIDATED V1): INFY DISCRETE_QUARTER 2026-09-30 | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-26 > 2026-10-16)` |

## E. Ranked Candidate Explanations

| Rank | Evidence ID / Candidate | Category / Role | Score | Confidence | Type | Contradicted? |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **1** | `EV_MKT_NIFTY_IT_20261016_PRI` | `SECTOR_SYSTEMATIC_SURGE` | `90.0` | **HIGH_CONFIDENCE** | Systematic | No |
| **2** | `EV_MKT_NIFTY_50_20261015_PRI` | `SECTOR_SYSTEMATIC_SURGE` | `80.0` | **HIGH_CONFIDENCE** | Systematic | No |
| **3** | `EV_MKT_NIFTY_IT_20261015_PRI` | `SECTOR_SYSTEMATIC_SURGE` | `80.0` | **HIGH_CONFIDENCE** | Systematic | No |
| **4** | `EV_MKT_NIFTY_50_20261013_PRI` | `SECTOR_SYSTEMATIC_SURGE` | `65.0` | **MODERATE_CONFIDENCE** | Systematic | No |
| **5** | `EV_MKT_NIFTY_IT_20261013_PRI` | `SECTOR_SYSTEMATIC_SURGE` | `65.0` | **MODERATE_CONFIDENCE** | Systematic | No |
| **6** | `EV_MKT_NIFTY_IT_20261009_PRI` | `SECTOR_SYSTEMATIC_SURGE` | `55.0` | **MODERATE_CONFIDENCE** | Systematic | No |

#### Primary Explanation Rationale:
Tier 3 base score: 35.0; Same-session announcement: +15.0; Evidence direction POSITIVE aligned with market move: +15.0; Large positive abnormal return (AR: 4.29%): +15.0; High volume surge (VR: 2.12x): +10.0

## F. Contradictory Evidence & Alternative Hypotheses

*No contradictory evidence detected for this session.*

## G. Data Gaps, Methodological Limitations & Governance

### Methodological Limitations:
- Frozen offline research dataset; real-time streaming market data is paused.
- Zero-LLM deterministic attribution; score measures evidence strength, not causal certainty.
- Consensus estimates must be authenticated; unauthenticated surprise remains UNKNOWN.

## H. Final Assessment & Audit Stamp

> **Final Assessment:** **STRONGLY_SUPPORTED_EXPLANATION**  
> **Conclusion:** The observed price action is STRONGLY SUPPORTED by candidate catalyst 'EV_MKT_NIFTY_IT_20261016_PRI'. The evidence exhibits consistent directional alignment, temporal proximity, and quantitative compatibility with observed market returns.  
> **Audit Provenance Hash:** `f284cf4ea14488b4268425a0d00c5591ebea0d7f6f03760fcc3e2bfb5ccfa76d`  
> **Dataset / Checkpoint:** `MIL_FROZEN_BENCHMARK_2024_2026_V1`  

> *Note on Provenance Hash:* The SHA-256 audit hash cryptographically protects the canonical structured analytical payload (symbols, timestamps, classifications, price action, and ranked hypothesis scores). It ensures reproducibility and tamper-detection of analytical results across research environments independently of presentation markup or whitespace.

---
*DATA GOVERNANCE NOTICE: Market Intelligence Lab operates on a frozen historical research benchmark (October 2024 – October 2026). Automated web scraping is paused in compliance with exchange terms. Commercial deployment or live simulation requires authorized data licensing or academic agreements.*
