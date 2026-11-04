#!/usr/bin/env python3
"""
Backfills official historical P/E, P/B, and dividend-yield observations for the 9 Nifty indices
in index_daily using the official NSE Model Context Protocol (MCP) server endpoint.

Preserves exact source values, archives raw JSON payloads in data/raw/index_valuations/,
matches records by index identity and trading date, and records audit metrics.
"""
import os
import sys
import json
import time
import datetime
from typing import Dict, Any, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.storage.database import DatabaseManager
from src.client.nse_mcp_client import NseMcpClient
from src.client.fundamentals_client import FundamentalsClient

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

def backfill_index(
    db_index_name: str,
    mcp_index_name: str,
    client: NseMcpClient,
    fundamentals_client: FundamentalsClient,
    raw_dir: str
) -> Dict[str, Any]:
    print(f"\n>>> Processing Index: {db_index_name} (MCP query: '{mcp_index_name}')")

    all_records: List[Dict[str, Any]] = []
    chunks_raw: List[Dict[str, Any]] = []

    # Chunk 1: latest 12 months up to 2026-10-23
    current_end_date = "2026-10-23"
    for chunk_num in range(1, 3):
        print(f"  Fetching Chunk {chunk_num} (endDate: {current_end_date}, months: 12)...")
        try:
            res, raw = client.call_tool("get_index_history", {
                "indexName": mcp_index_name,
                "months": 12,
                "endDate": current_end_date
            })
            chunks_raw.append(res)
            data = res.get("data", [])
            print(f"    Received {len(data)} trading days in chunk {chunk_num}.")
            all_records.extend(data)
            next_end = res.get("next_end_date")
            if not next_end or next_end == current_end_date:
                break
            current_end_date = next_end
            time.sleep(1.0)
        except Exception as e:
            print(f"    Error fetching chunk {chunk_num}: {e}")
            break

    # Archive raw payload
    safe_name = db_index_name.replace(" ", "_")
    raw_path = os.path.join(raw_dir, f"{safe_name}_valuation_history.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump({
            "index_name": db_index_name,
            "mcp_index_name": mcp_index_name,
            "retrieved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_records": len(all_records),
            "chunks": chunks_raw
        }, f, indent=2)
    print(f"  Archived {len(all_records)} raw records to {raw_path}")

    # Reconcile and update index_daily
    # Deduplicate records by date
    records_by_date = {}
    for r in all_records:
        d = r.get("date")
        if d:
            records_by_date[d] = r

    update_payloads = []
    for d, r in records_by_date.items():
        pe = r.get("pe")
        pb = r.get("pb")
        dy = r.get("divYield")
        update_payloads.append({
            "index_name": db_index_name,
            "trading_date": d,
            "pe_ratio": float(pe) if pe is not None else None,
            "pb_ratio": float(pb) if pb is not None else None,
            "div_yield": float(dy) if dy is not None else None
        })

    updated_rows = fundamentals_client.update_index_valuations(update_payloads)
    print(f"  Updated {updated_rows} rows in index_daily for {db_index_name}.")

    return {
        "index_name": db_index_name,
        "mcp_records_received": len(all_records),
        "distinct_dates": len(records_by_date),
        "db_rows_updated": updated_rows,
        "archive_file": raw_path
    }

def main():
    db = DatabaseManager("data/market_lab.db")
    client = NseMcpClient()
    fundamentals_client = FundamentalsClient(db)

    raw_dir = "data/raw/index_valuations"
    os.makedirs(raw_dir, exist_ok=True)

    print("=" * 80)
    print("MILESTONE B4.2: OFFICIAL HISTORICAL INDEX VALUATION BACKFILL")
    print(f"Timestamp: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print("=" * 80)

    summary = []
    for db_name, mcp_name in INDEX_MAPPING.items():
        res = backfill_index(db_name, mcp_name, client, fundamentals_client, raw_dir)
        summary.append(res)
        time.sleep(1.0)

    print("\n" + "=" * 80)
    print("BACKFILL AUDIT SUMMARY:")
    print("=" * 80)
    for s in summary:
        print(f"Index: {s['index_name']:<25} | Received: {s['mcp_records_received']} | Distinct Dates: {s['distinct_dates']} | Rows Updated: {s['db_rows_updated']}")

    # Verify coverage in database
    print("\n" + "=" * 80)
    print("DATABASE COVERAGE VERIFICATION (index_daily):")
    print("=" * 80)
    with db.get_connection() as conn:
        cursor = conn.execute("""
            SELECT index_name,
                   COUNT(*) as total_rows,
                   MIN(trading_date) as start_date,
                   MAX(trading_date) as end_date,
                   COUNT(pe_ratio) as non_null_pe,
                   COUNT(pb_ratio) as non_null_pb,
                   COUNT(div_yield) as non_null_div_yield
            FROM index_daily
            GROUP BY index_name
            ORDER BY index_name;
        """)
        for r in cursor.fetchall():
            print(f"{r['index_name']:<25} | Total: {r['total_rows']} | PE: {r['non_null_pe']} | PB: {r['non_null_pb']} | DivYield: {r['non_null_div_yield']}")

if __name__ == "__main__":
    main()
