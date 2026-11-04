import time
import datetime
from src.storage.database import DatabaseManager
from src.client.index_client import IndexClient

def main():
    print("=== Milestone B3.1: Sectoral Indices Ingestion ===")
    t0 = time.time()
    db = DatabaseManager("data/market_lab.db")
    client = IndexClient(db)

    print(f"Indices to sync: {client.SECTORAL_INDICES}")
    res = client.sync_all_sectoral_indices(
        start_date_iso="2024-10-21",
        end_date_iso="2026-10-23",
        delay_seconds=0.4
    )

    print(f"\n--- Ingestion Complete in {time.time() - t0:.2f}s ---")
    print(f"Indices synced: {res['indices_synced']}")
    print(f"Total PRI synced: {res['total_pri_synced']}")
    print(f"Total TRI synced: {res['total_tri_synced']}")

    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT index_name, index_type, COUNT(*), MIN(trading_date), MAX(trading_date),
                   SUM(CASE WHEN open IS NULL AND high IS NULL AND low IS NULL THEN 1 ELSE 0 END) as null_ohl_count
            FROM index_daily
            GROUP BY index_name, index_type
            ORDER BY index_name, index_type
        """)
        rows = c.fetchall()
        print("\n--- Current index_daily State ---")
        for r in rows:
            print(f"{r[0]:25} | {r[1]:3} | Count: {r[2]:3} | Range: {r[3]} to {r[4]} | Null OH&L: {r[5]}")

if __name__ == "__main__":
    main()
