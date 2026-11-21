# Market Intelligence Lab: Master Data Coverage & Frontend Audit Report

**Generated:** 2026-11-21 15:12:54 UTC  
**Database File:** `data/market_lab.db` (SQLite WAL)  
**Total Master Equities:** 1,297 | **Active Equities:** 1,153  
**Total Historical Daily Bars:** 2,750,945  

---

## 1. Exact Universe Composition (Securities Master)

The database registers **1297 total equity records**, representing the institutional NSE equity universe.

| Category | Count | Pct of Master | Description |
| :--- | :---: | :---: | :--- |
| **Active Equities** | **1153** | 88.9% | Active NSE cash segment listings eligible for live execution and analytics |
| **NIFTY 50 Constituents** | **50** | 3.9% | Official exchange index benchmark constituents |
| **Inactive / Delisted** | **144** | 11.1% | Historical tickers preserved for survival-bias-free backtesting |
| **Total Universe** | **1297** | 100.0% | Master security registry |

### Sector Distribution

| Sector | Total Companies | Active Companies | Pct of Universe |
| :--- | :---: | :---: | :---: |
| **Equities** | 758 | 758 | 58.4% |
| **Financial Services** | 100 | 79 | 7.7% |
| **Capital Goods** | 71 | 44 | 5.5% |
| **Healthcare** | 49 | 37 | 3.8% |
| **Automobile and Auto Components** | 49 | 37 | 3.8% |
| **Information Technology** | 28 | 23 | 2.2% |
| **Fast Moving Consumer Goods** | 28 | 21 | 2.2% |
| **Consumer Services** | 27 | 17 | 2.1% |
| **Chemicals** | 26 | 18 | 2.0% |
| **Metals & Mining** | 20 | 14 | 1.5% |
| **Power** | 19 | 13 | 1.5% |
| **Oil Gas & Consumable Fuels** | 19 | 18 | 1.5% |

---

## 2. Historical Data Depth & Truth Layer Inventory

The database contains **2,750,945 daily OHLCV bars** spanning from `2011-01-03` to `2026-11-21` (**15.8 years** of market history).

### Historical Tiering Distribution

| Tier | Bar Range | Years Span | Symbol Count | Pct of Universe | Analytical Role |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Tier 1: Deep 10Y+** | 2,500 – 4,011 | 10.0 – 15.8 yrs | **586** | 45.2% | Full 10-year ML walk-forward training & multi-cycle backtests |
| **Tier 2: Standard 5Y** | 1,250 – 2,499 | 5.0 – 9.9 yrs | **192** | 14.8% | 5-year cross-validation, GARCH volatility, full factor calculation |
| **Tier 3: Tactical 2Y** | 500 – 1,249 | 2.0 – 4.9 yrs | **159** | 12.3% | 200 SMA regime, 52W High/Low drawdown, medium swing analytics |
| **Tier 4: Minimal 1Y** | 250 – 499 | 1.0 – 1.9 yrs | **68** | 5.2% | Minimum required for 200-day SMA and Screener score |
| **Tier 5: Insufficient** | 5 – 249 | < 1.0 yr | **143** | 11.0% | Recent IPOs & newly seeded equities |
| **Tier 6: Unseeded** | 0 | 0.0 yrs | **149** | 11.5% | Queued for Bhavcopy / yfinance archive backfill |

### Provenance Breakdown
- **Official Exchange Settlement (`EXCHANGE_OFFICIAL`):** **2,735,582 bars** (99.44%)
- **Synthetic Test Data (`is_synthetic = 1`):** **4,155 bars** (Quarantined, strictly excluded from live analytics & ML)

---

## 3. Frontend Display Mapping: What is Actually Delivered to Users

The frontend presents multi-tier quantitative intelligence across 4 primary interfaces:

### A. Screener Workspace (`/` via `/api/v1/screener`)
- **Capacity:** Delivers top **1,000 active equities** sorted by Composite Conviction Score (0-100).
- **Eligible in DB:** **1127 equities** currently meet the >= 50 bars & active listing threshold.
- **Fields Rendered per Row (24 parameters):**
  `Symbol`, `Company Name`, `Sector`, `Industry`, `Close Price (₹)`, `1D Return %`, `20D Momentum %`, `52W High`, `52W Low`, `Composite Score`, `Conviction Tier`, `Action Signal`, `SMA 20/50/200 Distance`, `Volume (Shares)`, `Turnover (₹ Cr)`, `ROE %`, `D/E Ratio`, `TTM P/E`, `OPM %`.

### B. Stock Inspector & Candlestick Chart (`/stocks/{symbol}` via `/api/v1/stocks/{symbol}/bundle`)
- **Chart Data:** Returns **all historical OHLCV bars** available in `ohlcv_daily` for the selected stock (1127 symbols have >= 50 bars; up to 4,000 bars rendered in Lightweight Charts with full pan/zoom).
- **GARCH(1,1) Volatility Cone:** Renders 20-day probabilistic cones with **80% and 95% confidence bands** (1148 symbols eligible).
- **Multi-Horizon Investment Memo:** Blends 5D Tactical (Ridge), 20D Tactical (HistGradientBoosting), and 60D Trend models into a unified institutional conviction verdict (1121 symbols eligible).
- **Live News Feed:** Top **10 articles** with NLP-scored directional impact (`BULLISH`, `BEARISH`, `NEUTRAL`), publisher, and timestamp.
- **Corporate Disclosures:** **5 most recent statutory filings** with verified category, dividend declared, and operating margins.

### C. Copilot Grounding Engine (`⌘J` Copilot Drawer)
- Delivers live 52W High/Low drawdown telemetry, peak-to-trough dip analysis, historical worst/best single-day moves, fundamental valuation, and 3-agent bull/bear committee debate.

---

## 4. Gap Analysis & Engine Requirements Roadmap

| Subsystem / Engine | Current Inventory | Target Institutional Baseline | Gap to Extract | Extraction Strategy |
| :--- | :--- | :--- | :--- | :--- |
| **WalkForwardMLTrainer** | 778 symbols >= 5Y<br>586 symbols >= 10Y | 1,148 symbols >= 10Y (2.5M rows) | 1,235,078 bars across 711 symbols | Run `Bhavcopy10YHarvester.harvest_next_batch()` walking back to 2016-01-01 into `bhavcopy_10y.milz`. |
| **GARCH(1,1) Volatility Forecaster** | 778 symbols >= 750 bars | 1,148 symbols >= 750 bars | 370 symbols need 250-500 more bars | Backfill historical daily bars for newer listings. |
| **4-Pillar Catalyst Engine** | News: 281 symbols<br>Disclosures: 56 symbols | News & Disclosures across all 1,153 active symbols | 872 symbols lack news feed; 1,097 lack filings | Extend Google News RSS scraper & NSE corporate announcement harvester to full active universe. |
| **Delivery Microstructure Radar** | 49 symbols with deep delivery | 1,148 symbols with daily delivery % | 1147 symbols lack delivery data | Ingest NSE MTO (Market Turnover & Delivery) archive files. |
| **Financial Statements & Ratios** | 181 symbols quarterly<br>1,153 symbols annual | 1,148 symbols with 5-year quarterly P&L + BS | 24,706 quarterly reports across 967 symbols | Ingest 10-year quarterly financials via Screener.in / NSE corporate API. |
| **Benchmark Attribution Engine** | NIFTY 50 PRI (8,973 bars) | 15 Sectoral Indices (NIFTY BANK, IT, AUTO, FMCG) | 15 Sectoral index histories (~35,000 bars) | Backfill NSE Sectoral Index CSV archives from 2011 to present. |
