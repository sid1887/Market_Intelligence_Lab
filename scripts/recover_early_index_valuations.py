#!/usr/bin/env python3
"""
Backfills the 5 missing early dates (2024-10-21 to 2024-10-25) for all 9 Nifty indices
in index_daily using official historical records from get_index_history.
Updates raw JSON archives in data/raw/index_valuations/ and updates SQLite index_daily.
"""
import os
import sys
import json
import datetime
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.storage.database import DatabaseManager
from src.client.nse_mcp_client import NseMcpClient

INDEX_MAPPING = {
    "NIFTY 50": "Nifty 50",
    "NIFTY BANK": "Nifty Bank",
    "NIFTY IT": "Nifty IT",
    "NIFTY FINANCIAL SERVICES": "Nifty Financial Services",
    "NIFTY AUTO": "Nifty Auto",
    "NIFTY FMCG": "Nifty FMCG",
    "NIFTY METAL": "Nifty Metal",
    "NIFTY PHARMA": "Nifty Pharma",
    "NIFTY REALTY": "Nifty Realty"
}

TARGET_DATES = {"2024-10-21", "2024-10-22", "2024-10-23", "2024-10-24", "2024-10-25"}

def recover_early_index_valuations():
    print("==================================================================")
    print("Milestone B4: Recovering Missing Index Valuations (2024-10-21 to 2024-10-25)")
    print("==================================================================")
    db = DatabaseManager("data/market_lab.db")
    client = NseMcpClient()
    raw_dir = "data/raw/index_valuations"
    os.makedirs(raw_dir, exist_ok=True)

    total_rows_updated = 0

    for db_index_name, mcp_index_name in INDEX_MAPPING.items():
        print(f"\n>>> Querying {db_index_name} (MCP: '{mcp_index_name}')...")
        res, _ = client.call_tool("get_index_history", {
            "indexName": mcp_index_name,
            "months": 1,
            "endDate": "2024-10-25"
        })
        
        data = res.get("data", [])
        recovered = [r for r in data if r.get("date") in TARGET_DATES]
        print(f"    Found {len(recovered)} matching records for {db_index_name}")

        # 1. Update raw JSON archive
        safe_name = db_index_name.replace(" ", "_")
        raw_path = os.path.join(raw_dir, f"{safe_name}_valuation_history.json")
        if os.path.exists(raw_path):
            with open(raw_path, "r", encoding="utf-8") as f:
                archived = json.load(f)
            archived["chunks"].append({
                "from_date": "2024-10-21",
                "to_date": "2024-10-25",
                "trading_days": len(recovered),
                "data": recovered,
                "note": "Recovered early benchmark sessions"
            })
            archived["total_records"] = archived.get("total_records", 0) + len(recovered)
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump(archived, f, indent=2)
            print(f"    Updated raw archive: {raw_path}")

        # 2. Update database index_daily
        with db.get_connection() as conn:
            cur = conn.cursor()
            for r in recovered:
                date = r.get("date")
                pe = r.get("pe")
                pb = r.get("pb")
                div_yield = r.get("divYield")
                
                # Update both PRI and TRI rows for this date
                cur.execute("""
                    UPDATE index_daily
                    SET pe_ratio = ?,
                        pb_ratio = ?,
                        div_yield = ?,
                        source = 'nse_mcp_get_index_history',
                        retrieval_timestamp = ?
                    WHERE index_name = ? AND trading_date = ?
                """, (pe, pb, div_yield, datetime.datetime.now(datetime.timezone.utc).isoformat(), db_index_name, date))
                total_rows_updated += cur.rowcount
            conn.commit()

    print(f"\n==================================================================")
    print(f"Recovery Complete. Total index_daily rows updated: {total_rows_updated}")
    print("==================================================================")

    # Verification
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                COUNT(*) as total_rows,
                COUNT(pe_ratio) as non_null_pe,
                COUNT(pb_ratio) as non_null_pb,
                COUNT(div_yield) as non_null_div_yield,
                SUM(CASE WHEN pe_ratio IS NULL THEN 1 ELSE 0 END) as null_pe
            FROM index_daily
        """)
        totals = cur.fetchone()
        print(f"Final index_daily totals:")
        print(f"  Total rows: {totals[0]}")
        print(f"  Non-null PE: {totals[1]}")
        print(f"  Non-null PB: {totals[2]}")
        print(f"  Non-null DivYield: {totals[3]}")
        print(f"  Remaining NULL rows: {totals[4]}")

        cur.execute("""
            SELECT DISTINCT trading_date
            FROM index_daily
            WHERE pe_ratio IS NULL
            ORDER BY trading_date
        """)
        null_dates = [r[0] for r in cur.fetchall()]
        print(f"Remaining NULL dates ({len(null_dates)} dates): {null_dates}")

if __name__ == "__main__":
    recover_early_index_valuations()
