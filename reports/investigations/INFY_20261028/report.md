# Stock Movement Investigation Report: Infosys Ltd. (INFY)

> **Investigation ID:** `EXP_INFY_20261028`  
> **Trading Date:** `2026-10-28` | **Generated At:** `2026-11-01T11:15:30.893313+00:00`  
> **Final Outcome:** **MODERATELY_SUPPORTED_EXPLANATION** (`MODERATE_CONFIDENCE`)  
> **Audit Provenance Hash:** `d5785d25369a5feeda3204e10b5639f3225453e2e40b38fd10cb588ab7944b80`  

## A. Investigation Overview

| Attribute | Value | Attribute | Value |
| :--- | :--- | :--- | :--- |
| **Symbol** | `INFY` | **Company Name** | Infosys Ltd. |
| **ISIN** | `INE009A01021` | **Trading Date** | `2026-10-28` |
| **Sector** | Information Technology | **Industry** | Information Technology |
| **Reporting Basis** | `CONSOLIDATED` | **Standalone Isolated?** | `No` |
| **Primary Classification** | `INSUFFICIENT_DATA` | **Secondary Tags** | `None` |
| **Confidence Level** | **MODERATE_CONFIDENCE** | **Dataset Benchmark** | `MIL_FROZEN_BENCHMARK_2024_2026_V1` |

## B. Executive Summary

On 2026-10-28, Infosys Ltd. (INFY) declined 3.43% (Close: ₹1,123.15) with an unadjusted raw return of -3.43%. The movement was classified as 'INSUFFICIENT_DATA'.

- **Relative Performance:** SAR was unavailable.
- **Systematic Coupling:** The price action did not exhibit strong systematic coupling; classified as idiosyncratic or routine drift.
- **Strongest Hypothesis:** The highest-ranked explanatory candidate is 'EV_DISC_INFY_DISC_20261023_Q2' with an evidence strength score of 55.0/100.0 (MODERATE_CONFIDENCE).
- **Evidential Sufficiency:** Available evidence provides sufficient corroboration for the candidate explanation.

> [!NOTE]
> Methodological Note: The evidence strength score (0.0 to 100.0) is a deterministic heuristic measuring evidence quality, temporal proximity, and directional consistency. It is NOT a statistical probability or a calibrated confidence interval.

## C. Quantitative Market Movement Analysis

### 1. Price Action & Return Structure

| Metric | Value | Baseline / Context |
| :--- | :---: | :--- |
| **Close Price** | `₹1,123.15` | Open: `₹1,130.00`, High: `₹1,133.80`, Low: `₹1,103.40` |
| **Raw 1-Day Return** | `-3.43%` | Close-to-close unadjusted change |
| **Adjusted 1-Day Return** | `-3.43%` | Corporate-action adjusted price return |
| **Overnight Gap Open** | `-2.84%` | Previous close to session open |
| **Intraday Drift** | `-0.61%` | Session open to session close |
| **5-Session Return** | `-0.67%` | Preceding 5 trading days momentum |
| **20-Session Return** | `+12.29%` | Preceding 20 trading days momentum |

### 2. Benchmark & Econometric Market Model

| Metric | Value | Econometric Interpretation |
| :--- | :---: | :--- |
| **NIFTY 50 PRI Return** | `N/A` | Broad-market baseline return ($R_{m,t}$) |
| **Sector Return** | `N/A` | NIFTY IT (OFFICIAL_SECTOR_PRI) |
| **Abnormal Return ($AR_t$)** | `Unavailable` | OLS Market Model excess return ($t = N/A$) |
| **Sector-Adjusted Return ($SAR_t$)** | `N/A` | Net outperformance over sector benchmark |
| **Market Beta ($\beta$) & Alpha ($\alpha$)** | `β=0.68, α=-0.00143` | OLS Market Model coefficients (229 sessions) |

### 3. Volume & Liquidity Anomalies

- **Volume Ratio (vs 20d SMA):** `1.00x`
- **Log Volume Z-Score (vs 50d SMA):** `+0.94`
- **Volume Spike Flag:** `No (Normal / Muted Activity)`

## D. Event and Evidence Timeline

### 1. Eligible Coinciding Evidence (Chronological)

| Date / Session | Evidence ID | Category | Direction | Tier | Headline |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `2026-10-21` | `EV_MKT_NIFTY_IT_20261021_PRI` | `SECTOR_MOMENTUM` | `POSITIVE` | T3 | Significant Index Move: NIFTY IT Surge (+2.88%) [PRI] |
| `2026-10-23` | `EV_VOL_INFY_20261023` | `VOLUME_LIQUIDITY_SURGE` | `NEUTRAL` | T3 | Volume Anomaly: INFY Volume Ratio=2.43x, Log Z=2.89 |
| `2026-10-26` | `EV_DISC_INFY_DISC_20261023_Q2` | `EARNINGS_RELEASE` | `NEUTRAL` | T1 | Exchange Disclosure: Outcome of Board Meeting: Audited Standalone & Consolidated Financial Results for Q2 FY2027 and Declaration of Interim Dividend |
| `2026-10-26` | `EV_FS_INFY_Q2_FY27_CONS_V1` | `EARNINGS_RELEASE` | `AMBIGUOUS` | T2 | Quarterly Financial Statement (CONSOLIDATED V1): INFY DISCRETE_QUARTER 2026-09-30 |

### 2. Excluded Candidate Records & Audit Trail

*No candidate records were excluded by filters.*

## E. Ranked Candidate Explanations

| Rank | Evidence ID / Candidate | Category / Role | Score | Confidence | Type | Contradicted? |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **1** | `EV_DISC_INFY_DISC_20261023_Q2` | `INSUFFICIENT_DATA` | `55.0` | **MODERATE_CONFIDENCE** | Company-Specific | No |
| **2** | `EV_FS_INFY_Q2_FY27_CONS_V1` | `INSUFFICIENT_DATA` | `45.0` | **LOW_CONFIDENCE** | Company-Specific | No |
| **3** | `EV_VOL_INFY_20261023` | `ACTIVITY_OBSERVATION` | `25.0` | **INSUFFICIENT_EVIDENCE** | Company-Specific | No |
| **4** | `EV_MKT_NIFTY_IT_20261021_PRI` | `INSUFFICIENT_DATA` | `0.0` | **INSUFFICIENT_EVIDENCE** | Systematic | YES (-30) |

#### Primary Explanation Rationale:
Tier 1 base score: 60.0; Multi-day lag (2 days): +0.0, decay: -5.0; Financial statement evaluated with ExpectationSurprise.UNKNOWN; PAT sign does NOT award directional points.; Abnormal return unavailable (insufficient history): +0.0

## F. Contradictory Evidence & Alternative Hypotheses

| Conflicting Evidence ID | Direction | Observed Return | Conflict Description | Penalty |
| :--- | :---: | :---: | :--- | :---: |
| `EV_MKT_NIFTY_IT_20261021_PRI` | `POSITIVE` | `-3.43%` | Evidence direction POSITIVE conflicts with price move NEGATIVE (ret: -3.43%). | `-30.0 pts` |

## G. Data Gaps, Methodological Limitations & Governance

### Diagnostic Notes & Data Gaps:
- Analyst consensus expectations unavailable in offline archive; quarterly financial statements evaluated under ExpectationSurprise.UNKNOWN.
- Econometric Market Model status is 'BENCHMARK_UNAVAILABLE' (229 valid sessions). Abnormal return (AR) and Sector-Adjusted Return (SAR) are unestimated.

### Methodological Limitations:
- Frozen offline research dataset; real-time streaming market data is paused.
- Zero-LLM deterministic attribution; score measures evidence strength, not causal certainty.
- Consensus estimates must be authenticated; unauthenticated surprise remains UNKNOWN.

## H. Final Assessment & Audit Stamp

> **Final Assessment:** **MODERATELY_SUPPORTED_EXPLANATION**  
> **Conclusion:** The observed price action is MODERATELY SUPPORTED by candidate catalyst 'EV_DISC_INFY_DISC_20261023_Q2'. While temporally coincident, unverified expectations or absence of independent corroboration preclude a definitive high-confidence conclusion.  
> **Audit Provenance Hash:** `d5785d25369a5feeda3204e10b5639f3225453e2e40b38fd10cb588ab7944b80`  
> **Dataset / Checkpoint:** `MIL_FROZEN_BENCHMARK_2024_2026_V1`  

> *Note on Provenance Hash:* The SHA-256 audit hash cryptographically protects the canonical structured analytical payload (symbols, timestamps, classifications, price action, and ranked hypothesis scores). It ensures reproducibility and tamper-detection of analytical results across research environments independently of presentation markup or whitespace.

---
*DATA GOVERNANCE NOTICE: Market Intelligence Lab operates on a frozen historical research benchmark (October 2024 – October 2026). Automated web scraping is paused in compliance with exchange terms. Commercial deployment or live simulation requires authorized data licensing or academic agreements.*
