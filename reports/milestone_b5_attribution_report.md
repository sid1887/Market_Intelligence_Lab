# Market Intelligence Lab — Milestone B5 Movement Attribution Report

**Generated:** `2026-11-04 06:33:20 UTC` | **Evaluation Horizon:** Last 30 Trading Sessions  
**Database:** `data/market_lab.db` | **Universe Scope:** 54 Instruments (50 NIFTY + 4 Watchlist)  

---

## 1. Executive Summary

The Generalized Movement Attribution Engine integrates mathematical return decomposition, anomaly detection, and event study correlation across all tracked instruments.

### Empirical Decomposition Identity:
$$\text{Total Return } R_t = \text{Market Component } (\beta_{\text{Nifty}} \times R_{\text{Nifty}}) + \text{Sector Component } (\beta_{\text{Sector}} \times R_{\text{Sector}}) + \text{Idiosyncratic Residual } \epsilon_t$$

| Metric | Count / Value | Proportion | Description |
| :--- | :---: | :---: | :--- |
| **Total Anomalous Sessions** | **200** | 100.0% | Sessions triggered by Volume Z >= 2.5 or Return >= 2.5σ |
| **Corporate Disclosure Correlated** | **64** | 32.0% | Temporally correlated with filings in [-1, +1] window |
| **Sector Systematic Flow** | **12** | 6.0% | Movement dominated by sectoral peer/index momentum |
| **Market Beta Driven** | **6** | 3.0% | Movement dominated by NIFTY 50 index variance |
| **Unexplained Idiosyncratic Flow** | **118** | 59.0% | Idiosyncratic repricing without co-occurring filings |

---

## 2. Top Correlated Corporate Disclosures & Event Study CAR[-1, +1]

Anomalies with verified exchange disclosures occurring within $t \in [-1, +1]$ trading days:

| Symbol | Date | Category | Filing / Disclosure Subject | Total Ret | Market | Sector | Residual | CAR[-1, +1] | Direct Document Link |
| :--- | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **INFY** | `2026-10-23` | `EARNINGS` | Outcome of Board Meeting: Audited Standalone ... | `+0.04%` | `-0.41%` | `-0.27%` | `+0.72%` | *Awaiting Post-Data* | [Official Document PDF](https://www.infosys.com/investors/documents/exchange-filings/2026/outcome-board-meeting23oct2026.pdf) |
| **BAJFINANCE** | `2026-10-21` | `GENERAL_ANNOUNCEMENT` | Allotment of Securities... | `-3.27%` | `-0.52%` | `-1.18%` | `-1.57%` | *Awaiting Post-Data* | [Official Document PDF](https://nsearchives.nseindia.com/corporate/BAJFINANCE_21102026122914_REG30_Allotment_intimation.pdf) |
| **AXISBANK** | `2026-10-19` | `GENERAL_ANNOUNCEMENT` | ESOP/ESOS/ESPS... | `-4.19%` | `-1.27%` | `-0.64%` | `-2.28%` | *Awaiting Post-Data* | [Official Document PDF](https://nsearchives.nseindia.com/corporate/Kapil_21102026191242_SE21102026.pdf) |
| **ICICIBANK** | `2026-10-19` | `EARNINGS` | Analysts/Institutional Investor Meet/Con. Cal... | `-1.15%` | `-0.94%` | `-0.64%` | `+0.43%` | *Awaiting Post-Data* | [Official Document PDF](https://nsearchives.nseindia.com/corporate/ICICI2022_17102026202758_NSEBSE_17102026.pdf) |
| **ULTRACEMCO** | `2026-10-19` | `GENERAL_ANNOUNCEMENT` | Copy of Newspaper Publication... | `-2.36%` | `-1.18%` | `-1.11%` | `-0.07%` | *Awaiting Post-Data* | [Official Document PDF](https://nsearchives.nseindia.com/corporate/ULTRACEMCO1_20102026142616_Newspaper_Publication.pdf) |
| **BHARTIARTL** | `2026-10-16` | `GENERAL_ANNOUNCEMENT` | Action(s) taken or orders passed... | `+2.75%` | `+0.71%` | `+0.65%` | `+1.39%` | *Awaiting Post-Data* | [Official Document PDF](https://nsearchives.nseindia.com/corporate/BHARTIARTL_14102026160249_BhartiAirtelReg30disclosure.pdf) |
| **INFY** | `2026-10-16` | `GENERAL_ANNOUNCEMENT` | Updates... | `+4.61%` | `+0.73%` | `+3.92%` | `-0.04%` | *Awaiting Post-Data* | [Official Document PDF](https://nsearchives.nseindia.com/corporate/Infosys_19102026154028_PR_19102026.pdf) |
| **TCS** | `2026-10-16` | `GENERAL_ANNOUNCEMENT` | Updates... | `+4.89%` | `+0.75%` | `+3.92%` | `+0.22%` | *Awaiting Post-Data* | [Official Document PDF](https://nsearchives.nseindia.com/corporate/TCS_CORPCS_19102026112258_PR_19Oct26_signed.pdf) |
| **TECHM** | `2026-10-16` | `GENERAL_ANNOUNCEMENT` | Copy of Newspaper Publication... | `+8.48%` | `+0.66%` | `+3.92%` | `+3.90%` | *Awaiting Post-Data* | [Official Document PDF](https://nsearchives.nseindia.com/corporate/TECHM_16102026141113_SEintimationnewpaperadvFR_Q2FY27_s.pdf) |
| **ICICIBANK** | `2026-10-15` | `GENERAL_ANNOUNCEMENT` | ESOP/ESOS/ESPS... | `+3.80%` | `+1.42%` | `+0.89%` | `+1.48%` | *Awaiting Post-Data* | [Official Document PDF](https://nsearchives.nseindia.com/corporate/ICICIBANK1_15102026142254_Lettertoexchange.pdf) |
| **NESTLEIND** | `2026-10-15` | `EARNINGS` | Press Release... | `-7.76%` | `+0.56%` | `-1.06%` | `-7.26%` | *Awaiting Post-Data* | [Official Document PDF](https://nsearchives.nseindia.com/corporate/NESTLEIND1_15102026124531_BSENSEOutcomeResults15102026signed.pdf) |
| **SUZLON** | `2026-10-15` | `GENERAL_ANNOUNCEMENT` | Award of 300 MW Wind Energy Project Order fro... | `+0.30%` | `-0.05%` | `+1.66%` | `-1.31%` | *Awaiting Post-Data* | [Official Document PDF](https://nsearchives.nseindia.com/corporate/SUZLON_14102026_Order_Win_300MW.pdf) |
| **TECHM** | `2026-10-15` | `GENERAL_ANNOUNCEMENT` | Copy of Newspaper Publication... | `+4.75%` | `+1.42%` | `+1.82%` | `+1.51%` | *Awaiting Post-Data* | [Official Document PDF](https://nsearchives.nseindia.com/corporate/TECHM_16102026141113_SEintimationnewpaperadvFR_Q2FY27_s.pdf) |
| **AXISBANK** | `2026-10-14` | `GENERAL_ANNOUNCEMENT` | ESOP/ESOS/ESPS... | `-0.30%` | `-0.48%` | `-0.30%` | `+0.47%` | *Awaiting Post-Data* | [Official Document PDF](https://nsearchives.nseindia.com/corporate/AXISBANK1_15102026184025_SEintimation_-_Grant_of_ESOPsSigned.pdf) |
| **INFY** | `2026-10-14` | `BOARD_MEETING_SCHEDULE` | Claimed Intimation of Board Meeting (Unverifi... | `+2.44%` | `-0.47%` | `+1.14%` | `+1.76%` | *Awaiting Post-Data* | [Exchange Filing](https://www.nseindia.com/companies-listing/corporate-filings-announcements) |

---

## 3. Top Anomalous Movements & Conserved Mathematical Decomposition

Sample anomalous sessions sorted by absolute idiosyncratic residual magnitude ($|\epsilon_t|$):

| Symbol | Date | Sector | Triggers | Total Return | Market Comp | Sector Comp | Idiosyncratic Residual | Conservation Check | Attribution Tag |
| :--- | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **TRENT** | `2026-10-06` | Consumer Services | `VOLUME_SPIKE_ZSCORE, RETURN_VOLATILITY_SPIKE` | **`+12.64%`** | `+1.57%` | `+0.98%` | **`+10.10%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **NESTLEIND** | `2026-10-15` | Fast Moving Consumer Goods | `VOLUME_SPIKE_ZSCORE, RETURN_VOLATILITY_SPIKE` | **`-7.76%`** | `+0.56%` | `-1.06%` | **`-7.26%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **MAXHEALTH** | `2026-09-09` | Healthcare | `VOLUME_SPIKE_ZSCORE, RETURN_VOLATILITY_SPIKE` | **`+4.48%`** | `-0.64%` | `-0.70%` | **`+5.83%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **TECHM** | `2026-10-16` | Information Technology | `VOLUME_SPIKE_ZSCORE, RETURN_VOLATILITY_SPIKE` | **`+8.48%`** | `+0.66%` | `+3.92%` | **`+3.90%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **APOLLOHOSP** | `2026-09-30` | Healthcare | `VOLUME_SPIKE_ZSCORE, RETURN_VOLATILITY_SPIKE` | **`-5.70%`** | `-0.14%` | `-1.84%` | **`-3.72%`** | `PASS (0.000)` | `UNEXPLAINED_IDIOSYNCRATIC_FLOW` |
| **SBILIFE** | `2026-09-24` | Financial Services | `VOLUME_SPIKE_ZSCORE` | **`-0.28%`** | `-1.52%` | `-2.39%` | **`+3.63%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **SBILIFE** | `2026-09-17` | Financial Services | `VOLUME_SPIKE_ZSCORE` | **`+4.06%`** | `+0.22%` | `+0.22%` | **`+3.62%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **BSE** | `2026-09-29` | Financial Services | `VOLUME_SPIKE_ZSCORE` | **`+3.31%`** | `-0.08%` | `-0.09%` | **`+3.48%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **APOLLOHOSP** | `2026-10-09` | Healthcare | `VOLUME_SPIKE_ZSCORE` | **`+4.72%`** | `+0.81%` | `+0.54%` | **`+3.37%`** | `PASS (0.000)` | `UNEXPLAINED_IDIOSYNCRATIC_FLOW` |
| **HDFCBANK** | `2026-10-05` | Financial Services | `VOLUME_SPIKE_ZSCORE` | **`-2.27%`** | `+0.52%` | `+0.48%` | **`-3.27%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **TMPV** | `2026-09-17` | Automobile and Auto Components | `RETURN_VOLATILITY_SPIKE` | **`+4.49%`** | `+0.25%` | `+0.99%` | **`+3.25%`** | `PASS (0.000)` | `UNEXPLAINED_IDIOSYNCRATIC_FLOW` |
| **MAXHEALTH** | `2026-09-30` | Healthcare | `VOLUME_SPIKE_ZSCORE, RETURN_VOLATILITY_SPIKE` | **`-5.33%`** | `-0.32%` | `-1.84%` | **`-3.17%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **BAJAJ-AUTO** | `2026-10-01` | Automobile and Auto Components | `VOLUME_SPIKE_ZSCORE, RETURN_VOLATILITY_SPIKE` | **`-7.62%`** | `-1.02%` | `-3.46%` | **`-3.14%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **BEL** | `2026-09-15` | Capital Goods | `RETURN_VOLATILITY_SPIKE` | **`-5.30%`** | `-1.16%` | `-1.19%` | **`-2.94%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **INFY** | `2026-10-13` | Information Technology | `VOLUME_SPIKE_ZSCORE` | **`+4.13%`** | `+1.78%` | `+5.22%` | **`-2.87%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **NESTLEIND** | `2026-10-14` | Fast Moving Consumer Goods | `VOLUME_SPIKE_ZSCORE` | **`+3.69%`** | `-0.37%` | `+1.21%` | **`+2.85%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **TMPV** | `2026-09-25` | Automobile and Auto Components | `VOLUME_SPIKE_ZSCORE` | **`-1.54%`** | `+0.38%` | `+0.89%` | **`-2.81%`** | `PASS (0.000)` | `UNEXPLAINED_IDIOSYNCRATIC_FLOW` |
| **INDIGO** | `2026-10-09` | Services | `VOLUME_SPIKE_ZSCORE` | **`+0.41%`** | `+1.90%` | `+1.30%` | **`-2.79%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **ITC** | `2026-10-05` | Fast Moving Consumer Goods | `VOLUME_SPIKE_ZSCORE, RETURN_VOLATILITY_SPIKE` | **`+5.08%`** | `+0.62%` | `+1.80%` | **`+2.66%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **SBILIFE** | `2026-10-01` | Financial Services | `VOLUME_SPIKE_ZSCORE` | **`+1.49%`** | `-0.73%` | `-0.38%` | **`+2.60%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **BHARTIARTL** | `2026-09-18` | Telecommunication | `VOLUME_SPIKE_ZSCORE` | **`+3.12%`** | `+0.25%` | `+0.33%` | **`+2.54%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **KOTAKBANK** | `2026-09-30` | Financial Services | `VOLUME_SPIKE_ZSCORE` | **`+2.71%`** | `-0.44%` | `+0.69%` | **`+2.46%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **TITAN** | `2026-10-07` | Consumer Durables | `VOLUME_SPIKE_ZSCORE` | **`-3.80%`** | `-0.72%` | `-0.76%` | **`-2.32%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **AXISBANK** | `2026-10-19` | Financial Services | `VOLUME_SPIKE_ZSCORE` | **`-4.19%`** | `-1.27%` | `-0.64%` | **`-2.28%`** | `PASS (0.000)` | `DISCLOSURE_CORRELATED_EVENT` |
| **TATACONSUM** | `2026-09-29` | Fast Moving Consumer Goods | `VOLUME_SPIKE_ZSCORE` | **`+0.80%`** | `-0.27%` | `-1.05%` | **`+2.12%`** | `PASS (0.000)` | `UNEXPLAINED_IDIOSYNCRATIC_FLOW` |

---

## 4. Watchlist Instrument Attribution Audit

Analysis of onboarded user watchlist securities (`SUZLON`, `TRIDENT`, `DRONACHRYA`, `MOREPENLAB`):

| Symbol | Recent Close | 200 SMA | Trend | Anomaly Count | Latest Anomaly Date | Primary Tag | Verified Disclosures Logged |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :---: |
| **SUZLON** | ₹36.85 | ₹34.82 | Bullish Uptrend (Price > 200 SMA) | 30 sessions | `2026-10-23` | `UNEXPLAINED_IDIOSYNCRATIC_FLOW` | 2 verified filings |
| **TRIDENT** | ₹35.80 | ₹36.78 | Below 200 SMA | 30 sessions | `2026-10-23` | `UNEXPLAINED_IDIOSYNCRATIC_FLOW` | 0 verified filings |
| **DRONACHRYA** | ₹156.40 | ₹148.02 | Bullish Uptrend (Price > 200 SMA) | 30 sessions | `2026-10-23` | `UNEXPLAINED_IDIOSYNCRATIC_FLOW` | 0 verified filings |
| **MOREPENLAB** | ₹52.80 | ₹49.38 | Bullish Uptrend (Price > 200 SMA) | 30 sessions | `2026-10-23` | `UNEXPLAINED_IDIOSYNCRATIC_FLOW` | 0 verified filings |

---

## 5. Epistemic Guardrails & Governance Standards

1. **Mathematical Conservation**: The identity $\text{Total Return} = \text{Market} + \text{Sector} + \text{Residual}$ is conserved across 100% of observations without leakage.
2. **Non-Causal Interpretation**: Disclosures co-occurring in the $t \in [-1, +1]$ window establish empirical informational proximity, not deterministic causality.
3. **Offline Integrity**: All calculations are executed strictly against local SQLite historical records with network access disabled.