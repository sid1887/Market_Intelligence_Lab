# ADR-0001: Market Intelligence Lab Truth, Provenance & Architecture Decisions (ADR 0001–0012)

**Status:** Ratified & Approved  
**Date:** 2026-11-05  
**Context:** Institutional hardening and elimination of synthetic data, fabricated financial defaults, and unverified claims across Market Intelligence Lab.

---

### ADR-0001: Research Scope & Local-First Deployment
MIL is a single-user local-first quantitative research workbench. Backend API binds to `127.0.0.1` by default (overrideable via `MIL_BIND_HOST`). CORS allowlist is restricted strictly to local origins (`http://localhost:3000`, `http://127.0.0.1:3000`). If non-loopback binding is enabled, an `X-MIL-API-Key` header is strictly required.

### ADR-0002: Data Rights, Sourcing & Attribution
All data ingested via exchange tools (`nse-bhavcopy` MCP) and macro providers (`alphavantage` MCP) is strictly for personal quantitative research. Every API response and UI component must carry `source_id`, `observed_at`, and `freshness_status` timestamps.

### ADR-0003: Price Basis & Corporate Actions
Raw unadjusted prices must remain immutable in `ohlcv_daily`. Corporate action adjustment factors (splits, bonuses, dividends) are stored in a versioned ledger (`corporate_actions` / `corporate_action_adjustments`) and applied dynamically or in versioned analytical views.

### ADR-0004: Benchmark Mandate
Official `NIFTY 50 TRI` is the primary benchmark for total return strategies. `NIFTY 50 PRI` is permitted strictly as an explicitly labelled price-return benchmark (`benchmark_type="PRICE_INDEX"`). Chaining synthetic cross-sectional stock averages (`AVG(ret_1d)`) to invent missing benchmark dates is strictly prohibited. If benchmark data is stale or missing, return `BENCHMARK_STALE` / `BENCHMARK_UNAVAILABLE`.

### ADR-0005: Eligible Universe
The standard active universe consists of the 180 NSE mainboard equities defined in `securities_master` with point-in-time listing bounds (`listed_from <= date <= delisted_at`). SME issues, illiquid lots, and restricted surveillance scrips (`XT`) are excluded from general composite screening.

### ADR-0006: Financial Ratios & Point-in-Time Accounting
Financial statements must enforce publication availability time (`available_at <= as_of_date`). When publication time is unavailable, apply a conservative regulatory lag (45 days quarterly, 60 days annual) tagged with `availability_method = "CONSERVATIVE_REGULATORY_LAG"`. Prefer `CONSOLIDATED` filings and never mix standalone and consolidated periods within a single TTM calculation. Missing debt must remain `None` (`status="MISSING"`), never coerced to `0.0`. Financial sector institutions (Banks/NBFCs) receive `NOT_APPLICABLE` for manufacturing debt-to-equity and operating margins.

### ADR-0007: Transparent Multi-Factor Screener
The screener is a transparent multi-factor ranking model exposing separate `quality_score`, `momentum_score`, `risk_score`, and `data_completeness_score`. Factor percentile ranks are computed strictly across valid non-null observations. If valid weight completeness $\ge 60\%$, active weights are renormalized; if completeness $< 60\%$, `composite_score` is `None` with status `INSUFFICIENT_DATA`.

### ADR-0008: Prediction Objectives & Econometric Forecasts
The GARCH/OU forecasting module models 20-trading-session forward log-normal price quantiles ($q_{0.025}, q_{0.10}, q_{0.50}, q_{0.90}, q_{0.975}$). The adaptive ML module targets 20-trading-session forward excess total return over official NIFTY 50 TRI net of statutory Indian transaction costs. Forecasts can only be evaluated after maturity (`latest_settled_session >= target_date`).

### ADR-0009: Execution Timing & Indian Statutory Delivery Cost Schedule
Signals generated at session $t$ close execute at session $t+1$ open (`next_open`). Same-day close execution fallback is forbidden. The statutory Indian delivery transaction cost schedule is strictly enforced:
- STT: 0.10% on Buy and Sell delivery turnover
- NSE Transaction Charges: 0.00297%
- SEBI Turnover Fee: 0.0001%
- Stamp Duty: 0.015% (Buy side only)
- GST: 18% on (Brokerage + Exchange + SEBI fees)
- DP Charge: ₹15.34 (₹13 + 18% GST) per scrip (Sell side only)
- Slippage / Impact: 10 bps default (large caps)

### ADR-0010: LLM Isolation & Offline Core Operation
The `openai` SDK and external LLM connections are optional lazy-loaded extras. The core research platform, SQLite migrations, quant pipelines, backtest engine, and `pytest` suite must run 100% offline with zero external dependencies and zero errors when `openai` is uninstalled.

### ADR-0011: Strict CQRS Separation (Read-Only GET Endpoints)
HTTP `GET` endpoints are strictly read-only and execute on read-only SQLite URI connections (`mode=ro`). `GET` requests must never trigger database writes, forecast audit logging, RSS refreshes, or backtest simulations. All mutations and heavy computational workflows require explicit `POST` endpoints.

### ADR-0012: Data Immutability & Quarantine Lifecycle
Raw source records and historical audit entries must never be overwritten without a verified backup in `data/backups/`. Legacy contaminated factor rows or backtest runs with valuation defects must be quarantined with explicit status flags (`LEGACY_FALLBACK_CONTAMINATED`, `LEGACY_INVALID_VALUATION`) to maintain complete historical reproducibility.
