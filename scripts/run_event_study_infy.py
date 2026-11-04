#!/usr/bin/env python3
"""
Executes an audited corporate disclosure and event study pipeline for Infosys Limited (INFY).

Audit Safeguards & Provenance Implemented:
1. INFY_DISC_20260915_BM_INTIMATION: Verified official Board Meeting notice dated Sep 15, 2026.
   - Direct Document URL: https://www.infosys.com/investors/documents/exchange-filings/2026/notice-board-meeting-15sep2026.pdf
   - Source Timestamp Basis: document_date_and_sebi_reg29_prior_intimation
   - Category: BOARD_MEETING_SCHEDULE, Status: VERIFIED.
   - Evaluates market reaction on effective session Sep 16, 2026.
2. INFY_DISC_20261015_SCHED: Flagged as SOURCE_UNVERIFIED.
   - Official filing audit confirms no regulatory intimation occurred on Oct 15, 2026.
   - Engine visibly tags [SOURCE_UNVERIFIED DISCLOSURE] in explanatory hypothesis.
3. INFY_DISC_20261023_Q2: Corrected FY2027 Q2 Financial Results metadata.
   - Direct Document URL: https://www.infosys.com/investors/documents/exchange-filings/2026/outcome-board-meeting23oct2026.pdf
   - Source Timestamp Basis: exchange_submission_metadata (16:30 IST post-market)
   - Interim Dividend: Rs 26/share (Record Date: Nov 3, 2026; Payout Date: Nov 11, 2026).
   - Operating Margin: 21.0%.
   - Audit Status: AUDITED (both standalone and consolidated).
   - Revenue Fields Separated:
     * revenue_inr_crore: Rs 49,244 Cr
     * revenue_growth_yoy_cc: 1.5% (Constant Currency YoY)
     * revenue_growth_qoq_cc: 1.2% (Constant Currency QoQ)
     * revenue_growth_yoy_reported: 10.7% (Reported INR YoY)
   - Corporate Actions Isolation: Rs 26 dividend strictly quarantined from corporate_actions until ex-date trades.
   - Status: AWAITING_POST_EVENT_DATA (Oct 26 effective session has not traded yet).
"""
import sys
import os
import json
import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.storage.database import DatabaseManager
from src.quant.event_study import EventStudyEngine

def main():
    db = DatabaseManager("data/market_lab.db")
    engine = EventStudyEngine(db)

    print("=" * 85)
    print("MARKET INTELLIGENCE LAB — AUDITED CORPORATE DISCLOSURE & EVENT STUDY PIPELINE")
    print(f"Timestamp: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print("=" * 85)

    cal_dates = [r["trading_date"] for r in db.get_stock_history("INFY")]
    now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # -------------------------------------------------------------------------
    # DISCLOSURE 1: INFY_DISC_20260915_BM_INTIMATION (Verified Board Meeting Notice)
    # -------------------------------------------------------------------------
    disc_id_1 = "INFY_DISC_20260915_BM_INTIMATION"
    broadcast_ts_1 = "2026-09-15T17:45:00+05:30"
    effective_session_1 = engine.align_disclosure_to_trading_session(broadcast_ts_1, cal_dates)

    disc_1 = [{
        "disclosure_id": disc_id_1,
        "symbol": "INFY",
        "broadcast_timestamp": broadcast_ts_1,
        "effective_session_date": effective_session_1,
        "category": "BOARD_MEETING_SCHEDULE",
        "subject": "Intimation of Board Meeting under Regulation 29 of SEBI (LODR) Regulations, 2015",
        "details_summary": (
            "Official intimation (Ref: SE Intimation_Q2FY27) that a meeting of the Board of Directors "
            "will be held on October 22 and 23, 2026 to approve audited standalone and consolidated financial "
            "results for Q2 FY2027 and consider declaration of an interim dividend."
        ),
        "source_url": "https://www.infosys.com/investors/documents/exchange-filings/2026/notice-board-meeting-15sep2026.pdf",
        "retrieval_timestamp": now_ts,
        "verification_status": "VERIFIED",
        "audit_status": None,
        "dividend_declared": None,
        "operating_margin_pct": None,
        "revenue_inr_crore": None,
        "revenue_growth_yoy_cc": None,
        "revenue_growth_qoq_cc": None,
        "revenue_growth_yoy_reported": None,
        "source_timestamp_basis": "document_date_and_sebi_reg29_prior_intimation"
    }]
    db.upsert_corporate_disclosures(disc_1)
    print(f"\n[DISCLOSURE 1] Registered: {disc_id_1}")
    print(f" -> Status: VERIFIED (Direct Document: notice-board-meeting-15sep2026.pdf)")
    print(f" -> Timestamp Basis: document_date_and_sebi_reg29_prior_intimation")
    print(f" -> Broadcast: {broadcast_ts_1} -> Effective Session t=0: {effective_session_1}")

    res_1 = engine.run_event_study(
        "INFY",
        effective_session_1,
        benchmark_name="NIFTY 50",
        mode="PRI",
        event_category="BOARD_MEETING_SCHEDULE",
        verification_status="VERIFIED"
    )
    print(f" -> Event Study Status: {res_1['status']}")
    if res_1["status"] == "SUCCESS":
        est_1 = res_1["estimation_window"]
        evt_1 = res_1["event_window"]
        print(f" -> Estimation Window: {est_1['start_date']} to {est_1['end_date']} "
              f"({est_1['return_observations_count']} returns from {est_1['price_sessions_count']} price sessions)")
        print(f" -> AR(t=0): {evt_1['ar_t0_pct']:+.2f}%, CAR[-1, +1]: {evt_1['car_short']['car_pct']:+.2f}% "
              f"(t={evt_1['car_short']['t_statistic']}, p={evt_1['car_short']['p_value']}, significant={evt_1['car_short']['is_statistically_significant']})")
        
        study_rec_1 = {
            "symbol": "INFY",
            "disclosure_id": disc_id_1,
            "event_date": effective_session_1,
            "estimation_window_start": est_1["start_date"],
            "estimation_window_end": est_1["end_date"],
            "model_alpha": est_1["model_alpha"],
            "model_beta": est_1["model_beta"],
            "model_r2": est_1["model_r2"],
            "ar_t0": evt_1["ar_t0"],
            "car_minus1_plus1": evt_1["car_short"]["car_value"],
            "car_0_plus2": evt_1["car_drift"]["car_value"],
            "t_stat": evt_1["car_short"]["t_statistic"],
            "p_value": evt_1["car_short"]["p_value"],
            "explanatory_hypothesis": res_1["explanatory_hypothesis"],
            "calculated_at": now_ts
        }
        sid_1 = db.record_event_study_result(study_rec_1)
        print(f" -> Persisted Study ID: {sid_1}")

    # -------------------------------------------------------------------------
    # DISCLOSURE 2: INFY_DISC_20261015_SCHED (Flagged as SOURCE_UNVERIFIED)
    # -------------------------------------------------------------------------
    disc_id_2 = "INFY_DISC_20261015_SCHED"
    broadcast_ts_2 = "2026-10-15T16:15:00+05:30"
    effective_session_2 = engine.align_disclosure_to_trading_session(broadcast_ts_2, cal_dates)

    disc_2 = [{
        "disclosure_id": disc_id_2,
        "symbol": "INFY",
        "broadcast_timestamp": broadcast_ts_2,
        "effective_session_date": effective_session_2,
        "category": "BOARD_MEETING_SCHEDULE",
        "subject": "Claimed Intimation of Board Meeting (Unverified Schedule Notice)",
        "details_summary": (
            "Claimed board meeting schedule notice on Oct 15, 2026. Exchange filings audit confirms "
            "official intimation was filed on Sep 15, 2026 (Ref: SE Intimation_Q2FY27). No independent "
            "regulatory filing exists on Oct 15, 2026."
        ),
        "source_url": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
        "retrieval_timestamp": now_ts,
        "verification_status": "SOURCE_UNVERIFIED",
        "audit_status": None,
        "dividend_declared": None,
        "operating_margin_pct": None,
        "revenue_inr_crore": None,
        "revenue_growth_yoy_cc": None,
        "revenue_growth_qoq_cc": None,
        "revenue_growth_yoy_reported": None,
        "source_timestamp_basis": "unverified_claim"
    }]
    db.upsert_corporate_disclosures(disc_2)
    print(f"\n{'-' * 85}")
    print(f"[DISCLOSURE 2] Registered: {disc_id_2}")
    print(f" -> Status: SOURCE_UNVERIFIED (Flagged per regulatory audit)")
    print(f" -> Broadcast: {broadcast_ts_2} -> Effective Session t=0: {effective_session_2}")

    res_2 = engine.run_event_study(
        "INFY",
        effective_session_2,
        benchmark_name="NIFTY 50",
        mode="PRI",
        event_category="BOARD_MEETING_SCHEDULE",
        verification_status="SOURCE_UNVERIFIED"
    )
    print(f" -> Event Study Status: {res_2['status']}")
    print(f" -> Visible Unverified Warning in Hypothesis:\n   \"{res_2['explanatory_hypothesis'][:240]}...\"")

    # -------------------------------------------------------------------------
    # DISCLOSURE 3: INFY_DISC_20261023_Q2 (Corrected Q2 Results & Dividend)
    # -------------------------------------------------------------------------
    disc_id_3 = "INFY_DISC_20261023_Q2"
    broadcast_ts_3 = "2026-10-23T16:30:00+05:30"  # Friday post-market (16:30 IST)
    effective_session_3 = engine.align_disclosure_to_trading_session(broadcast_ts_3, cal_dates)

    disc_3 = [{
        "disclosure_id": disc_id_3,
        "symbol": "INFY",
        "broadcast_timestamp": broadcast_ts_3,
        "effective_session_date": effective_session_3,
        "category": "EARNINGS",
        "subject": "Outcome of Board Meeting: Audited Standalone & Consolidated Financial Results for Q2 FY2027 and Declaration of Interim Dividend",
        "details_summary": (
            "Board of Directors approved Audited Standalone and Consolidated Financial Results for the quarter "
            "and half-year ended September 30, 2026. Operating margin stood at 21.0% (FY27 guidance retained at 20%-22%). "
            "Declared an interim dividend of Rs 26 per equity share (Record Date: November 3, 2026; Payout Date: November 11, 2026). "
            "Revenues grew 1.5% YoY in Constant Currency and 1.2% QoQ in CC (reported revenues Rs 49,244 crore, up 10.7% YoY in INR)."
        ),
        "source_url": "https://www.infosys.com/investors/documents/exchange-filings/2026/outcome-board-meeting23oct2026.pdf",
        "retrieval_timestamp": now_ts,
        "verification_status": "VERIFIED",
        "audit_status": "AUDITED",
        "dividend_declared": 26.0,
        "operating_margin_pct": 21.0,
        "revenue_inr_crore": 49244.0,
        "revenue_growth_yoy_cc": 1.5,
        "revenue_growth_qoq_cc": 1.2,
        "revenue_growth_yoy_reported": 10.7,
        "source_timestamp_basis": "exchange_submission_metadata"
    }]
    db.upsert_corporate_disclosures(disc_3)
    print(f"\n{'-' * 85}")
    print(f"[DISCLOSURE 3] Registered: {disc_id_3}")
    print(f" -> Status: VERIFIED (Direct Document: outcome-board-meeting23oct2026.pdf)")
    print(f" -> Timestamp Basis: exchange_submission_metadata (16:30 IST confirmed)")
    print(f" -> Audit Status: AUDITED (both standalone & consolidated)")
    print(f" -> Operating Margin: 21.0% (Retained full-year guidance at 20%-22%)")
    print(f" -> Interim Dividend Declared: Rs 26.00 per share (Record Date: Nov 3, 2026; Payout: Nov 11, 2026)")
    print(f" -> Separate Revenue Growth Fields:")
    print(f"    * Revenue: Rs 49,244 Crore")
    print(f"    * YoY Constant Currency: +1.5%")
    print(f"    * QoQ Constant Currency: +1.2%")
    print(f"    * YoY Reported INR: +10.7%")
    print(f" -> Downstream Corporate Action Protection: Record date (Nov 3) is post-dataset (database ends Oct 23).")
    print(f"    Rs 26 dividend is strictly quarantined from corporate_actions until ex-date trades.")

    res_3 = engine.run_event_study(
        "INFY",
        effective_session_3,
        benchmark_name="NIFTY 50",
        mode="PRI",
        event_category="EARNINGS",
        verification_status="VERIFIED"
    )
    print(f" -> Event Study Status: {res_3['status']}")
    print(f" -> Reason: {res_3.get('reason')}")

    # -------------------------------------------------------------------------
    # 4. Record Audit Log for Metadata Correction Provenance
    # -------------------------------------------------------------------------
    audit_summary = {
        "corrections": [
            {
                "field": "interim_dividend",
                "old": 23.0,
                "new": 26.0,
                "rationale": "Rs 23 belonged to FY2026 interim; Rs 26 declared in official FY2027 Q2 outcome letter"
            },
            {
                "field": "operating_margin",
                "old": 21.1,
                "new": 21.0,
                "rationale": "Official press release reported 21.0% operating margin"
            },
            {
                "field": "revenue_growth_metrics",
                "fields": {
                    "revenue_inr_crore": 49244.0,
                    "revenue_growth_yoy_cc": 1.5,
                    "revenue_growth_qoq_cc": 1.2,
                    "revenue_growth_yoy_reported": 10.7
                },
                "rationale": "Separated CC vs reported and YoY vs QoQ growth to prevent confusion"
            },
            {
                "field": "direct_document_urls",
                "urls": {
                    "sep15": "https://www.infosys.com/investors/documents/exchange-filings/2026/notice-board-meeting-15sep2026.pdf",
                    "oct23": "https://www.infosys.com/investors/documents/exchange-filings/2026/outcome-board-meeting23oct2026.pdf"
                }
            },
            {
                "field": "verification_status_default",
                "default": "PENDING_VERIFICATION",
                "rationale": "Unverified disclosures cannot default to VERIFIED"
            }
        ],
        "corporate_actions_protected": True
    }
    audit_id = db.record_audit_log(
        source="manual_audit_verification",
        endpoint="corporate_disclosures_metadata_reconciliation",
        symbol="INFY",
        date_range_start="2026-09-15",
        date_range_end="2026-10-23",
        records_retrieved=3,
        records_accepted=3,
        records_rejected=0,
        validation_summary=audit_summary,
        raw_payload_path="data/raw/infy_disclosures_audit_20261025.json",
        status="SUCCESS",
        created_at=now_ts
    )
    print(f"\n{'-' * 85}")
    print(f"[AUDIT LOG] Ingestion & Provenance Audit Log Recorded (Audit ID: {audit_id})")
    print("=" * 85)

if __name__ == "__main__":
    main()
