import pytest
from pathlib import Path
from src.storage.database import DatabaseManager
from src.client.symbol_resolver import SymbolResolver

def test_symbol_resolver_isin_and_alias(tmp_path: Path):
    db_file = tmp_path / "resolver_test.db"
    db = DatabaseManager(str(db_file))
    
    with db.get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS securities_master (
                symbol TEXT PRIMARY KEY,
                company_name TEXT NOT NULL,
                isin TEXT NOT NULL UNIQUE,
                industry TEXT NOT NULL,
                sector TEXT NOT NULL,
                macro_sector TEXT NOT NULL,
                listing_date TEXT DEFAULT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                is_nifty50 INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
        """)
        conn.execute("""
            INSERT INTO securities_master (
                symbol, company_name, isin, industry, sector, macro_sector, is_active, is_nifty50, updated_at
            ) VALUES (
                'TMPV', 'Tata Motors Passenger Vehicles Ltd', 'INE155A01022', 'Auto Manufacturers',
                'Automobile', 'Consumer Discretionary', 1, 0, '2024-01-01T00:00:00Z'
            );
        """)
        conn.execute("""
            INSERT INTO securities_master (
                symbol, company_name, isin, industry, sector, macro_sector, is_active, is_nifty50, updated_at
            ) VALUES (
                'UNCLASSIFIED_STOCK', 'Some Generic Corp', 'INE999X01019', 'Chemicals Specialty',
                'Basic Materials', 'Equities', 1, 0, '2024-01-01T00:00:00Z'
            );
        """)
        conn.commit()

    resolver = SymbolResolver(db)

    # 1. Direct ISIN resolution
    by_isin = resolver.resolve_by_isin("INE155A01022")
    assert by_isin is not None
    assert by_isin["symbol"] == "TMPV"

    # 2. ISIN string passed into resolve_symbol
    by_sym_isin = resolver.resolve_symbol("INE155A01022")
    assert by_sym_isin["symbol"] == "TMPV"

    # 3. Demerger alias resolution (TATAMOTORS -> TMPV)
    resolved_alias = resolver.resolve_symbol("TATAMOTORS")
    assert resolved_alias["symbol"] == "TMPV"

    # 4. Taxonomy normalization
    updated_count = resolver.normalize_all_securities_taxonomy()
    assert updated_count >= 1

    with db.get_connection() as conn:
        cur = conn.execute("SELECT macro_sector FROM securities_master WHERE symbol = 'UNCLASSIFIED_STOCK'")
        row = cur.fetchone()
        assert row["macro_sector"] == "Basic Materials & Chemicals"
