#!/usr/bin/env python3
"""
Seed NIFTY 500 constituents into securities_master.
Milestone B9.0: Data Bedrock Expansion.

Strict benchmark isolation:
- Existing NIFTY 50 constituents retain is_nifty50 = 1, is_active = 1.
- All other constituents are seeded with is_nifty50 = 0, is_active = 0 (or retain existing active status if in watchlist).
- index_membership_history is completely untouched.
"""

import os
import csv
import sys
import datetime
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.database import DatabaseManager

def seed_nifty500(csv_path: str = "data/universe/ind_nifty500list.csv"):
    db = DatabaseManager()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Universe CSV file not found at {csv_path}")
        
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        records = list(reader)
        
    print(f"Loaded {len(records)} records from {csv_path}")
    
    with db.get_connection() as conn:
        # Check current existing symbols and ISINs
        cur = conn.execute("SELECT symbol, isin, is_nifty50, is_active FROM securities_master")
        all_sec = [dict(r) for r in cur.fetchall()]
        existing_by_symbol = {r["symbol"].upper(): r for r in all_sec}
        existing_by_isin = {r["isin"]: r for r in all_sec if r["isin"]}
        
        inserted_count = 0
        updated_count = 0
        
        for row in records:
            symbol = row.get("Symbol", "").strip().upper()
            if not symbol:
                continue
                
            company_name = row.get("Company Name", "").strip()
            industry = row.get("Industry", "").strip()
            isin = row.get("ISIN Code", "").strip()
            
            matched_sym = None
            if symbol in existing_by_symbol:
                matched_sym = symbol
            elif isin and isin in existing_by_isin:
                matched_sym = existing_by_isin[isin]["symbol"]
                print(f"Mapped {symbol} to existing symbol {matched_sym} via ISIN {isin}")
            
            if matched_sym:
                # Retain existing is_nifty50 and is_active to ensure benchmark isolation
                updated_count += 1
                conn.execute(
                    """
                    UPDATE securities_master 
                    SET company_name = COALESCE(NULLIF(company_name, ''), :company_name),
                        industry = COALESCE(NULLIF(industry, ''), :industry),
                        sector = COALESCE(NULLIF(sector, ''), :industry),
                        macro_sector = COALESCE(NULLIF(macro_sector, ''), :industry),
                        isin = COALESCE(NULLIF(isin, ''), :isin),
                        updated_at = :updated_at
                    WHERE symbol = :symbol;
                    """,
                    {
                        "symbol": matched_sym,
                        "company_name": company_name,
                        "industry": industry,
                        "isin": isin,
                        "updated_at": now_iso
                    }
                )
            else:
                # Insert as inactive constituent with is_nifty50 = 0
                conn.execute(
                    """
                    INSERT INTO securities_master (
                        symbol, company_name, isin, industry, sector, macro_sector,
                        listing_date, is_active, updated_at, is_nifty50
                    ) VALUES (
                        :symbol, :company_name, :isin, :industry, :industry, :industry,
                        NULL, 0, :updated_at, 0
                    );
                    """,
                    {
                        "symbol": symbol,
                        "company_name": company_name,
                        "isin": isin,
                        "industry": industry,
                        "updated_at": now_iso
                    }
                )
                existing_by_symbol[symbol] = {"symbol": symbol, "isin": isin, "is_nifty50": 0, "is_active": 0}
                if isin:
                    existing_by_isin[isin] = existing_by_symbol[symbol]
                inserted_count += 1
                
        # Verification counts
        cur = conn.execute(
            """
            SELECT 
                COUNT(*) as total_sec,
                SUM(is_nifty50) as total_nifty50,
                SUM(is_active) as total_active
            FROM securities_master;
            """
        )
        res = dict(cur.fetchone())
        
        # Verify index_membership_history remains intact
        cur_idx = conn.execute("SELECT COUNT(*) as cnt FROM index_membership_history")
        idx_count = cur_idx.fetchone()["cnt"]
        
    print("\n--- NIFTY 500 Universe Seeding Complete ---")
    print(f"Inserted: {inserted_count} new constituents (is_nifty50=0, is_active=0)")
    print(f"Updated/Retained: {updated_count} existing constituents")
    print(f"Total securities in securities_master: {res['total_sec']}")
    print(f"Total NIFTY 50 securities: {res['total_nifty50']} (Preserved)")
    print(f"Total Active securities: {res['total_active']} (Preserved)")
    print(f"Index membership history records: {idx_count} (Untouched)")

if __name__ == "__main__":
    seed_nifty500()
