import time
import datetime
from src.storage.database import DatabaseManager
from src.client.udiff_client import UDiffClient
from src.client.validator import RecordValidator

def main():
    print("=== Ingesting Official Union Budget Sessions (2025-02-01 & 2026-02-01) ===")
    t0 = time.time()
    db = DatabaseManager("data/market_lab.db")
    udiff = UDiffClient()
    validator = RecordValidator()

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT symbol FROM securities_master WHERE is_active = 1 ORDER BY symbol")
        active_symbols = set(r[0] for r in cursor.fetchall())

    total_ingested = 0

    for budget_date in ["2025-02-01", "2026-02-01"]:
        print(f"\nProcessing Budget Session: {budget_date}")
        zpath, err = udiff.download_udiff_zip(budget_date)
        if not zpath:
            print(f"  Error downloading ZIP: {err}")
            continue

        # For 2025-02-01, ZOMATO was the active ticker for ETERNAL
        symbols_to_query = set(active_symbols)
        if budget_date == "2025-02-01":
            symbols_to_query.add("ZOMATO")

        raw_records, summary = udiff.parse_udiff_archive(
            zpath,
            universe_symbols=symbols_to_query,
            series_filter="EQ"
        )
        print(f"  Raw records parsed from exchange CM-UDiFF ZIP: {len(raw_records)}")

        # Normalize and set source provenance
        records_to_validate = []
        for r in raw_records:
            sym = r.get("symbol")
            if sym == "ZOMATO" and budget_date == "2025-02-01":
                # Map to canonical ETERNAL identity with alias provenance
                rec = dict(r)
                rec["symbol"] = "ETERNAL"
                rec["_provenance"] = "cm_udiff_alias_zomato"
                records_to_validate.append(rec)
            elif sym in active_symbols:
                rec = dict(r)
                rec["_provenance"] = "cm_udiff"
                records_to_validate.append(rec)

        # Validate through RecordValidator
        accepted = []
        rejected = []
        for rec in records_to_validate:
            src = rec.pop("_provenance", "cm_udiff")
            ok, cleaned, err = validator.validate_record(rec, source=src)
            if ok and cleaned:
                accepted.append(cleaned)
            else:
                rejected.append({"record": rec, "error": err})

        print(f"  Validator: accepted={len(accepted)}, rejected={len(rejected)}")
        if rejected:
            print(f"  Sample rejected: {rejected[:3]}")

        upserted = db.upsert_ohlcv_records(accepted)
        total_ingested += upserted
        print(f"  Upserted {upserted} records into ohlcv_daily")

        # Record audit log
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        db.record_audit_log(
            source="cm_udiff",
            endpoint="https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date}_F_0000.csv.zip",
            symbol="BUDGET_SESSION_BASKET",
            date_range_start=budget_date,
            date_range_end=budget_date,
            records_retrieved=len(raw_records),
            records_accepted=len(accepted),
            records_rejected=len(rejected),
            validation_summary={
                "date": budget_date,
                "accepted_count": len(accepted),
                "rejected_count": len(rejected),
                "has_zomato_mapped": any(r["symbol"] == "ETERNAL" and r["source"] == "cm_udiff_alias_zomato" for r in accepted)
            },
            raw_payload_path=zpath,
            status="SUCCESS",
            created_at=now_ts
        )

    print(f"\n--- Ingestion Complete in {time.time() - t0:.2f}s ---")
    print(f"Total Budget Day records upserted: {total_ingested}")

if __name__ == "__main__":
    main()
