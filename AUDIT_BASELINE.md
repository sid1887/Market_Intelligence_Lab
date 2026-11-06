# Market Intelligence Lab — Baseline Audit Record
**Recorded At:** 2026-11-05T16:29:00+05:30  
**Git Head:** `5311d7a` (main)  
**Database Path:** `data/market_lab.db`  
**Verified Pre-Audit Backup:** `data/backups/market_lab_pre_truth_audit.db`  
**Backup SHA-256 Checksum:** `3c439c8cdf6359f285d520119818e79417d676aafc9c1e7df1ca57a320a6647f`

---

## 1. Verified Baseline Database Counts (22 Tables)
- `backtest_equity_curve`: 6,147 rows
- `backtest_runs`: 11 rows (Status: 10 completed, 1 latest with 99.99% MaxDD defect)
- `catalyst_audit_ledger`: 1 row
- `company_financial_statements`: 453 rows
- `corporate_actions`: 911 rows
- `corporate_disclosures`: 95,796 rows (95,766 PENDING_VERIFICATION, 29 VERIFIED, 1 SOURCE_UNVERIFIED)
- `equity_news_feed`: 1,904 rows
- `event_study_results`: 4 rows
- `evidence_records`: 1,418 rows (1,417 VERIFIED, 1 SOURCE_UNVERIFIED)
- `financial_statements_annual`: 119 rows
- `financial_statements_quarterly`: 546 rows
- `forecast_audit_ledger`: 1,187 rows (4 evaluated, 219 distinct keys, 968 duplicate entries)
- `fundamental_factors_daily`: 211 rows
- `index_daily`: 8,964 rows (Ends on 2026-10-23, lag of 12 calendar days vs equities)
- `index_membership_history`: 300 rows
- `ingestion_audit_log`: 576 rows
- `movement_explanations`: 6 rows
- `ohlcv_daily`: 254,507 rows (2020-01-01 to 2026-11-04; 2026-10-26 has only 123 rows vs 180 expected)
- `quant_factors_daily`: 255,789 rows (222,892 rows contain fabricated defaults 18.5/0.12/22.0; 121 of 180 latest rows contaminated)
- `securities_master`: 503 rows (180 active)
- `sqlite_sequence`: 2 rows
- `user_watchlists`: 4 rows

---

## 2. Verified High-Severity Defect Baselines
1. **P0-01 Contaminated Factors:** 222,892 total rows and 121 of 180 latest active rows contain hardcoded fallback tuple `(roe_pct=18.5, debt_to_equity=0.12, opm_pct=22.0)`.
2. **P0-02 Backtest Missing-Bar Valuation:** Held equities without OHLCV bars on a session evaluated at `close = 0.0`, resulting in artificial 99.99% drawdown spikes (e.g. 2026-10-26 where 57 symbols were missing).
3. **P0-03 Benchmark Fabrication:** NIFTY 50 TRI benchmark gap filled with cross-sectional `AVG(ret_1d)` over stocks. Index records stopped at 2026-10-23 while stock bars continued to 2026-11-04.
4. **P0-04 Forecast Ledger Duplication & Premature Evaluation:** 1,187 rows with only 4 evaluated, duplicated up to 75x per symbol/date; backward bar fallback evaluated pre-maturity.
5. **P0-05 UI Fake Accuracy & Hardcoded Macro:** Terminal fallback displayed `96% 20D Containment · 3.8% RMSE` with only 4 historical evaluations; `/macro` served static figures marked `live`.
6. **P0-06 Screener Null-to-Zero Ranking:** Missing 20-day returns and missing percentiles filled with `0.0`.
7. **P0-08 CQRS Mutation on GET:** `GET /backtest/latest` created runs; `GET /forecast` created audit ledger entries.
8. **P0-09 Missing Dependency Declarations:** `pyproject.toml` omitted `fastapi`, `uvicorn`, `pydantic`, `pandas`, `pytest`; `src/copilot/deliberation.py` caused pytest import failures when `openai` uninstalled.
