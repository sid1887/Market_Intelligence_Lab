# Stock Movement Investigation Report: Infosys Ltd. (INFY)

> **Investigation ID:** `EXP_INFY_20261023`  
> **Trading Date:** `2026-10-23` | **Generated At:** `2026-11-01T11:15:30.856751+00:00`  
> **Final Outcome:** **UNEXPLAINED_PRICE_MOVEMENT** (`UNEXPLAINED_MOVEMENT`)  
> **Audit Provenance Hash:** `25da17900452db6209273fcf9f1dd7e5376793afb125e1623ed84dfe89b2eaae`  

## A. Investigation Overview

| Attribute | Value | Attribute | Value |
| :--- | :--- | :--- | :--- |
| **Symbol** | `INFY` | **Company Name** | Infosys Ltd. |
| **ISIN** | `INE009A01021` | **Trading Date** | `2026-10-23` |
| **Sector** | Information Technology | **Industry** | Information Technology |
| **Reporting Basis** | `CONSOLIDATED` | **Standalone Isolated?** | `No` |
| **Primary Classification** | `UNEXPLAINED_MOVEMENT` | **Secondary Tags** | `ANOMALOUS_VOLUME` |
| **Confidence Level** | **UNEXPLAINED_MOVEMENT** | **Dataset Benchmark** | `MIL_FROZEN_BENCHMARK_2024_2026_V1` |

## B. Executive Summary

On 2026-10-23, Infosys Ltd. (INFY) rose 0.04% (Close: ₹1,153.80) with an unadjusted raw return of +0.04%. The movement was classified as 'UNEXPLAINED_MOVEMENT'.

- **Relative Performance:** Against broad-market benchmark NIFTY 50 (-0.39%), the stock exhibited an excess return of +0.43%. Compared to sector benchmark NIFTY IT (-0.27%), the sector-adjusted return (SAR) was +0.31%.
- **Systematic Coupling:** The price action did not exhibit strong systematic coupling; classified as idiosyncratic or routine drift.
- **Strongest Hypothesis:** No verified explanatory catalyst met the minimum confidence threshold.
- **Evidential Sufficiency:** Available local evidence is INSUFFICIENT to establish a causal explanation for this price movement.

> [!NOTE]
> Methodological Note: The evidence strength score (0.0 to 100.0) is a deterministic heuristic measuring evidence quality, temporal proximity, and directional consistency. It is NOT a statistical probability or a calibrated confidence interval.

## C. Quantitative Market Movement Analysis

### 1. Price Action & Return Structure

| Metric | Value | Baseline / Context |
| :--- | :---: | :--- |
| **Close Price** | `₹1,153.80` | Open: `₹1,187.00`, High: `₹1,197.80`, Low: `₹1,038.05` |
| **Raw 1-Day Return** | `+0.04%` | Close-to-close unadjusted change |
| **Adjusted 1-Day Return** | `+0.04%` | Corporate-action adjusted price return |
| **Overnight Gap Open** | `+2.92%` | Previous close to session open |
| **Intraday Drift** | `-2.80%` | Session open to session close |
| **5-Session Return** | `+3.95%` | Preceding 5 trading days momentum |
| **20-Session Return** | `+13.06%` | Preceding 20 trading days momentum |

### 2. Benchmark & Econometric Market Model

| Metric | Value | Econometric Interpretation |
| :--- | :---: | :--- |
| **NIFTY 50 PRI Return** | `-0.39%` | Broad-market baseline return ($R_{m,t}$) |
| **Sector Return** | `-0.27%` | NIFTY IT (OFFICIAL_SECTOR_PRI) |
| **Abnormal Return ($AR_t$)** | `+0.45%` | OLS Market Model excess return ($t = 0.24$) |
| **Sector-Adjusted Return ($SAR_t$)** | `+0.31%` | Net outperformance over sector benchmark |
| **Market Beta ($\beta$) & Alpha ($\alpha$)** | `β=0.68, α=-0.00147` | OLS Market Model coefficients (229 sessions) |

### 3. Volume & Liquidity Anomalies

- **Volume Ratio (vs 20d SMA):** `2.43x`
- **Log Volume Z-Score (vs 50d SMA):** `+2.89`
- **Volume Spike Flag:** `YES (ANOMALOUS ACTIVITY)`

## D. Event and Evidence Timeline

### 1. Eligible Coinciding Evidence (Chronological)

| Date / Session | Evidence ID | Category | Direction | Tier | Headline |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `2026-10-15` | `EV_MKT_NIFTY_50_20261015_PRI` | `SECTOR_MOMENTUM` | `POSITIVE` | T3 | Significant Index Move: NIFTY 50 Surge (+1.66%) [PRI] |
| `2026-10-15` | `EV_MKT_NIFTY_IT_20261015_PRI` | `SECTOR_MOMENTUM` | `POSITIVE` | T3 | Significant Index Move: NIFTY IT Surge (+1.82%) [PRI] |
| `2026-10-16` | `EV_MKT_NIFTY_IT_20261016_PRI` | `SECTOR_MOMENTUM` | `POSITIVE` | T3 | Significant Index Move: NIFTY IT Surge (+3.92%) [PRI] |
| `2026-10-21` | `EV_MKT_NIFTY_IT_20261021_PRI` | `SECTOR_MOMENTUM` | `POSITIVE` | T3 | Significant Index Move: NIFTY IT Surge (+2.88%) [PRI] |
| `2026-10-23` | `EV_VOL_INFY_20261023` | `VOLUME_LIQUIDITY_SURGE` | `NEUTRAL` | T3 | Volume Anomaly: INFY Volume Ratio=2.43x, Log Z=2.89 |

### 2. Excluded Candidate Records & Audit Trail

| Evidence ID | Tier | Effective Session | Headline | Exclusion Reason |
| :--- | :---: | :---: | :--- | :--- |
| `EV_DISC_INFY_DISC_20261015_SCHED` | T5 | `2026-10-16` | Exchange Disclosure: Claimed Intimation of Board Meeting (Unverified Schedule Notice) | `PIT_INELIGIBLE (look-ahead or untimed hazard)` |
| `EV_DISC_INFY_DISC_20261023_Q2` | T1 | `2026-10-26` | Exchange Disclosure: Outcome of Board Meeting: Audited Standalone & Consolidated Financial Results for Q2 FY2027 and Declaration of Interim Dividend | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-26 > 2026-10-23)` |
| `EV_FS_INFY_Q2_FY27_CONS_V1` | T2 | `2026-10-26` | Quarterly Financial Statement (CONSOLIDATED V1): INFY DISCRETE_QUARTER 2026-09-30 | `FUTURE_EVENT_LOOKAHEAD (effective 2026-10-26 > 2026-10-23)` |

## E. Ranked Candidate Explanations

| Rank | Evidence ID / Candidate | Category / Role | Score | Confidence | Type | Contradicted? |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: |
| **1** | `EV_VOL_INFY_20261023` | `ACTIVITY_OBSERVATION` | `49.9` | **LOW_CONFIDENCE** | Company-Specific | No |
| **2** | `EV_MKT_NIFTY_IT_20261021_PRI` | `UNEXPLAINED_MOVEMENT` | `10.0` | **INSUFFICIENT_EVIDENCE** | Systematic | YES (-30) |
| **3** | `EV_MKT_NIFTY_50_20261015_PRI` | `UNEXPLAINED_MOVEMENT` | `0.0` | **INSUFFICIENT_EVIDENCE** | Systematic | YES (-30) |
| **4** | `EV_MKT_NIFTY_IT_20261015_PRI` | `UNEXPLAINED_MOVEMENT` | `0.0` | **INSUFFICIENT_EVIDENCE** | Systematic | YES (-30) |
| **5** | `EV_MKT_NIFTY_IT_20261016_PRI` | `UNEXPLAINED_MOVEMENT` | `0.0` | **INSUFFICIENT_EVIDENCE** | Systematic | YES (-30) |

#### Primary Explanation Rationale:
Tier 3 base score: 35.0; Same-session announcement: +15.0; Neutral corporate action on flat session: +10.0; Volume activity observation guard applied: explanatory score capped at 49.9 (LOW_CONFIDENCE) as volume measures market activity, not causal explanation.

## F. Contradictory Evidence & Alternative Hypotheses

| Conflicting Evidence ID | Direction | Observed Return | Conflict Description | Penalty |
| :--- | :---: | :---: | :--- | :---: |
| `EV_MKT_NIFTY_50_20261015_PRI` | `POSITIVE` | `+0.04%` | Expected directional catalyst POSITIVE failed to move stock (return: 0.04%). | `-30.0 pts` |
| `EV_MKT_NIFTY_IT_20261015_PRI` | `POSITIVE` | `+0.04%` | Expected directional catalyst POSITIVE failed to move stock (return: 0.04%). | `-30.0 pts` |
| `EV_MKT_NIFTY_IT_20261016_PRI` | `POSITIVE` | `+0.04%` | Expected directional catalyst POSITIVE failed to move stock (return: 0.04%). | `-30.0 pts` |
| `EV_MKT_NIFTY_IT_20261021_PRI` | `POSITIVE` | `+0.04%` | Expected directional catalyst POSITIVE failed to move stock (return: 0.04%). | `-30.0 pts` |

## G. Data Gaps, Methodological Limitations & Governance

### Methodological Limitations:
- Frozen offline research dataset; real-time streaming market data is paused.
- Zero-LLM deterministic attribution; score measures evidence strength, not causal certainty.
- Consensus estimates must be authenticated; unauthenticated surprise remains UNKNOWN.

## H. Final Assessment & Audit Stamp

> **Final Assessment:** **UNEXPLAINED_PRICE_MOVEMENT**  
> **Conclusion:** The price action of INFY on 2026-10-23 remains an UNEXPLAINED MOVEMENT. While quantitative market metrics were captured, no verified explanatory event in the local evidence store met the minimum evidential threshold.  
> **Audit Provenance Hash:** `25da17900452db6209273fcf9f1dd7e5376793afb125e1623ed84dfe89b2eaae`  
> **Dataset / Checkpoint:** `MIL_FROZEN_BENCHMARK_2024_2026_V1`  

> *Note on Provenance Hash:* The SHA-256 audit hash cryptographically protects the canonical structured analytical payload (symbols, timestamps, classifications, price action, and ranked hypothesis scores). It ensures reproducibility and tamper-detection of analytical results across research environments independently of presentation markup or whitespace.

---
*DATA GOVERNANCE NOTICE: Market Intelligence Lab operates on a frozen historical research benchmark (October 2024 – October 2026). Automated web scraping is paused in compliance with exchange terms. Commercial deployment or live simulation requires authorized data licensing or academic agreements.*
