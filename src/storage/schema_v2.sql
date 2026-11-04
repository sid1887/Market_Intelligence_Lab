-- ====================================================================
-- Market Intelligence Lab: Phase 2 Additive Schema Migration (v2.1)
-- Safe, additive migration preserving all Phase 1 tables and data.
-- ====================================================================

-- 1. Index Constituents & Point-in-Time Membership History
CREATE TABLE IF NOT EXISTS index_membership_history (
    symbol TEXT NOT NULL,
    index_name TEXT NOT NULL,                -- e.g. 'NIFTY 50', 'NIFTY BANK', 'NIFTY IT'
    valid_from TEXT NOT NULL,                -- YYYY-MM-DD (inclusive)
    valid_to TEXT DEFAULT NULL,              -- YYYY-MM-DD (exclusive, NULL = current)
    is_verified_historical INTEGER NOT NULL DEFAULT 1, -- 1=Circular verified, 0=proxy
    source TEXT NOT NULL,                    -- e.g. 'nifty_circular_20240930', 'ind_nifty50list'
    retrieved_at TEXT NOT NULL,              -- ISO 8601 UTC
    PRIMARY KEY (symbol, index_name, valid_from)
);

CREATE INDEX IF NOT EXISTS idx_mem_hist_lookup 
ON index_membership_history(index_name, valid_from, valid_to);

-- 2. Enhanced Securities Master
CREATE TABLE IF NOT EXISTS securities_master (
    symbol TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    isin TEXT NOT NULL UNIQUE,
    industry TEXT NOT NULL,
    sector TEXT NOT NULL,
    macro_sector TEXT NOT NULL,
    listing_date TEXT DEFAULT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    is_nifty50 INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

-- 3. Benchmark Index Daily History (PRI and TRI)
-- Note: open, high, low are nullable because TRI publishes index values only.
CREATE TABLE IF NOT EXISTS index_daily (
    index_name TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    index_type TEXT NOT NULL,                -- 'PRI' (Price Return) or 'TRI' (Total Return)
    open REAL DEFAULT NULL,                  -- NULL for TRI series
    high REAL DEFAULT NULL,                  -- NULL for TRI series
    low REAL DEFAULT NULL,                   -- NULL for TRI series
    close REAL NOT NULL,                     -- Official index value
    volume INTEGER DEFAULT NULL,
    pe_ratio REAL DEFAULT NULL,
    pb_ratio REAL DEFAULT NULL,
    div_yield REAL DEFAULT NULL,
    source TEXT NOT NULL,                    -- 'nse_mcp', 'nifty_indices_archive'
    retrieval_timestamp TEXT NOT NULL,
    PRIMARY KEY (index_name, trading_date, index_type),
    CHECK (index_type IN ('PRI', 'TRI'))
);

CREATE INDEX IF NOT EXISTS idx_index_daily_date 
ON index_daily(index_name, trading_date);

-- 4. Corporate Disclosures & Material Announcements
CREATE TABLE IF NOT EXISTS corporate_disclosures (
    id TEXT UNIQUE,
    disclosure_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    broadcast_timestamp TEXT NOT NULL,       -- ISO 8601 IST
    effective_session_date TEXT NOT NULL,    -- Aligned t=0 trading session YYYY-MM-DD
    category TEXT NOT NULL,                  -- 'EARNINGS', 'MANAGEMENT', 'M&A', 'DIVIDEND', 'ORDERS', 'OTHER'
    subject TEXT NOT NULL,
    details_summary TEXT,
    source_url TEXT,
    retrieval_timestamp TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'PENDING_VERIFICATION', -- 'VERIFIED', 'PENDING_VERIFICATION', 'SOURCE_UNVERIFIED'
    audit_status TEXT DEFAULT NULL,          -- 'AUDITED', 'UNAUDITED'
    dividend_declared REAL DEFAULT NULL,     -- Amount per share in INR
    operating_margin_pct REAL DEFAULT NULL,  -- Operating margin percentage
    revenue_inr_crore REAL DEFAULT NULL,     -- Reported revenue in INR Crores
    revenue_growth_yoy_cc REAL DEFAULT NULL, -- Constant-currency YoY growth percentage
    revenue_growth_qoq_cc REAL DEFAULT NULL, -- Constant-currency QoQ growth percentage
    revenue_growth_yoy_reported REAL DEFAULT NULL, -- Reported INR YoY growth percentage
    source_timestamp_basis TEXT DEFAULT NULL -- 'exchange_submission_metadata', 'document_date_inferred'
);

CREATE INDEX IF NOT EXISTS idx_disc_symbol_session 
ON corporate_disclosures(symbol, effective_session_date);

-- 5. Calculated Quantitative Daily Factors & Anomalies
-- Note: Rolling factors are nullable to accommodate initial warm-up periods.
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
    PRIMARY KEY (symbol, trading_date)
);

CREATE INDEX IF NOT EXISTS idx_factors_date 
ON quant_factors_daily(trading_date);

-- 6. Event Study Results Cache
CREATE TABLE IF NOT EXISTS event_study_results (
    study_id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    disclosure_id TEXT NOT NULL,
    event_date TEXT NOT NULL,
    estimation_window_start TEXT NOT NULL,
    estimation_window_end TEXT NOT NULL,
    model_alpha REAL NOT NULL,
    model_beta REAL NOT NULL,
    model_r2 REAL NOT NULL,
    ar_t0 REAL NOT NULL,
    car_minus1_plus1 REAL NOT NULL,
    car_0_plus2 REAL NOT NULL,
    t_stat REAL NOT NULL,
    p_value REAL NOT NULL,
    explanatory_hypothesis TEXT NOT NULL,
    calculated_at TEXT NOT NULL,
    FOREIGN KEY (disclosure_id) REFERENCES corporate_disclosures(disclosure_id)
);
