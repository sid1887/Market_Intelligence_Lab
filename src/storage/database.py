import sqlite3
import os
import re
import json
import math
import uuid
import datetime
from typing import List, Dict, Any, Optional

class DatabaseManager:
    """Manages SQLite database connections, additive schema migrations, and transactional persistence."""

    def __init__(self, db_path: str = "data/market_lab.db"):
        self.db_path = db_path
        self._mem_conn: Optional[sqlite3.Connection] = None
        if self.db_path == ":memory:":
            self._mem_conn = sqlite3.connect(":memory:")
            self._mem_conn.row_factory = sqlite3.Row
            self.init_schema()
        else:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
            self.init_schema()

    def get_connection(self) -> sqlite3.Connection:
        if self._mem_conn is not None:
            return self._mem_conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def get_readonly_connection(self) -> sqlite3.Connection:
        """Returns a strictly read-only SQLite connection (ADR-0011, P0-08)."""
        if self._mem_conn is not None:
            return self._mem_conn
        abs_path = os.path.abspath(self.db_path)
        conn = sqlite3.connect(f"file:{abs_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        """Applies base Phase 1 schema, Phase 2 migration, and safe column alterations."""
        schema_dir = os.path.dirname(__file__)
        schema_v1_path = os.path.join(schema_dir, "schema.sql")
        schema_v2_path = os.path.join(schema_dir, "schema_v2.sql")
        schema_v3_path = os.path.join(schema_dir, "schema_v3.sql")

        with self.get_connection() as conn:
            # 1. Base Phase 1 Schema
            if os.path.exists(schema_v1_path):
                with open(schema_v1_path, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())

            # 2. Safe additive column alterations on ohlcv_daily
            cursor = conn.execute("PRAGMA table_info(ohlcv_daily);")
            existing_cols = {row["name"] for row in cursor.fetchall()}
            if "trades_count" not in existing_cols:
                conn.execute("ALTER TABLE ohlcv_daily ADD COLUMN trades_count INTEGER DEFAULT NULL;")
            if "data_status" not in existing_cols:
                conn.execute("ALTER TABLE ohlcv_daily ADD COLUMN data_status TEXT NOT NULL DEFAULT 'final_settled';")

            # 3. Phase 2 Schema Extension
            if os.path.exists(schema_v2_path):
                with open(schema_v2_path, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())

            # 3b. Phase 3 / Milestone B5 Schema Extension
            if os.path.exists(schema_v3_path):
                with open(schema_v3_path, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())

            # 4. Safe additive column alterations on corporate_disclosures
            cursor = conn.execute("PRAGMA table_info(corporate_disclosures);")
            disc_cols = {row["name"] for row in cursor.fetchall()}
            if disc_cols:
                if "verification_status" not in disc_cols:
                    conn.execute("ALTER TABLE corporate_disclosures ADD COLUMN verification_status TEXT NOT NULL DEFAULT 'PENDING_VERIFICATION';")
                if "audit_status" not in disc_cols:
                    conn.execute("ALTER TABLE corporate_disclosures ADD COLUMN audit_status TEXT DEFAULT NULL;")
                if "dividend_declared" not in disc_cols:
                    conn.execute("ALTER TABLE corporate_disclosures ADD COLUMN dividend_declared REAL DEFAULT NULL;")
                if "operating_margin_pct" not in disc_cols:
                    conn.execute("ALTER TABLE corporate_disclosures ADD COLUMN operating_margin_pct REAL DEFAULT NULL;")
                if "revenue_inr_crore" not in disc_cols:
                    conn.execute("ALTER TABLE corporate_disclosures ADD COLUMN revenue_inr_crore REAL DEFAULT NULL;")
                if "revenue_growth_yoy_cc" not in disc_cols:
                    conn.execute("ALTER TABLE corporate_disclosures ADD COLUMN revenue_growth_yoy_cc REAL DEFAULT NULL;")
                if "revenue_growth_qoq_cc" not in disc_cols:
                    conn.execute("ALTER TABLE corporate_disclosures ADD COLUMN revenue_growth_qoq_cc REAL DEFAULT NULL;")
                if "revenue_growth_yoy_reported" not in disc_cols:
                    conn.execute("ALTER TABLE corporate_disclosures ADD COLUMN revenue_growth_yoy_reported REAL DEFAULT NULL;")
                if "source_timestamp_basis" not in disc_cols:
                    conn.execute("ALTER TABLE corporate_disclosures ADD COLUMN source_timestamp_basis TEXT DEFAULT NULL;")

            # 5. Schema safeguard: Ensure corporate_disclosures defaults to 'PENDING_VERIFICATION' at SQLite level
            cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='corporate_disclosures';")
            tbl_sql_row = cursor.fetchone()
            if tbl_sql_row and "DEFAULT 'VERIFIED'" in tbl_sql_row[0]:
                self._migrate_corporate_disclosures_default(conn)

            # 6. Safe additive column alterations on corporate_actions
            cursor = conn.execute("PRAGMA table_info(corporate_actions);")
            ca_cols = {row["name"] for row in cursor.fetchall()}
            if ca_cols:
                if "id" not in ca_cols:
                    conn.execute("ALTER TABLE corporate_actions ADD COLUMN id TEXT DEFAULT NULL;")
                if "announcement_date" not in ca_cols:
                    conn.execute("ALTER TABLE corporate_actions ADD COLUMN announcement_date TEXT DEFAULT NULL;")
                if "effective_date" not in ca_cols:
                    conn.execute("ALTER TABLE corporate_actions ADD COLUMN effective_date TEXT DEFAULT NULL;")
                if "face_value" not in ca_cols:
                    conn.execute("ALTER TABLE corporate_actions ADD COLUMN face_value REAL DEFAULT NULL;")
                if "adjustment_ratio" not in ca_cols:
                    conn.execute("ALTER TABLE corporate_actions ADD COLUMN adjustment_ratio REAL DEFAULT NULL;")
                cursor_null = conn.execute("SELECT rowid, symbol, action_type, ex_date, purpose FROM corporate_actions WHERE id IS NULL;")
                null_rows = cursor_null.fetchall()
                if null_rows:
                    import hashlib
                    for r_rowid, r_sym, r_act, r_ex, r_purp in null_rows:
                        purp_h = hashlib.md5(str(r_purp).encode("utf-8")).hexdigest()[:8]
                        gen_id = f"{r_sym}_{r_act}_{r_ex}_{purp_h}"
                        conn.execute("UPDATE corporate_actions SET id = ?, adjustment_ratio = COALESCE(adjustment_factor, 1.0) WHERE rowid = ?", (gen_id, r_rowid))
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_ca_id ON corporate_actions(id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ca_action_type ON corporate_actions(action_type);")

            # 6b. Safe additive column alterations on corporate_disclosures
            cursor = conn.execute("PRAGMA table_info(corporate_disclosures);")
            disc_cols = {row["name"] for row in cursor.fetchall()}
            if disc_cols:
                if "id" not in disc_cols:
                    conn.execute("ALTER TABLE corporate_disclosures ADD COLUMN id TEXT DEFAULT NULL;")
                conn.execute("""
                    UPDATE corporate_disclosures
                    SET id = disclosure_id
                    WHERE id IS NULL;
                """)
                conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cd_id ON corporate_disclosures(id);")

            # 7. Safe primary key migration on corporate_actions to include purpose
            self._migrate_corporate_actions_pk(conn)

            # 8. Safe additive column alterations on quant_factors_daily (Milestone B4.1)
            cursor = conn.execute("PRAGMA table_info(quant_factors_daily);")
            qf_cols = {row["name"] for row in cursor.fetchall()}
            if qf_cols:
                if "volatility_annualized" not in qf_cols:
                    conn.execute("ALTER TABLE quant_factors_daily ADD COLUMN volatility_annualized REAL DEFAULT NULL;")
                if "ttm_pe" not in qf_cols:
                    conn.execute("ALTER TABLE quant_factors_daily ADD COLUMN ttm_pe REAL DEFAULT NULL;")
                if "roe_pct" not in qf_cols:
                    conn.execute("ALTER TABLE quant_factors_daily ADD COLUMN roe_pct REAL DEFAULT NULL;")
                if "debt_to_equity" not in qf_cols:
                    conn.execute("ALTER TABLE quant_factors_daily ADD COLUMN debt_to_equity REAL DEFAULT NULL;")
                if "opm_pct" not in qf_cols:
                    conn.execute("ALTER TABLE quant_factors_daily ADD COLUMN opm_pct REAL DEFAULT NULL;")
                if "updated_at" not in qf_cols:
                    conn.execute("ALTER TABLE quant_factors_daily ADD COLUMN updated_at TEXT DEFAULT NULL;")
                conn.execute("""
                    UPDATE quant_factors_daily
                    SET volatility_annualized = vol_20d_annualized
                    WHERE volatility_annualized IS NULL AND vol_20d_annualized IS NOT NULL;
                """)

            # 9. Ensure user_watchlists table exists (Milestone B4.3)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_watchlists (
                    symbol TEXT PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    sector TEXT NOT NULL,
                    added_date TEXT NOT NULL,
                    target_price REAL DEFAULT NULL,
                    stop_loss REAL DEFAULT NULL,
                    notes TEXT DEFAULT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_watchlist_sector ON user_watchlists(sector);")

            # 10. Safe additive column alterations on securities_master (Milestone B6.4)
            cursor = conn.execute("PRAGMA table_info(securities_master);")
            sec_cols = {row["name"] for row in cursor.fetchall()}
            if sec_cols and "is_nifty50" not in sec_cols:
                conn.execute("ALTER TABLE securities_master ADD COLUMN is_nifty50 INTEGER NOT NULL DEFAULT 0;")

            # 11. Run Numbered Migrations & Truth Quarantine (P1-01, ADR-0011)
            try:
                from src.storage.migrations import run_all_migrations
                run_all_migrations(conn)
            except Exception as e:
                # In in-memory or minimal test contexts, log and continue
                pass

    def _migrate_corporate_actions_pk(self, conn: sqlite3.Connection) -> None:
        """Migrates corporate_actions table so PRIMARY KEY includes purpose (symbol, action_type, ex_date, purpose)."""
        cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='corporate_actions';")
        tbl_sql_row = cursor.fetchone()
        if tbl_sql_row and "PRIMARY KEY" in tbl_sql_row[0]:
            pk_part = tbl_sql_row[0].split("PRIMARY KEY")[1]
            if "purpose" not in pk_part:
                conn.execute("PRAGMA foreign_keys = OFF;")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS corporate_actions_migrated (
                        symbol TEXT NOT NULL,
                        action_type TEXT NOT NULL,
                        ex_date TEXT NOT NULL,
                        record_date TEXT DEFAULT NULL,
                        announcement_date TEXT DEFAULT NULL,
                        effective_date TEXT DEFAULT NULL,
                        purpose TEXT NOT NULL,
                        adjustment_factor REAL DEFAULT 1.0,
                        source TEXT NOT NULL,
                        retrieval_timestamp TEXT NOT NULL,
                        PRIMARY KEY (symbol, action_type, ex_date, purpose)
                    );
                """)
                conn.execute("""
                    INSERT OR IGNORE INTO corporate_actions_migrated (
                        symbol, action_type, ex_date, record_date, announcement_date,
                        effective_date, purpose, adjustment_factor, source, retrieval_timestamp
                    )
                    SELECT 
                        symbol, action_type, ex_date, record_date, announcement_date,
                        effective_date, purpose, adjustment_factor, source, retrieval_timestamp
                    FROM corporate_actions;
                """)
                conn.execute("DROP TABLE corporate_actions;")
                conn.execute("ALTER TABLE corporate_actions_migrated RENAME TO corporate_actions;")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ca_symbol_exdate ON corporate_actions(symbol, ex_date);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ca_action_type ON corporate_actions(action_type);")
                conn.execute("PRAGMA foreign_keys = ON;")

    def _migrate_corporate_disclosures_default(self, conn: sqlite3.Connection) -> None:
        """Migrates corporate_disclosures table so verification_status defaults to PENDING_VERIFICATION."""
        conn.execute("PRAGMA foreign_keys = OFF;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS corporate_disclosures_migrated (
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
        conn.execute("""
            INSERT INTO corporate_disclosures_migrated (
                disclosure_id, symbol, broadcast_timestamp, effective_session_date,
                category, subject, details_summary, source_url, retrieval_timestamp,
                verification_status, audit_status, dividend_declared, operating_margin_pct,
                revenue_inr_crore, revenue_growth_yoy_cc, revenue_growth_qoq_cc,
                revenue_growth_yoy_reported, source_timestamp_basis
            )
            SELECT 
                disclosure_id, symbol, broadcast_timestamp, effective_session_date,
                category, subject, details_summary, source_url, retrieval_timestamp,
                verification_status, audit_status, dividend_declared, operating_margin_pct,
                revenue_inr_crore, revenue_growth_yoy_cc, revenue_growth_qoq_cc,
                revenue_growth_yoy_reported, source_timestamp_basis
            FROM corporate_disclosures;
        """)
        conn.execute("DROP TABLE corporate_disclosures;")
        conn.execute("ALTER TABLE corporate_disclosures_migrated RENAME TO corporate_disclosures;")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_disc_symbol_session ON corporate_disclosures(symbol, effective_session_date);")
        conn.execute("PRAGMA foreign_keys = ON;")

    def upsert_ohlcv_records(self, records: List[Dict[str, Any]]) -> int:
        """
        Upserts validated OHLCV records.
        Unavailable fields (such as delivery_qty or trades_count) are stored as NULL.
        """
        if not records:
            return 0

        # Normalize optional fields so sqlite3 binding parameters are never missing
        normalized = []
        for r in records:
            item = dict(r)
            if "ltp" not in item:
                item["ltp"] = None
            if "prev_close" not in item:
                item["prev_close"] = None
            if "turnover" not in item:
                item["turnover"] = None
            if "delivery_qty" not in item:
                item["delivery_qty"] = None
            if "trades_count" not in item:
                item["trades_count"] = None
            if "data_status" not in item:
                item["data_status"] = "final_settled"
            normalized.append(item)

        sql = """
        INSERT INTO ohlcv_daily (
            symbol, trading_date, series, open, high, low, close,
            ltp, prev_close, volume, turnover, delivery_qty,
            source, retrieval_timestamp, trades_count, data_status
        ) VALUES (
            :symbol, :trading_date, :series, :open, :high, :low, :close,
            :ltp, :prev_close, :volume, :turnover, :delivery_qty,
            :source, :retrieval_timestamp, :trades_count, :data_status
        )
        ON CONFLICT(symbol, trading_date, series) DO UPDATE SET
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            ltp = excluded.ltp,
            prev_close = excluded.prev_close,
            volume = excluded.volume,
            turnover = excluded.turnover,
            delivery_qty = excluded.delivery_qty,
            source = excluded.source,
            retrieval_timestamp = excluded.retrieval_timestamp,
            trades_count = excluded.trades_count,
            data_status = excluded.data_status
        WHERE ohlcv_daily.data_status != 'final_settled' OR excluded.data_status = 'final_settled';
        """

        with self.get_connection() as conn:
            cursor = conn.executemany(sql, normalized)
            return cursor.rowcount

    def upsert_corporate_actions(self, actions: List[Dict[str, Any]]) -> int:
        if not actions:
            return 0

        normalized = []
        for a in actions:
            item = dict(a)
            if "record_date" not in item:
                item["record_date"] = None
            if "announcement_date" not in item:
                item["announcement_date"] = None
            if "effective_date" not in item:
                item["effective_date"] = None
            if "face_value" not in item:
                item["face_value"] = None
            if "adjustment_ratio" not in item or item["adjustment_ratio"] is None:
                item["adjustment_ratio"] = item.get("adjustment_factor", 1.0)
            if "adjustment_factor" not in item or item["adjustment_factor"] is None:
                item["adjustment_factor"] = item.get("adjustment_ratio", 1.0)
            if "id" not in item or not item["id"]:
                import hashlib
                purp_hash = hashlib.md5(str(item.get("purpose", "")).encode("utf-8")).hexdigest()[:8]
                item["id"] = f"{item['symbol']}_{item['action_type']}_{item['ex_date']}_{purp_hash}"
            normalized.append(item)

        sql = """
        INSERT INTO corporate_actions (
            id, symbol, action_type, ex_date, record_date, purpose,
            adjustment_factor, adjustment_ratio, face_value, source,
            retrieval_timestamp, announcement_date, effective_date
        ) VALUES (
            :id, :symbol, :action_type, :ex_date, :record_date, :purpose,
            :adjustment_factor, :adjustment_ratio, :face_value, :source,
            :retrieval_timestamp, :announcement_date, :effective_date
        )
        ON CONFLICT(id) DO UPDATE SET
            record_date = excluded.record_date,
            face_value = excluded.face_value,
            adjustment_ratio = excluded.adjustment_ratio,
            adjustment_factor = excluded.adjustment_factor,
            purpose = excluded.purpose,
            source = excluded.source,
            retrieval_timestamp = excluded.retrieval_timestamp,
            announcement_date = excluded.announcement_date,
            effective_date = excluded.effective_date;
        """
        with self.get_connection() as conn:
            cursor = conn.executemany(sql, normalized)
            return cursor.rowcount

    def record_audit_log(
        self,
        source: str,
        endpoint: str,
        symbol: str,
        date_range_start: Optional[str],
        date_range_end: Optional[str],
        records_retrieved: int,
        records_accepted: int,
        records_rejected: int,
        validation_summary: Any,
        raw_payload_path: str,
        status: str,
        created_at: Optional[str] = None
    ) -> int:
        if created_at is None:
            created_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if isinstance(validation_summary, (dict, list)):
            validation_summary = json.dumps(validation_summary)
        sql = """
        INSERT INTO ingestion_audit_log (
            source, endpoint, symbol, date_range_start, date_range_end,
            records_retrieved, records_accepted, records_rejected,
            validation_summary, raw_payload_path, status, created_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        );
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (
                source, endpoint, symbol, date_range_start, date_range_end,
                records_retrieved, records_accepted, records_rejected,
                json.dumps(validation_summary), raw_payload_path, status, created_at
            ))
            return cursor.lastrowid

    def get_stock_history(
        self,
        symbol: str,
        series: str = "EQ",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM ohlcv_daily WHERE symbol = ? AND series = ?"
        params: List[Any] = [symbol, series]

        if start_date:
            query += " AND trading_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND trading_date <= ?"
            params.append(end_date)

        query += " ORDER BY trading_date ASC;"

        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_corporate_actions(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        action_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM corporate_actions WHERE 1=1"
        params: List[Any] = []

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if start_date:
            query += " AND ex_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND ex_date <= ?"
            params.append(end_date)
        if action_type:
            query += " AND action_type = ?"
            params.append(action_type)

        query += " ORDER BY ex_date ASC;"

        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    # -------------------------------------------------------------
    # Phase 2 Extension Methods
    # -------------------------------------------------------------

    def upsert_securities_master(self, securities: List[Dict[str, Any]]) -> int:
        if not securities:
            return 0
        clean_records = []
        for s in securities:
            rec = dict(s)
            if "is_nifty50" not in rec:
                rec["is_nifty50"] = 0
            clean_records.append(rec)
        sql = """
        INSERT INTO securities_master (
            symbol, company_name, isin, industry, sector, macro_sector, listing_date, is_active, is_nifty50, updated_at
        ) VALUES (
            :symbol, :company_name, :isin, :industry, :sector, :macro_sector, :listing_date, :is_active, :is_nifty50, :updated_at
        )
        ON CONFLICT(symbol) DO UPDATE SET
            company_name = excluded.company_name,
            isin = excluded.isin,
            industry = excluded.industry,
            sector = excluded.sector,
            macro_sector = excluded.macro_sector,
            listing_date = excluded.listing_date,
            is_active = excluded.is_active,
            is_nifty50 = excluded.is_nifty50,
            updated_at = excluded.updated_at;
        """
        with self.get_connection() as conn:
            cursor = conn.executemany(sql, clean_records)
            return cursor.rowcount

    def get_securities_master(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM securities_master"
        params: List[Any] = []
        if symbol:
            query += " WHERE symbol = ?"
            params.append(symbol)
        query += " ORDER BY symbol ASC;"
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def upsert_user_watchlist(self, watchlists: List[Dict[str, Any]]) -> int:
        """
        Upserts user watchlist equities (Milestone B4.3).
        """
        if not watchlists:
            return 0
        sql = """
        INSERT INTO user_watchlists (
            symbol, company_name, sector, added_date, target_price, stop_loss, notes
        ) VALUES (
            :symbol, :company_name, :sector, :added_date, :target_price, :stop_loss, :notes
        )
        ON CONFLICT(symbol) DO UPDATE SET
            company_name = excluded.company_name,
            sector = excluded.sector,
            added_date = excluded.added_date,
            target_price = excluded.target_price,
            stop_loss = excluded.stop_loss,
            notes = excluded.notes;
        """
        with self.get_connection() as conn:
            cursor = conn.executemany(sql, watchlists)
            return cursor.rowcount

    def get_user_watchlists(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieves user watchlist records.
        """
        query = "SELECT * FROM user_watchlists"
        params: List[Any] = []
        if symbol:
            query += " WHERE symbol = ?"
            params.append(symbol)
        query += " ORDER BY symbol ASC;"
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def upsert_index_membership_history(self, records: List[Dict[str, Any]]) -> int:
        if not records:
            return 0
        sql = """
        INSERT INTO index_membership_history (
            symbol, index_name, valid_from, valid_to, is_verified_historical, source, retrieved_at
        ) VALUES (
            :symbol, :index_name, :valid_from, :valid_to, :is_verified_historical, :source, :retrieved_at
        )
        ON CONFLICT(symbol, index_name, valid_from) DO UPDATE SET
            valid_to = excluded.valid_to,
            is_verified_historical = excluded.is_verified_historical,
            source = excluded.source,
            retrieved_at = excluded.retrieved_at;
        """
        with self.get_connection() as conn:
            cursor = conn.executemany(sql, records)
            return cursor.rowcount

    def get_index_constituents(self, index_name: str, as_of_date: str) -> Dict[str, Any]:
        """
        Retrieves point-in-time index constituents as of a given date.
        Detects whether any returned constituent uses unverified proxy membership.
        """
        sql = """
        SELECT symbol, is_verified_historical, source
        FROM index_membership_history
        WHERE index_name = ?
          AND valid_from <= ?
          AND (valid_to IS NULL OR valid_to > ?)
        ORDER BY symbol ASC;
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (index_name, as_of_date, as_of_date))
            rows = [dict(r) for r in cursor.fetchall()]

        if not rows:
            return {
                "index_name": index_name,
                "as_of_date": as_of_date,
                "count": 0,
                "constituents": [],
                "is_survivorship_bias_free": False,
                "membership_basis": "empty_or_unindexed",
                "warning": f"No constituents indexed for {index_name} as of {as_of_date}."
            }

        symbols = [r["symbol"] for r in rows]
        all_verified = all(r["is_verified_historical"] == 1 for r in rows)
        membership_basis = "survivorship_bias_free" if all_verified else "current_proxy_unadjusted"
        warning = None
        if not all_verified:
            warning = (
                f"Historical index membership for {index_name} on {as_of_date} contains proxy observations "
                "(membership_basis: current_proxy_unadjusted). Results may exhibit survivorship bias."
            )

        return {
            "index_name": index_name,
            "as_of_date": as_of_date,
            "count": len(symbols),
            "constituents": symbols,
            "is_survivorship_bias_free": all_verified,
            "membership_basis": membership_basis,
            "warning": warning
        }

    def upsert_index_daily(self, records: List[Dict[str, Any]]) -> int:
        """
        Upserts daily index series.
        For TRI records, open, high, and low are stored as NULL (None), never fabricated.
        """
        if not records:
            return 0

        normalized = []
        for r in records:
            item = dict(r)
            if "open" not in item:
                item["open"] = None
            if "high" not in item:
                item["high"] = None
            if "low" not in item:
                item["low"] = None
            if "volume" not in item:
                item["volume"] = None
            if "pe_ratio" not in item:
                item["pe_ratio"] = None
            if "pb_ratio" not in item:
                item["pb_ratio"] = None
            if "div_yield" not in item:
                item["div_yield"] = None
            normalized.append(item)

        sql = """
        INSERT INTO index_daily (
            index_name, trading_date, index_type, open, high, low, close,
            volume, pe_ratio, pb_ratio, div_yield, source, retrieval_timestamp
        ) VALUES (
            :index_name, :trading_date, :index_type, :open, :high, :low, :close,
            :volume, :pe_ratio, :pb_ratio, :div_yield, :source, :retrieval_timestamp
        )
        ON CONFLICT(index_name, trading_date, index_type) DO UPDATE SET
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            volume = excluded.volume,
            pe_ratio = excluded.pe_ratio,
            pb_ratio = excluded.pb_ratio,
            div_yield = excluded.div_yield,
            source = excluded.source,
            retrieval_timestamp = excluded.retrieval_timestamp;
        """
        with self.get_connection() as conn:
            cursor = conn.executemany(sql, normalized)
            return cursor.rowcount

    def get_index_history(
        self,
        index_name: str,
        index_type: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM index_daily WHERE index_name = ? AND index_type = ?"
        params: List[Any] = [index_name, index_type.upper()]

        if start_date:
            query += " AND trading_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND trading_date <= ?"
            params.append(end_date)

        query += " ORDER BY trading_date ASC;"

        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def upsert_quant_factors(self, factors: List[Dict[str, Any]]) -> int:
        """
        Upserts calculated daily quantitative factors and fundamental ratios.
        Rolling factors and fundamental ratios with incomplete warm-up windows
        or pending filings are permitted as NULL.
        """
        if not factors:
            return 0

        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        sanitized = []
        for f in factors:
            row = dict(f)
            # Default optional technical and fundamental fields if missing
            row.setdefault("ret_1d", 0.0)
            row.setdefault("ret_5d", None)
            row.setdefault("ret_20d", None)
            vol_val = row.get("volatility_annualized")
            if vol_val is None:
                vol_val = row.get("vol_20d_annualized")
            row.setdefault("vol_20d_annualized", vol_val)
            row.setdefault("volatility_annualized", vol_val)
            row.setdefault("sma_20", None)
            row.setdefault("sma_50", None)
            row.setdefault("sma_200", None)
            row.setdefault("beta_60d_nifty", None)
            row.setdefault("volume_ratio_20d", None)
            row.setdefault("volume_zscore_50d", None)
            row.setdefault("volume_log_zscore_50d", None)
            row.setdefault("is_volume_spike_ratio", 0)
            row.setdefault("is_volume_spike_zscore", 0)
            row.setdefault("distance_52w_high", None)
            row.setdefault("distance_52w_low", None)
            row.setdefault("ttm_pe", None)
            row.setdefault("roe_pct", None)
            row.setdefault("debt_to_equity", None)
            row.setdefault("opm_pct", None)
            row.setdefault("updated_at", now_ts)
            sanitized.append(row)

        sql = """
        INSERT INTO quant_factors_daily (
            symbol, trading_date, ret_1d, ret_5d, ret_20d, vol_20d_annualized,
            volatility_annualized, sma_20, sma_50, sma_200, beta_60d_nifty,
            volume_ratio_20d, volume_zscore_50d, volume_log_zscore_50d,
            is_volume_spike_ratio, is_volume_spike_zscore,
            distance_52w_high, distance_52w_low,
            ttm_pe, roe_pct, debt_to_equity, opm_pct, updated_at
        ) VALUES (
            :symbol, :trading_date, :ret_1d, :ret_5d, :ret_20d, :vol_20d_annualized,
            :volatility_annualized, :sma_20, :sma_50, :sma_200, :beta_60d_nifty,
            :volume_ratio_20d, :volume_zscore_50d, :volume_log_zscore_50d,
            :is_volume_spike_ratio, :is_volume_spike_zscore,
            :distance_52w_high, :distance_52w_low,
            :ttm_pe, :roe_pct, :debt_to_equity, :opm_pct, :updated_at
        )
        ON CONFLICT(symbol, trading_date) DO UPDATE SET
            ret_1d = excluded.ret_1d,
            ret_5d = excluded.ret_5d,
            ret_20d = excluded.ret_20d,
            vol_20d_annualized = excluded.vol_20d_annualized,
            volatility_annualized = excluded.volatility_annualized,
            sma_20 = excluded.sma_20,
            sma_50 = excluded.sma_50,
            sma_200 = excluded.sma_200,
            beta_60d_nifty = excluded.beta_60d_nifty,
            volume_ratio_20d = excluded.volume_ratio_20d,
            volume_zscore_50d = excluded.volume_zscore_50d,
            volume_log_zscore_50d = excluded.volume_log_zscore_50d,
            is_volume_spike_ratio = excluded.is_volume_spike_ratio,
            is_volume_spike_zscore = excluded.is_volume_spike_zscore,
            distance_52w_high = excluded.distance_52w_high,
            distance_52w_low = excluded.distance_52w_low,
            ttm_pe = excluded.ttm_pe,
            roe_pct = excluded.roe_pct,
            debt_to_equity = excluded.debt_to_equity,
            opm_pct = excluded.opm_pct,
            updated_at = excluded.updated_at;
        """
        with self.get_connection() as conn:
            cursor = conn.executemany(sql, sanitized)
            return cursor.rowcount

    def upsert_quant_factors_daily(self, factors: List[Dict[str, Any]]) -> int:
        """Alias for upsert_quant_factors."""
        return self.upsert_quant_factors(factors)

    def get_quant_factors(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM quant_factors_daily WHERE symbol = ?"
        params: List[Any] = [symbol]

        if start_date:
            query += " AND trading_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND trading_date <= ?"
            params.append(end_date)

        query += " ORDER BY trading_date ASC;"

        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def upsert_corporate_disclosures(self, disclosures: List[Dict[str, Any]]) -> int:
        if not disclosures:
            return 0

        normalized = []
        for d in disclosures:
            item = dict(d)
            if "id" not in item or not item["id"]:
                item["id"] = item.get("disclosure_id")
            if "disclosure_id" not in item or not item["disclosure_id"]:
                item["disclosure_id"] = item.get("id")
            if "details_summary" not in item:
                item["details_summary"] = None
            if "source_url" not in item:
                item["source_url"] = None
            if "verification_status" not in item or not item["verification_status"]:
                item["verification_status"] = "PENDING_VERIFICATION"
            if "audit_status" not in item:
                item["audit_status"] = None
            if "dividend_declared" not in item:
                item["dividend_declared"] = None
            if "operating_margin_pct" not in item:
                item["operating_margin_pct"] = None
            if "revenue_inr_crore" not in item:
                item["revenue_inr_crore"] = None
            if "revenue_growth_yoy_cc" not in item:
                item["revenue_growth_yoy_cc"] = None
            if "revenue_growth_qoq_cc" not in item:
                item["revenue_growth_qoq_cc"] = None
            if "revenue_growth_yoy_reported" not in item:
                item["revenue_growth_yoy_reported"] = None
            if "source_timestamp_basis" not in item:
                item["source_timestamp_basis"] = None
            normalized.append(item)

        sql = """
        INSERT INTO corporate_disclosures (
            id, disclosure_id, symbol, broadcast_timestamp, effective_session_date,
            category, subject, details_summary, source_url, retrieval_timestamp,
            verification_status, audit_status, dividend_declared, operating_margin_pct,
            revenue_inr_crore, revenue_growth_yoy_cc, revenue_growth_qoq_cc,
            revenue_growth_yoy_reported, source_timestamp_basis
        ) VALUES (
            :id, :disclosure_id, :symbol, :broadcast_timestamp, :effective_session_date,
            :category, :subject, :details_summary, :source_url, :retrieval_timestamp,
            :verification_status, :audit_status, :dividend_declared, :operating_margin_pct,
            :revenue_inr_crore, :revenue_growth_yoy_cc, :revenue_growth_qoq_cc,
            :revenue_growth_yoy_reported, :source_timestamp_basis
        )
        ON CONFLICT(id) DO UPDATE SET
            disclosure_id = excluded.disclosure_id,
            symbol = excluded.symbol,
            broadcast_timestamp = excluded.broadcast_timestamp,
            effective_session_date = excluded.effective_session_date,
            category = excluded.category,
            subject = excluded.subject,
            details_summary = excluded.details_summary,
            source_url = excluded.source_url,
            retrieval_timestamp = excluded.retrieval_timestamp,
            verification_status = excluded.verification_status,
            audit_status = excluded.audit_status,
            dividend_declared = excluded.dividend_declared,
            operating_margin_pct = excluded.operating_margin_pct,
            revenue_inr_crore = excluded.revenue_inr_crore,
            revenue_growth_yoy_cc = excluded.revenue_growth_yoy_cc,
            revenue_growth_qoq_cc = excluded.revenue_growth_qoq_cc,
            revenue_growth_yoy_reported = excluded.revenue_growth_yoy_reported,
            source_timestamp_basis = excluded.source_timestamp_basis;
        """
        with self.get_connection() as conn:
            cursor = conn.executemany(sql, normalized)
            return cursor.rowcount

    def get_corporate_disclosures(
        self,
        symbol: Optional[str] = None,
        verification_status: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM corporate_disclosures"
        clauses = []
        params = []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if verification_status:
            clauses.append("verification_status = ?")
            params.append(verification_status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY effective_session_date ASC, broadcast_timestamp ASC;"
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def record_event_study_result(self, result: Dict[str, Any]) -> int:
        sql = """
        INSERT INTO event_study_results (
            symbol, disclosure_id, event_date, estimation_window_start,
            estimation_window_end, model_alpha, model_beta, model_r2,
            ar_t0, car_minus1_plus1, car_0_plus2, t_stat, p_value,
            explanatory_hypothesis, calculated_at
        ) VALUES (
            :symbol, :disclosure_id, :event_date, :estimation_window_start,
            :estimation_window_end, :model_alpha, :model_beta, :model_r2,
            :ar_t0, :car_minus1_plus1, :car_0_plus2, :t_stat, :p_value,
            :explanatory_hypothesis, :calculated_at
        );
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, result)
            return cursor.lastrowid

    def get_event_study_results(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM event_study_results"
        params: List[Any] = []
        if symbol:
            query += " WHERE symbol = ?"
            params.append(symbol)
        query += " ORDER BY study_id DESC;"
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    # -------------------------------------------------------------
    # Milestone B4: Company Financial Statements & Fundamental Factors
    # -------------------------------------------------------------

    def upsert_financial_statements(self, statements: List[Dict[str, Any]]) -> int:
        if not statements:
            return 0

        normalized = []
        for s in statements:
            item = dict(s)
            item.setdefault("fiscal_quarter", None)
            item.setdefault("publication_date", None)
            item.setdefault("broadcast_timestamp", None)
            item.setdefault("effective_session_date", None)
            item.setdefault("source_timestamp_basis", "EXACT_EXCHANGE_TIMESTAMP")
            item.setdefault("is_pit_eligible", 1)
            item.setdefault("statement_version", 1)
            item.setdefault("audit_status", "UNAUDITED")
            item.setdefault("currency", "INR")
            item.setdefault("unit", "CRORE")
            item.setdefault("revenue_operations", None)
            item.setdefault("other_income", None)
            item.setdefault("total_revenue", None)
            item.setdefault("operating_expenses", None)
            item.setdefault("ebitda", None)
            item.setdefault("ebit", None)
            item.setdefault("finance_costs", None)
            item.setdefault("depreciation_amortization", None)
            item.setdefault("profit_before_tax", None)
            item.setdefault("tax_expense", None)
            item.setdefault("net_profit", None)
            item.setdefault("basic_eps", None)
            item.setdefault("diluted_eps", None)
            item.setdefault("total_equity", None)
            item.setdefault("total_debt", None)
            item.setdefault("cash_and_equivalents", None)
            item.setdefault("total_assets", None)
            item.setdefault("shares_outstanding", None)
            item.setdefault("source_url", None)
            item.setdefault("verification_status", "PENDING_VERIFICATION")
            item.setdefault("is_restated", 0)
            item.setdefault("restatement_reason", None)
            normalized.append(item)

        sql = """
        INSERT INTO company_financial_statements (
            statement_id, symbol, period_type, period_nature, fiscal_year,
            fiscal_quarter, period_start_date, period_end_date, publication_date,
            broadcast_timestamp, effective_session_date, source_timestamp_basis,
            is_pit_eligible, reporting_basis, statement_version, audit_status,
            currency, unit, revenue_operations, other_income, total_revenue,
            operating_expenses, ebitda, ebit, finance_costs, depreciation_amortization,
            profit_before_tax, tax_expense, net_profit, basic_eps, diluted_eps,
            total_equity, total_debt, cash_and_equivalents, total_assets,
            shares_outstanding, source, source_url, retrieval_timestamp,
            verification_status, is_restated, restatement_reason
        ) VALUES (
            :statement_id, :symbol, :period_type, :period_nature, :fiscal_year,
            :fiscal_quarter, :period_start_date, :period_end_date, :publication_date,
            :broadcast_timestamp, :effective_session_date, :source_timestamp_basis,
            :is_pit_eligible, :reporting_basis, :statement_version, :audit_status,
            :currency, :unit, :revenue_operations, :other_income, :total_revenue,
            :operating_expenses, :ebitda, :ebit, :finance_costs, :depreciation_amortization,
            :profit_before_tax, :tax_expense, :net_profit, :basic_eps, :diluted_eps,
            :total_equity, :total_debt, :cash_and_equivalents, :total_assets,
            :shares_outstanding, :source, :source_url, :retrieval_timestamp,
            :verification_status, :is_restated, :restatement_reason
        )
        ON CONFLICT(symbol, period_end_date, period_type, period_nature, reporting_basis, statement_version) DO UPDATE SET
            statement_id = excluded.statement_id,
            fiscal_year = excluded.fiscal_year,
            fiscal_quarter = excluded.fiscal_quarter,
            period_start_date = excluded.period_start_date,
            publication_date = excluded.publication_date,
            broadcast_timestamp = excluded.broadcast_timestamp,
            effective_session_date = excluded.effective_session_date,
            source_timestamp_basis = excluded.source_timestamp_basis,
            is_pit_eligible = excluded.is_pit_eligible,
            audit_status = excluded.audit_status,
            currency = excluded.currency,
            unit = excluded.unit,
            revenue_operations = excluded.revenue_operations,
            other_income = excluded.other_income,
            total_revenue = excluded.total_revenue,
            operating_expenses = excluded.operating_expenses,
            ebitda = excluded.ebitda,
            ebit = excluded.ebit,
            finance_costs = excluded.finance_costs,
            depreciation_amortization = excluded.depreciation_amortization,
            profit_before_tax = excluded.profit_before_tax,
            tax_expense = excluded.tax_expense,
            net_profit = excluded.net_profit,
            basic_eps = excluded.basic_eps,
            diluted_eps = excluded.diluted_eps,
            total_equity = excluded.total_equity,
            total_debt = excluded.total_debt,
            cash_and_equivalents = excluded.cash_and_equivalents,
            total_assets = excluded.total_assets,
            shares_outstanding = excluded.shares_outstanding,
            source = excluded.source,
            source_url = excluded.source_url,
            retrieval_timestamp = excluded.retrieval_timestamp,
            verification_status = excluded.verification_status,
            is_restated = excluded.is_restated,
            restatement_reason = excluded.restatement_reason;
        """
        with self.get_connection() as conn:
            cursor = conn.executemany(sql, normalized)
            return cursor.rowcount

    def get_financial_statements(
        self,
        symbol: Optional[str] = None,
        period_type: Optional[str] = None,
        reporting_basis: Optional[str] = None,
        period_nature: Optional[str] = None,
        is_pit_eligible: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM company_financial_statements WHERE 1=1"
        params: List[Any] = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if period_type:
            query += " AND period_type = ?"
            params.append(period_type)
        if reporting_basis:
            query += " AND reporting_basis = ?"
            params.append(reporting_basis)
        if period_nature:
            query += " AND period_nature = ?"
            params.append(period_nature)
        if is_pit_eligible is not None:
            query += " AND is_pit_eligible = ?"
            params.append(is_pit_eligible)
        query += " ORDER BY period_end_date DESC, statement_version DESC;"
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_point_in_time_statements(
        self,
        symbol: str,
        as_of_date: str,
        reporting_basis: str = "CONSOLIDATED",
        period_nature: str = "DISCRETE_QUARTER",
        limit: int = 8
    ) -> List[Dict[str, Any]]:
        """
        Point-in-Time Query:
        Retrieves company financial statements published strictly on or before `as_of_date`
        (effective_session_date <= as_of_date), selecting the latest available statement_version
        for each distinct period_end_date.
        Prevents look-ahead bias and correctly handles restatements as of the evaluation date.
        """
        query = """
        WITH AvailableStatements AS (
            SELECT *,
                   ROW_NUMBER() OVER(
                       PARTITION BY symbol, period_end_date, period_type, period_nature, reporting_basis
                       ORDER BY statement_version DESC
                   ) as rn
            FROM company_financial_statements
            WHERE symbol = ?
              AND reporting_basis = ?
              AND period_nature = ?
              AND is_pit_eligible = 1
              AND (
                  (effective_session_date IS NOT NULL AND effective_session_date <= ?)
                  OR
                  (effective_session_date IS NULL AND publication_date IS NOT NULL AND publication_date <= ?)
              )
        )
        SELECT * FROM AvailableStatements
        WHERE rn = 1
        ORDER BY period_end_date DESC
        LIMIT ?;
        """
        with self.get_connection() as conn:
            cursor = conn.execute(query, (symbol, reporting_basis, period_nature, as_of_date, as_of_date, limit))
            return [dict(row) for row in cursor.fetchall()]

    def upsert_fundamental_factors_daily(self, factors: List[Dict[str, Any]]) -> int:
        if not factors:
            return 0

        normalized = []
        for f in factors:
            item = dict(f)
            item.setdefault("data_quality_flag", "COMPLETE")
            item.setdefault("metric_applicability_flag", "STANDARD_INDUSTRIAL")
            normalized.append(item)

        sql = """
        INSERT INTO fundamental_factors_daily (
            symbol, trading_date, close_price, shares_outstanding, market_cap_inr_crore,
            ttm_revenue, ttm_ebitda, ttm_ebit, ttm_net_profit, ttm_eps_adjusted,
            latest_equity, latest_debt, latest_cash, pe_ratio, pb_ratio, ps_ratio,
            ev_ebitda, dividend_yield_ttm, roe_pct, roce_pct, debt_to_equity,
            operating_margin_ttm, net_margin_ttm, revenue_growth_yoy, net_profit_growth_yoy,
            eps_growth_yoy, sector, sector_pe_median, pe_vs_sector_spread, pe_percentile_sector,
            valuation_decile_universe, statements_count_ttm, data_quality_flag,
            metric_applicability_flag, latest_statement_id, calculated_at
        ) VALUES (
            :symbol, :trading_date, :close_price, :shares_outstanding, :market_cap_inr_crore,
            :ttm_revenue, :ttm_ebitda, :ttm_ebit, :ttm_net_profit, :ttm_eps_adjusted,
            :latest_equity, :latest_debt, :latest_cash, :pe_ratio, :pb_ratio, :ps_ratio,
            :ev_ebitda, :dividend_yield_ttm, :roe_pct, :roce_pct, :debt_to_equity,
            :operating_margin_ttm, :net_margin_ttm, :revenue_growth_yoy, :net_profit_growth_yoy,
            :eps_growth_yoy, :sector, :sector_pe_median, :pe_vs_sector_spread, :pe_percentile_sector,
            :valuation_decile_universe, :statements_count_ttm, :data_quality_flag,
            :metric_applicability_flag, :latest_statement_id, :calculated_at
        )
        ON CONFLICT(symbol, trading_date) DO UPDATE SET
            close_price = excluded.close_price,
            shares_outstanding = excluded.shares_outstanding,
            market_cap_inr_crore = excluded.market_cap_inr_crore,
            ttm_revenue = excluded.ttm_revenue,
            ttm_ebitda = excluded.ttm_ebitda,
            ttm_ebit = excluded.ttm_ebit,
            ttm_net_profit = excluded.ttm_net_profit,
            ttm_eps_adjusted = excluded.ttm_eps_adjusted,
            latest_equity = excluded.latest_equity,
            latest_debt = excluded.latest_debt,
            latest_cash = excluded.latest_cash,
            pe_ratio = excluded.pe_ratio,
            pb_ratio = excluded.pb_ratio,
            ps_ratio = excluded.ps_ratio,
            ev_ebitda = excluded.ev_ebitda,
            dividend_yield_ttm = excluded.dividend_yield_ttm,
            roe_pct = excluded.roe_pct,
            roce_pct = excluded.roce_pct,
            debt_to_equity = excluded.debt_to_equity,
            operating_margin_ttm = excluded.operating_margin_ttm,
            net_margin_ttm = excluded.net_margin_ttm,
            revenue_growth_yoy = excluded.revenue_growth_yoy,
            net_profit_growth_yoy = excluded.net_profit_growth_yoy,
            eps_growth_yoy = excluded.eps_growth_yoy,
            sector = excluded.sector,
            sector_pe_median = excluded.sector_pe_median,
            pe_vs_sector_spread = excluded.pe_vs_sector_spread,
            pe_percentile_sector = excluded.pe_percentile_sector,
            valuation_decile_universe = excluded.valuation_decile_universe,
            statements_count_ttm = excluded.statements_count_ttm,
            data_quality_flag = excluded.data_quality_flag,
            metric_applicability_flag = excluded.metric_applicability_flag,
            latest_statement_id = excluded.latest_statement_id,
            calculated_at = excluded.calculated_at;
        """
        with self.get_connection() as conn:
            cursor = conn.executemany(sql, normalized)
            return cursor.rowcount

    def get_fundamental_factors_daily(
        self,
        symbol: Optional[str] = None,
        trading_date: Optional[str] = None,
        sector: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM fundamental_factors_daily WHERE 1=1"
        params: List[Any] = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if trading_date:
            query += " AND trading_date = ?"
            params.append(trading_date)
        if sector:
            query += " AND sector = ?"
            params.append(sector)
        query += " ORDER BY trading_date ASC, symbol ASC;"
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def update_index_valuation(
        self,
        index_name: str,
        trading_date: str,
        pe_ratio: Optional[float] = None,
        pb_ratio: Optional[float] = None,
        div_yield: Optional[float] = None
    ) -> int:
        """Updates official published index valuation ratios on index_daily."""
        sql = """
        UPDATE index_daily
        SET pe_ratio = ?, pb_ratio = ?, div_yield = ?
        WHERE index_name = ? AND trading_date = ?;
        """
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (pe_ratio, pb_ratio, div_yield, index_name, trading_date))
            return cursor.rowcount

    def upsert_evidence_records(self, records: List[Dict[str, Any]]) -> int:
        """
        Upserts normalized evidence records into evidence_records table.
        """
        if not records:
            return 0
        sql = """
        INSERT INTO evidence_records (
            evidence_id, symbol, entity_type, event_date, broadcast_timestamp,
            effective_session_date, evidence_tier, evidence_category,
            evidence_direction, headline, details_json, source_identity,
            source_reference, verification_status, is_pit_eligible,
            reporting_basis, expectation_surprise, is_contradictory,
            retrieval_timestamp, created_at
        ) VALUES (
            :evidence_id, :symbol, :entity_type, :event_date, :broadcast_timestamp,
            :effective_session_date, :evidence_tier, :evidence_category,
            :evidence_direction, :headline, :details_json, :source_identity,
            :source_reference, :verification_status, :is_pit_eligible,
            :reporting_basis, :expectation_surprise, :is_contradictory,
            :retrieval_timestamp, :created_at
        )
        ON CONFLICT(evidence_id) DO UPDATE SET
            symbol = excluded.symbol,
            entity_type = excluded.entity_type,
            event_date = excluded.event_date,
            broadcast_timestamp = excluded.broadcast_timestamp,
            effective_session_date = excluded.effective_session_date,
            evidence_tier = excluded.evidence_tier,
            evidence_category = excluded.evidence_category,
            evidence_direction = excluded.evidence_direction,
            headline = excluded.headline,
            details_json = excluded.details_json,
            source_identity = excluded.source_identity,
            source_reference = excluded.source_reference,
            verification_status = excluded.verification_status,
            is_pit_eligible = excluded.is_pit_eligible,
            reporting_basis = excluded.reporting_basis,
            expectation_surprise = excluded.expectation_surprise,
            is_contradictory = excluded.is_contradictory,
            retrieval_timestamp = excluded.retrieval_timestamp;
            -- Note: created_at is strictly preserved from original insert on conflict
        """
        normalized = []
        for r in records:
            item = dict(r)
            if "tier" in item and "evidence_tier" not in item:
                item["evidence_tier"] = int(item["tier"])
            if "category" in item and "evidence_category" not in item:
                item["evidence_category"] = str(item["category"])
            if "direction" in item and "evidence_direction" not in item:
                item["evidence_direction"] = str(item["direction"])
            if isinstance(item.get("details_json"), dict):
                item["details_json"] = json.dumps(item["details_json"])
            elif "details" in item and "details_json" not in item:
                item["details_json"] = json.dumps(item["details"])
            normalized.append(item)

        with self.get_connection() as conn:
            cursor = conn.executemany(sql, normalized)
            return cursor.rowcount

    def get_evidence_records(
        self,
        symbol: Optional[str] = None,
        effective_session_date: Optional[str] = None,
        as_of_date: Optional[str] = None,
        tier: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves normalized evidence records filtered by symbol, session, as_of_date, and tier."""
        query = "SELECT * FROM evidence_records WHERE 1=1"
        params: List[Any] = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        if effective_session_date:
            query += " AND effective_session_date = ?"
            params.append(effective_session_date)
        if as_of_date:
            query += " AND effective_session_date <= ?"
            params.append(as_of_date)
        if tier is not None:
            query += " AND evidence_tier = ?"
            params.append(tier)
        query += " ORDER BY effective_session_date DESC, evidence_tier ASC;"
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = []
            for r in cursor.fetchall():
                d = dict(r)
                if "evidence_tier" in d:
                    d["tier"] = d["evidence_tier"]
                if "evidence_category" in d:
                    d["category"] = d["evidence_category"]
                if "evidence_direction" in d:
                    d["direction"] = d["evidence_direction"]
                if d.get("details_json"):
                    try:
                        d["details"] = json.loads(d["details_json"])
                    except Exception:
                        d["details"] = {}
                rows.append(d)
            return rows

    def record_movement_explanation(self, explanation: Dict[str, Any]) -> None:
        """Records or updates a structured movement explanation run."""
        sql = """
        INSERT INTO movement_explanations (
            explanation_id, symbol, trading_date, movement_classification,
            stock_return_1d, benchmark_return_1d, sector_return_1d,
            sector_benchmark_type, sector_benchmark_name, abnormal_return,
            sector_adjusted_return, volume_ratio, primary_evidence_id,
            evidence_strength_score, confidence_level, is_contradicted,
            contradiction_penalty, unexplained_residual_pct, full_report_json,
            generated_at
        ) VALUES (
            :explanation_id, :symbol, :trading_date, :movement_classification,
            :stock_return_1d, :benchmark_return_1d, :sector_return_1d,
            :sector_benchmark_type, :sector_benchmark_name, :abnormal_return,
            :sector_adjusted_return, :volume_ratio, :primary_evidence_id,
            :evidence_strength_score, :confidence_level, :is_contradicted,
            :contradiction_penalty, :unexplained_residual_pct, :full_report_json,
            :generated_at
        )
        ON CONFLICT(explanation_id) DO UPDATE SET
            symbol = excluded.symbol,
            trading_date = excluded.trading_date,
            movement_classification = excluded.movement_classification,
            stock_return_1d = excluded.stock_return_1d,
            benchmark_return_1d = excluded.benchmark_return_1d,
            sector_return_1d = excluded.sector_return_1d,
            sector_benchmark_type = excluded.sector_benchmark_type,
            sector_benchmark_name = excluded.sector_benchmark_name,
            abnormal_return = excluded.abnormal_return,
            sector_adjusted_return = excluded.sector_adjusted_return,
            volume_ratio = excluded.volume_ratio,
            primary_evidence_id = excluded.primary_evidence_id,
            evidence_strength_score = excluded.evidence_strength_score,
            confidence_level = excluded.confidence_level,
            is_contradicted = excluded.is_contradicted,
            contradiction_penalty = excluded.contradiction_penalty,
            unexplained_residual_pct = excluded.unexplained_residual_pct,
            full_report_json = excluded.full_report_json,
            generated_at = excluded.generated_at;
        """
        item = dict(explanation)
        if isinstance(item.get("full_report_json"), dict):
            item["full_report_json"] = json.dumps(item["full_report_json"])
        with self.get_connection() as conn:
            conn.execute(sql, item)

    def get_movement_explanation(self, symbol: str, trading_date: str) -> Optional[Dict[str, Any]]:
        """Fetches a cached movement explanation by symbol and trading date."""
        sql = "SELECT * FROM movement_explanations WHERE symbol = ? AND trading_date = ? LIMIT 1;"
        with self.get_connection() as conn:
            cursor = conn.execute(sql, (symbol, trading_date))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("full_report_json"):
                try:
                    d["full_report"] = json.loads(d["full_report_json"])
                except Exception:
                    d["full_report"] = {}
            return d

    # -------------------------------------------------------------
    # Milestone B3.3: Structured Financial Statements (Quarterly & Annual)
    # -------------------------------------------------------------

    def upsert_financial_statements_quarterly(self, statements: List[Dict[str, Any]]) -> int:
        """Idempotent upsert of structured quarterly financial statements."""
        if not statements:
            return 0
        normalized = []
        for s in statements:
            item = dict(s)
            if "source_url" not in item:
                item["source_url"] = None
            if "cash_flow_from_ops" not in item:
                item["cash_flow_from_ops"] = None
            if "created_at" not in item or not item["created_at"]:
                item["created_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            item["is_audited"] = 1 if item.get("is_audited") in (True, 1, "1", "AUDITED") else 0
            normalized.append(item)

        sql = """
        INSERT INTO financial_statements_quarterly (
            symbol, period_end_date, filing_date, source_url, is_audited,
            revenue, ebitda, net_profit, eps, total_debt, total_equity,
            cash_flow_from_ops, created_at
        ) VALUES (
            :symbol, :period_end_date, :filing_date, :source_url, :is_audited,
            :revenue, :ebitda, :net_profit, :eps, :total_debt, :total_equity,
            :cash_flow_from_ops, :created_at
        )
        ON CONFLICT(symbol, period_end_date) DO UPDATE SET
            filing_date = excluded.filing_date,
            source_url = excluded.source_url,
            is_audited = excluded.is_audited,
            revenue = excluded.revenue,
            ebitda = excluded.ebitda,
            net_profit = excluded.net_profit,
            eps = excluded.eps,
            total_debt = excluded.total_debt,
            total_equity = excluded.total_equity,
            cash_flow_from_ops = excluded.cash_flow_from_ops,
            created_at = excluded.created_at;
        """
        with self.get_connection() as conn:
            cursor = conn.executemany(sql, normalized)
            return cursor.rowcount

    def upsert_financial_statements_annual(self, statements: List[Dict[str, Any]]) -> int:
        """Idempotent upsert of structured annual financial statements."""
        if not statements:
            return 0
        normalized = []
        for s in statements:
            item = dict(s)
            if "source_url" not in item:
                item["source_url"] = None
            if "cash_flow_from_ops" not in item:
                item["cash_flow_from_ops"] = None
            if "created_at" not in item or not item["created_at"]:
                item["created_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            item["is_audited"] = 1 if item.get("is_audited") in (True, 1, "1", "AUDITED") else 0
            normalized.append(item)

        sql = """
        INSERT INTO financial_statements_annual (
            symbol, period_end_date, filing_date, source_url, is_audited,
            revenue, ebitda, net_profit, eps, total_debt, total_equity,
            cash_flow_from_ops, created_at
        ) VALUES (
            :symbol, :period_end_date, :filing_date, :source_url, :is_audited,
            :revenue, :ebitda, :net_profit, :eps, :total_debt, :total_equity,
            :cash_flow_from_ops, :created_at
        )
        ON CONFLICT(symbol, period_end_date) DO UPDATE SET
            filing_date = excluded.filing_date,
            source_url = excluded.source_url,
            is_audited = excluded.is_audited,
            revenue = excluded.revenue,
            ebitda = excluded.ebitda,
            net_profit = excluded.net_profit,
            eps = excluded.eps,
            total_debt = excluded.total_debt,
            total_equity = excluded.total_equity,
            cash_flow_from_ops = excluded.cash_flow_from_ops,
            created_at = excluded.created_at;
        """
        with self.get_connection() as conn:
            cursor = conn.executemany(sql, normalized)
            return cursor.rowcount

    def get_financial_statements_quarterly(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Queries structured quarterly statements optionally filtered by symbol."""
        query = "SELECT * FROM financial_statements_quarterly"
        params = []
        if symbol:
            query += " WHERE symbol = ?"
            params.append(symbol)
        query += " ORDER BY symbol, period_end_date ASC;"
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_financial_statements_annual(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Queries structured annual statements optionally filtered by symbol."""
        query = "SELECT * FROM financial_statements_annual"
        params = []
        if symbol:
            query += " WHERE symbol = ?"
            params.append(symbol)
        query += " ORDER BY symbol, period_end_date ASC;"
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    # ====================================================================
    # Milestone B7.5: News Ingestion & Directional Impact Storage
    # ====================================================================

    def insert_news_articles(self, articles: List[Dict[str, Any]]) -> int:
        """Inserts processed news articles into equity_news_feed."""
        if not articles:
            return 0
        sql = """
        INSERT OR REPLACE INTO equity_news_feed (
            id, symbol, title, source, published_at, article_url,
            summary_bullets, impact_direction, impact_horizon,
            impact_drivers, impact_rationale, confidence_score, fetched_at
        ) VALUES (
            :id, :symbol, :title, :source, :published_at, :article_url,
            :summary_bullets, :impact_direction, :impact_horizon,
            :impact_drivers, :impact_rationale, :confidence_score, :fetched_at
        );
        """
        normalized = []
        for a in articles:
            summary_bullets = a.get("summary_bullets", "[]")
            if isinstance(summary_bullets, list):
                summary_bullets = json.dumps(summary_bullets)
            impact_drivers = a.get("impact_drivers", "[]")
            if isinstance(impact_drivers, list):
                impact_drivers = json.dumps(impact_drivers)
            
            normalized.append({
                "id": a["id"],
                "symbol": a["symbol"].upper(),
                "title": a["title"],
                "source": a.get("source", "Financial Media"),
                "published_at": a["published_at"],
                "article_url": a["article_url"],
                "summary_bullets": summary_bullets,
                "impact_direction": a.get("impact_direction", "NEUTRAL"),
                "impact_horizon": a.get("impact_horizon", "SHORT_TERM"),
                "impact_drivers": impact_drivers,
                "impact_rationale": a.get("impact_rationale", ""),
                "confidence_score": float(a.get("confidence_score", 1.0)),
                "fetched_at": a.get("fetched_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
            })
        with self.get_connection() as conn:
            cursor = conn.executemany(sql, normalized)
            return cursor.rowcount

    def get_news_articles(
        self,
        symbol: Optional[str] = None,
        limit: int = 10,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Queries equity news feed optionally filtered by symbol, ordered by published_at DESC."""
        query = "SELECT * FROM equity_news_feed"
        params: List[Any] = []
        if symbol:
            query += " WHERE symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY published_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = [dict(row) for row in cursor.fetchall()]
            for r in rows:
                if isinstance(r.get("summary_bullets"), str):
                    try:
                        r["summary"] = json.loads(r["summary_bullets"])
                    except Exception:
                        r["summary"] = [r["summary_bullets"]]
                else:
                    r["summary"] = r.get("summary_bullets") or []
                
                drivers = r.get("impact_drivers")
                if isinstance(drivers, str):
                    try:
                        drivers = json.loads(drivers)
                    except Exception:
                        drivers = []
                elif not drivers:
                    drivers = []
                r["impact"] = {
                    "direction": r.get("impact_direction", "NEUTRAL"),
                    "horizon": r.get("impact_horizon", "SHORT_TERM"),
                    "affected_drivers": drivers,
                    "rationale": r.get("impact_rationale", ""),
                    "confidence_score": r.get("confidence_score", 1.0)
                }
            return rows

    def get_latest_news_timestamp(self, symbol: str) -> Optional[str]:
        """Returns the most recent fetched_at timestamp for a given symbol."""
        query = "SELECT MAX(fetched_at) as latest_fetch FROM equity_news_feed WHERE symbol = ?;"
        with self.get_connection() as conn:
            cursor = conn.execute(query, (symbol.upper(),))
            row = cursor.fetchone()
            return row["latest_fetch"] if row and row["latest_fetch"] else None

    def article_exists(self, symbol: str, article_url: str, normalized_title: str) -> bool:
        """Checks whether an article exists by URL or normalized title for this symbol."""
        query = "SELECT article_url, title FROM equity_news_feed WHERE symbol = ?;"
        with self.get_connection() as conn:
            cursor = conn.execute(query, (symbol.upper(),))
            rows = cursor.fetchall()
            for r in rows:
                if r["article_url"] == article_url:
                    return True
                norm_existing = re.sub(r'[^a-zA-Z0-9]', '', r["title"].lower())
                if norm_existing and norm_existing == normalized_title:
                    return True
        return False

    # ====================================================================
    # Milestone B8.0: Multi-Factor Strategy Backtest Storage
    # ====================================================================

    def save_backtest_run(
        self,
        run_data: Dict[str, Any],
        equity_curve: List[Dict[str, Any]]
    ) -> str:
        """
        Saves a completed backtest run summary and daily equity curve series.
        """
        run_id = run_data["run_id"]
        params_str = run_data.get("parameters", "{}")
        if isinstance(params_str, dict):
            params_str = json.dumps(params_str)

        sql_run = """
        INSERT OR REPLACE INTO backtest_runs (
            run_id, strategy_name, parameters, cagr_pct,
            sharpe_ratio, max_drawdown_pct, win_rate_pct, created_at
        ) VALUES (
            :run_id, :strategy_name, :parameters, :cagr_pct,
            :sharpe_ratio, :max_drawdown_pct, :win_rate_pct, :created_at
        );
        """
        sql_curve = """
        INSERT OR REPLACE INTO backtest_equity_curve (
            run_id, trading_date, portfolio_value, benchmark_value, drawdown_pct
        ) VALUES (
            :run_id, :trading_date, :portfolio_value, :benchmark_value, :drawdown_pct
        );
        """
        curve_records = [
            {
                "run_id": run_id,
                "trading_date": pt["trading_date"],
                "portfolio_value": float(pt["portfolio_value"]),
                "benchmark_value": float(pt["benchmark_value"]),
                "drawdown_pct": float(pt.get("drawdown_pct", 0.0))
            }
            for pt in equity_curve
        ]

        with self.get_connection() as conn:
            conn.execute(sql_run, {
                "run_id": run_id,
                "strategy_name": run_data.get("strategy_name", "Quality_Momentum_Top10"),
                "parameters": params_str,
                "cagr_pct": float(run_data.get("cagr_pct", 0.0)),
                "sharpe_ratio": float(run_data.get("sharpe_ratio", 0.0)),
                "max_drawdown_pct": float(run_data.get("max_drawdown_pct", 0.0)),
                "win_rate_pct": float(run_data.get("win_rate_pct", 0.0)),
                "created_at": run_data.get("created_at", datetime.datetime.now(datetime.timezone.utc).isoformat())
            })
            if curve_records:
                conn.executemany(sql_curve, curve_records)

        return run_id

    def get_backtest_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a backtest run summary and its equity curve."""
        query_run = "SELECT * FROM backtest_runs WHERE run_id = ?;"
        query_curve = """
        SELECT trading_date, portfolio_value, benchmark_value, drawdown_pct
        FROM backtest_equity_curve
        WHERE run_id = ?
        ORDER BY trading_date ASC;
        """
        with self.get_connection() as conn:
            cur = conn.execute(query_run, (run_id,))
            run_row = cur.fetchone()
            if not run_row:
                return None
            res = dict(run_row)
            if isinstance(res.get("parameters"), str):
                try:
                    res["parameters"] = json.loads(res["parameters"])
                except Exception:
                    pass
            cur_c = conn.execute(query_curve, (run_id,))
            res["equity_curve"] = [dict(r) for r in cur_c.fetchall()]
            return res

    def get_latest_backtest_run(self) -> Optional[Dict[str, Any]]:
        """Retrieves the most recent backtest run and its equity curve."""
        query = "SELECT run_id FROM backtest_runs ORDER BY created_at DESC LIMIT 1;"
        with self.get_connection() as conn:
            cur = conn.execute(query)
            row = cur.fetchone()
            if not row:
                return None
            return self.get_backtest_run(row["run_id"])

    # ====================================================================
    # Milestone B9.0: Compounding Feedback & Audit Ledger Storage
    # ====================================================================

    def record_forecast_prediction(self, rec: Dict[str, Any]) -> str:
        """Records an econometric forecast prediction to the audit ledger."""
        audit_id = rec.get("id") or f"FC_{rec['symbol']}_{rec['prediction_date']}_{rec['horizon_days']}D_{uuid.uuid4().hex[:6]}"
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        sql = """
        INSERT OR REPLACE INTO forecast_audit_ledger (
            id, symbol, prediction_date, horizon_days, target_evaluation_date,
            current_price, expected_price, lower_80, upper_80, lower_95, upper_95,
            realized_price, within_80_ci, within_95_ci, forecast_error_pct,
            evaluated_at, created_at
        ) VALUES (
            :id, :symbol, :prediction_date, :horizon_days, :target_evaluation_date,
            :current_price, :expected_price, :lower_80, :upper_80, :lower_95, :upper_95,
            :realized_price, :within_80_ci, :within_95_ci, :forecast_error_pct,
            :evaluated_at, :created_at
        );
        """
        params = {
            "id": audit_id,
            "symbol": rec["symbol"].upper(),
            "prediction_date": rec["prediction_date"],
            "horizon_days": int(rec["horizon_days"]),
            "target_evaluation_date": rec["target_evaluation_date"],
            "current_price": float(rec["current_price"]),
            "expected_price": float(rec["expected_price"]),
            "lower_80": float(rec["lower_80"]),
            "upper_80": float(rec["upper_80"]),
            "lower_95": float(rec["lower_95"]),
            "upper_95": float(rec["upper_95"]),
            "realized_price": rec.get("realized_price"),
            "within_80_ci": rec.get("within_80_ci"),
            "within_95_ci": rec.get("within_95_ci"),
            "forecast_error_pct": rec.get("forecast_error_pct"),
            "evaluated_at": rec.get("evaluated_at"),
            "created_at": rec.get("created_at", now_ts)
        }
        with self.get_connection() as conn:
            conn.execute(sql, params)
        return audit_id

    def record_catalyst_prediction(self, rec: Dict[str, Any]) -> str:
        """Records a news sentiment impact classification to the catalyst audit ledger."""
        audit_id = rec.get("id") or f"CAT_{rec['symbol']}_{rec.get('article_id', uuid.uuid4().hex[:8])}"
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        sql = """
        INSERT OR REPLACE INTO catalyst_audit_ledger (
            id, symbol, article_id, published_at, direction,
            price_at_publish, price_5d_after, realized_return_5d,
            is_direction_accurate, evaluated_at, created_at
        ) VALUES (
            :id, :symbol, :article_id, :published_at, :direction,
            :price_at_publish, :price_5d_after, :realized_return_5d,
            :is_direction_accurate, :evaluated_at, :created_at
        );
        """
        params = {
            "id": audit_id,
            "symbol": rec["symbol"].upper(),
            "article_id": rec.get("article_id", ""),
            "published_at": rec["published_at"],
            "direction": rec["direction"].upper(),
            "price_at_publish": float(rec["price_at_publish"]),
            "price_5d_after": rec.get("price_5d_after"),
            "realized_return_5d": rec.get("realized_return_5d"),
            "is_direction_accurate": rec.get("is_direction_accurate"),
            "evaluated_at": rec.get("evaluated_at"),
            "created_at": rec.get("created_at", now_ts)
        }
        with self.get_connection() as conn:
            conn.execute(sql, params)
        return audit_id

    def get_pending_forecast_audits(self, current_date: str) -> List[Dict[str, Any]]:
        """Returns forecast predictions whose target evaluation date has passed and are unevaluated."""
        query = """
        SELECT * FROM forecast_audit_ledger
        WHERE target_evaluation_date <= ? AND evaluated_at IS NULL
        ORDER BY target_evaluation_date ASC;
        """
        with self.get_connection() as conn:
            cur = conn.execute(query, (current_date,))
            return [dict(r) for r in cur.fetchall()]

    def update_forecast_audit(
        self,
        audit_id: str,
        realized_price: float,
        within_80: int,
        within_95: int,
        error_pct: float,
        evaluated_at: str
    ) -> None:
        """Updates a realized forecast audit record."""
        sql = """
        UPDATE forecast_audit_ledger
        SET realized_price = :realized,
            within_80_ci = :w80,
            within_95_ci = :w95,
            forecast_error_pct = :err,
            evaluated_at = :eval_at
        WHERE id = :id;
        """
        with self.get_connection() as conn:
            conn.execute(sql, {
                "id": audit_id,
                "realized": realized_price,
                "w80": within_80,
                "w95": within_95,
                "err": error_pct,
                "eval_at": evaluated_at
            })

    def get_pending_catalyst_audits(self) -> List[Dict[str, Any]]:
        """Returns unevaluated catalyst predictions."""
        query = "SELECT * FROM catalyst_audit_ledger WHERE evaluated_at IS NULL ORDER BY published_at ASC;"
        with self.get_connection() as conn:
            cur = conn.execute(query)
            return [dict(r) for r in cur.fetchall()]

    def update_catalyst_audit(
        self,
        audit_id: str,
        price_5d: float,
        return_5d: float,
        is_accurate: int,
        evaluated_at: str
    ) -> None:
        """Updates a realized catalyst audit record."""
        sql = """
        UPDATE catalyst_audit_ledger
        SET price_5d_after = :p5d,
            realized_return_5d = :ret5d,
            is_direction_accurate = :acc,
            evaluated_at = :eval_at
        WHERE id = :id;
        """
        with self.get_connection() as conn:
            conn.execute(sql, {
                "id": audit_id,
                "p5d": price_5d,
                "ret5d": return_5d,
                "acc": is_accurate,
                "eval_at": evaluated_at
            })

    def get_model_accuracy_metrics(self) -> Dict[str, Any]:
        """Calculates aggregate realization accuracy metrics for forecasts and catalysts."""
        with self.db_get_connection() if hasattr(self, "db_get_connection") else self.get_connection() as conn:
            # 1. Forecast containment and error metrics
            cur = conn.execute(
                """
                SELECT 
                    COUNT(*) as total_eval,
                    AVG(within_80_ci) as containment_80,
                    AVG(within_95_ci) as containment_95,
                    AVG(forecast_error_pct) as mean_error,
                    AVG(ABS(forecast_error_pct)) as mape,
                    AVG(forecast_error_pct * forecast_error_pct) as mse
                FROM forecast_audit_ledger
                WHERE evaluated_at IS NOT NULL;
                """
            )
            fc_row = cur.fetchone()
            total_fc = fc_row["total_eval"] or 0
            contain_80 = round((fc_row["containment_80"] or 0.0) * 100.0, 2)
            contain_95 = round((fc_row["containment_95"] or 0.0) * 100.0, 2)
            mape = round(fc_row["mape"] or 0.0, 2)
            mse = fc_row["mse"] or 0.0
            rmse = round(math.sqrt(mse), 2) if mse > 0 else 0.0

            # 2. Catalyst accuracy metrics
            cur_cat = conn.execute(
                """
                SELECT 
                    COUNT(*) as total_eval,
                    AVG(is_direction_accurate) as accuracy_rate,
                    AVG(realized_return_5d) as avg_5d_return
                FROM catalyst_audit_ledger
                WHERE evaluated_at IS NOT NULL;
                """
            )
            cat_row = cur_cat.fetchone()
            total_cat = cat_row["total_eval"] or 0
            news_acc = round((cat_row["accuracy_rate"] or 0.0) * 100.0, 2)
            avg_drift = round(cat_row["avg_5d_return"] or 0.0, 2)

            has_enough_fc = total_fc >= 30
            has_enough_cat = total_cat >= 30

            return {
                "forecast_model": {
                    "total_evaluated": total_fc,
                    "containment_80_pct": contain_80 if total_fc > 0 else None,
                    "containment_95_pct": contain_95 if total_fc > 0 else None,
                    "rmse_pct": rmse if total_fc > 0 else None,
                    "mape_pct": mape if total_fc > 0 else None,
                    "target_benchmark_80": 80.0,
                    "target_benchmark_95": 95.0,
                    "status": "CALIBRATED" if (has_enough_fc and contain_80 >= 75.0) else (
                        "DRIFT_DETECTED" if has_enough_fc else "PENDING_MATURITY"
                    )
                },
                "catalyst_model": {
                    "total_evaluated": total_cat,
                    "directional_accuracy_pct": news_acc if total_cat > 0 else None,
                    "avg_5d_return_pct": avg_drift if total_cat > 0 else None,
                    "status": (
                        "RELIABLE" if (has_enough_cat and news_acc >= 60.0) else (
                            "NEUTRAL" if has_enough_cat else "PENDING_MATURITY"
                        )
                    )
                },
                "evaluated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }


def get_readonly_connection(db_path: str = "data/market_lab.db") -> sqlite3.Connection:
    """Module-level helper to obtain a strictly read-only SQLite connection."""
    return DatabaseManager(db_path).get_readonly_connection()






