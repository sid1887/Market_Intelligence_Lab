# Milestone B6.4.1 Hotfix Verification Report: API NaN Serialization, Route Fix & Memory Optimization

**Date:** 2026-11-04  
**Milestone:** B6.4.1 (Stability & Hotfix)  
**System Status:** Platform Hardened & Verified  
**Repository:** `https://github.com/sid1887/Market_Intelligence_Lab.git`  
**Working Directory:** `/home/siddharth/Desktop/Market_Intelligence_Lab`  

---

## 1. Executive Summary

Milestone B6.4.1 resolves three critical production stability issues identified in the FastAPI backend and dynamic ingestion engine:
1. **JSON NaN / Infinity Serialization Crash:** Fixed `ValueError: Out of range float values are not JSON compliant: nan` when querying `/api/v1/screener` and stock tearsheets by introducing a recursive serialization sanitizer (`sanitize_for_json`) and explicit NaN filtering.
2. **Missing / Misrouted `/stocks/{symbol}/status` Route:** Mounted unified routes (`/stocks/{symbol}/status` and `/api/v1/stocks/{symbol}/status`) in `src/api/routes_market.py` and `src/api/main.py`. The endpoint never returns a 404 for unseeded or unknown tickers; instead, it checks active jobs, database readiness, and returns `READY`, `INGESTING`, `FAILED`, or `NOT_STARTED`.
3. **Ingestion Worker Memory Optimization:** Hardened `DynamicIngestionManager` and background ingestion tasks by restricting intermediate SQLite query column sets, executing explicit garbage collection (`gc.collect()`), and wrapping workers in robust exception handlers to prevent OS OOM kills.

---

## 2. Root Cause Analysis & Implementations

### Bug 1: JSON NaN / Infinity Serialization Crash
- **Root Cause:** Rolling technical indicators (warm-up periods) and fundamental ratios (stocks with negative net worth or zero revenue) generated `np.nan` or `float('inf')`. Python's `row.get("roe_pct") is not None` evaluated to `True` for `np.nan`, and Starlette's `json.dumps()` crashed with `ValueError: Out of range float values are not JSON compliant: nan`.
- **Solution:**
  - Implemented [`src/api/utils.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/api/utils.py) with `sanitize_for_json(obj)` that recursively traverses dicts, lists, scalars, and Pandas DataFrames (`df.where(pd.notnull(df), None)`), mapping any `math.isnan(x)` or `math.isinf(x)` to Python `None` (which serializes to standard JSON `null`).
  - Added `safe_float(val, precision)` and `safe_int(val)` helpers to sanitize numeric values during dictionary creation.
  - Applied `sanitize_for_json` across `/api/v1/screener`, `/api/v1/watchlist`, `/api/v1/stocks/{symbol}/status`, `/api/v1/stocks/{symbol}/tearsheet`, and `/api/v1/stocks/{symbol}/history`.

### Bug 2: Missing or Misrouted `/stocks/{symbol}/status` Route
- **Root Cause:** Requests to `GET /api/v1/stocks/{symbol}/status` or `GET /stocks/{symbol}/status` were misrouted or returned 404 when `routes_market.py` was not populated with explicit endpoints.
- **Solution:**
  - In [`src/api/routes_market.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/api/routes_market.py) and [`src/api/main.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/api/main.py), defined both `@router.get("/stocks/{symbol}/status")` and `@router.get("/api/v1/stocks/{symbol}/status")`.
  - Implemented the required fallback hierarchy:
    1. If `symbol` is in `DynamicIngestionManager._active_jobs`, return the active job's current progress dictionary (`status: "INGESTING"`, `progress_pct`, etc.).
    2. If `symbol` exists in `securities_master` or `user_watchlists` with populated OHLCV (`ohlcv_count > 0`), return `{"status": "READY", "progress_pct": 100, ...}`.
    3. If unknown and not queued, return `{"status": "NOT_STARTED", "progress_pct": 0, ...}` (never HTTP 404).

### Bug 3: Ingestion Worker Memory Leak Prevention
- **Root Cause:** Heavy factor computation across hundreds of sessions created large intermediate lists and DataFrames, increasing memory pressure in long-lived background workers.
- **Solution:**
  - Restricted SQLite queries to fetch only required columns rather than `SELECT *`.
  - Added explicit garbage collection (`import gc; gc.collect()`) after factor computation and in the `finally` block of `DynamicIngestionManager.ensure_symbol_data()`.
  - Wrapped background workers in `try / except` blocks in `run_dynamic_ingestion` so failures update status to `FAILED` with explicit error details rather than terminating the ASGI worker process.

---

## 3. Verification & Test Audit

### 3.1 Unit Test Suite (`tests/test_api_nan_handling.py`)
```text
test_01_sanitize_for_json_unit ... ok
test_02_screener_mocked_nan_and_infinity ... ok
test_03_screener_real_database_limit_54 ... ok
test_04_tatapower_status_returns_200 ... ok
test_05_unknown_status_returns_200_not_started ... ok
test_06_route_without_prefix_returns_200 ... ok
test_07_active_ingestion_job_status ... ok

----------------------------------------------------------------------
Ran 7 tests in 0.071s — OK
```

### 3.2 Full Platform Regression Test Suite
```text
Ran 246 tests in 114.937s — OK (skipped=1)
```

### 3.3 Live Endpoint Verification (`curl` against Platform Server)
```bash
# 1. Full universe screener (limit=54) returns HTTP 200 with clean nulls
curl -s -i "http://localhost:8000/api/v1/screener?limit=54"
# Response: HTTP/1.1 200 OK (returned_count: 54, IDEA debt_to_equity: null, roe_pct: null)

# 2. Status check for populated symbol returns HTTP 200
curl -s -i "http://localhost:8000/api/v1/stocks/TATAPOWER/status"
# Response: HTTP/1.1 200 OK {"status":"READY","symbol":"TATAPOWER","progress_pct":100}

# 3. Status check for unknown symbol returns HTTP 200 (not 404)
curl -s -i "http://localhost:8000/api/v1/stocks/UNKNOWN_XYZ/status"
# Response: HTTP/1.1 200 OK {"status":"NOT_STARTED","symbol":"UNKNOWN_XYZ","progress_pct":0}
```

### 3.4 Next.js Production Build
```text
✓ Compiled successfully
✓ Linting and checking validity of types
✓ Generating static pages (5/5)
0 TypeScript errors · 0 ESLint warnings
```
