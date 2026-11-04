# Daily Market Overview — NIFTY 50
**As-of Trading Session:** `2026-10-27` | **Generated:** `2026-10-27 11:15:02 UTC`  
**Benchmark Mode:** Official `PRI` (Price Return Index) | **Coverage:** 50 Constituents (100%)  
**System Status:** Local-First SQLite (`data/market_lab.db`) | **Trading Operations:** Strictly Disabled  

---

## 1. Benchmark Index Performance & Market Pulse

| Benchmark Index | Close Value | 1D Return | 1M Return | 3M Return | 6M Return | 1Y Return |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **NIFTY 50 (PRI)** | **`22,600.00`** | **`-0.39%`** | `-3.12%` | `-5.32%` | `-7.29%` | `-12.96%` |

> [!NOTE]
> **Return Horizon Methodology**: Trailing returns use fixed trading-session windows (1D = 1 trading session, 1M = 21 trading sessions, 3M = 63 trading sessions, 6M = 126 trading sessions, 1Y = 245 trading sessions), rather than calendar-day offsets, ensuring exact session-by-session reproducibility across holidays and suspensions.

## 2. Market Breadth & Moving Average Participation

| Market Breadth Metric | Observed Value | Specification & Accounting |
| :--- | :---: | :--- |
| **Universe Tracking** | `50 / 50` stocks | Point-in-time constituent coverage: **`100.0%`** |
| **Advancing Stocks** | **`25`** | Close > Prior Close |
| **Declining Stocks** | **`25`** | Close < Prior Close |
| **Unchanged Stocks** | `0` | Close == Prior Close |
| **Advance / Decline Ratio** | **`1.00`** | Advance count / Decline count |
| **Advance / Decline Volume Ratio** | **`1.05x`** | Advance Volume / Decline Volume (205,360,012 / 195,591,480 shares) |
| **Advancing Share of Total Volume** | **`51.22%`** | Advance Volume / Total Volume (205,360,012 / 400,951,492 shares) |
| **Constituents > 20-Day SMA** | **`38.0%`** | Short-term trend participation (`19` eligible stocks) |
| **Constituents > 50-Day SMA** | **`24.0%`** | Intermediate-term trend participation (`12` eligible stocks) |
| **Constituents > 200-Day SMA** | **`26.0%`** | Long-term structural trend participation (`13` eligible stocks) |


## 3. Relative Strength Leaderboards (Excess Return vs Nifty 50)

### 3.1 One-Month Horizon (1M)

| Category | Symbol | Stock Return (1M) | Benchmark Return (1M) | Excess Return | 60D Beta |
| :--- | :--- | :---: | :---: | :---: | :---: |
| Outperformer | **TCS** | `+20.19%` | `-3.12%` | **`+23.31%`** | `1.12` |
| Outperformer | **TECHM** | `+15.36%` | `-3.12%` | **`+18.49%`** | `1.02` |
| Outperformer | **INFY** | `+12.08%` | `-3.12%` | **`+15.21%`** | `1.07` |
| Outperformer | **HCLTECH** | `+11.95%` | `-3.12%` | **`+15.07%`** | `1.07` |
| Outperformer | **KOTAKBANK** | `+4.33%` | `-3.12%` | **`+7.45%`** | `0.72` |
| Underperformer | **MAXHEALTH** | `-22.86%` | `-3.12%` | **`-19.73%`** | `0.45` |
| Underperformer | **ADANIENT** | `-17.35%` | `-3.12%` | **`-14.23%`** | `1.31` |
| Underperformer | **SHRIRAMFIN** | `-14.02%` | `-3.12%` | **`-10.89%`** | `1.79` |
| Underperformer | **NESTLEIND** | `-13.85%` | `-3.12%` | **`-10.73%`** | `0.44` |
| Underperformer | **TITAN** | `-12.76%` | `-3.12%` | **`-9.63%`** | `0.86` |

### 3.2 Three-Month Horizon (3M)

| Category | Symbol | Stock Return (3M) | Benchmark Return (3M) | Excess Return | 60D Beta |
| :--- | :--- | :---: | :---: | :---: | :---: |
| Outperformer | **TECHM** | `+15.05%` | `-5.32%` | **`+20.37%`** | `1.02` |
| Outperformer | **HCLTECH** | `+14.26%` | `-5.32%` | **`+19.58%`** | `1.07` |
| Outperformer | **TCS** | `+12.80%` | `-5.32%` | **`+18.12%`** | `1.12` |
| Outperformer | **KOTAKBANK** | `+12.30%` | `-5.32%` | **`+17.62%`** | `0.72` |
| Outperformer | **ETERNAL** | `+10.55%` | `-5.32%` | **`+15.87%`** | `1.14` |
| Underperformer | **MAXHEALTH** | `-24.83%` | `-5.32%` | **`-19.51%`** | `0.45` |
| Underperformer | **NESTLEIND** | `-18.85%` | `-5.32%` | **`-13.53%`** | `0.44` |
| Underperformer | **TMPV** | `-18.41%` | `-5.32%` | **`-13.09%`** | `1.12` |
| Underperformer | **ADANIENT** | `-17.71%` | `-5.32%` | **`-12.39%`** | `1.31` |
| Underperformer | **MARUTI** | `-16.21%` | `-5.32%` | **`-10.89%`** | `0.81` |

> [!IMPORTANT]
> Relative strength calculations use Mode 1 (Price Return vs Nifty 50 PRI) with corporate action split/bonus price adjustments. Mode 2 (Total Return vs TRI) is reserved for stocks with verified dividend ledgers.

## 4. Statistical Volume Anomaly Scanner

| Symbol | Close Price | Traded Volume | 20D Volume Ratio | 50D Volume Z-Score | Anomaly Classification |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **BAJAJFINSV** | ₹1,677.00 | 2,481,029 | `2.25x` | `+4.39σ` | Statistical Z-Score Tail (>=2.5σ) |
| **CIPLA** | ₹1,350.00 | 4,078,811 | `4.17x` | `+9.65σ` | Both VR & Z-Score |
| **HINDUNILVR** | ₹1,818.00 | 3,796,225 | `2.61x` | `+4.75σ` | Both VR & Z-Score |
| **TATACONSUM** | ₹1,000.00 | 7,578,802 | `5.63x` | `+11.83σ` | Both VR & Z-Score |
## 5. Corporate Disclosures & Material Filings Audit

| Effective Session | Symbol | Category | Verification Status | Subject / Direct Source Document |
| :---: | :--- | :--- | :---: | :--- |
| `2026-10-26` | **INFY** | `EARNINGS` | **`VERIFIED`** | [Outcome of Board Meeting: Audited Standalone & Consolidated Financial Results for Q2 FY2027 and Declaration of Interim Dividend](https://www.infosys.com/investors/documents/exchange-filings/2026/outcome-board-meeting23oct2026.pdf) |
| `2026-10-16` | **INFY** | `BOARD_MEETING_SCHEDULE` | ⚠️ **`SOURCE_UNVERIFIED`** | [Claimed Intimation of Board Meeting (Unverified Schedule Notice)](https://www.nseindia.com/companies-listing/corporate-filings-announcements) |
| `2026-09-16` | **INFY** | `BOARD_MEETING_SCHEDULE` | **`VERIFIED`** | [Intimation of Board Meeting under Regulation 29 of SEBI (LODR) Regulations, 2015](https://www.infosys.com/investors/documents/exchange-filings/2026/notice-board-meeting-15sep2026.pdf) |


## 6. Explanatory Hypotheses & Epistemic Boundaries

1. **Market Regime Hypothesis**: Session `2026-10-27` exhibited characteristics of **mixed rotational consolidation**, with `50.0%` of Nifty 50 constituents advancing. Advance volume accounted for `1.05x` of total turnover.
2. **Participation Structure**: Long-term moving average breadth shows `26.0%` of the universe trading above their 200-day moving averages, while short-term 20-day participation is at `38.0%`.
3. **Confounding Market Factors**: All abnormal returns and volume spikes are documented as co-occurring empirical phenomena. Observed relative outperformance cannot be attributed to a single cause without accounting for global macro rates, institutional liquidity rebalancing, and industry-wide sector rotation.

> [!CAUTION]
> **Non-Execution Notice**: The Market Intelligence Lab operates strictly as a local-first quantitative research environment. Live order placement, broker credential storage, and autonomous execution are permanently disabled.
