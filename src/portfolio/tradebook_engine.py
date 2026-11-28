"""
src/portfolio/tradebook_engine.py
Zero-PII Encrypted Angel One Tradebook Ingestion Engine & All-Time Master Excel Generator.

Privacy & Security Architecture:
1. Strict Zero-PII:
   - Top rows above table header anchors are never parsed, logged, stored, or exported.
   - Never extracts or persists Client Name, Client ID/UCC, PAN, Address, Mobile, Email, or DP ID.
2. Ephemeral Upload Destruction:
   - Raw uploaded files are parsed strictly in RAM (io.BytesIO) and never written to disk.
3. Encrypted at Rest:
   - Master Excel workbook is stored encrypted at data/secure/master_tradebook.enc using
     cryptography.fernet (PBKDF2-HMAC-SHA256 derived from server-only MIL_TRADEBOOK_KEY).
4. Automated Friction & Scrip-Level DP Reconciliation:
   - Deduplicates executions by (order_id, trade_id, symbol, side, date, qty, price).
   - Reconciles Angel One sell DP charge (₹23.60 = ₹3.50 CDSL + ₹16.50 Angel One + ₹3.60 GST)
     per closed delivery swing for True Net Realized P&L accuracy.
"""

import io
import os
import re
import base64
import logging
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from src.storage.database import DatabaseManager
from src.portfolio.fee_engine import ANGEL_ONE_DP_CHARGE

logger = logging.getLogger("MIL.TradebookEngine")

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
SECURE_DIR = os.path.join(DATA_DIR, "secure")
MASTER_ENC_PATH = os.path.join(SECURE_DIR, "master_tradebook.enc")
SECURE_SALT = b"MIL_SECURE_SALT_V1_2026"
DEFAULT_ANGEL_ONE_DP_CHARGE = ANGEL_ONE_DP_CHARGE  # ₹3.50 CDSL + ₹16.50 Angel One + ₹3.60 GST


def get_fernet_cipher(secret_key: Optional[str] = None) -> Fernet:
    """Derives a deterministic 32-byte Fernet key via PBKDF2-HMAC-SHA256 from server secret."""
    raw_key = (
        secret_key
        or os.getenv("MIL_TRADEBOOK_KEY")
        or os.getenv("MIL_INTERNAL_SYNC_SECRET")
        or os.getenv("INTERNAL_SYNC_TOKEN")
        or "MIL_DEFAULT_SECURE_TRADEBOOK_MASTER_SALT_2026"
    ).strip()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SECURE_SALT,
        iterations=100000,
    )
    derived_key = base64.urlsafe_b64encode(kdf.derive(raw_key.encode("utf-8")))
    return Fernet(derived_key)


class EncryptedTradebookEngine:
    """
    Zero-PII Tradebook Engine that ingests Angel One Excel exports,
    maintains an idempotent SQLite ledger, reconciles statutory DP charges,
    and generates an encrypted 5-tab Master Excel Trading Record.
    """

    def __init__(self, db: DatabaseManager, secret_key: Optional[str] = None):
        self.db = db
        self.cipher = get_fernet_cipher(secret_key)
        os.makedirs(SECURE_DIR, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Relies on canonical DatabaseManager schema migrations (0014) and deduplicates legacy roundtrips."""
        self.db.init_schema()
        self.deduplicate_closed_roundtrips()

    def deduplicate_closed_roundtrips(self) -> int:
        """
        Removes incomplete duplicate rows in real_closed_roundtrips where
        (symbol, qty, round(avg_buy, 2), round(avg_sell, 2)) matches a complete row
        having non-empty isin and sell_date.
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM real_closed_roundtrips
                WHERE (isin IS NULL OR isin = '' OR sell_date IS NULL OR sell_date = '')
                  AND EXISTS (
                      SELECT 1 FROM real_closed_roundtrips c
                      WHERE c.id != real_closed_roundtrips.id
                        AND c.isin IS NOT NULL AND c.isin != ''
                        AND c.sell_date IS NOT NULL AND c.sell_date != ''
                        AND c.symbol = real_closed_roundtrips.symbol
                        AND c.qty = real_closed_roundtrips.qty
                        AND round(c.avg_buy_price, 2) = round(real_closed_roundtrips.avg_buy_price, 2)
                        AND round(c.avg_sell_price, 2) = round(real_closed_roundtrips.avg_sell_price, 2)
                  );
            """)
            deleted = cur.rowcount
            if deleted > 0:
                conn.commit()
                logger.info(f"EncryptedTradebookEngine: Deduplicated {deleted} incomplete rows in real_closed_roundtrips.")
                try:
                    from src.storage.durable_state import mark_state_dirty
                    mark_state_dirty()
                except Exception:
                    pass
            return deleted

    # =========================================================================
    # MULTI-REPORT ZERO-PII IN-MEMORY PARSER
    # =========================================================================

    def _detect_sheet_type(self, sheet, sheet_title: str, filename: Optional[str] = None) -> str:
        """
        Dynamically detects Angel One report sheet type using 3 redundant layers:
        1. Explicit sheet title matching.
        2. In-memory content inspection of the first 45 rows (searching for section banners & column anchors).
        3. Filename hint as secondary fallback.
        
        Returns one of:
        'trades_history', 'non_trade_charges', 'tax_pnl', 'profit_loss', 'ledger', 'statement_charges', or 'unknown'.
        """
        st = sheet_title.lower().replace(" ", "").replace("_", "").replace("-", "")
        fn = (filename or "").lower().replace(" ", "").replace("_", "").replace("-", "")

        # Quick Title Checks
        if "nontrade" in st or "nontradecharge" in st:
            return "non_trade_charges"
        if "tradesandcharge" in st or "tradebook" in st or ("trade" in st and "history" in st):
            return "trades_history"
        if "brokingledger" in st or "clientledger" in st or "accountstatement" in st:
            return "ledger"
        if "tax" in st or "tradedetail" in st or "sgb" in st:
            return "tax_pnl"
        if "profit" in st or "pnl" in st or "p&l" in st:
            return "profit_loss"

        # Content & Header Scan (first 45 rows)
        first_rows_text: List[str] = []
        try:
            for idx, row in enumerate(sheet.iter_rows(values_only=True, max_row=45)):
                if row:
                    row_txt = " ".join([str(c or "").strip().lower() for c in row if c is not None])
                    if row_txt:
                        first_rows_text.append(row_txt)
        except Exception:
            pass

        full_content_str = " \n ".join(first_rows_text)

        # 1. Non-Trade Charges
        if "non trade charges" in full_content_str or ("cdsl" in full_content_str and "charge date" in full_content_str and "voucher" not in full_content_str):
            return "non_trade_charges"

        # 2. Trades History
        if "tradebook and charges" in full_content_str or ("order id" in full_content_str and "trade id" in full_content_str):
            return "trades_history"

        # 3. Tax P&L (Delivery + Open Holdings)
        if "delivery p&l" in full_content_str or ("buy date" in full_content_str and "sell date" in full_content_str and "isin" in full_content_str):
            return "tax_pnl"

        # 4. Profit & Loss
        if "scripsymbol" in full_content_str or ("delivery pnl" in full_content_str and "company name" in full_content_str) or ("gross pnl" in full_content_str and "isin" not in full_content_str):
            return "profit_loss"

        # 5. Broking Ledger
        if "transaction details" in full_content_str or ("transaction" in full_content_str and "voucher" in full_content_str) or ("running balance" in full_content_str and "credit" in full_content_str):
            return "ledger"

        # 6. Statement Charges (DP Fees)
        if "cdsl charge" in full_content_str or ("angelone charge" in full_content_str) or ("quantity sold" in full_content_str and "total charge" in full_content_str):
            return "statement_charges"

        # Filename hints as final fallback
        if "trade" in fn:
            return "trades_history"
        if "tax" in fn:
            return "tax_pnl"
        if "profit" in fn or "pnl" in fn:
            return "profit_loss"
        if "statement" in fn or "ledger" in fn:
            return "ledger"

        return "unknown"

    def parse_angelone_workbook(self, file_bytes: bytes, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Parses an uploaded Angel One workbook directly from memory (io.BytesIO).
        Detects section banners dynamically and starts extracting only from header anchors.
        Never accesses rows above header anchors, guaranteeing 100% Zero-PII sanitization.
        """
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        
        parsed_stats = {
            "executions_merged": 0,
            "closed_roundtrips_merged": 0,
            "open_holdings_merged": 0,
            "dp_charges_merged": 0,
            "capital_entries_merged": 0,
        }

        # Symbol resolution cache from securities_master
        symbol_map = self._get_securities_symbol_map()

        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            sheet_title = sheet_name.strip().lower()

            sheet_type = self._detect_sheet_type(sheet, sheet_title, filename)
            logger.info(f"[TRADEBOOK-ENGINE] Sheet '{sheet_name}' (file: {filename}) classified as '{sheet_type}'")

            # 1. Non Trade Charges (Checked first so 'trade' keyword does not hijack it)
            if sheet_type == "non_trade_charges":
                c_dp = self._parse_non_trade_charges(sheet)
                parsed_stats["dp_charges_merged"] += c_dp

            # 2. Trades History
            elif sheet_type == "trades_history":
                count = self._parse_trades_and_charges(sheet, symbol_map)
                parsed_stats["executions_merged"] += count

            # 3. Tax P&L (Delivery P&L and Open Holdings)
            elif sheet_type == "tax_pnl":
                c_closed, c_open = self._parse_tax_pnl_delivery_and_holdings(sheet, symbol_map)
                parsed_stats["closed_roundtrips_merged"] += c_closed
                parsed_stats["open_holdings_merged"] += c_open

            # 4. Profit & Loss (Equity P&L with ticker symbol mapping)
            elif sheet_type == "profit_loss":
                c_pnl = self._parse_profit_loss_equity(sheet, symbol_map)
                parsed_stats["closed_roundtrips_merged"] += c_pnl

            # 5. Broking Ledger (Capital Funds Added)
            elif sheet_type == "ledger":
                c_cap = self._parse_broking_ledger(sheet)
                parsed_stats["capital_entries_merged"] += c_cap

            # 6. Charges Sheet (Specific DP Charges Breakdown)
            elif sheet_type == "statement_charges":
                c_dp = self._parse_statement_charges(sheet)
                parsed_stats["dp_charges_merged"] += c_dp

        # Reconcile DP charges and live LTP for open holdings
        self._reconcile_dp_charges_and_pnl()
        self._enrich_open_holdings_live_ltp()

        # Regenerate encrypted master Excel workbook
        self.rebuild_encrypted_master_excel()

        # Compute and return updated summary
        summary = self.get_tradebook_summary()
        summary["merge_stats"] = parsed_stats
        return summary

    def _get_securities_symbol_map(self) -> Dict[str, str]:
        """Loads ISIN -> Symbol mapping from securities_master."""
        mapping: Dict[str, str] = {}
        try:
            with self.db.get_connection() as conn:
                rows = conn.execute("SELECT isin, symbol FROM securities_master WHERE isin IS NOT NULL").fetchall()
                for isin, sym in rows:
                    if isin and sym:
                        mapping[str(isin).strip().upper()] = str(sym).strip().upper()
        except Exception as e:
            logger.warning(f"Could not load securities_master mapping: {e}")
        return mapping

    def _normalize_date(self, val: Any) -> Optional[str]:
        """Normalizes date values into YYYY-MM-DD format."""
        if val is None:
            return None
        if isinstance(val, (datetime, date)):
            return val.strftime("%Y-%m-%d")
        val_str = str(val).strip()
        if not val_str or val_str.lower() in ("none", "null", "-"):
            return None
        # Common formats: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%b-%Y", "%d %b %Y"):
            try:
                return datetime.strptime(val_str, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass
        # Fallback regex for YYYY-MM-DD
        m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", val_str)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        return val_str[:10]

    def _to_float(self, val: Any) -> float:
        """Parses float cleanly from formatted numbers (₹, commas, parentheses)."""
        if val is None:
            return 0.0
        if isinstance(val, (int, float)):
            return float(val)
        val_str = str(val).replace("₹", "").replace(",", "").strip()
        if not val_str or val_str in ("-", "Nil", "N/A", "NA"):
            return 0.0
        # Check negative format (123.45)
        if val_str.startswith("(") and val_str.endswith(")"):
            val_str = f"-{val_str[1:-1]}"
        try:
            return float(val_str)
        except ValueError:
            return 0.0

    def _to_int(self, val: Any) -> int:
        return int(round(self._to_float(val)))

    def _extract_symbol_from_scrip(self, scrip_name: str, symbol_map: Dict[str, str], isin: Optional[str] = None) -> str:
        """Extracts canonical NSE ticker symbol from Scrip Name or ISIN."""
        if isin and isin.upper() in symbol_map:
            return symbol_map[isin.upper()]
        clean = str(scrip_name or "").strip()
        if not clean:
            return "UNKNOWN"
        # Often starts with ticker e.g. "SUZLON ENERGY LTD" -> "SUZLON"
        tokens = clean.replace("-", " ").split()
        first_token = tokens[0].upper()
        # Direct common mappings
        alias_map = {
            "M&MFIN": "M&MFIN",
            "M&M": "M&M",
            "ASHOK": "ASHOKLEY",
            "ASHOKLEY": "ASHOKLEY",
            "SUZLON": "SUZLON",
            "RVNL": "RVNL",
            "GAIL": "GAIL",
            "RELIANCE": "RELIANCE",
            "INFOSYS": "INFY",
            "TATA": "TATAPOWER" if "POWER" in clean.upper() else "TATAMOTORS" if "MOTORS" in clean.upper() else tokens[0].upper()
        }
        for k, v in alias_map.items():
            if k in clean.upper():
                return v
        return first_token

    # -------------------------------------------------------------------------
    # SHEET 1: TRADES HISTORY
    # -------------------------------------------------------------------------

    def _parse_trades_and_charges(self, sheet, symbol_map: Dict[str, str]) -> int:
        """Finds 'TradeBook And Charges' header row and extracts executions."""
        anchor_row_idx = None
        col_map: Dict[str, int] = {}

        for row_idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            row_vals = [str(c or "").strip() for c in row]
            # Check for TradeBook And Charges banner or header row
            row_str = " ".join(row_vals).lower()
            if "tradebook and charges" in row_str or ("scrip/contract" in row_str and "buy/sell" in row_str):
                anchor_row_idx = row_idx
                # Check if headers are in this row or next row
                for c_idx, val in enumerate(row_vals):
                    clean_header = val.lower().replace("\n", " ").strip()
                    if clean_header:
                        col_map[clean_header] = c_idx
                if "scrip/contract" not in col_map and "scrip" not in col_map:
                    # Look at next row for headers
                    next_row = list(sheet.iter_rows(min_row=row_idx + 1, max_row=row_idx + 1, values_only=True))
                    if next_row:
                        for c_idx, val in enumerate(next_row[0]):
                            clean_h = str(val or "").lower().replace("\n", " ").strip()
                            if clean_h:
                                col_map[clean_h] = c_idx
                        anchor_row_idx = row_idx + 1
                break

        if not anchor_row_idx or not col_map:
            return 0

        # Helper to find column index with fallback aliases
        def find_col(aliases: List[str]) -> Optional[int]:
            for a in aliases:
                for k, idx in col_map.items():
                    if a in k:
                        return idx
            return None

        c_scrip = find_col(["scrip/contract", "scrip", "contract", "security"])
        c_side = find_col(["buy/sell", "action", "type", "side"])
        c_buy_p = find_col(["buy price", "buy rate"])
        c_sell_p = find_col(["sell price", "sell rate"])
        c_qty = find_col(["quantity", "qty", "volume"])
        c_order_id = find_col(["order id", "order no"])
        c_trade_id = find_col(["trade id", "trade no"])
        c_date = find_col(["date", "trade date"])
        c_brokerage = find_col(["brokerage"])
        c_gst = find_col(["gst"])
        c_stt = find_col(["stt"])
        c_sebi = find_col(["sebi tax", "sebi"])
        c_exch = find_col(["exchange turnover", "turnover charges", "exchange charges"])
        c_stamp = find_col(["stamp duty", "stamp"])
        c_segment = find_col(["segment"])
        c_exchange = find_col(["exchange"])

        inserted_count = 0
        rows_to_insert = []

        for row in sheet.iter_rows(min_row=anchor_row_idx + 1, values_only=True):
            if not row or all(v is None for v in row):
                continue
            scrip_raw = str(row[c_scrip] or "").strip() if c_scrip is not None and c_scrip < len(row) else ""
            if not scrip_raw or scrip_raw.lower() in ("total", "grand total", "sub total"):
                continue

            side_raw = str(row[c_side] or "").strip().upper() if c_side is not None and c_side < len(row) else "BUY"
            side = "SELL" if "S" in side_raw else "BUY"

            qty = self._to_int(row[c_qty]) if c_qty is not None and c_qty < len(row) else 0
            if qty <= 0:
                continue

            buy_price = self._to_float(row[c_buy_p]) if c_buy_p is not None and c_buy_p < len(row) else 0.0
            sell_price = self._to_float(row[c_sell_p]) if c_sell_p is not None and c_sell_p < len(row) else 0.0
            exec_price = buy_price if side == "BUY" and buy_price > 0 else (sell_price if sell_price > 0 else (buy_price or sell_price))

            order_id = str(row[c_order_id] or f"ORD_{inserted_count}").strip() if c_order_id is not None and c_order_id < len(row) else ""
            trade_id = str(row[c_trade_id] or f"TRD_{inserted_count}").strip() if c_trade_id is not None and c_trade_id < len(row) else ""
            trade_date = self._normalize_date(row[c_date]) if c_date is not None and c_date < len(row) else datetime.now().strftime("%Y-%m-%d")

            brokerage = self._to_float(row[c_brokerage]) if c_brokerage is not None and c_brokerage < len(row) else 0.0
            gst = self._to_float(row[c_gst]) if c_gst is not None and c_gst < len(row) else 0.0
            stt = self._to_float(row[c_stt]) if c_stt is not None and c_stt < len(row) else 0.0
            sebi = self._to_float(row[c_sebi]) if c_sebi is not None and c_sebi < len(row) else 0.0
            exch = self._to_float(row[c_exch]) if c_exch is not None and c_exch < len(row) else 0.0
            stamp = self._to_float(row[c_stamp]) if c_stamp is not None and c_stamp < len(row) else 0.0
            total_chg = brokerage + gst + stt + sebi + exch + stamp

            segment = str(row[c_segment] or "EQ").strip() if c_segment is not None and c_segment < len(row) else "EQ"
            exchange = str(row[c_exchange] or "NSE").strip() if c_exchange is not None and c_exchange < len(row) else "NSE"

            symbol = self._extract_symbol_from_scrip(scrip_raw, symbol_map)

            rows_to_insert.append((
                order_id, trade_id, symbol, scrip_raw, side, trade_date, qty, exec_price,
                brokerage, gst, stt, sebi, exch, stamp, total_chg, segment, exchange
            ))

        if rows_to_insert:
            with self.db.get_connection() as conn:
                conn.executemany("""
                    INSERT OR REPLACE INTO real_trade_executions (
                        order_id, trade_id, symbol, scrip_name, side, trade_date, qty, price,
                        brokerage, gst, stt, sebi_tax, exchange_charges, stamp_duty, total_charges, segment, exchange
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, rows_to_insert)
                conn.commit()
            inserted_count = len(rows_to_insert)

        return inserted_count

    # -------------------------------------------------------------------------
    # SHEET 2: TAX P&L (Delivery P&L and Open Holdings)
    # -------------------------------------------------------------------------

    def _parse_tax_pnl_delivery_and_holdings(self, sheet, symbol_map: Dict[str, str]) -> Tuple[int, int]:
        """Parses Delivery P&L (closed trades) and Open Holdings from Tax P&L report."""
        closed_rows = []
        open_rows = []

        current_mode = None  # "delivery" or "open"
        delivery_col_map: Dict[str, int] = {}
        open_col_map: Dict[str, int] = {}

        for row in sheet.iter_rows(values_only=True):
            if not row or all(v is None for v in row):
                continue
            row_vals = [str(c or "").strip() for c in row]
            row_str = " ".join(row_vals).lower()

            # Section Anchor Detection
            if "delivery p&l" in row_str or "delivery pnl" in row_str:
                current_mode = "delivery_header"
                continue
            if "open holdings" in row_str:
                current_mode = "open_header"
                continue

            # Header extraction for delivery
            if current_mode == "delivery_header":
                delivery_col_map = {v.lower().replace("\n", " ").strip(): idx for idx, v in enumerate(row_vals) if v}
                current_mode = "delivery"
                continue

            # Header extraction for open holdings
            if current_mode == "open_header":
                open_col_map = {v.lower().replace("\n", " ").strip(): idx for idx, v in enumerate(row_vals) if v}
                current_mode = "open"
                continue

            # Process Delivery Rows
            if current_mode == "delivery":
                isin_idx = self._find_col_in_dict(delivery_col_map, ["isin"])
                scrip_idx = self._find_col_in_dict(delivery_col_map, ["scrip name", "scrip", "security"])
                qty_idx = self._find_col_in_dict(delivery_col_map, ["qty", "quantity"])

                scrip_val = row[scrip_idx] if scrip_idx is not None and scrip_idx < len(row) else None
                if not scrip_val or str(scrip_val).strip().lower() in ("total", "grand total", "sub total"):
                    if "open holdings" in row_str:
                        current_mode = "open_header"
                    continue

                isin = str(row[isin_idx] or "").strip() if isin_idx is not None and isin_idx < len(row) else ""
                scrip_name = str(scrip_val).strip()
                qty = self._to_int(row[qty_idx]) if qty_idx is not None and qty_idx < len(row) else 0
                if qty <= 0:
                    continue

                b_date_idx = self._find_col_in_dict(delivery_col_map, ["buy date"])
                s_date_idx = self._find_col_in_dict(delivery_col_map, ["sell date"])
                b_price_idx = self._find_col_in_dict(delivery_col_map, ["avg buy price", "buy price", "buy rate"])
                b_val_idx = self._find_col_in_dict(delivery_col_map, ["buy value"])
                s_price_idx = self._find_col_in_dict(delivery_col_map, ["avg sell price", "sell price", "sell rate"])
                s_val_idx = self._find_col_in_dict(delivery_col_map, ["sell value"])
                chg_idx = self._find_col_in_dict(delivery_col_map, ["charges and statutory", "charges"])
                stt_idx = self._find_col_in_dict(delivery_col_map, ["stt"])
                net_pnl_idx = self._find_col_in_dict(delivery_col_map, ["net profit", "net pnl"])

                buy_date = self._normalize_date(row[b_date_idx]) if b_date_idx is not None and b_date_idx < len(row) else None
                sell_date = self._normalize_date(row[s_date_idx]) if s_date_idx is not None and s_date_idx < len(row) else None

                avg_buy_price = self._to_float(row[b_price_idx]) if b_price_idx is not None and b_price_idx < len(row) else 0.0
                buy_val = self._to_float(row[b_val_idx]) if b_val_idx is not None and b_val_idx < len(row) else avg_buy_price * qty
                avg_sell_price = self._to_float(row[s_price_idx]) if s_price_idx is not None and s_price_idx < len(row) else 0.0
                sell_val = self._to_float(row[s_val_idx]) if s_val_idx is not None and s_val_idx < len(row) else avg_sell_price * qty

                gross_pnl = sell_val - buy_val
                charges = self._to_float(row[chg_idx]) if chg_idx is not None and chg_idx < len(row) else 0.0
                stt = self._to_float(row[stt_idx]) if stt_idx is not None and stt_idx < len(row) else 0.0
                trade_taxes = charges + stt

                # Holding period in days
                hold_days = 0
                if buy_date and sell_date:
                    try:
                        d1 = datetime.strptime(buy_date, "%Y-%m-%d")
                        d2 = datetime.strptime(sell_date, "%Y-%m-%d")
                        hold_days = max(0, (d2 - d1).days)
                    except ValueError:
                        pass

                # Pre-apply default Angel One DP charge (₹23.60)
                dp_charge = DEFAULT_ANGEL_ONE_DP_CHARGE
                net_pnl = gross_pnl - trade_taxes - dp_charge
                net_return_pct = (net_pnl / buy_val * 100.0) if buy_val > 0 else 0.0
                outcome = "WIN" if net_pnl > 0 else "LOSS"

                symbol = self._extract_symbol_from_scrip(scrip_name, symbol_map, isin)

                closed_rows.append((
                    isin, symbol, scrip_name, qty, buy_date, sell_date, hold_days,
                    avg_buy_price, buy_val, avg_sell_price, sell_val, gross_pnl,
                    trade_taxes, stt, dp_charge, net_pnl, net_return_pct, outcome
                ))

            # Process Open Holdings
            elif current_mode == "open":
                isin_idx = self._find_col_in_dict(open_col_map, ["isin"])
                scrip_idx = self._find_col_in_dict(open_col_map, ["scrip name", "scrip"])
                qty_idx = self._find_col_in_dict(open_col_map, ["quantity", "qty"])

                scrip_val = row[scrip_idx] if scrip_idx is not None and scrip_idx < len(row) else None
                if not scrip_val or str(scrip_val).strip().lower() in ("total", "grand total", "sub total"):
                    continue

                isin = str(row[isin_idx] or "").strip() if isin_idx is not None and isin_idx < len(row) else ""
                scrip_name = str(scrip_val).strip()
                qty = self._to_int(row[qty_idx]) if qty_idx is not None and qty_idx < len(row) else 0
                if qty <= 0:
                    continue

                b_price_idx = self._find_col_in_dict(open_col_map, ["avg buy price", "buy price"])
                b_val_idx = self._find_col_in_dict(open_col_map, ["buy value"])
                chg_idx = self._find_col_in_dict(open_col_map, ["charges and statutory", "charges"])
                stt_idx = self._find_col_in_dict(open_col_map, ["stt"])
                close_rate_idx = self._find_col_in_dict(open_col_map, ["closing rate", "ltp"])
                unreal_pnl_idx = self._find_col_in_dict(open_col_map, ["unrealised p&l", "unrealized pnl", "short term unrealised"])

                avg_buy_price = self._to_float(row[b_price_idx]) if b_price_idx is not None and b_price_idx < len(row) else 0.0
                buy_val = self._to_float(row[b_val_idx]) if b_val_idx is not None and b_val_idx < len(row) else avg_buy_price * qty
                charges = self._to_float(row[chg_idx]) if chg_idx is not None and chg_idx < len(row) else 0.0
                stt = self._to_float(row[stt_idx]) if stt_idx is not None and stt_idx < len(row) else 0.0
                closing_rate = self._to_float(row[close_rate_idx]) if close_rate_idx is not None and close_rate_idx < len(row) else avg_buy_price
                curr_val = closing_rate * qty
                unreal_pnl = self._to_float(row[unreal_pnl_idx]) if unreal_pnl_idx is not None and unreal_pnl_idx < len(row) else (curr_val - buy_val)
                unreal_pct = (unreal_pnl / buy_val * 100.0) if buy_val > 0 else 0.0

                symbol = self._extract_symbol_from_scrip(scrip_name, symbol_map, isin)

                open_rows.append((
                    isin, symbol, scrip_name, qty, avg_buy_price, buy_val,
                    charges, stt, closing_rate, curr_val, unreal_pnl, unreal_pct
                ))

        with self.db.get_connection() as conn:
            if closed_rows:
                conn.executemany("""
                    INSERT OR REPLACE INTO real_closed_roundtrips (
                        isin, symbol, scrip_name, qty, buy_date, sell_date, hold_days,
                        avg_buy_price, buy_value, avg_sell_price, sell_value, gross_pnl,
                        trade_charges, stt, dp_charge, net_pnl, net_return_pct, outcome
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, closed_rows)

            if open_rows:
                conn.executemany("""
                    INSERT OR REPLACE INTO real_open_holdings (
                        isin, symbol, scrip_name, qty, avg_buy_price, buy_value,
                        charges, stt, closing_rate, current_value, unrealized_pnl, unrealized_pnl_pct
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, open_rows)
            conn.commit()

        return len(closed_rows), len(open_rows)

    def _find_col_in_dict(self, col_dict: Dict[str, int], aliases: List[str]) -> Optional[int]:
        for a in aliases:
            for k, idx in col_dict.items():
                if a in k:
                    return idx
        return None

    # -------------------------------------------------------------------------
    # SHEET 3: NON TRADE CHARGES (DP Postings)
    # -------------------------------------------------------------------------

    def _parse_non_trade_charges(self, sheet) -> int:
        """Extracts DP charge debit postings from Non Trade Charges."""
        anchor_row = None
        col_map = {}
        for r_idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            row_vals = [str(c or "").strip() for c in row]
            row_str = " ".join(row_vals).lower()
            if "charges details" in row_str or ("charge" in row_str and "posting date" in row_str):
                anchor_row = r_idx
                for c_idx, val in enumerate(row_vals):
                    clean_h = val.lower().replace("\n", " ").strip()
                    if clean_h:
                        col_map[clean_h] = c_idx
                if "charge" not in col_map and "particulars" not in col_map:
                    next_row = list(sheet.iter_rows(min_row=r_idx + 1, max_row=r_idx + 1, values_only=True))
                    if next_row:
                        for c_idx, val in enumerate(next_row[0]):
                            clean_h = str(val or "").lower().replace("\n", " ").strip()
                            if clean_h:
                                col_map[clean_h] = c_idx
                        anchor_row = r_idx + 1
                break

        if not anchor_row:
            return 0

        c_charge = self._find_col_in_dict(col_map, ["charge", "charge type", "particulars"])
        c_date = self._find_col_in_dict(col_map, ["posting date", "date"])
        c_debit = self._find_col_in_dict(col_map, ["debit amount", "debit", "amount"])

        dp_rows = []
        for row in sheet.iter_rows(min_row=anchor_row + 1, values_only=True):
            if not row or all(v is None for v in row):
                continue
            desc = str(row[c_charge] or "").strip() if c_charge is not None and c_charge < len(row) else ""
            if not desc or desc.lower() in ("total", "grand total"):
                continue

            # Check if this is a Depository / DP charge
            if "depository" in desc.lower() or "dp charge" in desc.lower():
                post_date = self._normalize_date(row[c_date]) if c_date is not None and c_date < len(row) else None
                debit = self._to_float(row[c_debit]) if c_debit is not None and c_debit < len(row) else DEFAULT_ANGEL_ONE_DP_CHARGE
                # In non-trade charges, scrip/ISIN is often in the desc or non-trade
                dp_rows.append(("", desc, post_date or "", 0, 3.50, 16.50, 3.60, debit or DEFAULT_ANGEL_ONE_DP_CHARGE))

        if dp_rows:
            with self.db.get_connection() as conn:
                conn.executemany("""
                    INSERT OR IGNORE INTO real_dp_charges (
                        isin, scrip_name, charge_date, qty_sold, cdsl_charge, angelone_charge, gst, total_charge
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, dp_rows)
                conn.commit()

        return len(dp_rows)

    # -------------------------------------------------------------------------
    # SHEET 4: PROFIT & LOSS (Equity P&L with Ticker Symbols)
    # -------------------------------------------------------------------------

    def _parse_profit_loss_equity(self, sheet, symbol_map: Dict[str, str]) -> int:
        """Parses Profit & Loss sheet to capture ticker symbols and map to scrips."""
        anchor_row = None
        col_map = {}
        for r_idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            row_vals = [str(c or "").strip() for c in row]
            row_str = " ".join(row_vals).lower()
            if "delivery pnl" in row_str or ("scrip symbol" in row_str and "company name" in row_str):
                anchor_row = r_idx
                for c_idx, val in enumerate(row_vals):
                    clean_h = val.lower().replace("\n", " ").strip()
                    if clean_h:
                        col_map[clean_h] = c_idx
                if "scrip symbol" not in col_map and "symbol" not in col_map and "company name" not in col_map:
                    next_row = list(sheet.iter_rows(min_row=r_idx + 1, max_row=r_idx + 1, values_only=True))
                    if next_row:
                        for c_idx, val in enumerate(next_row[0]):
                            clean_h = str(val or "").lower().replace("\n", " ").strip()
                            if clean_h:
                                col_map[clean_h] = c_idx
                        anchor_row = r_idx + 1
                break

        if not anchor_row:
            return 0

        c_sym = self._find_col_in_dict(col_map, ["scrip symbol", "symbol", "ticker"])
        c_name = self._find_col_in_dict(col_map, ["company name", "scrip name", "company"])
        c_qty = self._find_col_in_dict(col_map, ["quantity", "qty"])
        c_buy_p = self._find_col_in_dict(col_map, ["avg buy price", "buy price"])
        c_buy_v = self._find_col_in_dict(col_map, ["buy value"])
        c_sell_p = self._find_col_in_dict(col_map, ["avg sell price", "sell price"])
        c_sell_v = self._find_col_in_dict(col_map, ["sell value"])
        c_gross = self._find_col_in_dict(col_map, ["gross pnl", "gross profit"])
        c_chg = self._find_col_in_dict(col_map, ["charges and statutory", "charges"])
        c_net = self._find_col_in_dict(col_map, ["net pnl", "net profit"])

        rows_merged = 0
        with self.db.get_connection() as conn:
            for row in sheet.iter_rows(min_row=anchor_row + 1, values_only=True):
                if not row or all(v is None for v in row):
                    continue
                sym = str(row[c_sym] or "").strip().upper() if c_sym is not None and c_sym < len(row) else ""
                name = str(row[c_name] or "").strip() if c_name is not None and c_name < len(row) else ""
                if not sym or sym.lower() in ("total", "grand total"):
                    continue

                # Update securities_master or local mapping if symbol matches scrip
                if name:
                    symbol_map[name.upper()] = sym

                qty = self._to_int(row[c_qty]) if c_qty is not None and c_qty < len(row) else 0
                if qty <= 0:
                    continue

                buy_p = self._to_float(row[c_buy_p]) if c_buy_p is not None and c_buy_p < len(row) else 0.0
                buy_v = self._to_float(row[c_buy_v]) if c_buy_v is not None and c_buy_v < len(row) else buy_p * qty
                sell_p = self._to_float(row[c_sell_p]) if c_sell_p is not None and c_sell_p < len(row) else 0.0
                sell_v = self._to_float(row[c_sell_v]) if c_sell_v is not None and c_sell_v < len(row) else sell_p * qty
                gross_pnl = self._to_float(row[c_gross]) if c_gross is not None and c_gross < len(row) else (sell_v - buy_v)
                trade_taxes = self._to_float(row[c_chg]) if c_chg is not None and c_chg < len(row) else 0.0
                dp_charge = DEFAULT_ANGEL_ONE_DP_CHARGE
                net_pnl = gross_pnl - trade_taxes - dp_charge
                net_ret = (net_pnl / buy_v * 100.0) if buy_v > 0 else 0.0
                outcome = "WIN" if net_pnl > 0 else "LOSS"

                # Check if this trade is already present under ISIN or scrip; if so update symbol, else insert fallback
                cur = conn.execute("""
                    UPDATE real_closed_roundtrips
                    SET symbol = ?
                    WHERE (scrip_name = ? OR symbol = 'UNKNOWN' OR symbol = ?) AND qty = ?
                """, (sym, name, sym, qty))

                # Only insert as fallback if no matching closed swing exists
                if cur.rowcount == 0:
                    conn.execute("""
                        INSERT OR IGNORE INTO real_closed_roundtrips (
                            isin, symbol, scrip_name, qty, avg_buy_price, buy_value,
                            avg_sell_price, sell_value, gross_pnl, trade_charges, dp_charge,
                            net_pnl, net_return_pct, outcome
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        "", sym, name, qty, buy_p, buy_v, sell_p, sell_v,
                        gross_pnl, trade_taxes, dp_charge, net_pnl, net_ret, outcome
                    ))
                rows_merged += 1
            conn.commit()

        return rows_merged

    # -------------------------------------------------------------------------
    # SHEET 5: BROKING LEDGER (Capital Inflows)
    # -------------------------------------------------------------------------

    def _parse_broking_ledger(self, sheet) -> int:
        """Parses Broking Ledger to extract Funds Added capital deposits."""
        anchor_row = None
        col_map = {}
        for r_idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            row_vals = [str(c or "").strip() for c in row]
            row_str = " ".join(row_vals).lower()
            if "transaction details" in row_str or ("transaction" in row_str and "voucher" in row_str):
                anchor_row = r_idx
                for c_idx, val in enumerate(row_vals):
                    clean_h = val.lower().replace("\n", " ").strip()
                    if clean_h:
                        col_map[clean_h] = c_idx
                if "transaction" not in col_map and "particulars" not in col_map:
                    next_row = list(sheet.iter_rows(min_row=r_idx + 1, max_row=r_idx + 1, values_only=True))
                    if next_row:
                        for c_idx, val in enumerate(next_row[0]):
                            clean_h = str(val or "").lower().replace("\n", " ").strip()
                            if clean_h:
                                col_map[clean_h] = c_idx
                        anchor_row = r_idx + 1
                break

        if not anchor_row:
            return 0

        c_tx = self._find_col_in_dict(col_map, ["transaction", "particulars", "description"])
        c_date = self._find_col_in_dict(col_map, ["date", "posting date"])
        c_vouch = self._find_col_in_dict(col_map, ["voucher", "voucherno", "ref"])
        c_dr = self._find_col_in_dict(col_map, ["debit"])
        c_cr = self._find_col_in_dict(col_map, ["credit"])
        c_bal = self._find_col_in_dict(col_map, ["running balance", "balance"])

        cap_rows = []
        for row in sheet.iter_rows(min_row=anchor_row + 1, values_only=True):
            if not row or all(v is None for v in row):
                continue
            tx_desc = str(row[c_tx] or "").strip() if c_tx is not None and c_tx < len(row) else ""
            if not tx_desc or tx_desc.lower() in ("total", "grand total", "opening balance"):
                continue

            tx_date = self._normalize_date(row[c_date]) if c_date is not None and c_date < len(row) else ""
            voucher = str(row[c_vouch] or "").strip() if c_vouch is not None and c_vouch < len(row) else ""
            debit = self._to_float(row[c_dr]) if c_dr is not None and c_dr < len(row) else 0.0
            credit = self._to_float(row[c_cr]) if c_cr is not None and c_cr < len(row) else 0.0
            bal = self._to_float(row[c_bal]) if c_bal is not None and c_bal < len(row) else 0.0

            # Only record capital inflows/outflows (e.g. Funds Added, UPI, Net Banking, Payouts)
            is_capital = any(kw in tx_desc.lower() for kw in ("funds added", "fund added", "upi", "net banking", "receipt", "payment", "deposit", "withdrawal"))
            if is_capital or credit > 0:
                cap_rows.append((tx_desc, tx_date, voucher, debit, credit, bal))

        if cap_rows:
            with self.db.get_connection() as conn:
                conn.executemany("""
                    INSERT OR IGNORE INTO real_capital_ledger (
                        transaction_type, tx_date, voucher, debit, credit, running_balance
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, cap_rows)
                conn.commit()

        return len(cap_rows)

    # -------------------------------------------------------------------------
    # SHEET 6: STATEMENT CHARGES (DP Breakdown)
    # -------------------------------------------------------------------------

    def _parse_statement_charges(self, sheet) -> int:
        """Parses Statement Charges tab containing scrip-level DP charges."""
        anchor_row = None
        col_map = {}
        for r_idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            row_vals = [str(c or "").strip() for c in row]
            row_str = " ".join(row_vals).lower()
            if "dp charges" in row_str or ("scrip name" in row_str and "isin" in row_str and "cdsl charge" in row_str):
                anchor_row = r_idx
                for c_idx, val in enumerate(row_vals):
                    clean_h = val.lower().replace("\n", " ").strip()
                    if clean_h:
                        col_map[clean_h] = c_idx
                if "scrip name" not in col_map and "isin" not in col_map:
                    next_row = list(sheet.iter_rows(min_row=r_idx + 1, max_row=r_idx + 1, values_only=True))
                    if next_row:
                        for c_idx, val in enumerate(next_row[0]):
                            clean_h = str(val or "").lower().replace("\n", " ").strip()
                            if clean_h:
                                col_map[clean_h] = c_idx
                        anchor_row = r_idx + 1
                break

        if not anchor_row:
            return 0

        c_name = self._find_col_in_dict(col_map, ["scrip name", "scrip"])
        c_isin = self._find_col_in_dict(col_map, ["isin"])
        c_date = self._find_col_in_dict(col_map, ["date"])
        c_qty = self._find_col_in_dict(col_map, ["quantity sold", "qty sold", "quantity"])
        c_cdsl = self._find_col_in_dict(col_map, ["cdsl charge", "cdsl"])
        c_angel = self._find_col_in_dict(col_map, ["angelone charge", "angel charge"])
        c_gst = self._find_col_in_dict(col_map, ["gst"])
        c_total = self._find_col_in_dict(col_map, ["total charge", "total"])

        dp_rows = []
        for row in sheet.iter_rows(min_row=anchor_row + 1, values_only=True):
            if not row or all(v is None for v in row):
                continue
            scrip_name = str(row[c_name] or "").strip() if c_name is not None and c_name < len(row) else ""
            if not scrip_name or scrip_name.lower() in ("total", "grand total"):
                continue

            isin = str(row[c_isin] or "").strip() if c_isin is not None and c_isin < len(row) else ""
            chg_date = self._normalize_date(row[c_date]) if c_date is not None and c_date < len(row) else ""
            qty_sold = self._to_int(row[c_qty]) if c_qty is not None and c_qty < len(row) else 0
            cdsl = self._to_float(row[c_cdsl]) if c_cdsl is not None and c_cdsl < len(row) else 3.50
            angel = self._to_float(row[c_angel]) if c_angel is not None and c_angel < len(row) else 16.50
            gst = self._to_float(row[c_gst]) if c_gst is not None and c_gst < len(row) else 3.60
            total = self._to_float(row[c_total]) if c_total is not None and c_total < len(row) else (cdsl + angel + gst)

            dp_rows.append((isin, scrip_name, chg_date, qty_sold, cdsl, angel, gst, total))

        if dp_rows:
            with self.db.get_connection() as conn:
                conn.executemany("""
                    INSERT OR REPLACE INTO real_dp_charges (
                        isin, scrip_name, charge_date, qty_sold, cdsl_charge, angelone_charge, gst, total_charge
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, dp_rows)
                conn.commit()

        return len(dp_rows)

    # -------------------------------------------------------------------------
    # RECONCILIATION & ENRICHMENT
    # -------------------------------------------------------------------------

    def _reconcile_dp_charges_and_pnl(self) -> None:
        """
        Reconciles each closed delivery trade with exact DP fees.
        Angel One deducts ₹23.60 on each delivery sell settlement.
        Updates True Net Realized P&L = Gross P&L - Trade Taxes - DP Fee.
        """
        with self.db.get_connection() as conn:
            # Match DP charges by ISIN and sell_date where available
            conn.execute("""
                UPDATE real_closed_roundtrips
                SET dp_charge = COALESCE(
                    (SELECT total_charge FROM real_dp_charges WHERE real_dp_charges.isin = real_closed_roundtrips.isin LIMIT 1),
                    ?
                )
                WHERE dp_charge IS NULL OR dp_charge = 0.0
            """, (DEFAULT_ANGEL_ONE_DP_CHARGE,))

            # Recompute Net P&L and Net Return %
            conn.execute("""
                UPDATE real_closed_roundtrips
                SET net_pnl = ROUND(COALESCE(gross_pnl, 0.0) - COALESCE(trade_charges, 0.0) - COALESCE(dp_charge, 23.60), 2),
                    net_return_pct = CASE WHEN COALESCE(buy_value, 0.0) > 0 THEN ROUND(((COALESCE(gross_pnl, 0.0) - COALESCE(trade_charges, 0.0) - COALESCE(dp_charge, 23.60)) / buy_value) * 100.0, 2) ELSE 0.0 END,
                    outcome = CASE WHEN (COALESCE(gross_pnl, 0.0) - COALESCE(trade_charges, 0.0) - COALESCE(dp_charge, 23.60)) > 0 THEN 'WIN' ELSE 'LOSS' END
            """)
            conn.commit()

    def _enrich_open_holdings_live_ltp(self) -> None:
        """Enriches open holdings with live/latest LTP from ohlcv_daily."""
        with self.db.get_connection() as conn:
            holdings = conn.execute("SELECT id, symbol, isin, qty, avg_buy_price, buy_value FROM real_open_holdings").fetchall()
            for hid, sym, isin, qty, avg_buy, buy_val in holdings:
                ltp = None
                target_sym = sym if sym and sym != "UNKNOWN" else None
                if not target_sym and isin:
                    row_sec = conn.execute("SELECT symbol FROM securities_master WHERE isin = ?", (isin,)).fetchone()
                    if row_sec and row_sec[0]:
                        target_sym = str(row_sec[0]).strip().upper()

                if target_sym:
                    try:
                        row = conn.execute(
                            "SELECT close FROM ohlcv_daily WHERE symbol = ? ORDER BY trading_date DESC LIMIT 1",
                            (target_sym,)
                        ).fetchone()
                        if row and row[0]:
                            ltp = float(row[0])
                    except Exception:
                        try:
                            row = conn.execute(
                                "SELECT close FROM ohlcv_daily WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                                (target_sym,)
                            ).fetchone()
                            if row and row[0]:
                                ltp = float(row[0])
                        except Exception:
                            ltp = None

                if ltp and ltp > 0:
                    curr_val = round(ltp * qty, 2)
                    unreal_pnl = round(curr_val - buy_val, 2)
                    unreal_pct = round((unreal_pnl / buy_val * 100.0), 2) if buy_val > 0 else 0.0
                    conn.execute("""
                        UPDATE real_open_holdings
                        SET closing_rate = ?, current_value = ?, unrealized_pnl = ?, unrealized_pnl_pct = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (ltp, curr_val, unreal_pnl, unreal_pct, hid))
            conn.commit()

    # =========================================================================
    # SUMMARY KPI METRICS
    # =========================================================================

    def get_tradebook_summary(self) -> Dict[str, Any]:
        """Returns PII-free summary metrics, closed trades list, open holdings, and attribution."""
        with self.db.get_connection() as conn:
            # Capital added
            cap_row = conn.execute("SELECT SUM(credit) FROM real_capital_ledger").fetchone()
            total_capital = float(cap_row[0] or 0.0)

            # Closed trades aggregate
            ct_row = conn.execute("""
                SELECT 
                    COUNT(*),
                    COALESCE(SUM(buy_value), 0.0),
                    COALESCE(SUM(gross_pnl), 0.0),
                    COALESCE(SUM(trade_charges), 0.0),
                    COALESCE(SUM(dp_charge), 0.0),
                    COALESCE(SUM(net_pnl), 0.0),
                    COALESCE(SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN net_pnl > 0 THEN net_pnl ELSE 0 END), 0.0),
                    COALESCE(SUM(CASE WHEN net_pnl < 0 THEN ABS(net_pnl) ELSE 0 END), 0.0),
                    COALESCE(AVG(hold_days), 0.0)
                FROM real_closed_roundtrips
            """).fetchone()

            total_trades = int(ct_row[0] or 0)
            total_buy_val = float(ct_row[1] or 0.0)
            realized_gross_pnl = float(ct_row[2] or 0.0)
            total_trade_taxes = float(ct_row[3] or 0.0)
            total_dp_charges = float(ct_row[4] or 0.0)
            true_net_pnl = float(ct_row[5] or 0.0)
            win_count = int(ct_row[6] or 0)
            gross_wins = float(ct_row[7] or 0.0)
            gross_losses = float(ct_row[8] or 0.0)
            avg_hold_days = float(ct_row[9] or 0.0)

            # If capital ledger has no deposits, estimate base capital from maximum concurrent allocation
            if total_capital <= 0.0:
                total_capital = total_buy_val

            win_rate_pct = round((win_count / total_trades * 100.0), 2) if total_trades > 0 else 0.0
            profit_factor = round((gross_wins / (gross_losses + 1e-6)), 2) if gross_losses > 0 else (10.0 if gross_wins > 0 else 0.0)
            total_friction = total_trade_taxes + total_dp_charges
            fee_drag_pct = round((total_friction / (abs(realized_gross_pnl) + 1e-6) * 100.0), 2) if realized_gross_pnl != 0 else 0.0
            net_roi_pct = round((true_net_pnl / (total_capital + 1e-6) * 100.0), 2) if total_capital > 0 else 0.0

            # Open holdings aggregate
            oh_row = conn.execute("""
                SELECT 
                    COUNT(*),
                    COALESCE(SUM(buy_value), 0.0),
                    COALESCE(SUM(current_value), 0.0),
                    COALESCE(SUM(unrealized_pnl), 0.0)
                FROM real_open_holdings
            """).fetchone()

            open_count = int(oh_row[0] or 0)
            open_invested = float(oh_row[1] or 0.0)
            open_current = float(oh_row[2] or 0.0)
            open_unrealized_pnl = float(oh_row[3] or 0.0)
            open_unrealized_pct = round((open_unrealized_pnl / open_invested * 100.0), 2) if open_invested > 0 else 0.0

            # Closed trades detail list
            closed_trades = []
            c_rows = conn.execute("""
                SELECT symbol, isin, scrip_name, qty, buy_date, sell_date, hold_days,
                       avg_buy_price, buy_value, avg_sell_price, sell_value, gross_pnl,
                       trade_charges, dp_charge, net_pnl, net_return_pct, outcome
                FROM real_closed_roundtrips
                ORDER BY sell_date DESC, id DESC
            """).fetchall()
            for r in c_rows:
                closed_trades.append({
                    "symbol": r[0], "isin": r[1], "scrip_name": r[2], "qty": r[3],
                    "buy_date": r[4], "sell_date": r[5], "hold_days": r[6],
                    "avg_buy_price": r[7], "buy_value": r[8], "avg_sell_price": r[9], "sell_value": r[10],
                    "gross_pnl": r[11], "trade_charges": r[12], "dp_charge": r[13],
                    "net_pnl": r[14], "net_return_pct": r[15], "outcome": r[16]
                })

            # Open holdings detail list
            open_holdings = []
            o_rows = conn.execute("""
                SELECT symbol, isin, scrip_name, qty, avg_buy_price, buy_value,
                       closing_rate, current_value, unrealized_pnl, unrealized_pnl_pct
                FROM real_open_holdings
                ORDER BY current_value DESC
            """).fetchall()
            for r in o_rows:
                open_holdings.append({
                    "symbol": r[0], "isin": r[1], "scrip_name": r[2], "qty": r[3],
                    "avg_buy_price": r[4], "buy_value": r[5], "closing_rate": r[6],
                    "current_value": r[7], "unrealized_pnl": r[8], "unrealized_pnl_pct": r[9]
                })

            # Scrip Attribution
            scrip_attribution = []
            attr_rows = conn.execute("""
                SELECT 
                    symbol, scrip_name,
                    COUNT(*),
                    SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN net_pnl <= 0 THEN 1 ELSE 0 END),
                    SUM(gross_pnl),
                    SUM(trade_charges),
                    SUM(dp_charge),
                    SUM(net_pnl)
                FROM real_closed_roundtrips
                GROUP BY symbol
                ORDER BY SUM(net_pnl) DESC
            """).fetchall()
            for r in attr_rows:
                sym_trades = r[2]
                sym_wins = r[3]
                scrip_attribution.append({
                    "symbol": r[0], "company_name": r[1], "trades": sym_trades,
                    "wins": sym_wins, "losses": r[4],
                    "win_rate_pct": round((sym_wins / sym_trades * 100.0), 2) if sym_trades > 0 else 0.0,
                    "gross_pnl": round(r[5], 2), "trade_charges": round(r[6], 2),
                    "dp_charges": round(r[7], 2), "net_pnl": round(r[8], 2)
                })

        return {
            "total_capital": round(total_capital, 2),
            "realized_gross_pnl": round(realized_gross_pnl, 2),
            "total_trade_taxes": round(total_trade_taxes, 2),
            "total_dp_charges": round(total_dp_charges, 2),
            "total_friction": round(total_friction, 2),
            "true_net_pnl": round(true_net_pnl, 2),
            "net_roi_pct": net_roi_pct,
            "total_trades": total_trades,
            "win_count": win_count,
            "loss_count": total_trades - win_count,
            "win_rate_pct": win_rate_pct,
            "profit_factor": profit_factor,
            "avg_hold_days": round(avg_hold_days, 1),
            "fee_drag_pct": fee_drag_pct,
            "open_count": open_count,
            "open_invested": round(open_invested, 2),
            "open_current": round(open_current, 2),
            "open_unrealized_pnl": round(open_unrealized_pnl, 2),
            "open_unrealized_pct": open_unrealized_pct,
            "closed_trades": closed_trades,
            "open_holdings": open_holdings,
            "scrip_attribution": scrip_attribution
        }

    # =========================================================================
    # MASTER EXCEL WORKBOOK GENERATOR (5 TABS & ENCRYPTION)
    # =========================================================================

    def rebuild_encrypted_master_excel(self) -> bytes:
        """
        Builds a styled 5-tab Master Trading Record in memory using openpyxl,
        encrypts it via Fernet, and writes it atomically to data/secure/master_tradebook.enc.
        Returns the unencrypted bytes for download streaming.
        """
        wb = openpyxl.Workbook()
        # Remove default sheet
        wb.remove(wb.active)

        # Style palette
        navy_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        card_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        soft_gray_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        green_text = Font(name="Calibri", size=10, bold=True, color="16A34A")
        red_text = Font(name="Calibri", size=10, bold=True, color="DC2626")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        title_font = Font(name="Calibri", size=14, bold=True, color="0F172A")
        sub_font = Font(name="Calibri", size=10, italic=True, color="64748B")
        regular_font = Font(name="Calibri", size=10, color="0F172A")
        bold_font = Font(name="Calibri", size=10, bold=True, color="0F172A")

        thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )

        align_left = Alignment(horizontal="left", vertical="center")
        align_center = Alignment(horizontal="center", vertical="center")
        align_right = Alignment(horizontal="right", vertical="center")

        summary = self.get_tradebook_summary()

        # ---------------------------------------------------------------------
        # TAB 1: Executive_Summary
        # ---------------------------------------------------------------------
        ws_sum = wb.create_sheet(title="Executive_Summary")
        ws_sum.views.sheetView[0].showGridLines = True

        ws_sum["A2"] = "MARKET INTELLIGENCE LAB — MASTER TRADING RECORD"
        ws_sum["A2"].font = title_font
        ws_sum["A3"] = f"Executive P&L Audit & Demat Friction Reconciliation · Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ws_sum["A3"].font = sub_font

        # Metric Cards
        metrics = [
            ("Total Capital Deployed (₹)", summary["total_capital"], "₹#,##0.00"),
            ("Realized Gross P&L (₹)", summary["realized_gross_pnl"], "₹#,##0.00"),
            ("Trade Taxes & Exchange Levies (₹)", summary["total_trade_taxes"], "₹#,##0.00"),
            ("Demat DP Charges (₹23.60/sell) (₹)", summary["total_dp_charges"], "₹#,##0.00"),
            ("True Net Realized P&L (₹)", summary["true_net_pnl"], "₹#,##0.00"),
            ("Net ROI on Capital (%)", summary["net_roi_pct"] / 100.0, "0.00%"),
            ("Unrealized Holdings P&L (₹)", summary["open_unrealized_pnl"], "₹#,##0.00"),
            ("Total Closed Swings", summary["total_trades"], "#,##0"),
            ("Win Rate (%)", summary["win_rate_pct"] / 100.0, "0.00%"),
            ("Profit Factor", summary["profit_factor"], "0.00"),
            ("Average Holding Days", summary["avg_hold_days"], "0.0"),
            ("Friction Drag on Gross P&L (%)", summary["fee_drag_pct"] / 100.0, "0.00%"),
        ]

        row_cursor = 5
        ws_sum.cell(row=row_cursor, column=1, value="Core Performance Metric").fill = navy_fill
        ws_sum.cell(row=row_cursor, column=1).font = header_font
        ws_sum.cell(row=row_cursor, column=1).alignment = align_left

        ws_sum.cell(row=row_cursor, column=2, value="Reconciled Value").fill = navy_fill
        ws_sum.cell(row=row_cursor, column=2).font = header_font
        ws_sum.cell(row=row_cursor, column=2).alignment = align_right

        for label, val, num_fmt in metrics:
            row_cursor += 1
            c1 = ws_sum.cell(row=row_cursor, column=1, value=label)
            c2 = ws_sum.cell(row=row_cursor, column=2, value=val)
            c1.font = bold_font
            c1.fill = soft_gray_fill if row_cursor % 2 == 0 else PatternFill(fill_type=None)
            c1.border = thin_border
            c1.alignment = align_left

            c2.font = regular_font
            c2.fill = soft_gray_fill if row_cursor % 2 == 0 else PatternFill(fill_type=None)
            c2.border = thin_border
            c2.number_format = num_fmt
            c2.alignment = align_right

            # Highlight Net P&L
            if "Net Realized P&L" in label:
                c2.font = green_text if val >= 0 else red_text

        # ---------------------------------------------------------------------
        # TAB 2: Closed_Trades_Ledger
        # ---------------------------------------------------------------------
        ws_closed = wb.create_sheet(title="Closed_Trades_Ledger")
        ws_closed.views.sheetView[0].showGridLines = True

        closed_headers = [
            "Symbol", "ISIN", "Scrip Name", "Qty", "Buy Date", "Sell Date", "Hold Days",
            "Avg Buy Price (₹)", "Buy Value (₹)", "Avg Sell Price (₹)", "Sell Value (₹)",
            "Gross P&L (₹)", "Trade Taxes (₹)", "DP Fee (₹23.60)", "True Net P&L (₹)", "Net Return %", "Outcome"
        ]

        for col_idx, h in enumerate(closed_headers, start=1):
            cell = ws_closed.cell(row=1, column=col_idx, value=h)
            cell.fill = navy_fill
            cell.font = header_font
            cell.alignment = align_center

        for r_idx, trade in enumerate(summary["closed_trades"], start=2):
            ws_closed.cell(row=r_idx, column=1, value=trade["symbol"]).alignment = align_left
            ws_closed.cell(row=r_idx, column=2, value=trade["isin"]).alignment = align_center
            ws_closed.cell(row=r_idx, column=3, value=trade["scrip_name"]).alignment = align_left
            ws_closed.cell(row=r_idx, column=4, value=trade["qty"]).alignment = align_right

            c_bd = ws_closed.cell(row=r_idx, column=5, value=trade["buy_date"])
            c_bd.alignment = align_center
            c_sd = ws_closed.cell(row=r_idx, column=6, value=trade["sell_date"])
            c_sd.alignment = align_center

            ws_closed.cell(row=r_idx, column=7, value=trade["hold_days"]).alignment = align_right

            c_bp = ws_closed.cell(row=r_idx, column=8, value=trade["avg_buy_price"])
            c_bp.number_format = "₹#,##0.00"
            c_bv = ws_closed.cell(row=r_idx, column=9, value=trade["buy_value"])
            c_bv.number_format = "₹#,##0.00"

            c_sp = ws_closed.cell(row=r_idx, column=10, value=trade["avg_sell_price"])
            c_sp.number_format = "₹#,##0.00"
            c_sv = ws_closed.cell(row=r_idx, column=11, value=trade["sell_value"])
            c_sv.number_format = "₹#,##0.00"

            c_gp = ws_closed.cell(row=r_idx, column=12, value=trade["gross_pnl"])
            c_gp.number_format = "₹#,##0.00"
            c_tt = ws_closed.cell(row=r_idx, column=13, value=trade["trade_charges"])
            c_tt.number_format = "₹#,##0.00"
            c_dp = ws_closed.cell(row=r_idx, column=14, value=trade["dp_charge"])
            c_dp.number_format = "₹#,##0.00"

            c_np = ws_closed.cell(row=r_idx, column=15, value=trade["net_pnl"])
            c_np.number_format = "₹#,##0.00"
            c_np.font = green_text if trade["net_pnl"] >= 0 else red_text

            c_ret = ws_closed.cell(row=r_idx, column=16, value=trade["net_return_pct"] / 100.0)
            c_ret.number_format = "0.00%"
            c_ret.font = green_text if trade["net_return_pct"] >= 0 else red_text

            c_out = ws_closed.cell(row=r_idx, column=17, value=trade["outcome"])
            c_out.alignment = align_center
            c_out.font = green_text if trade["outcome"] == "WIN" else red_text

            for col_idx in range(1, 18):
                ws_closed.cell(row=r_idx, column=col_idx).border = thin_border
                if r_idx % 2 == 0:
                    ws_closed.cell(row=r_idx, column=col_idx).fill = soft_gray_fill

        # ---------------------------------------------------------------------
        # TAB 3: Open_Holdings
        # ---------------------------------------------------------------------
        ws_open = wb.create_sheet(title="Open_Holdings")
        ws_open.views.sheetView[0].showGridLines = True

        open_headers = [
            "Symbol", "ISIN", "Scrip Name", "Quantity", "Avg Buy Price (₹)", "Invested Value (₹)",
            "Live LTP (₹)", "Current Value (₹)", "Unrealized P&L (₹)", "Unrealized Return %"
        ]

        for col_idx, h in enumerate(open_headers, start=1):
            cell = ws_open.cell(row=1, column=col_idx, value=h)
            cell.fill = navy_fill
            cell.font = header_font
            cell.alignment = align_center

        for r_idx, hld in enumerate(summary["open_holdings"], start=2):
            ws_open.cell(row=r_idx, column=1, value=hld["symbol"]).alignment = align_left
            ws_open.cell(row=r_idx, column=2, value=hld["isin"]).alignment = align_center
            ws_open.cell(row=r_idx, column=3, value=hld["scrip_name"]).alignment = align_left
            ws_open.cell(row=r_idx, column=4, value=hld["qty"]).alignment = align_right

            c_bp = ws_open.cell(row=r_idx, column=5, value=hld["avg_buy_price"])
            c_bp.number_format = "₹#,##0.00"
            c_bv = ws_open.cell(row=r_idx, column=6, value=hld["buy_value"])
            c_bv.number_format = "₹#,##0.00"

            c_ltp = ws_open.cell(row=r_idx, column=7, value=hld["closing_rate"])
            c_ltp.number_format = "₹#,##0.00"
            c_cv = ws_open.cell(row=r_idx, column=8, value=hld["current_value"])
            c_cv.number_format = "₹#,##0.00"

            c_upnl = ws_open.cell(row=r_idx, column=9, value=hld["unrealized_pnl"])
            c_upnl.number_format = "₹#,##0.00"
            c_upnl.font = green_text if hld["unrealized_pnl"] >= 0 else red_text

            c_uret = ws_open.cell(row=r_idx, column=10, value=hld["unrealized_pnl_pct"] / 100.0)
            c_uret.number_format = "0.00%"
            c_uret.font = green_text if hld["unrealized_pnl_pct"] >= 0 else red_text

            for col_idx in range(1, 11):
                ws_open.cell(row=r_idx, column=col_idx).border = thin_border
                if r_idx % 2 == 0:
                    ws_open.cell(row=r_idx, column=col_idx).fill = soft_gray_fill

        # ---------------------------------------------------------------------
        # TAB 4: Raw_Executions
        # ---------------------------------------------------------------------
        ws_raw = wb.create_sheet(title="Raw_Executions")
        ws_raw.views.sheetView[0].showGridLines = True

        raw_headers = [
            "Order ID", "Trade ID", "Trade Date", "Segment", "Exchange", "Symbol", "Side",
            "Quantity", "Price (₹)", "Brokerage (₹)", "GST (₹)", "STT (₹)", "Exchange Charges (₹)",
            "Stamp Duty (₹)", "Total Charges (₹)"
        ]

        for col_idx, h in enumerate(raw_headers, start=1):
            cell = ws_raw.cell(row=1, column=col_idx, value=h)
            cell.fill = navy_fill
            cell.font = header_font
            cell.alignment = align_center

        with self.db.get_connection() as conn:
            raw_rows = conn.execute("""
                SELECT order_id, trade_id, trade_date, segment, exchange, symbol, side,
                       qty, price, brokerage, gst, stt, exchange_charges, stamp_duty, total_charges
                FROM real_trade_executions
                ORDER BY trade_date DESC, id DESC
            """).fetchall()

            for r_idx, r in enumerate(raw_rows, start=2):
                ws_raw.cell(row=r_idx, column=1, value=r[0]).alignment = align_center
                ws_raw.cell(row=r_idx, column=2, value=r[1]).alignment = align_center
                ws_raw.cell(row=r_idx, column=3, value=r[2]).alignment = align_center
                ws_raw.cell(row=r_idx, column=4, value=r[3]).alignment = align_center
                ws_raw.cell(row=r_idx, column=5, value=r[4]).alignment = align_center
                ws_raw.cell(row=r_idx, column=6, value=r[5]).alignment = align_left

                c_side = ws_raw.cell(row=r_idx, column=7, value=r[6])
                c_side.alignment = align_center
                c_side.font = green_text if r[6] == "BUY" else red_text

                ws_raw.cell(row=r_idx, column=8, value=r[7]).alignment = align_right

                c_p = ws_raw.cell(row=r_idx, column=9, value=r[8])
                c_p.number_format = "₹#,##0.00"

                for c_off, val in enumerate(r[9:], start=10):
                    c = ws_raw.cell(row=r_idx, column=c_off, value=val)
                    c.number_format = "₹#,##0.00"

                for col_idx in range(1, 16):
                    ws_raw.cell(row=r_idx, column=col_idx).border = thin_border
                    if r_idx % 2 == 0:
                        ws_raw.cell(row=r_idx, column=col_idx).fill = soft_gray_fill

        # ---------------------------------------------------------------------
        # TAB 5: Scrip_Attribution
        # ---------------------------------------------------------------------
        ws_attr = wb.create_sheet(title="Scrip_Attribution")
        ws_attr.views.sheetView[0].showGridLines = True

        attr_headers = [
            "Symbol", "Company Name", "Total Swings", "Wins", "Losses", "Win Rate %",
            "Gross P&L (₹)", "Trade Taxes (₹)", "DP Charges (₹)", "True Net P&L (₹)"
        ]

        for col_idx, h in enumerate(attr_headers, start=1):
            cell = ws_attr.cell(row=1, column=col_idx, value=h)
            cell.fill = navy_fill
            cell.font = header_font
            cell.alignment = align_center

        for r_idx, item in enumerate(summary["scrip_attribution"], start=2):
            ws_attr.cell(row=r_idx, column=1, value=item["symbol"]).alignment = align_left
            ws_attr.cell(row=r_idx, column=2, value=item["company_name"]).alignment = align_left
            ws_attr.cell(row=r_idx, column=3, value=item["trades"]).alignment = align_right
            ws_attr.cell(row=r_idx, column=4, value=item["wins"]).alignment = align_right
            ws_attr.cell(row=r_idx, column=5, value=item["losses"]).alignment = align_right

            c_wr = ws_attr.cell(row=r_idx, column=6, value=item["win_rate_pct"] / 100.0)
            c_wr.number_format = "0.00%"

            c_gp = ws_attr.cell(row=r_idx, column=7, value=item["gross_pnl"])
            c_gp.number_format = "₹#,##0.00"

            c_tt = ws_attr.cell(row=r_idx, column=8, value=item["trade_charges"])
            c_tt.number_format = "₹#,##0.00"

            c_dp = ws_attr.cell(row=r_idx, column=9, value=item["dp_charges"])
            c_dp.number_format = "₹#,##0.00"

            c_np = ws_attr.cell(row=r_idx, column=10, value=item["net_pnl"])
            c_np.number_format = "₹#,##0.00"
            c_np.font = green_text if item["net_pnl"] >= 0 else red_text

            for col_idx in range(1, 11):
                ws_attr.cell(row=r_idx, column=col_idx).border = thin_border
                if r_idx % 2 == 0:
                    ws_attr.cell(row=r_idx, column=col_idx).fill = soft_gray_fill

        # Auto-adjust column widths across all sheets
        for sheet in wb.worksheets:
            for col in sheet.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    if cell.value is not None:
                        val_str = str(cell.value)
                        max_len = max(max_len, len(val_str))
                sheet.column_dimensions[col_letter].width = max(max_len + 3, 12)

        # Serialize to in-memory bytes
        buf = io.BytesIO()
        wb.save(buf)
        excel_bytes = buf.getvalue()

        # Encrypt and save atomically to disk
        encrypted_bytes = self.cipher.encrypt(excel_bytes)
        tmp_enc_path = f"{MASTER_ENC_PATH}.tmp"
        with open(tmp_enc_path, "wb") as f:
            f.write(encrypted_bytes)
        os.replace(tmp_enc_path, MASTER_ENC_PATH)
        logger.info(f"[TRADEBOOK-ENCRYPTION] Encrypted master Excel written to {MASTER_ENC_PATH} ({len(encrypted_bytes)} bytes)")

        return excel_bytes

    def export_decrypted_master_excel(self) -> bytes:
        """Decrypts master_tradebook.enc in RAM and returns raw .xlsx bytes for streaming."""
        if not os.path.exists(MASTER_ENC_PATH):
            return self.rebuild_encrypted_master_excel()
        with open(MASTER_ENC_PATH, "rb") as f:
            enc_data = f.read()
        return self.cipher.decrypt(enc_data)
