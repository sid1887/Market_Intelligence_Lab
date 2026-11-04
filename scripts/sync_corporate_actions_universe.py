"""
Milestone B3.2 — Corporate Actions Universe Synchronization Script

Fetches, validates, and ingests official corporate actions (dividends, splits, bonuses, rights)
across all 50 active constituents in securities_master from the official NSE MCP server.
Enforces deduplication on natural key (symbol, action_type, ex_date), validates adjustment factors,
retains raw payloads and audit logs with exact retrieved/accepted/rejected counts.
"""

import os
import sys
import json
import time
import argparse
import datetime
from typing import List, Dict, Any, Optional

from src.storage.database import DatabaseManager
from src.client.nse_mcp_client import NseMcpClient
from src.client.validator import RecordValidator

def parse_args():
    parser = argparse.ArgumentParser(description="Synchronize corporate actions for the active universe.")
    parser.add_argument("--db-path", default="data/market_lab.db", help="Path to SQLite database")
    parser.add_argument("--from-date", default="2024-10-21", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", default="2026-10-23", help="End date (YYYY-MM-DD)")
    parser.add_argument("--symbol", default=None, help="Optional single symbol to synchronize")
    parser.add_argument("--raw-dir", default="data/raw/corporate_actions", help="Directory for raw payloads")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout per MCP tool call in seconds")
    return parser.parse_args()

def sync_corporate_actions_for_symbol(
    client: NseMcpClient,
    validator: RecordValidator,
    db: DatabaseManager,
    symbol: str,
    from_date: str,
    to_date: str,
    source: str = "nse_mcp",
    target_symbol: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetches corporate actions for a single symbol, validates records,
    persists accepted records to the database, and records an ingestion audit log.
    """
    target_sym = target_symbol or symbol
    validator.seen_ca_keys.clear()

    # Retry up to 3 times on network glitch
    max_retries = 3
    raw_actions = []
    raw_resp = {}
    last_err = None

    for attempt in range(max_retries):
        try:
            raw_actions, backup_path = client.fetch_corporate_actions(
                symbol=symbol,
                from_date=from_date,
                to_date=to_date
            )
            last_err = None
            break
        except Exception as e:
            last_err = str(e)
            time.sleep(0.5 * (attempt + 1))

    if last_err is not None:
        # Record failed audit log
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        audit_id = db.record_audit_log(
            source=source,
            endpoint="get_corporate_actions",
            symbol=target_sym,
            date_range_start=from_date,
            date_range_end=to_date,
            records_retrieved=0,
            records_accepted=0,
            records_rejected=0,
            validation_summary={"error": last_err, "status": "FAILED"},
            raw_payload_path=os.path.join(client.raw_data_dir, f"{symbol}_ca_failed.json"),
            status="FAILED",
            created_at=now_iso
        )
        return {
            "symbol": target_sym,
            "status": "FAILED",
            "error": last_err,
            "retrieved": 0,
            "accepted": 0,
            "rejected": 0,
            "audit_id": audit_id
        }

    # Validate
    retrieval_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    accepted, rejected, summary = validator.validate_corporate_actions_batch(
        raw_actions=raw_actions,
        symbol=target_sym,
        source=source,
        retrieval_timestamp=retrieval_ts
    )

    # Persist accepted records
    upserted_count = db.upsert_corporate_actions(accepted)

    # Record audit log
    status_str = "SUCCESS" if len(rejected) == 0 else ("PARTIAL" if len(accepted) > 0 else "FAILED")
    audit_id = db.record_audit_log(
        source=source,
        endpoint="get_corporate_actions",
        symbol=target_sym,
        date_range_start=from_date,
        date_range_end=to_date,
        records_retrieved=len(raw_actions),
        records_accepted=len(accepted),
        records_rejected=len(rejected),
        validation_summary=summary,
        raw_payload_path=backup_path,
        status=status_str,
        created_at=retrieval_ts
    )

    return {
        "symbol": target_sym,
        "query_symbol": symbol,
        "status": status_str,
        "retrieved": len(raw_actions),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "upserted": upserted_count,
        "audit_id": audit_id,
        "backup_path": backup_path
    }

def main():
    args = parse_args()
    print("=" * 80)
    print("MILESTONE B3.2: CORPORATE ACTIONS UNIVERSE SYNCHRONIZATION")
    print(f"Database: {args.db_path}")
    print(f"Window:   {args.from_date} to {args.to_date}")
    print("=" * 80)

    db = DatabaseManager(args.db_path)
    db.init_schema()

    client = NseMcpClient(
        endpoint="https://mcp.nseindia.in/bhavcopy/cm/mcp",
        timeout_seconds=args.timeout,
        max_affinity_retries=6,
        max_reinit_attempts=3,
        raw_data_dir=args.raw_dir
    )
    validator = RecordValidator()

    # Discover target universe
    if args.symbol:
        symbols = [args.symbol.strip().upper()]
    else:
        with db.get_connection() as conn:
            cursor = conn.execute("SELECT symbol FROM securities_master WHERE is_active = 1 ORDER BY symbol;")
            symbols = [row[0] for row in cursor.fetchall()]

    print(f"Target Universe: {len(symbols)} symbols")

    # Establish MCP session
    try:
        session_id = client.initialize()
        print(f"Established NSE MCP Session: {session_id}")
    except Exception as e:
        print(f"Failed to initialize NSE MCP session: {e}")
        sys.exit(1)

    total_retrieved = 0
    total_accepted = 0
    total_rejected = 0
    symbols_with_actions = 0
    failed_symbols = []

    start_time = time.time()

    for idx, sym in enumerate(symbols, 1):
        print(f"[{idx:02d}/{len(symbols):02d}] Syncing {sym}...", end="", flush=True)

        res = sync_corporate_actions_for_symbol(
            client=client,
            validator=validator,
            db=db,
            symbol=sym,
            from_date=args.from_date,
            to_date=args.to_date,
            source="nse_mcp"
        )

        # Handle alias for ETERNAL (ZOMATO pre-2025-04-09)
        if sym == "ETERNAL":
            alias_res = sync_corporate_actions_for_symbol(
                client=client,
                validator=validator,
                db=db,
                symbol="ZOMATO",
                from_date=args.from_date,
                to_date="2025-04-08",
                source="nse_mcp_alias_zomato",
                target_symbol="ETERNAL"
            )
            res["retrieved"] += alias_res["retrieved"]
            res["accepted"] += alias_res["accepted"]
            res["rejected"] += alias_res["rejected"]

        if res["status"] == "FAILED":
            print(f" FAILED: {res.get('error')}")
            failed_symbols.append(sym)
        else:
            print(f" OK | Retrieved: {res['retrieved']} | Accepted: {res['accepted']} | Rejected: {res['rejected']}")
            total_retrieved += res["retrieved"]
            total_accepted += res["accepted"]
            total_rejected += res["rejected"]
            if res["accepted"] > 0:
                symbols_with_actions += 1

        # Gentle pacing
        time.sleep(0.15)

    elapsed = time.time() - start_time
    print("=" * 80)
    print("SYNCHRONIZATION COMPLETE")
    print(f"Elapsed Time:       {elapsed:.2f}s")
    print(f"Symbols Processed:  {len(symbols)}")
    print(f"Symbols with CAs:   {symbols_with_actions}")
    print(f"Total Retrieved:    {total_retrieved}")
    print(f"Total Accepted:     {total_accepted}")
    print(f"Total Rejected:     {total_rejected}")
    if failed_symbols:
        print(f"Failed Symbols:     {failed_symbols}")
    print("=" * 80)

    # Database summary queries
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT action_type, COUNT(*) as count, COUNT(DISTINCT symbol) as unique_symbols
            FROM corporate_actions
            WHERE ex_date BETWEEN ? AND ?
            GROUP BY action_type
            ORDER BY count DESC;
        """, (args.from_date, args.to_date))
        print("\nCorporate Actions in Window by Type:")
        for r in c.fetchall():
            print(f"  {r[0]:<12}: {r[1]:>3} events across {r[2]:>2} symbols")

        c.execute("""
            SELECT symbol, action_type, ex_date, purpose, adjustment_factor
            FROM corporate_actions
            WHERE adjustment_factor != 1.0 AND ex_date BETWEEN ? AND ?
            ORDER BY ex_date ASC;
        """, (args.from_date, args.to_date))
        non_neutral = c.fetchall()
        print(f"\nNon-Neutral Corporate Actions (adjustment_factor != 1.0): {len(non_neutral)}")
        for r in non_neutral:
            print(f"  {r[0]} | {r[1]} | {r[2]} | factor={r[4]} | {r[3]}")

if __name__ == "__main__":
    main()
