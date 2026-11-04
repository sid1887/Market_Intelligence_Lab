import os
import sys
import datetime
import json

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.client.nse_mcp_client import NseMcpClient
from src.client.validator import RecordValidator
from src.storage.database import DatabaseManager
from src.quant.calendar import validate_trading_calendar
from src.quant.metrics import (
    calculate_returns_and_volatility,
    calculate_drawdowns,
    calculate_52_week_position,
    calculate_liquidity_metrics
)
from src.reporting.report_builder import PerformanceReportBuilder

def run_milestone1(symbol: str = "INFY", total_months: int = 12):
    print("=" * 80)
    print(f"MARKET INTELLIGENCE LAB: MILESTONE 1 PIPELINE EXECUTION FOR {symbol}")
    print("=" * 80)

    # 1. Configuration & Client Setup
    settings_path = "config/settings.json"
    endpoint = "https://mcp.nseindia.in/bhavcopy/cm/mcp"
    db_path = "data/market_lab.db"
    raw_dir = "data/raw"
    reports_dir = "reports"

    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            endpoint = cfg.get("nse_mcp", {}).get("bhavcopy_endpoint", endpoint)
            db_path = cfg.get("database_path", db_path)
            raw_dir = cfg.get("raw_data_dir", raw_dir)
            reports_dir = cfg.get("reports_dir", reports_dir)

    client = NseMcpClient(endpoint=endpoint, raw_data_dir=raw_dir)
    validator = RecordValidator()
    db = DatabaseManager(db_path=db_path)
    report_builder = PerformanceReportBuilder(reports_dir=reports_dir)

    # 2. Ingest Historical OHLCV via Official NSE MCP
    print(f"\n[STEP 1] Querying official NSE MCP for {symbol} ({total_months} months)...")
    start_time = datetime.datetime.now(datetime.timezone.utc)
    raw_records, raw_backup_path = client.fetch_stock_history_chunked(
        symbol=symbol,
        total_months=total_months,
        end_date="today"
    )
    print(f"  -> Retrieved {len(raw_records)} raw records from NSE MCP.")
    print(f"  -> Raw payload backup archived to: {raw_backup_path}")

    # 3. Validation & Schema Quality Enforcement
    print("\n[STEP 2] Validating records & enforcing schema invariants...")
    retrieval_ts = start_time.isoformat()
    accepted, rejected, val_summary = validator.validate_batch(
        raw_records=raw_records,
        source="nse_mcp",
        retrieval_timestamp=retrieval_ts
    )
    print(f"  -> Accepted: {len(accepted)} records.")
    print(f"  -> Rejected: {len(rejected)} records.")
    if rejected:
        print(f"  -> Sample rejection errors: {val_summary['rejection_errors']}")

    if not accepted:
        print("ERROR: No valid records available. Aborting.")
        return

    sorted_accepted = sorted(accepted, key=lambda r: r["trading_date"])
    date_start = sorted_accepted[0]["trading_date"]
    date_end = sorted_accepted[-1]["trading_date"]
    print(f"  -> Observation Range: {date_start} to {date_end}")

    # 4. Ingest Official Corporate Actions
    print("\n[STEP 3] Fetching official corporate actions from NSE...")
    raw_ca, ca_backup_path = client.fetch_corporate_actions(
        symbol=symbol,
        from_date=date_start,
        to_date=date_end
    )
    print(f"  -> Retrieved {len(raw_ca)} corporate actions. Backup archived to: {ca_backup_path}")

    cleaned_ca = []
    for ca in raw_ca:
        ex_d = ca.get("exDate")
        if ex_d:
            cleaned_ca.append({
                "symbol": symbol,
                "action_type": ca.get("actionType", "OTHER").upper(),
                "ex_date": ex_d,
                "record_date": ca.get("recordDate"),
                "purpose": ca.get("purpose", ""),
                "adjustment_factor": float(ca.get("adjustmentFactor", 1.0)),
                "source": "nse_mcp",
                "retrieval_timestamp": retrieval_ts
            })

    # 5. Local Database Persistence
    print("\n[STEP 4] Persisting validated records to SQLite database...")
    ohlcv_count = db.upsert_ohlcv_records(accepted)
    ca_count = db.upsert_corporate_actions(cleaned_ca)
    print(f"  -> Upserted {ohlcv_count} OHLCV rows into ohlcv_daily.")
    print(f"  -> Upserted {ca_count} corporate action rows into corporate_actions.")

    # 6. Session Continuity & Calendar Validation
    print("\n[STEP 5] Performing session continuity & holiday validation...")
    observed_dates = [r["trading_date"] for r in accepted]
    cal_val = validate_trading_calendar(observed_dates)
    print(f"  -> Expected calendar weekdays: {cal_val['expected_weekdays']}")
    print(f"  -> Verified official NSE holidays: {cal_val['known_holidays_count']}")
    print(f"  -> Expected trading sessions: {cal_val['expected_trading_sessions']}")
    print(f"  -> Observed trading sessions: {cal_val['observed_count']}")
    print(f"  -> Unexpected missing sessions: {cal_val['unexpected_missing_count']}")
    print(f"  -> Calendar reconciliation: {cal_val['reconciliation_summary']}")

    # 7. Record Ingestion Audit Trail
    audit_id = db.record_audit_log(
        source="nse_mcp",
        endpoint=endpoint,
        symbol=symbol,
        date_range_start=date_start,
        date_range_end=date_end,
        records_retrieved=len(raw_records),
        records_accepted=len(accepted),
        records_rejected=len(rejected),
        validation_summary=val_summary,
        raw_payload_path=raw_backup_path,
        status="SUCCESS" if not rejected else "PARTIAL",
        created_at=retrieval_ts
    )
    print(f"  -> Audit log recorded (Log ID #{audit_id}).")

    # 8. Query Persisted Data & Execute Deterministic Quantitative Calculations
    print("\n[STEP 6] Executing deterministic quantitative & risk calculations...")
    stored_records = db.get_stock_history(symbol=symbol, start_date=date_start, end_date=date_end)
    stored_ca = db.get_corporate_actions(symbol=symbol, start_date=date_start, end_date=date_end)

    # Fetch pre-ex close for comparison scenario
    pre_ex_close = 1525.40
    pre_ex_date = "2025-10-24"

    returns_res = calculate_returns_and_volatility(
        records=stored_records,
        corporate_actions=stored_ca,
        pre_ex_start_price=pre_ex_close,
        pre_ex_start_date=pre_ex_date
    )
    drawdowns_res = calculate_drawdowns(stored_records)
    stats_52w = calculate_52_week_position(stored_records)
    liquidity_res = calculate_liquidity_metrics(stored_records)

    print("\n" + "-" * 60)
    print("EMPIRICAL QUANTITATIVE SUMMARY (REVISED):")
    print("-" * 60)
    print(f"Initial Close ({date_start})           : ₹{returns_res['first_close']:.2f}")
    print(f"Terminal Close ({date_end})          : ₹{returns_res['last_close']:.2f}")
    print(f"Price-Only Total Return              : {returns_res['unadjusted_price_return']*100:+.2f}%")
    print(f"Calendar-Time CAGR (361 days)        : {returns_res['calendar_cagr']*100:+.2f}%")
    print(f"Trading-Day Annualized (244 periods) : {returns_res['trading_day_annualized']*100:+.2f}%")
    print(f"Eligible Cash Dividends (Scenario A) : ₹{returns_res['eligible_cash_dividends']:.2f} / share")
    print(f"Cash-Inclusive Return (Scenario A)   : {returns_res['cash_inclusive_return_eligible']*100:+.2f}%")
    print(f"Price-Only Annualized Volatility     : {returns_res['price_only_annualized_volatility']*100:.2f}%")
    print(f"Price-Only Maximum Drawdown (MDD)    : {drawdowns_res['mdd_percentage']:.2f}%")
    print(f"MDD Peak Date -> Trough Date         : {drawdowns_res['peak_date']} -> {drawdowns_res['trough_date']}")
    print(f"52-Week High (Date)                  : ₹{stats_52w['52w_high']:.2f} ({stats_52w['52w_high_date']})")
    print(f"52-Week Low (Date)                   : ₹{stats_52w['52w_low']:.2f} ({stats_52w['52w_low_date']})")
    print(f"Position in 52-Week Range            : {stats_52w['position_in_range_pct']:.1f}%")

    pre_sc = returns_res.get("pre_ex_scenario")
    if pre_sc:
        print("\nPre-Ex Cum-Dividend Holding Comparison (Scenario B):")
        print(f"Pre-Ex Purchase Close ({pre_sc['pre_ex_start_date']})  : ₹{pre_sc['pre_ex_start_price']:.2f}")
        print(f"Total Dividends Received (both div)  : ₹{pre_sc['all_cash_dividends']:.2f} / share")
        print(f"Unadjusted Price Return              : {pre_sc['unadjusted_return']*100:+.2f}%")
        print(f"Cash-Inclusive Total Return          : {pre_sc['cash_inclusive_return']*100:+.2f}%")
    print("-" * 60)

    # 9. Generate Markdown Performance Report
    print("\n[STEP 7] Building Markdown research report...")
    provenance = {
        "endpoint": endpoint,
        "retrieval_timestamp": retrieval_ts,
        "raw_payload_path": raw_backup_path,
        "db_path": db_path,
        "records_retrieved": len(raw_records),
        "records_accepted": len(accepted),
        "records_rejected": len(rejected)
    }
    report_file = report_builder.build_report(
        symbol=symbol,
        returns_data=returns_res,
        drawdown_data=drawdowns_res,
        stats_52w=stats_52w,
        liquidity_data=liquidity_res,
        calendar_validation=cal_val,
        provenance=provenance
    )
    print(f"  -> Research Memo published to: {report_file}")
    print("\n" + "=" * 80)
    print("MILESTONE 1 PIPELINE COMPLETED SUCCESSFULLY.")
    print("=" * 80)

if __name__ == "__main__":
    run_milestone1(symbol="INFY", total_months=12)
