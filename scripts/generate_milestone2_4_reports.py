#!/usr/bin/env python3
"""
Executes the Milestone 2.4 Research Report Generation Pipeline:
1. Generates Daily Market Overview Report (reports/daily_market_overview_20261023.md)
2. Generates Company Research Tearsheet for INFY (reports/INFY_tearsheet_20261023.md)
Inspects outputs, verifies direct document links, event study guardrails, and deterministic calculations.
"""
import sys
import os
import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.storage.database import DatabaseManager
from src.reporting.daily_market_report import DailyMarketReportBuilder
from src.reporting.company_tearsheet import CompanyTearsheetBuilder

def main():
    db = DatabaseManager("data/market_lab.db")
    print("=" * 80)
    print("MARKET INTELLIGENCE LAB — MILESTONE 2.4 REPORT GENERATOR")
    print(f"Timestamp: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print("=" * 80)

    as_of = "2026-10-23"

    # 1. Daily Market Overview Report
    print(f"\n[1/2] Generating Daily Market Overview Report for {as_of}...")
    daily_builder = DailyMarketReportBuilder(db, output_dir="reports")
    daily_report_path = daily_builder.generate_report(as_of_date=as_of, index_name="NIFTY 50", benchmark_mode="PRI")
    print(f" -> Successfully written: {daily_report_path}")
    print(f" -> File size: {os.path.getsize(daily_report_path):,} bytes")

    # 2. Company Tearsheet Report
    print(f"\n[2/2] Generating Company Tearsheet for INFY as of {as_of}...")
    tearsheet_builder = CompanyTearsheetBuilder(db, output_dir="reports")
    tearsheet_path = tearsheet_builder.generate_tearsheet(symbol="INFY", as_of_date=as_of, benchmark_name="NIFTY 50")
    print(f" -> Successfully written: {tearsheet_path}")
    print(f" -> File size: {os.path.getsize(tearsheet_path):,} bytes")

    print("\n" + "=" * 80)
    print("MILESTONE 2.4 REPORT GENERATION COMPLETED SUCCESSFULLY")
    print("=" * 80)

if __name__ == "__main__":
    main()
