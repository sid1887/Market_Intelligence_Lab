"""
tests/test_tradebook_engine.py
Zero-PII Encrypted Angel One Tradebook Ingestion Engine Test Suite.

Verification Gates:
1. Strict PII exclusion:
   Assert client name, PAN, client ID, address, mobile, email, and DP ID strings
   never appear in parsed dicts, SQLite rows, or decrypted .xlsx cells.
2. Idempotent deduplication:
   Ingesting overlapping reports twice yields zero duplicate executions or roundtrips.
3. Scrip-level DP friction reconciliation:
   Validates exact ₹23.60 DP fee per closed sell round-trip and true net P&L calculation.
4. Cryptographic round-trip:
   Ensures master_tradebook.enc is encrypted at rest via Fernet and can be decrypted
   in RAM with all 5 tabs and institutional styling.
5. Secure API routes:
   Upload, summary, and binary export endpoints operate correctly with Zero-PII.
"""

import io
import os
import re
import pytest
import openpyxl
from fastapi.testclient import TestClient

from src.api.main import app
from src.storage.database import DatabaseManager
from src.portfolio.tradebook_engine import (
    EncryptedTradebookEngine,
    DEFAULT_ANGEL_ONE_DP_CHARGE,
    get_fernet_cipher,
    MASTER_ENC_PATH,
)


@pytest.fixture
def temp_db(tmp_path):
    """Provides an isolated SQLite database."""
    db_file = tmp_path / "test_tradebook.db"
    db = DatabaseManager(str(db_file))
    # Populate a securities_master entry for ISIN resolution
    with db.get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS securities_master (
                symbol TEXT, company_name TEXT, isin TEXT PRIMARY KEY,
                industry TEXT, sector TEXT, macro_sector TEXT,
                listing_date TEXT, is_active INTEGER DEFAULT 1,
                updated_at TEXT, is_nifty50 INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            INSERT OR REPLACE INTO securities_master (symbol, company_name, isin, industry, sector, macro_sector, listing_date, is_active, is_nifty50, updated_at)
            VALUES 
                ('SUZLON', 'SUZLON ENERGY LIMITED', 'INE040H01021', 'Energy', 'Power', 'Energy', '2005-10-19', 1, 0, '2026-11-20 00:00:00'),
                ('M&MFIN', 'MAHINDRA & MAHINDRA FINANCIAL SERVICES LTD', 'INE774D01024', 'Financials', 'NBFC', 'Financials', '2006-03-17', 1, 0, '2026-11-20 00:00:00'),
                ('RVNL', 'RAIL VIKAS NIGAM LIMITED', 'INE415G01027', 'Railways', 'Construction', 'Industrials', '2019-04-11', 1, 0, '2026-11-20 00:00:00'),
                ('ASHOKLEY', 'ASHOK LEYLAND LIMITED', 'INE208A01029', 'Automobile', 'Commercial Vehicles', 'Auto', '1995-01-01', 1, 0, '2026-11-20 00:00:00'),
                ('GAIL', 'GAIL (INDIA) LIMITED', 'INE129A01019', 'Energy', 'Gas Utility', 'Energy', '1997-05-15', 1, 0, '2026-11-20 00:00:00')
        """)
        # Populate ohlcv_daily for live LTP enrichment
        conn.execute("""
            INSERT OR REPLACE INTO ohlcv_daily (symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp)
            VALUES 
                ('SUZLON', '2026-11-20', 'EQ', 65.0, 67.0, 64.0, 66.20, 1000000, 'TEST', '2026-11-20T00:00:00Z'),
                ('GAIL', '2026-11-20', 'EQ', 190.0, 195.0, 188.0, 192.50, 500000, 'TEST', '2026-11-20T00:00:00Z')
        """)
        conn.commit()
    return db


def create_synthetic_angel_one_tradebook() -> bytes:
    """
    Creates an in-memory Angel One multi-sheet .xlsx workbook containing:
    1. Realistic PII in top rows (rows 1-33) to verify strict filtering.
    2. TradesAndCharges sheet with 9 executions.
    3. Tax PNL sheet with 4 closed delivery swings + 1 open holding (GAIL).
    4. ProfitLoss sheet with Scrip Symbol to Company Name mapping.
    5. YourStatement sheets with Broking Ledger (Funds Added) and DP Charges (₹23.60).
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # Remove default sheet

    # -------------------------------------------------------------------------
    # Sheet 1: TradesAndCharges (Trades History)
    # -------------------------------------------------------------------------
    ws_trades = wb.create_sheet(title="TradesAndCharges")
    # Top rows with blatant PII
    ws_trades["A1"] = "ANGEL ONE LIMITED - TRADE CONFIRMATION"
    ws_trades["A2"] = "Client Code: ANGEL_SECRET_UCC_9988"
    ws_trades["A3"] = "Client Name: SIDDHARTH PRIVACY TEST"
    ws_trades["A4"] = "PAN: ABCDE1234F"
    ws_trades["A5"] = "Address: 42 Silicon Highway, Cyber City, Bangalore 560001"
    ws_trades["A6"] = "Mobile: +91-9876543210 | Email: user.private@secretmail.com"
    ws_trades["A7"] = "DP ID: 1203320012345678"

    # Row 34: Banner Header Anchor
    ws_trades["A34"] = "TradeBook And Charges"

    # Row 35: Table Columns
    headers_trades = [
        "Scrip/Contract", "Buy/Sell", "Buy Price", "Sell Price", "Quantity", "Brokerage",
        "GST", "STT", "Sebi Tax", "Exchange Turnover Charges", "Stamp Duty", "Other Charges",
        "IPFT Charges", "Order Type", "Segment", "Exchange", "Order ID", "Trade ID", "Date"
    ]
    for c_idx, h in enumerate(headers_trades, start=1):
        ws_trades.cell(row=35, column=c_idx, value=h)

    # 9 Fills (SUZLON, M&MFIN, RVNL, ASHOKLEY, GAIL)
    trades_data = [
        # SUZLON Round-Trip (Buy + Sell)
        ("SUZLON ENERGY LTD", "B", 60.0, 0.0, 25, 0.0, 0.15, 1.50, 0.01, 0.05, 0.22, 0.0, 0.0, "DELIVERY", "EQ", "NSE", "ORD101", "TRD201", "10/05/2024"),
        ("SUZLON ENERGY LTD", "S", 0.0, 58.5, 25, 0.0, 0.14, 1.46, 0.01, 0.05, 0.00, 0.0, 0.0, "DELIVERY", "EQ", "NSE", "ORD102", "TRD202", "15/05/2024"),
        # M&MFIN Round-Trip
        ("M&MFIN LTD", "B", 290.0, 0.0, 5, 0.0, 0.14, 1.45, 0.01, 0.05, 0.21, 0.0, 0.0, "DELIVERY", "EQ", "NSE", "ORD103", "TRD203", "12/05/2024"),
        ("M&MFIN LTD", "S", 0.0, 285.0, 5, 0.0, 0.13, 1.42, 0.01, 0.05, 0.00, 0.0, 0.0, "DELIVERY", "EQ", "NSE", "ORD104", "TRD204", "20/05/2024"),
        # RVNL Round-Trip
        ("RVNL LTD", "B", 380.0, 0.0, 5, 0.0, 0.18, 1.90, 0.01, 0.06, 0.28, 0.0, 0.0, "DELIVERY", "EQ", "NSE", "ORD105", "TRD205", "18/05/2024"),
        ("RVNL LTD", "S", 0.0, 375.0, 5, 0.0, 0.17, 1.87, 0.01, 0.06, 0.00, 0.0, 0.0, "DELIVERY", "EQ", "NSE", "ORD106", "TRD206", "25/05/2024"),
        # ASHOKLEY Round-Trip
        ("ASHOK LEYLAND LTD", "B", 210.0, 0.0, 10, 0.0, 0.20, 2.10, 0.01, 0.07, 0.31, 0.0, 0.0, "DELIVERY", "EQ", "NSE", "ORD107", "TRD207", "22/05/2024"),
        ("ASHOK LEYLAND LTD", "S", 0.0, 205.0, 10, 0.0, 0.19, 2.05, 0.01, 0.07, 0.00, 0.0, 0.0, "DELIVERY", "EQ", "NSE", "ORD108", "TRD208", "30/05/2024"),
        # GAIL Open Position (Buy only)
        ("GAIL (INDIA) LTD", "B", 195.0, 0.0, 9, 0.0, 0.17, 1.75, 0.01, 0.06, 0.26, 0.0, 0.0, "DELIVERY", "EQ", "NSE", "ORD109", "TRD209", "01/06/2024"),
    ]

    for r_idx, row in enumerate(trades_data, start=36):
        for c_idx, val in enumerate(row, start=1):
            ws_trades.cell(row=r_idx, column=c_idx, value=val)

    # -------------------------------------------------------------------------
    # Sheet 2: Tax PNL (Equity+Bonds+SGB Trade Details)
    # -------------------------------------------------------------------------
    ws_tax = wb.create_sheet(title="Equity+Bonds+SGB Trade Details")
    ws_tax["A1"] = "TAX PROFIT & LOSS STATEMENT"
    ws_tax["A2"] = "Client ID: ANGEL_SECRET_UCC_9988 | PAN: ABCDE1234F"

    # Row 20: Delivery P&L Header
    ws_tax["A20"] = "Delivery P&L"
    headers_deliv = [
        "ISIN", "Scrip Name", "Qty", "Buy Date", "Sell Date", "Avg Buy Price", "Buy Value",
        "Avg Sell Price", "Sell Value", "Charges and Statutory Levies", "STT", "Net Profit/Loss"
    ]
    for c_idx, h in enumerate(headers_deliv, start=1):
        ws_tax.cell(row=21, column=c_idx, value=h)

    # 4 Closed Delivery Swings
    delivery_data = [
        ("INE040H01021", "SUZLON ENERGY LTD", 25, "10/05/2024", "15/05/2024", 60.00, 1500.00, 58.50, 1462.50, 0.50, 2.96, -40.96),
        ("INE774D01024", "M&MFIN LTD", 5, "12/05/2024", "20/05/2024", 290.00, 1450.00, 285.00, 1425.00, 0.45, 2.87, -28.32),
        ("INE415G01027", "RVNL LTD", 5, "18/05/2024", "25/05/2024", 380.00, 1900.00, 375.00, 1875.00, 0.55, 3.77, -29.32),
        ("INE208A01029", "ASHOK LEYLAND LTD", 10, "22/05/2024", "30/05/2024", 210.00, 2100.00, 205.00, 2050.00, 0.60, 4.15, -54.75),
    ]
    for r_idx, row in enumerate(delivery_data, start=22):
        for c_idx, val in enumerate(row, start=1):
            ws_tax.cell(row=r_idx, column=c_idx, value=val)

    # Row 43: Open Holdings Table
    ws_tax["A43"] = "Open Holdings"
    headers_open = [
        "ISIN", "Scrip Name", "Quantity", "Avg Buy Price", "Buy Value",
        "Charges and Statutory Levies", "STT", "Closing rate", "Turnover",
        "Short term Unrealised P&L", "Long term Unrealised P&L"
    ]
    for c_idx, h in enumerate(headers_open, start=1):
        ws_tax.cell(row=44, column=c_idx, value=h)

    # GAIL Open Position
    open_data = [
        ("INE129A01019", "GAIL (INDIA) LTD", 9, 195.00, 1755.00, 0.50, 1.75, 192.50, 1732.50, -22.50, 0.0),
    ]
    for r_idx, row in enumerate(open_data, start=45):
        for c_idx, val in enumerate(row, start=1):
            ws_tax.cell(row=r_idx, column=c_idx, value=val)

    # -------------------------------------------------------------------------
    # Sheet 3: Profit & Loss (Equity P&L with official Ticker mappings)
    # -------------------------------------------------------------------------
    ws_pnl = wb.create_sheet(title="Equity P&L")
    ws_pnl["A30"] = "Delivery PnL"
    headers_pnl = [
        "Scrip Symbol", "Company Name", "Quantity", "Avg Buy Price", "Buy Value",
        "Avg Sell Price", "Sell Value", "Gross PnL", "Charges and Statutory Levies", "Net PnL"
    ]
    for c_idx, h in enumerate(headers_pnl, start=1):
        ws_pnl.cell(row=31, column=c_idx, value=h)

    pnl_data = [
        ("SUZLON", "SUZLON ENERGY LTD", 25, 60.0, 1500.0, 58.5, 1462.5, -37.5, 3.46, -40.96),
        ("M&MFIN", "M&MFIN LTD", 5, 290.0, 1450.0, 285.0, 1425.0, -25.0, 3.32, -28.32),
        ("RVNL", "RVNL LTD", 5, 380.0, 1900.0, 375.0, 1875.0, -25.0, 4.32, -29.32),
        ("ASHOKLEY", "ASHOK LEYLAND LTD", 10, 210.0, 2100.0, 205.0, 2050.0, -50.0, 4.75, -54.75),
    ]
    for r_idx, row in enumerate(pnl_data, start=32):
        for c_idx, val in enumerate(row, start=1):
            ws_pnl.cell(row=r_idx, column=c_idx, value=val)

    # -------------------------------------------------------------------------
    # Sheet 4: Statement (Broking Ledger & DP Charges)
    # -------------------------------------------------------------------------
    ws_stmt = wb.create_sheet(title="Broking Ledger")
    ws_stmt["A17"] = "Transaction Details"
    headers_stmt = ["Transaction", "Date", "Segment", "Voucher", "Debit", "Credit", "Running Balance"]
    for c_idx, h in enumerate(headers_stmt, start=1):
        ws_stmt.cell(row=18, column=c_idx, value=h)

    ledger_data = [
        ("Funds Added - UPI/REF998811", "09/05/2024", "EQ", "VOUCH1001", 0.0, 10000.0, 10000.0),
    ]
    for r_idx, row in enumerate(ledger_data, start=19):
        for c_idx, val in enumerate(row, start=1):
            ws_stmt.cell(row=r_idx, column=c_idx, value=val)

    # Charges Sheet (DP Charges breakdown)
    ws_chg = wb.create_sheet(title="Charges")
    ws_chg["A14"] = "DP Charges"
    headers_chg = ["Scrip Name", "ISIN", "Date", "Quantity sold", "CDSL charge", "Angelone charge", "GST", "Total charge"]
    for c_idx, h in enumerate(headers_chg, start=1):
        ws_chg.cell(row=15, column=c_idx, value=h)

    chg_data = [
        ("SUZLON ENERGY LTD", "INE040H01021", "16/05/2024", 25, 3.50, 16.50, 3.60, 23.60),
        ("M&MFIN LTD", "INE774D01024", "21/05/2024", 5, 3.50, 16.50, 3.60, 23.60),
        ("RVNL LTD", "INE415G01027", "26/05/2024", 5, 3.50, 16.50, 3.60, 23.60),
        ("ASHOK LEYLAND LTD", "INE208A01029", "31/05/2024", 10, 3.50, 16.50, 3.60, 23.60),
    ]
    for r_idx, row in enumerate(chg_data, start=16):
        for c_idx, val in enumerate(row, start=1):
            ws_chg.cell(row=r_idx, column=c_idx, value=val)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# =============================================================================
# TEST CASES
# =============================================================================

def test_strict_zero_pii_sanitization(temp_db):
    """
    Asserts that sensitive personal metadata (Client Name, Client Code, PAN, Address,
    Mobile, Email, DP ID) from top rows is completely excluded from database tables
    and decrypted master Excel.
    """
    engine = EncryptedTradebookEngine(temp_db, secret_key="test_secret_key_123")
    raw_bytes = create_synthetic_angel_one_tradebook()

    # Ingest in-memory
    summary = engine.parse_angelone_workbook(raw_bytes)
    assert summary is not None

    # Blacklisted PII strings that must NEVER be found
    pii_blacklist = [
        "ANGEL_SECRET_UCC_9988",
        "SIDDHARTH PRIVACY TEST",
        "ABCDE1234F",
        "Silicon Highway",
        "9876543210",
        "secretmail.com",
        "1203320012345678",
    ]

    # 1. Check all tables in SQLite
    with temp_db.get_connection() as conn:
        for table in ["real_trade_executions", "real_closed_roundtrips", "real_open_holdings", "real_dp_charges", "real_capital_ledger"]:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            for r in rows:
                row_str = " ".join(str(val) for val in r)
                for pii in pii_blacklist:
                    assert pii not in row_str, f"PII leak '{pii}' detected in SQLite table {table}: {row_str}"

    # 2. Check decrypted Excel workbook cells
    decrypted_bytes = engine.export_decrypted_master_excel()
    wb_dec = openpyxl.load_workbook(io.BytesIO(decrypted_bytes), data_only=True)
    for sheet_name in wb_dec.sheetnames:
        sheet = wb_dec[sheet_name]
        for row in sheet.iter_rows(values_only=True):
            for cell_val in row:
                if cell_val is not None:
                    c_str = str(cell_val)
                    for pii in pii_blacklist:
                        assert pii not in c_str, f"PII leak '{pii}' found in sheet '{sheet_name}' cell: {c_str}"


def test_idempotent_deduplication(temp_db):
    """
    Asserts that uploading overlapping reports twice produces zero duplicates
    due to composite unique constraints.
    """
    engine = EncryptedTradebookEngine(temp_db, secret_key="test_secret_key_123")
    raw_bytes = create_synthetic_angel_one_tradebook()

    # Ingest Pass 1
    engine.parse_angelone_workbook(raw_bytes)
    with temp_db.get_connection() as conn:
        exec_count_1 = conn.execute("SELECT COUNT(*) FROM real_trade_executions").fetchone()[0]
        closed_count_1 = conn.execute("SELECT COUNT(*) FROM real_closed_roundtrips").fetchone()[0]
        open_count_1 = conn.execute("SELECT COUNT(*) FROM real_open_holdings").fetchone()[0]
        dp_count_1 = conn.execute("SELECT COUNT(*) FROM real_dp_charges").fetchone()[0]

    assert exec_count_1 == 9
    assert closed_count_1 == 4
    assert open_count_1 == 1
    assert dp_count_1 == 4

    # Ingest Pass 2 (Exact duplicate file)
    engine.parse_angelone_workbook(raw_bytes)
    with temp_db.get_connection() as conn:
        exec_count_2 = conn.execute("SELECT COUNT(*) FROM real_trade_executions").fetchone()[0]
        closed_count_2 = conn.execute("SELECT COUNT(*) FROM real_closed_roundtrips").fetchone()[0]
        open_count_2 = conn.execute("SELECT COUNT(*) FROM real_open_holdings").fetchone()[0]
        dp_count_2 = conn.execute("SELECT COUNT(*) FROM real_dp_charges").fetchone()[0]

    # Counts must remain identical (zero duplicate inflation)
    assert exec_count_2 == exec_count_1
    assert closed_count_2 == closed_count_1
    assert open_count_2 == open_count_1
    assert dp_count_2 == dp_count_1


def test_dp_charge_reconciliation_and_true_net_pnl(temp_db):
    """
    Verifies that the exact ₹23.60 DP fee is attached to each closed delivery swing
    and that True Net P&L = Gross P&L - Trade Taxes - DP Fee.
    """
    engine = EncryptedTradebookEngine(temp_db, secret_key="test_secret_key_123")
    raw_bytes = create_synthetic_angel_one_tradebook()
    summary = engine.parse_angelone_workbook(raw_bytes)

    # 4 closed swings: 4 * 23.60 = 94.40
    assert summary["total_dp_charges"] == 94.40
    assert summary["total_trades"] == 4

    # In our synthetic data:
    # Gross P&L: -37.50 (SUZLON) - 25.00 (M&MFIN) - 25.00 (RVNL) - 50.00 (ASHOKLEY) = -137.50
    # Or as reported in Tax PNL:
    # Each trade has dp_charge = 23.60 attached
    for trade in summary["closed_trades"]:
        assert trade["dp_charge"] == 23.60
        # True Net P&L = Gross P&L - Trade Taxes - DP Fee
        expected_net = round(trade["gross_pnl"] - trade["trade_charges"] - 23.60, 2)
        assert abs(trade["net_pnl"] - expected_net) < 0.05
        assert trade["outcome"] == ("WIN" if trade["net_pnl"] > 0 else "LOSS")


def test_fernet_encryption_and_5_tabs_export(temp_db):
    """
    Verifies that the generated file at data/secure/master_tradebook.enc is encrypted,
    cannot be loaded as plain zip, and decrypts cleanly into 5 styled institutional tabs.
    """
    engine = EncryptedTradebookEngine(temp_db, secret_key="test_secret_key_123")
    raw_bytes = create_synthetic_angel_one_tradebook()
    engine.parse_angelone_workbook(raw_bytes)

    assert os.path.exists(MASTER_ENC_PATH)

    # Ensure disk file is cipher encrypted (not raw zip/xlsx)
    with open(MASTER_ENC_PATH, "rb") as f:
        encrypted_disk_bytes = f.read()

    assert not encrypted_disk_bytes.startswith(b"PK\x03\x04"), "Disk file must NOT be raw unencrypted zip/xlsx"

    # Decrypt in memory
    decrypted_bytes = engine.export_decrypted_master_excel()
    assert decrypted_bytes.startswith(b"PK\x03\x04"), "Decrypted stream must be valid zip/xlsx archive"

    wb = openpyxl.load_workbook(io.BytesIO(decrypted_bytes), data_only=True)
    expected_tabs = [
        "Executive_Summary",
        "Closed_Trades_Ledger",
        "Open_Holdings",
        "Raw_Executions",
        "Scrip_Attribution",
    ]
    for tab in expected_tabs:
        assert tab in wb.sheetnames, f"Tab '{tab}' missing from master Excel"


def test_portfolio_tradebook_api_endpoints():
    """
    Verifies FastAPI endpoints:
    1. POST /api/v1/portfolio/tradebook/upload
    2. GET /api/v1/portfolio/tradebook/summary
    3. GET /api/v1/portfolio/tradebook/export
    """
    client = TestClient(app)
    raw_bytes = create_synthetic_angel_one_tradebook()

    # 1. Upload in-memory
    upload_res = client.post(
        "/api/v1/portfolio/tradebook/upload",
        files=[("files", ("AngelOne_Test_Trades.xlsx", raw_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"))],
        headers={"X-API-Key": "test_auth_bypass"},
    )
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.text}"
    summary_data = upload_res.json()
    assert "total_dp_charges" in summary_data
    assert "closed_trades" in summary_data
    assert "open_holdings" in summary_data

    # 2. Summary GET
    get_res = client.get("/api/v1/portfolio/tradebook/summary")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["total_dp_charges"] >= 94.40

    # 3. Export GET
    export_res = client.get("/api/v1/portfolio/tradebook/export")
    assert export_res.status_code == 200
    assert export_res.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "MIL_Master_Trading_Record.xlsx" in export_res.headers["content-disposition"]
    assert export_res.content.startswith(b"PK\x03\x04")
