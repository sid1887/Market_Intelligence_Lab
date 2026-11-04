#!/usr/bin/env python3
"""
CLI entry point for the Market Intelligence Lab automated production pipeline.
Runs the daily post-market workflow under Asia/Kolkata timezone with:
- Exclusive POSIX scheduler lock
- Bounded CM-UDiFF polling
- Dependent multi-stage quantitative processing
- Automated report generation
"""
import sys
import os
import argparse
import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.storage.database import DatabaseManager
from src.pipeline.production_pipeline import ProductionPipeline, IST_TZ

def main():
    parser = argparse.ArgumentParser(description="Market Intelligence Lab Daily Production Pipeline")
    parser.add_argument("--date", type=str, default=None, help="Target trading date YYYY-MM-DD (defaults to 2026-10-23 if omitted)")
    parser.add_argument("--max-attempts", type=int, default=17, help="Max bounded retry attempts (default: 17)")
    parser.add_argument("--poll-interval", type=float, default=0.0, help="Polling interval in seconds (0 for immediate evaluation)")
    parser.add_argument("--symbols", nargs="+", default=["INFY"], help="Symbols to generate tear-sheets for (default: INFY)")
    parser.add_argument("--recovery", action="store_true", help="Flag indicating a morning recovery run")
    parser.add_argument("--recover-missing", action="store_true", help="Scan lookback window to recover missing or pending trading sessions")
    parser.add_argument("--lookback-days", type=int, default=14, help="Lookback window in days for missing session detection (default: 14)")
    args = parser.parse_args()

    db = DatabaseManager("data/market_lab.db")
    pipeline = ProductionPipeline(db=db)

    print("=" * 85)
    print("MARKET INTELLIGENCE LAB — DAILY PRODUCTION PIPELINE")
    print(f"Current Local Time (IST): {datetime.datetime.now(IST_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Max Bounded Retries:      {args.max_attempts} attempts (15-min intervals)")
    print(f"Target Tearsheet Stocks:  {', '.join(args.symbols)}")
    print(f"Recovery Run:             {'YES (08:30 IST Next Day)' if args.recovery else 'NO (16:30 IST Primary)'}")
    print(f"Execution Capability:     STRICTLY DISABLED (Research Only)")
    print("=" * 85)

    if args.recover_missing or (args.recovery and not args.date):
        print(f"\n[RECOVERY MODE] Scanning past {args.lookback_days} days for missing or pending sessions...")
        rec_summary = pipeline.recover_missing_sessions(
            lookback_days=args.lookback_days,
            as_of_date=args.date,
            symbols_to_tearsheet=args.symbols,
            max_poll_attempts=args.max_attempts,
            poll_interval_seconds=args.poll_interval
        )
        print("\nRECOVERY WORKFLOW SUMMARY:")
        print(f" -> Overall Status:             {rec_summary['status']}")
        print(f" -> Missing Sessions Detected:  {rec_summary['missing_sessions_identified']}")
        print(f" -> Total Sessions Processed:   {len(rec_summary.get('sessions_processed', {}))}")
        for s_date, s_res in rec_summary.get("sessions_processed", {}).items():
            print(f"    * {s_date}: Status={s_res['status']}, AuditLogID={s_res.get('audit_log_id')}")
        if rec_summary.get("message"):
            print(f" -> Info:                       {rec_summary['message']}")
    else:
        target_date = args.date or "2026-10-23"
        print(f"Target Session Date:      {target_date}")
        res = pipeline.execute_daily_workflow(
            trading_date_iso=target_date,
            symbols_to_tearsheet=args.symbols,
            max_poll_attempts=args.max_attempts,
            poll_interval_seconds=args.poll_interval,
            is_recovery_run=args.recovery
        )

        print("\nPIPELINE EXECUTION SUMMARY:")
        print(f" -> Overall Status:    {res['status']}")
        if res.get("reason"):
            print(f" -> Calendar Reason:   {res['reason']}")
        print(f" -> Started At:        {res.get('started_at_ist')}")
        print(f" -> Completed At:      {res.get('completed_at_ist')}")
        if res.get("audit_log_id"):
            print(f" -> Audit Log ID:      {res['audit_log_id']}")

        for stage_name, stage_info in res.get("stages", {}).items():
            print(f" -> Stage [{stage_name}]: {stage_info}")

        if res.get("errors"):
            print("\nERRORS ENCOUNTERED:")
            for err in res["errors"]:
                print(f"  * {err}")

    print("\n" + "=" * 85)
    print("DAILY PIPELINE RUN COMPLETE")
    print("=" * 85)

if __name__ == "__main__":
    main()
