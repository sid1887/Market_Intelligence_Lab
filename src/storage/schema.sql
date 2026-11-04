-- Market Intelligence Lab Schema (Phase 1)
-- Strict handling of nullable fields: missing delivery quantity is stored as NULL, not 0.

CREATE TABLE IF NOT EXISTS ohlcv_daily (
    symbol TEXT NOT NULL,
    trading_date TEXT NOT NULL,
    series TEXT NOT NULL DEFAULT 'EQ',
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    ltp REAL DEFAULT NULL,
    prev_close REAL DEFAULT NULL,
    volume INTEGER NOT NULL,
    turnover REAL DEFAULT NULL,
    delivery_qty INTEGER DEFAULT NULL,
    source TEXT NOT NULL,                -- e.g. 'nse_mcp', 'cm_udiff'
    retrieval_timestamp TEXT NOT NULL,   -- ISO 8601 UTC
    PRIMARY KEY (symbol, trading_date, series),
    CHECK (high >= low),
    CHECK (open >= 0 AND high >= 0 AND low >= 0 AND close >= 0),
    CHECK (volume >= 0)
);

CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_date ON ohlcv_daily(symbol, trading_date);

CREATE TABLE IF NOT EXISTS corporate_actions (
    id TEXT UNIQUE,
    symbol TEXT NOT NULL,
    action_type TEXT NOT NULL,           -- DIVIDEND, SPLIT, BONUS, RIGHTS, OTHER
    ex_date TEXT NOT NULL,               -- YYYY-MM-DD
    record_date TEXT DEFAULT NULL,
    announcement_date TEXT DEFAULT NULL,
    effective_date TEXT DEFAULT NULL,
    purpose TEXT NOT NULL,
    adjustment_factor REAL DEFAULT 1.0,
    adjustment_ratio REAL DEFAULT 1.0,
    face_value REAL DEFAULT NULL,
    source TEXT NOT NULL,
    retrieval_timestamp TEXT NOT NULL,
    PRIMARY KEY (symbol, action_type, ex_date, purpose)
);

CREATE INDEX IF NOT EXISTS idx_ca_symbol_exdate ON corporate_actions(symbol, ex_date);
CREATE INDEX IF NOT EXISTS idx_ca_action_type ON corporate_actions(action_type);

CREATE TABLE IF NOT EXISTS ingestion_audit_log (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    symbol TEXT NOT NULL,
    date_range_start TEXT,
    date_range_end TEXT,
    records_retrieved INTEGER NOT NULL,
    records_accepted INTEGER NOT NULL,
    records_rejected INTEGER NOT NULL,
    validation_summary TEXT NOT NULL,    -- JSON string with details of checks and rejections
    raw_payload_path TEXT NOT NULL,
    status TEXT NOT NULL,                -- SUCCESS, PARTIAL, FAILED
    created_at TEXT NOT NULL             -- ISO 8601 UTC
);

-- ====================================================================
-- Milestone B4: Normalized Company Financial Statements & Point-in-Time Fundamentals
-- ====================================================================

CREATE TABLE IF NOT EXISTS company_financial_statements (
    statement_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    period_type TEXT NOT NULL,               -- 'QUARTERLY', 'ANNUAL', 'HALF_YEAR'
    period_nature TEXT NOT NULL,             -- 'DISCRETE_QUARTER', 'CUMULATIVE_YTD', 'ANNUAL'
    fiscal_year INTEGER NOT NULL,            -- e.g. 2026, 2027
    fiscal_quarter INTEGER DEFAULT NULL,     -- 1, 2, 3, 4 (NULL for annual)
    period_start_date TEXT NOT NULL,         -- YYYY-MM-DD
    period_end_date TEXT NOT NULL,           -- YYYY-MM-DD
    
    -- Publication-Time Provenance & Point-in-Time Eligibility
    publication_date TEXT DEFAULT NULL,      -- YYYY-MM-DD (NULL if genuinely untimed)
    broadcast_timestamp TEXT DEFAULT NULL,   -- ISO 8601
    effective_session_date TEXT DEFAULT NULL,-- YYYY-MM-DD (first session market could react)
    source_timestamp_basis TEXT NOT NULL,    -- 'EXACT_EXCHANGE_TIMESTAMP', 'ANNOUNCEMENT_DATE_VERIFIED', 'UNKNOWN_UNTIMED'
    is_pit_eligible INTEGER NOT NULL DEFAULT 1, -- 1=Safe for PIT backtesting, 0=Excluded
    
    -- Reporting Scope & Versioning
    reporting_basis TEXT NOT NULL,           -- 'CONSOLIDATED', 'STANDALONE'
    statement_version INTEGER NOT NULL DEFAULT 1, -- 1=original reported, 2=restated
    audit_status TEXT NOT NULL DEFAULT 'UNAUDITED', -- 'AUDITED', 'UNAUDITED', 'LIMITED_REVIEW'
    currency TEXT NOT NULL DEFAULT 'INR',
    unit TEXT NOT NULL DEFAULT 'CRORE',      -- All financial figures in INR Crores
    
    -- Income Statement Flow Items
    revenue_operations REAL DEFAULT NULL,
    other_income REAL DEFAULT NULL,
    total_revenue REAL DEFAULT NULL,
    operating_expenses REAL DEFAULT NULL,
    ebitda REAL DEFAULT NULL,
    ebit REAL DEFAULT NULL,
    finance_costs REAL DEFAULT NULL,
    depreciation_amortization REAL DEFAULT NULL,
    profit_before_tax REAL DEFAULT NULL,
    tax_expense REAL DEFAULT NULL,
    net_profit REAL DEFAULT NULL,            -- Profit After Tax (PAT)
    basic_eps REAL DEFAULT NULL,
    diluted_eps REAL DEFAULT NULL,
    
    -- Balance Sheet Snapshot Items
    total_equity REAL DEFAULT NULL,          -- Shareholders' Funds / Net Worth
    total_debt REAL DEFAULT NULL,            -- Short-term + Long-term borrowings
    cash_and_equivalents REAL DEFAULT NULL,
    total_assets REAL DEFAULT NULL,
    shares_outstanding REAL DEFAULT NULL,    -- Absolute number of equity shares (e.g. 4150000000 for 415 Cr shares)
    
    -- Provenance & Governance
    source TEXT NOT NULL,
    source_url TEXT DEFAULT NULL,
    retrieval_timestamp TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'PENDING_VERIFICATION',
    is_restated INTEGER NOT NULL DEFAULT 0,
    restatement_reason TEXT DEFAULT NULL,
    
    FOREIGN KEY (symbol) REFERENCES securities_master(symbol),
    UNIQUE (symbol, period_end_date, period_type, period_nature, reporting_basis, statement_version)
);

CREATE INDEX IF NOT EXISTS idx_cfs_as_of 
ON company_financial_statements(symbol, effective_session_date, publication_date, is_pit_eligible);

CREATE INDEX IF NOT EXISTS idx_cfs_period 
ON company_financial_statements(symbol, period_end_date, reporting_basis, period_nature);

CREATE TABLE IF NOT EXISTS fundamental_factors_daily (
    symbol TEXT NOT NULL,
    trading_date TEXT NOT NULL,              -- As-of valuation session
    close_price REAL NOT NULL,               -- Unadjusted close on trading_date
    shares_outstanding REAL DEFAULT NULL,    -- Absolute number of equity shares
    market_cap_inr_crore REAL DEFAULT NULL,  -- (close_price * shares_outstanding) / 10^7
    
    -- TTM Fundamentals
    ttm_revenue REAL DEFAULT NULL,
    ttm_ebitda REAL DEFAULT NULL,
    ttm_ebit REAL DEFAULT NULL,
    ttm_net_profit REAL DEFAULT NULL,
    ttm_eps_adjusted REAL DEFAULT NULL,      -- Share-basis adjusted TTM EPS
    latest_equity REAL DEFAULT NULL,         -- Most recently published Net Worth
    latest_debt REAL DEFAULT NULL,
    latest_cash REAL DEFAULT NULL,
    
    -- Valuation Multiples
    pe_ratio REAL DEFAULT NULL,              -- Market Cap / TTM Net Profit (NULL if Net Profit <= 0)
    pb_ratio REAL DEFAULT NULL,              -- Market Cap / Latest Equity (NULL if Equity <= 0)
    ps_ratio REAL DEFAULT NULL,              -- Market Cap / TTM Revenue
    ev_ebitda REAL DEFAULT NULL,             -- (Market Cap + Debt - Cash) / TTM EBITDA (NULL for Financials)
    dividend_yield_ttm REAL DEFAULT NULL,    -- Share-adjusted TTM Cash Dividends / Close Price
    
    -- Profitability & Balance Sheet Quality
    roe_pct REAL DEFAULT NULL,               -- TTM Net Profit / Latest Equity * 100
    roce_pct REAL DEFAULT NULL,              -- TTM EBIT / (Equity + Debt) * 100 (NULL for Financials)
    debt_to_equity REAL DEFAULT NULL,        -- Debt / Equity (NULL for Financials or Equity <= 0)
    operating_margin_ttm REAL DEFAULT NULL,  -- TTM EBIT / TTM Revenue * 100
    net_margin_ttm REAL DEFAULT NULL,        -- TTM Net Profit / TTM Revenue * 100
    
    -- Growth Factors
    revenue_growth_yoy REAL DEFAULT NULL,
    net_profit_growth_yoy REAL DEFAULT NULL,
    eps_growth_yoy REAL DEFAULT NULL,
    
    -- Sector-Relative Metrics
    sector TEXT NOT NULL,
    sector_pe_median REAL DEFAULT NULL,
    pe_vs_sector_spread REAL DEFAULT NULL,   -- Stock P/E - Sector P/E Median
    pe_percentile_sector REAL DEFAULT NULL,  -- 0.0 to 100.0 within sector
    valuation_decile_universe INTEGER DEFAULT NULL, -- 1 (cheapest) to 10 (most expensive)
    
    -- Governance, Provenance & Quality Flags
    statements_count_ttm INTEGER NOT NULL,   -- Number of quarterly statements in TTM (expect 4)
    data_quality_flag TEXT NOT NULL DEFAULT 'COMPLETE', -- 'COMPLETE', 'PARTIAL_TTM', 'NEGATIVE_EARNINGS', 'NEGATIVE_EQUITY'
    metric_applicability_flag TEXT NOT NULL DEFAULT 'STANDARD', -- 'STANDARD', 'FINANCIAL_SECTOR_ADJUSTED'
    latest_statement_id TEXT DEFAULT NULL,   -- Link to the most recent statement used
    calculated_at TEXT NOT NULL,
    
    PRIMARY KEY (symbol, trading_date),
    FOREIGN KEY (symbol) REFERENCES securities_master(symbol)
);

CREATE INDEX IF NOT EXISTS idx_ffd_date_sector 
ON fundamental_factors_daily(trading_date, sector);
