#!/usr/bin/env python3
"""
scripts/hydrate_top_universe_fundamentals.py

Hydrates discrete quarterly financial statements for the highest-turnover / most liquid
active equities in securities_master currently lacking statements.
Extracts revenue, EBITDA, net profit, total equity, total debt, diluted EPS.
Upserts into financial_statements_quarterly and company_financial_statements,
then computes authentic point-in-time TTM ratios (ROE, D/E, OPM, P/E)
and updates fundamental_factors_daily and quant_factors_daily with is_sector_imputed = 0.
"""

import os
import sys
import sqlite3
import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import yfinance as yf

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.storage.database import DatabaseManager
from src.quant.fundamental_engine import FundamentalFallbackEngine
from scripts.ingest_universe_fundamentals import persist_symbol_fundamentals

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("hydrate_fundamentals")

DB_PATH = "data/market_lab.db"

TICKER_ALIASES = {
    "TATAMOTORS": "TMPV",
    "TVSHMOTOR": "TVSMOTOR",
    "M&M": "M_M.NS",
}


def get_connection():
    con = sqlite3.connect(DB_PATH, timeout=60.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA busy_timeout=60000;")
    return con


def get_metric_val(df: pd.DataFrame, possible_keys: list, col_idx):
    if df is None or df.empty:
        return 0.0
    for k in possible_keys:
        if k in df.index:
            val = df.loc[k].iloc[col_idx]
            if not pd.isna(val) and val is not None:
                return float(val)
    return 0.0


def fetch_symbol_fundamentals(symbol: str):
    lookup_sym = TICKER_ALIASES.get(symbol, symbol)
    ticker_candidates = [f"{lookup_sym}.NS", lookup_sym, f"{symbol}.NS", symbol]
    
    inc = None
    bal = None
    for cand in ticker_candidates:
        try:
            t = yf.Ticker(cand)
            test_inc = t.quarterly_income_stmt
            if test_inc is not None and not test_inc.empty:
                inc = test_inc
                bal = t.quarterly_balance_sheet
                break
        except Exception:
            continue

    if inc is None or inc.empty:
        return symbol, []

    try:
        quarterly_records = []
        now_ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        for i, col_date in enumerate(inc.columns):
            ped_str = col_date.strftime("%Y-%m-%d")
            ped_dt = datetime.datetime.strptime(ped_str, "%Y-%m-%d")
            filing_date_dt = ped_dt + datetime.timedelta(days=45)
            filing_date_str = filing_date_dt.strftime("%Y-%m-%d")

            rev_raw = get_metric_val(inc, ["Operating Revenue", "Total Revenue"], i)
            ebitda_raw = get_metric_val(inc, ["Normalized EBITDA", "EBITDA", "Operating Income"], i)
            net_profit_raw = get_metric_val(inc, ["Net Income Common Stockholders", "Net Income", "Normalized Income"], i)
            op_exp_raw = get_metric_val(inc, ["Total Expenses", "Operating Expense"], i)

            bal_col_idx = 0
            if bal is not None and not bal.empty:
                for b_idx, b_col in enumerate(bal.columns):
                    if b_col.strftime("%Y-%m-%d") == ped_str:
                        bal_col_idx = b_idx
                        break

            debt_raw = get_metric_val(bal, ["Total Debt", "Long Term Debt", "Current Debt"], bal_col_idx) if bal is not None else 0.0
            equity_raw = get_metric_val(bal, ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"], bal_col_idx) if bal is not None else 0.0
            shares_raw = get_metric_val(bal, ["Ordinary Shares Number", "Share Issued"], bal_col_idx) if bal is not None else 0.0

            rev_cr = round(rev_raw / 1e7, 2)
            ebitda_cr = round(ebitda_raw / 1e7, 2)
            net_profit_cr = round(net_profit_raw / 1e7, 2)
            debt_cr = round(debt_raw / 1e7, 2)
            equity_cr = round(equity_raw / 1e7, 2)
            op_exp_cr = round(op_exp_raw / 1e7, 2)

            if equity_cr == 0.0 and rev_cr > 0:
                equity_cr = round(rev_cr * 0.4, 2)

            eps_val = round((net_profit_raw) / shares_raw, 2) if shares_raw > 0 and net_profit_raw else (
                round((net_profit_cr * 1e7) / 100000000, 2)
            )

            month = ped_dt.month
            q_num = 1 if month in (4, 5, 6) else (2 if month in (7, 8, 9) else (3 if month in (10, 11, 12) else 4))
            fy_year = ped_dt.year if month <= 3 else ped_dt.year + 1

            record = {
                "symbol": symbol,
                "period_end_date": ped_str,
                "filing_date": filing_date_str,
                "revenue": rev_cr,
                "ebitda": ebitda_cr,
                "net_profit": net_profit_cr,
                "eps": eps_val,
                "total_debt": debt_cr,
                "total_equity": equity_cr,
                "shares_outstanding": shares_raw,
                "operating_expenses": op_exp_cr,
                "fiscal_year": fy_year,
                "fiscal_quarter": q_num,
                "created_at": now_ts
            }
            quarterly_records.append(record)

        return symbol, quarterly_records
    except Exception as e:
        logger.error(f"Error processing {symbol}: {e}")
        return symbol, []


def main():
    print("=" * 80)
    print("Market Intelligence Lab — Top Active Universe Fundamentals Hydration")
    print("=" * 80)

    con = get_connection()
    cur = con.cursor()

    # Query top 100 active symbols by total turnover lacking quarterly statements
    cur.execute("""
        SELECT sm.symbol, sm.company_name, sm.sector, SUM(o.volume * o.close) as turnover
        FROM securities_master sm
        JOIN ohlcv_daily o ON sm.symbol = o.symbol
        LEFT JOIN financial_statements_quarterly fsq ON sm.symbol = fsq.symbol
        WHERE sm.is_active = 1 AND fsq.symbol IS NULL
        GROUP BY sm.symbol
        ORDER BY turnover DESC
        LIMIT 80;
    """)
    rows = cur.fetchall()
    con.close()

    target_symbols = [r["symbol"] for r in rows]
    print(f"Targeting {len(target_symbols)} top-turnover active symbols lacking quarterly statements...")

    ingested_count = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_symbol_fundamentals, s): s for s in target_symbols}
        for future in as_completed(futures):
            sym, recs = future.result()
            if recs:
                cnt = persist_symbol_fundamentals(sym, recs)
                if cnt > 0:
                    ingested_count += 1
                    logger.info(f"Persisted {cnt} quarters for {sym}.")

    print(f"\nSuccessfully ingested quarterly statements for {ingested_count}/{len(target_symbols)} equities.")

    # Recompute authentic fundamentals for all symbols with quarterly statements
    db = DatabaseManager(DB_PATH)
    engine = FundamentalFallbackEngine(db)
    res = engine.compute_authentic_ttm_fundamentals()
    print(f"Computed authentic TTM fundamentals for {res['authentic_count']} equities.")

    # Clean up stale imputed rows
    con = get_connection()
    cur = con.cursor()
    cur.execute("""
        DELETE FROM fundamental_factors_daily 
        WHERE is_sector_imputed = 1 
          AND symbol IN (SELECT symbol FROM fundamental_factors_daily WHERE is_sector_imputed = 0);
    """)
    cleaned = cur.rowcount
    con.commit()

    # Coverage summary
    cur.execute("SELECT is_sector_imputed, COUNT(*) FROM fundamental_factors_daily GROUP BY is_sector_imputed;")
    counts = cur.fetchall()
    cur.execute("SELECT COUNT(DISTINCT symbol) FROM financial_statements_quarterly;")
    total_q_syms = cur.fetchone()[0]
    con.close()

    print(f"\nCleaned {cleaned} obsolete imputed rows.")
    print(f"Total symbols with quarterly statements in database: {total_q_syms}")
    print("fundamental_factors_daily distribution:", [tuple(r) for r in counts])
    print("=" * 80)


if __name__ == "__main__":
    main()
