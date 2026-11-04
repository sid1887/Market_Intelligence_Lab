# Milestone B3.2: Corporate Actions & Disclosures Live Ingestion Report

**Date:** 2026-11-03 16:49:33 UTC  
**System:** Market Intelligence Lab (B3.2 Ingestion Pipeline)  
**Database:** `data/market_lab.db`  
**Active Universe Constituents:** 50 symbols  
**Execution Runtime:** 102.22 seconds  
**Status:** **COMPLETE & SOURCE-VERIFIED**  

---

## 1. Executive Summary & Verification Metrics

Milestone B3.2 delivers source-verified, automated ingestion of corporate actions and official regulatory disclosures directly from the National Stock Exchange of India (NSE) structured API endpoints.

| Metric | Result | Description / Compliance |
| :--- | :--- | :--- |
| **Active Universe Coverage** | **50 / 50 Symbols** | 100% of active securities in `securities_master` processed. |
| **Corporate Actions Retrieved** | **910** | Official declared dividends, bonus issues, splits, and rights. |
| **Corporate Actions Ingested** | **910** | Persisted via idempotent `ON CONFLICT(id)` upserts. |
| **Corporate Disclosures Retrieved** | **96597** | Official regulatory filings and board notifications. |
| **Corporate Disclosures Ingested** | **96597** | Persisted with default `PENDING_VERIFICATION` status. |
| **HTTP 403 / 429 Failures** | **0** | Akamai WAF session resilience and exponential backoff verified. |
| **Zero-Action Graceful Handlers** | Verified | Stocks with zero actions logged as `NO_ACTIONS_FOUND`. |

---

## 2. Ingestion Summary by Symbol

| Symbol | Actions Retrieved | Actions Accepted | Actions Status | Disclosures Retrieved | Disclosures Accepted | Disclosures Status | Notes |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `ADANIENT` | 20 | 20 | `SUCCESS` | 1547 | 1547 | `SUCCESS` | Clean ingestion |
| `ADANIPORTS` | 20 | 20 | `SUCCESS` | 1478 | 1478 | `SUCCESS` | Clean ingestion |
| `APOLLOHOSP` | 20 | 20 | `SUCCESS` | 1191 | 1191 | `SUCCESS` | Clean ingestion |
| `ASIANPAINT` | 20 | 20 | `SUCCESS` | 1770 | 1770 | `SUCCESS` | Clean ingestion |
| `AXISBANK` | 20 | 20 | `SUCCESS` | 3129 | 3129 | `SUCCESS` | Clean ingestion |
| `BAJAJ-AUTO` | 20 | 20 | `SUCCESS` | 1201 | 1201 | `SUCCESS` | Clean ingestion |
| `BAJAJFINSV` | 20 | 20 | `SUCCESS` | 865 | 865 | `SUCCESS` | Clean ingestion |
| `BAJFINANCE` | 20 | 20 | `SUCCESS` | 1327 | 1327 | `SUCCESS` | Clean ingestion |
| `BEL` | 20 | 20 | `SUCCESS` | 1044 | 1044 | `SUCCESS` | Clean ingestion |
| `BHARTIARTL` | 20 | 20 | `SUCCESS` | 2604 | 2604 | `SUCCESS` | Clean ingestion |
| `BSE` | 17 | 17 | `SUCCESS` | 1317 | 1317 | `SUCCESS` | Clean ingestion |
| `CIPLA` | 20 | 20 | `SUCCESS` | 1799 | 1799 | `SUCCESS` | Clean ingestion |
| `COALINDIA` | 20 | 20 | `SUCCESS` | 1429 | 1429 | `SUCCESS` | Clean ingestion |
| `DRREDDY` | 20 | 20 | `SUCCESS` | 2024 | 2024 | `SUCCESS` | Clean ingestion |
| `EICHERMOT` | 20 | 20 | `SUCCESS` | 1948 | 1948 | `SUCCESS` | Clean ingestion |
| `ETERNAL` | 0 | 0 | `NO_ACTIONS_FOUND` | 451 | 451 | `SUCCESS` | Clean ingestion |
| `GRASIM` | 20 | 20 | `SUCCESS` | 1959 | 1959 | `SUCCESS` | Clean ingestion |
| `HCLTECH` | 20 | 20 | `SUCCESS` | 2755 | 2755 | `SUCCESS` | Clean ingestion |
| `HDFCBANK` | 20 | 20 | `SUCCESS` | 2358 | 2358 | `SUCCESS` | Clean ingestion |
| `HDFCLIFE` | 10 | 10 | `SUCCESS` | 783 | 783 | `SUCCESS` | Clean ingestion |
| `HINDALCO` | 20 | 20 | `SUCCESS` | 1759 | 1759 | `SUCCESS` | Clean ingestion |
| `HINDUNILVR` | 20 | 20 | `SUCCESS` | 1735 | 1735 | `SUCCESS` | Clean ingestion |
| `ICICIBANK` | 20 | 20 | `SUCCESS` | 5256 | 5256 | `SUCCESS` | Clean ingestion |
| `INDIGO` | 9 | 9 | `SUCCESS` | 800 | 800 | `SUCCESS` | Clean ingestion |
| `INFY` | 20 | 20 | `SUCCESS` | 2946 | 2946 | `SUCCESS` | Clean ingestion |
| `ITC` | 20 | 20 | `SUCCESS` | 1739 | 1739 | `SUCCESS` | Clean ingestion |
| `JIOFIN` | 2 | 2 | `SUCCESS` | 284 | 284 | `SUCCESS` | Clean ingestion |
| `JSWSTEEL` | 20 | 20 | `SUCCESS` | 2096 | 2096 | `SUCCESS` | Clean ingestion |
| `KOTAKBANK` | 20 | 20 | `SUCCESS` | 2334 | 2334 | `SUCCESS` | Clean ingestion |
| `LT` | 20 | 20 | `SUCCESS` | 2653 | 2653 | `SUCCESS` | Clean ingestion |
| `M&M` | 20 | 20 | `SUCCESS` | 3890 | 3890 | `SUCCESS` | Clean ingestion |
| `MARUTI` | 20 | 20 | `SUCCESS` | 2031 | 2031 | `SUCCESS` | Clean ingestion |
| `MAXHEALTH` | 4 | 4 | `SUCCESS` | 764 | 764 | `SUCCESS` | Clean ingestion |
| `NESTLEIND` | 20 | 20 | `SUCCESS` | 391 | 391 | `SUCCESS` | Clean ingestion |
| `NTPC` | 20 | 20 | `SUCCESS` | 1979 | 1979 | `SUCCESS` | Clean ingestion |
| `ONGC` | 20 | 20 | `SUCCESS` | 1466 | 1466 | `SUCCESS` | Clean ingestion |
| `POWERGRID` | 20 | 20 | `SUCCESS` | 1472 | 1472 | `SUCCESS` | Clean ingestion |
| `RELIANCE` | 20 | 20 | `SUCCESS` | 3373 | 3373 | `SUCCESS` | Clean ingestion |
| `SBILIFE` | 8 | 8 | `SUCCESS` | 807 | 807 | `SUCCESS` | Clean ingestion |
| `SBIN` | 20 | 20 | `SUCCESS` | 2766 | 2766 | `SUCCESS` | Clean ingestion |
| `SHRIRAMFIN` | 20 | 20 | `SUCCESS` | 3954 | 3954 | `SUCCESS` | Clean ingestion |
| `SUNPHARMA` | 20 | 20 | `SUCCESS` | 1821 | 1821 | `SUCCESS` | Clean ingestion |
| `TATACONSUM` | 20 | 20 | `SUCCESS` | 1661 | 1661 | `SUCCESS` | Clean ingestion |
| `TATASTEEL` | 20 | 20 | `SUCCESS` | 3028 | 3028 | `SUCCESS` | Clean ingestion |
| `TCS` | 20 | 20 | `SUCCESS` | 3383 | 3383 | `SUCCESS` | Clean ingestion |
| `TECHM` | 20 | 20 | `SUCCESS` | 1704 | 1704 | `SUCCESS` | Clean ingestion |
| `TITAN` | 20 | 20 | `SUCCESS` | 1479 | 1479 | `SUCCESS` | Clean ingestion |
| `TMPV` | 20 | 20 | `SUCCESS` | 2806 | 2806 | `SUCCESS` | Clean ingestion |
| `TRENT` | 20 | 20 | `SUCCESS` | 1238 | 1238 | `SUCCESS` | Clean ingestion |
| `ULTRACEMCO` | 20 | 20 | `SUCCESS` | 2003 | 2003 | `SUCCESS` | Clean ingestion |

---

## 3. Resilience, Rate Limiting & Gateway Diagnostics

- **Total HTTP Connection Errors:** 0
- **Rate-Limit Blocks Encountered:** 0
- **Session Cookie Warm-Up:** Passed on initial handshake to `https://www.nseindia.com`.
- **Idempotent Re-entrancy:** Guaranteed via SQLite `INSERT ... ON CONFLICT(id) DO UPDATE`.
- **Audit Trail:** Recorded in `ingestion_audit_log` with exact retrieved/accepted/rejected counts.

---

## 4. Architectural Invariants Sign-Off

1. **Zero UI / AI Elements:** The implementation is strictly limited to data-layer ingestion and provenance verification.
2. **Zero Price Series Modification:** Historical OHLCV records and prices from B3.1 remain unadjusted and unaltered.
3. **Zero Lookahead Bias:** All newly ingested disclosures strictly default to `PENDING_VERIFICATION` at the SQLite schema level.
4. **Complete Source Provenance:** Raw payload JSONs archived with timestamped paths under `data/raw/`.