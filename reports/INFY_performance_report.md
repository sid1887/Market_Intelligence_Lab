# Market Intelligence Lab: Equity Research Memo
## Symbol: INFY (NSE) | Milestone 1 Historical Performance Audit

**Report Date**: 2026-10-25 12:22:23 UTC  
**Observation Window**: `2025-10-27` to `2026-10-23` (245 trading sessions | 361 calendar days)  
**Security Series**: `EQ` (Mainboard Regular Equity)

---

## 1. Executive Performance & Annualization Summary

### Scenario A: Observed Series Window (Post-Ex Close Purchase)
*Purchased at the closing price of `2025-10-27` (₹1504.50), which is the ex-date for the ₹23.00 interim dividend.*

| Metric | Empirical Value | Formula / Convention |
| :--- | :--- | :--- |
| **Initial Price** (`2025-10-27`) | **₹1504.50** | Closing price of initial session |
| **Terminal Price** (`2026-10-23`) | **₹1153.80** | Closing price of latest session |
| **Price-Only Total Return** | **-23.31%** | $R_{price} = \frac{P_{end} - P_{start}}{P_{start}}$ |
| **Calendar-Time CAGR** | **-23.55%** | $\text{CAGR}_{calendar} = \left(\frac{P_{end}}{P_{start}}\right)^{\frac{365.25}{\Delta \text{days}}} - 1$ (over 361 calendar days) |
| **Trading-Day Annualized Return** | **-23.97%** | $\text{Ann}_{trading} = \left(\frac{P_{end}}{P_{start}}\right)^{\frac{252}{N - 1}} - 1$ (over 244 return periods) |
| **Eligible Cash Dividends** | **₹25.00 / share** | Subsequent cash dividends received (June 10, 2026) |
| **Cash-Inclusive Total Return** | **-21.65%** | $R_{cash-inc} = \frac{P_{end} + D_{eligible} - P_{start}}{P_{start}}$ (non-reinvested) |
| **Dividend Yield Contribution** | **+1.66%** | $\frac{D_{eligible}}{P_{start}}$ |
| **Price-Only Daily Volatility** | **1.98%** | $\sigma_{daily} = \sqrt{\frac{1}{N-1} \sum (r_t - \bar{r})^2}$ (nominal close prices) |
| **Price-Only Annualized Volatility** | **31.49%** | $\sigma_{price} = \sigma_{daily} \times \sqrt{252}$ |
| **Price-Only Maximum Drawdown (MDD)**| **-41.69%** | $\text{MDD}_{price} = \frac{985.30 - 1689.80}{1689.80}$ |
| **MDD Peak Date & Closing Price** | `2026-01-16` at **₹1689.80** | Exact running peak close |
| **MDD Trough Date & Closing Price** | `2026-07-01` at **₹985.30** | Exact subsequent trough close |
| **Intraday 52-Week High (Date)** | **₹1728.00** (`2026-02-03`) | Highest intra-day trade (Close: ₹1623.50) |
| **Intraday 52-Week Low (Date)** | **₹980.40** (`2026-09-29`) | Lowest intra-day trade (Close: ₹1008.50) |
| **Position in 52-Week Range** | **23.2%** | $\frac{P_{curr} - L_{52}}{H_{52} - L_{52}} \times 100\%$ |
| **Distance from 52-Week High** | **-33.23%** | Relative to 52w intraday peak |
| **Distance from 52-Week Low** | **+17.69%** | Relative to 52w intraday bottom |
| **Average Daily Volume (ADV)** | **12,051,407 shares** | Traded share count mean |
| **Average Daily Turnover (ADT)** | **₹1,512.94 Crore** | Total traded turnover mean |

### Drawdown Reconciliation & Intraday Extremes Distinction
* **Maximum Drawdown Calculation (Closing Prices)**:
  - Running Peak Close: **₹1689.80** on `2026-01-16`
  - Subsequent Trough Close: **₹985.30** on `2026-07-01`
  - Exact unrounded MDD: $\frac{985.30 - 1689.80}{1689.80} = \frac{-704.50}{1689.80} = -0.4169132... \rightarrow \mathbf{-41.69\%}$.
* **Distinction from Intraday 52-Week Extremes**:
  - The **Intraday 52-Week Low** of **₹980.40** occurred on **2026-09-29** (where the close was ₹1,008.50).
  - The **Intraday 52-Week High** of **₹1728.00** occurred on **2026-02-03** (where the close was ₹1,623.50).
  - Maximum drawdown is computed strictly from the ordered series of daily **closing prices** and must not combine intraday extreme prices across different dates.

---

### Scenario B: Pre-Ex Cum-Dividend Holding Period Comparison
* **Holding Dates**: `2025-10-24` (Friday pre-ex close) to `2026-10-23` (Friday close)
* **Pre-Ex Starting Price**: **₹1525.40**
* **Terminal Price**: **₹1153.80**
* **Total Cash Dividends Received**: **₹48.00 / share** (₹23.00 on Oct 27, 2025 + ₹25.00 on Jun 10, 2026)
* **Unadjusted Price Return**: **-24.36%**  
  $$R_{price} = \frac{1153.80 - 1525.40}{1525.40} = -24.36\%$$
* **Cash-Inclusive Total Return (Non-Reinvested)**: **-21.21%**  
  $$R_{cash-inc} = \frac{1153.80 + 48.00 - 1525.40}{1525.40} = -21.21\%$$
* **Dividend Yield Contribution**: **+3.15%**
* **Assumptions**: Investor purchased on or before the cum-dividend close of `2025-10-24`, qualified for both dividend disbursements, and held without reinvestment. Taxes and broker fees excluded.


---

## 2. Corporate Actions & Ex-Date Price Decomposition

> [!IMPORTANT]
> **Corporate Action Discontinuity & Eligibility Rule**:
> 1. An investor purchasing at the closing price on an ex-dividend date is **not** entitled to that dividend. Therefore, the ₹23 dividend with ex-date `2025-10-27` is excluded from holding-period income for Scenario A.
> 2. On ex-dividend dates, the nominal price drop must be decomposed into the **expected theoretical dividend adjustment** and the **residual market movement** to prevent misinterpreting capital distributions as organic investment losses.

### Ledger of Registered Corporate Actions in Observation Window
| Ex-Date | Type | Purpose / Description | Amount | Scenario A Eligible? | Ex-Date Decomposition |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `2025-10-27` | DIVIDEND | Interim Dividend - Rs 23 Per Share | ₹23.0 | No (Ex-date is Start Date) | N/A |
| `2025-11-14` | OTHER | Buy Back | ₹0.0 | Yes | Nominal: -2.53% (₹-39.0) | Residual Market: -2.53% (₹-39.0) |
| `2026-06-10` | DIVIDEND | Dividend - Rs 25 Per Share | ₹25.0 | Yes | Nominal: -2.97% (₹-35.0) | Residual Market: -0.85% (₹-10.0) |


### Ex-Date Price Decomposition Detail (June 10, 2026 Dividend of ₹25.00)
- **Previous Close (`2026-06-09`)**: ₹1,178.90
- **Ex-Date Close (`2026-06-10`)**: ₹1,143.90
- **Total Nominal Change**: -₹35.00 (-2.97%)
- **Expected Dividend Adjustment**: -₹25.00 (-2.12%)
- **Residual Market Movement**: -₹10.00 (-0.85%)
- *Conclusion*: Of the nominal 2.97% decline on June 10, 2026, **2.12 percentage points** were directly due to the dividend going ex, while residual market selling accounted for only **0.85 percentage points**.

---

## 3. Session Continuity & Trading Calendar Reconciliation

The trading calendar was validated against the official National Stock Exchange of India (NSE) holiday circular (`NSE/CMTR/71775` and official municipal election circulars).

### Exact Session Reconciliation
* **Calendar Weekdays in Window (Mon–Fri)**: 260
* **Official NSE Weekday Holidays in Window**: 15
* **Expected Trading Sessions**: 245 (260 weekdays - 15 holidays)
* **Observed Trading Sessions in Database**: 245
* **Unexplained Missing Sessions**: **0 days** (100% session continuity confirmed)

### Reconciled Official NSE Holidays in Observation Window
- `2025-11-05`: Prakash Gurpurb Sri Guru Nanak Dev Jayanti
- `2025-12-25`: Christmas
- `2026-01-15`: Municipal Corporation Election - Maharashtra
- `2026-01-26`: Republic Day
- `2026-03-03`: Holi
- `2026-03-26`: Shri Ram Navami
- `2026-03-31`: Shri Mahavir Jayanti
- `2026-04-03`: Good Friday
- `2026-04-14`: Dr. Baba Saheb Ambedkar Jayanti
- `2026-05-01`: Maharashtra Day
- `2026-05-28`: Bakri Id
- `2026-06-26`: Muharram
- `2026-09-14`: Ganesh Chaturthi
- `2026-10-02`: Mahatma Gandhi Jayanti
- `2026-10-20`: Dussehra


---

## 4. Methodological Distinctions & Known Limitations

1. **Price-Only vs Total-Return Risk Metrics**: Volatility (31.49%) and Maximum Drawdown (-41.69%) reported above are derived from nominal closing prices (**price-only metrics**). They do not represent a daily total return index (TRI), which would reinvest dividends on each ex-date.
2. **Annualization Conventions**:
   - **Calendar-Time CAGR (-23.55%)** scales return by the actual elapsed calendar time ($\\frac{365.25}{361}$ years).
   - **Trading-Day Annualisation (-23.97%)** scales return by the exchange trading day frequency ($\\frac{252}{244}$ periods).
3. **Data Provenance**:
   - Primary Source: Official NSE Model Context Protocol Server (`https://mcp.nseindia.in/bhavcopy/cm/mcp`).
   - Retrieval Timestamp (UTC): `2026-10-25T12:22:20.395631+00:00`
   - Raw Payload Archive: `data/raw/INFY_history_20261025T122222Z.json`
   - Local Database Store: `data/market_lab.db`

---

## 5. Statutory & Regulatory Notice

> [!WARNING]
> **Informational & Educational Use Only**: This document is generated by an automated computational pipeline for quantitative research and educational analysis. It does **not** constitute an investment recommendation, financial advice, or formal equity research as defined under the Securities and Exchange Board of India (SEBI) (Research Analysts) Regulations, 2014. Order execution capabilities are permanently disabled in this environment. Consult a SEBI-registered Investment Adviser (RIA) or Research Analyst (RA) for investment decisions.
