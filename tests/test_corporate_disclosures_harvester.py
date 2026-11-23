import pytest
from pathlib import Path
from src.storage.database import DatabaseManager
from src.data.corporate_disclosures import CorporateDisclosuresHarvester

def test_corporate_disclosures_pdf_url_normalization():
    # Relative or simple filename
    assert CorporateDisclosuresHarvester.normalize_pdf_url("INFY_15012024.pdf") == "https://nsearchives.nseindia.com/corporate/INFY_15012024.pdf"
    assert CorporateDisclosuresHarvester.normalize_pdf_url("/attachments/TCS_results.pdf") == "https://nsearchives.nseindia.com/corporate/attachments/TCS_results.pdf"
    
    # Absolute URL
    assert CorporateDisclosuresHarvester.normalize_pdf_url("https://nsearchives.nseindia.com/corporate/RELIANCE.pdf") == "https://nsearchives.nseindia.com/corporate/RELIANCE.pdf"
    
    # None / empty / invalid
    assert CorporateDisclosuresHarvester.normalize_pdf_url(None) is None
    assert CorporateDisclosuresHarvester.normalize_pdf_url("-") is None
    assert CorporateDisclosuresHarvester.normalize_pdf_url("") is None


def test_corporate_disclosures_materiality_classifier():
    # Highly material: Financial results
    c1, s1 = CorporateDisclosuresHarvester.classify_materiality(
        subject="Financial Results for Quarter Ended Dec 31, 2023",
        details_summary="Audited standalone and consolidated financial results",
        category="EARNINGS"
    )
    assert c1 == "HIGHLY_MATERIAL"
    assert s1 >= 0.90

    # Highly material: CEO resignation
    c2, s2 = CorporateDisclosuresHarvester.classify_materiality(
        subject="Resignation of Managing Director and CEO",
        details_summary="Board has accepted resignation effective immediately",
        category="RESIGNATION"
    )
    assert c2 == "HIGHLY_MATERIAL"
    assert s2 >= 0.90

    # Routine: Trading window closure
    c3, s3 = CorporateDisclosuresHarvester.classify_materiality(
        subject="Closure of Trading Window",
        details_summary="Trading window closed for insiders in compliance with SEBI PIT regulations",
        category="GENERAL_ANNOUNCEMENT"
    )
    assert c3 == "ROUTINE"
    assert s3 < 0.35


def test_corporate_disclosures_harvester_store(tmp_path: Path):
    db_file = tmp_path / "disc_test.db"
    db = DatabaseManager(str(db_file))
    
    # Create required tables in isolated database
    with db.get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS corporate_disclosures (
                id TEXT UNIQUE,
                disclosure_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                broadcast_timestamp TEXT NOT NULL,
                effective_session_date TEXT NOT NULL,
                category TEXT NOT NULL,
                subject TEXT NOT NULL,
                details_summary TEXT,
                source_url TEXT,
                retrieval_timestamp TEXT NOT NULL,
                verification_status TEXT NOT NULL DEFAULT 'PENDING_VERIFICATION',
                audit_status TEXT DEFAULT NULL,
                dividend_declared REAL DEFAULT NULL,
                operating_margin_pct REAL DEFAULT NULL,
                revenue_inr_crore REAL DEFAULT NULL,
                revenue_growth_yoy_cc REAL DEFAULT NULL,
                revenue_growth_qoq_cc REAL DEFAULT NULL,
                revenue_growth_yoy_reported REAL DEFAULT NULL,
                source_timestamp_basis TEXT DEFAULT NULL
            );
        """)
        conn.commit()

    harvester = CorporateDisclosuresHarvester(db=db)

    mock_raw_announcements = [
        {
            "symbol": "TCS",
            "seq_id": "998811",
            "sort_date": "2024-01-11 16:45:00",
            "desc": "Audited Financial Results for Q3 FY24",
            "attchmntText": "Board declared interim dividend of Rs 27 per share",
            "attchmntFile": "TCS_Q3_Results.pdf"
        },
        {
            "symbol": "INFY",
            "seq_id": "776655",
            "sort_date": "2024-01-11 14:00:00",
            "desc": "Trading Window Closure",
            "attchmntText": "Trading window closure notice",
            "attchmntFile": None
        }
    ]

    res = harvester.process_and_store_disclosures(mock_raw_announcements)
    assert res["status"] == "SUCCESS"
    assert res["accepted"] == 2

    with db.get_connection() as conn:
        cur = conn.execute("SELECT symbol, source_url, effective_session_date, category FROM corporate_disclosures ORDER BY symbol")
        rows = cur.fetchall()
        assert len(rows) == 2
        
        # INFY (disseminated at 14:00 IST on trading day -> same day 2024-01-11)
        infy = rows[0]
        assert infy["symbol"] == "INFY"
        assert infy["source_url"] is None

        # TCS (disseminated at 16:45 IST > 15:30 IST -> next trading session 2024-01-12)
        tcs = rows[1]
        assert tcs["symbol"] == "TCS"
        assert tcs["source_url"] == "https://nsearchives.nseindia.com/corporate/TCS_Q3_Results.pdf"
        assert tcs["effective_session_date"] == "2024-01-12"
        assert tcs["category"] == "EARNINGS"
