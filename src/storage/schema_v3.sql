-- ====================================================================
-- Market Intelligence Lab: Phase 3 / Milestone B5 Schema Migration (v3.0)
-- Safe, additive migration for Evidence Records and Movement Explanations.
-- ====================================================================

-- 1. Unified Evidence Records
CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    entity_type TEXT NOT NULL,               -- 'STOCK', 'SECTOR', 'BENCHMARK', 'MACRO'
    event_date TEXT NOT NULL,                -- YYYY-MM-DD
    broadcast_timestamp TEXT DEFAULT NULL,   -- ISO 8601 IST
    effective_session_date TEXT NOT NULL,    -- Aligned t=0 trading session YYYY-MM-DD
    evidence_tier INTEGER NOT NULL,          -- 1, 2, 3, 4, 5
    evidence_category TEXT NOT NULL,         -- 'EARNINGS_RELEASE', 'DIVIDEND_DECLARATION', etc.
    evidence_direction TEXT NOT NULL,        -- 'POSITIVE', 'NEGATIVE', 'NEUTRAL', 'AMBIGUOUS'
    headline TEXT NOT NULL,
    details_json TEXT NOT NULL,              -- JSON string with domain attributes
    source_identity TEXT NOT NULL,           -- e.g. 'nse_circular', 'bse_disclosure', 'cfs_table'
    source_reference TEXT DEFAULT NULL,      -- URL or document identifier
    verification_status TEXT NOT NULL DEFAULT 'PENDING_VERIFICATION', -- 'VERIFIED', 'PENDING_VERIFICATION', 'UNVERIFIED'
    is_pit_eligible INTEGER NOT NULL DEFAULT 1, -- 1=Point-in-time safe, 0=Lookahead hazard
    reporting_basis TEXT DEFAULT NULL,       -- 'CONSOLIDATED', 'STANDALONE', NULL
    expectation_surprise TEXT NOT NULL DEFAULT 'UNKNOWN', -- 'BEAT', 'MISS', 'IN_LINE', 'UNKNOWN'
    is_contradictory INTEGER NOT NULL DEFAULT 0, -- 1=Contradicts observed price action
    retrieval_timestamp TEXT NOT NULL,       -- ISO 8601 UTC
    created_at TEXT NOT NULL                 -- ISO 8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_evidence_sym_session 
ON evidence_records(symbol, effective_session_date);

CREATE INDEX IF NOT EXISTS idx_evidence_session 
ON evidence_records(effective_session_date);

CREATE INDEX IF NOT EXISTS idx_evidence_tier 
ON evidence_records(evidence_tier);

-- 2. Movement Explanations Cache / Ledger
CREATE TABLE IF NOT EXISTS movement_explanations (
    explanation_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    trading_date TEXT NOT NULL,              -- YYYY-MM-DD
    movement_classification TEXT NOT NULL,   -- 'IDIOSYNCRATIC_OUTPERFORMANCE', etc.
    stock_return_1d REAL NOT NULL,
    benchmark_return_1d REAL DEFAULT NULL,
    sector_return_1d REAL DEFAULT NULL,
    sector_benchmark_type TEXT NOT NULL,     -- 'OFFICIAL_SECTOR_PRI', 'SYNTHETIC_PEER_BASKET', etc.
    sector_benchmark_name TEXT NOT NULL,     -- e.g. 'NIFTY IT', 'SYNTHETIC_ENERGY_BASKET'
    abnormal_return REAL DEFAULT NULL,
    sector_adjusted_return REAL DEFAULT NULL,
    volume_ratio REAL DEFAULT NULL,
    primary_evidence_id TEXT DEFAULT NULL,
    evidence_strength_score REAL NOT NULL,   -- 0 to 100 deterministic heuristic score
    confidence_level TEXT NOT NULL,          -- 'HIGH_CONFIDENCE', 'MODERATE_CONFIDENCE', etc.
    is_contradicted INTEGER NOT NULL DEFAULT 0,
    contradiction_penalty REAL NOT NULL DEFAULT 0.0,
    unexplained_residual_pct REAL DEFAULT NULL,
    full_report_json TEXT NOT NULL,          -- Structured JSON of complete investigation
    generated_at TEXT NOT NULL               -- ISO 8601 UTC
);

CREATE INDEX IF NOT EXISTS idx_explanation_sym_date 
ON movement_explanations(symbol, trading_date);

-- ====================================================================
-- Milestone B3.3: Structured Financial Statements & Fundamental Data
-- ====================================================================

-- 3. Structured Financial Statements (Quarterly)
CREATE TABLE IF NOT EXISTS financial_statements_quarterly (
    symbol TEXT NOT NULL,
    period_end_date TEXT NOT NULL,           -- YYYY-MM-DD
    filing_date TEXT NOT NULL,               -- YYYY-MM-DD
    source_url TEXT,                         -- Direct link to filing / PDF
    is_audited INTEGER NOT NULL,             -- 1 for Audited, 0 for Unaudited/Limited Review
    revenue REAL NOT NULL,                   -- Exact value in Crores (INR)
    ebitda REAL NOT NULL,                    -- Exact value in Crores (INR)
    net_profit REAL NOT NULL,                -- Exact value in Crores (INR)
    eps REAL NOT NULL,                       -- Exact value in INR per share
    total_debt REAL NOT NULL,                -- Exact value in Crores (INR)
    total_equity REAL NOT NULL,              -- Exact value in Crores (INR)
    cash_flow_from_ops REAL,                 -- Exact value in Crores (INR)
    created_at TEXT NOT NULL,                -- ISO 8601 UTC
    PRIMARY KEY (symbol, period_end_date),
    FOREIGN KEY (symbol) REFERENCES securities_master(symbol)
);

CREATE INDEX IF NOT EXISTS idx_fsq_symbol_period 
ON financial_statements_quarterly(symbol, period_end_date);

-- 4. Structured Financial Statements (Annual)
CREATE TABLE IF NOT EXISTS financial_statements_annual (
    symbol TEXT NOT NULL,
    period_end_date TEXT NOT NULL,           -- YYYY-MM-DD
    filing_date TEXT NOT NULL,               -- YYYY-MM-DD
    source_url TEXT,                         -- Direct link to filing / PDF
    is_audited INTEGER NOT NULL,             -- 1 for Audited, 0 for Unaudited
    revenue REAL NOT NULL,                   -- Exact value in Crores (INR)
    ebitda REAL NOT NULL,                    -- Exact value in Crores (INR)
    net_profit REAL NOT NULL,                -- Exact value in Crores (INR)
    eps REAL NOT NULL,                       -- Exact value in INR per share
    total_debt REAL NOT NULL,                -- Exact value in Crores (INR)
    total_equity REAL NOT NULL,              -- Exact value in Crores (INR)
    cash_flow_from_ops REAL,                 -- Exact value in Crores (INR)
    created_at TEXT NOT NULL,                -- ISO 8601 UTC
    PRIMARY KEY (symbol, period_end_date),
    FOREIGN KEY (symbol) REFERENCES securities_master(symbol)
);

CREATE INDEX IF NOT EXISTS idx_fsa_symbol_period 
ON financial_statements_annual(symbol, period_end_date);

-- ====================================================================
-- Milestone B4.1: Persistent Quantitative Factors & Fundamental Ratios
-- ====================================================================

-- 5. Persistent Quantitative Factors & Fundamental Ratios Daily
CREATE TABLE IF NOT EXISTS quant_factors_daily (
    symbol TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    ret_1d REAL NOT NULL DEFAULT 0.0,
    ret_5d REAL DEFAULT NULL,
    ret_20d REAL DEFAULT NULL,
    vol_20d_annualized REAL DEFAULT NULL,
    volatility_annualized REAL DEFAULT NULL,
    sma_20 REAL DEFAULT NULL,
    sma_50 REAL DEFAULT NULL,
    sma_200 REAL DEFAULT NULL,
    beta_60d_nifty REAL DEFAULT NULL,
    volume_ratio_20d REAL DEFAULT NULL,      -- NULL during first 20 days warm-up
    volume_zscore_50d REAL DEFAULT NULL,     -- NULL during first 50 days warm-up
    volume_log_zscore_50d REAL DEFAULT NULL, -- NULL during first 50 days warm-up
    is_volume_spike_ratio INTEGER NOT NULL DEFAULT 0,  -- VR >= 2.5
    is_volume_spike_zscore INTEGER NOT NULL DEFAULT 0, -- Z >= 2.5
    distance_52w_high REAL DEFAULT NULL,
    distance_52w_low REAL DEFAULT NULL,
    ttm_pe REAL DEFAULT NULL,
    roe_pct REAL DEFAULT NULL,
    debt_to_equity REAL DEFAULT NULL,
    opm_pct REAL DEFAULT NULL,
    updated_at TEXT DEFAULT NULL,
    PRIMARY KEY (symbol, trading_date),
    FOREIGN KEY (symbol) REFERENCES securities_master(symbol)
);

CREATE INDEX IF NOT EXISTS idx_factors_date 
ON quant_factors_daily(trading_date);

CREATE INDEX IF NOT EXISTS idx_factors_symbol_date 
ON quant_factors_daily(symbol, trading_date);

-- ====================================================================
-- Milestone B4.3: Universe Expansion & User Watchlists
-- ====================================================================

-- 6. User Trading Watchlists
CREATE TABLE IF NOT EXISTS user_watchlists (
    symbol TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    sector TEXT NOT NULL,
    added_date TEXT NOT NULL,
    target_price REAL DEFAULT NULL,
    stop_loss REAL DEFAULT NULL,
    notes TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_watchlist_sector 
ON user_watchlists(sector);

-- ====================================================================
-- Milestone B7.5: News Ingestion, Structured Summarization & Directional Impact
-- ====================================================================

-- 7. Equity News Feed & Directional Impact Ledger
CREATE TABLE IF NOT EXISTS equity_news_feed (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    published_at TEXT NOT NULL,
    article_url TEXT NOT NULL,
    summary_bullets TEXT NOT NULL,
    impact_direction TEXT NOT NULL,
    impact_horizon TEXT NOT NULL,
    impact_drivers TEXT DEFAULT '[]',
    impact_rationale TEXT NOT NULL,
    confidence_score REAL DEFAULT 1.0,
    fetched_at TEXT NOT NULL,
    FOREIGN KEY (symbol) REFERENCES securities_master(symbol)
);

CREATE INDEX IF NOT EXISTS idx_news_sym_pub 
ON equity_news_feed(symbol, published_at DESC);

CREATE INDEX IF NOT EXISTS idx_news_article_url
ON equity_news_feed(article_url);

-- ====================================================================
-- Milestone B8.0: Multi-Factor Strategy Backtesting & Portfolio Rebalancing Engine
-- ====================================================================

-- 8. Backtest Runs Ledger
CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id TEXT PRIMARY KEY,
    strategy_name TEXT NOT NULL,
    parameters TEXT NOT NULL,          -- JSON serialized dict
    cagr_pct REAL NOT NULL,
    sharpe_ratio REAL NOT NULL,
    max_drawdown_pct REAL NOT NULL,
    win_rate_pct REAL NOT NULL,
    created_at TEXT NOT NULL
);

-- 9. Backtest Equity Curve Series
CREATE TABLE IF NOT EXISTS backtest_equity_curve (
    run_id TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    portfolio_value REAL NOT NULL,
    benchmark_value REAL NOT NULL,
    drawdown_pct REAL NOT NULL,
    PRIMARY KEY (run_id, trading_date),
    FOREIGN KEY (run_id) REFERENCES backtest_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_backtest_curve_run_date
ON backtest_equity_curve(run_id, trading_date ASC);

-- ====================================================================
-- Milestone B9.0: Compounding ML Feedback Ledger & Autonomous Evaluation
-- ====================================================================

-- 10. Econometric Forecast Realization & Outcome Ledger
CREATE TABLE IF NOT EXISTS forecast_audit_ledger (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    prediction_date TEXT NOT NULL,
    horizon_days INTEGER NOT NULL,
    target_evaluation_date TEXT NOT NULL,
    current_price REAL NOT NULL,
    expected_price REAL NOT NULL,
    lower_80 REAL NOT NULL,
    upper_80 REAL NOT NULL,
    lower_95 REAL NOT NULL,
    upper_95 REAL NOT NULL,
    realized_price REAL DEFAULT NULL,
    within_80_ci INTEGER DEFAULT NULL,
    within_95_ci INTEGER DEFAULT NULL,
    forecast_error_pct REAL DEFAULT NULL,
    evaluated_at TEXT DEFAULT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_forecast_audit_sym_target
ON forecast_audit_ledger(symbol, target_evaluation_date);

CREATE INDEX IF NOT EXISTS idx_forecast_audit_pending
ON forecast_audit_ledger(target_evaluation_date)
WHERE evaluated_at IS NULL;

-- 11. News & Catalyst Realization Ledger
CREATE TABLE IF NOT EXISTS catalyst_audit_ledger (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    article_id TEXT NOT NULL,
    published_at TEXT NOT NULL,
    direction TEXT NOT NULL,
    price_at_publish REAL NOT NULL,
    price_5d_after REAL DEFAULT NULL,
    realized_return_5d REAL DEFAULT NULL,
    is_direction_accurate INTEGER DEFAULT NULL,
    evaluated_at TEXT DEFAULT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_catalyst_audit_sym
ON catalyst_audit_ledger(symbol, published_at);

CREATE INDEX IF NOT EXISTS idx_catalyst_audit_pending
ON catalyst_audit_ledger(evaluated_at)
WHERE evaluated_at IS NULL;
