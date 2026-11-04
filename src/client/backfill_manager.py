import time
import os
import datetime
from typing import List, Dict, Any, Optional, Tuple, Set
from src.storage.database import DatabaseManager
from src.client.nse_mcp_client import NseMcpClient
from src.client.validator import RecordValidator

class BackfillManager:
    """
    Orchestrates historical multi-stock backfilling for universe constituents.
    Skips already-backfilled stocks, validates invariants, enforces session affinity,
    preserves source provenance, and records audit logs without corrupting Phase 1 data.
    """

    TICKER_ALIASES = {
        "ETERNAL": {
            "historical_symbol": "ZOMATO",
            "isin": "INE758T01015",
            "effective_date": "2025-04-09",
            "nature": "PURE_NAME_CHANGE",
            "is_economically_comparable": True,
            "normalization_strategy": "STITCH_SOURCE_PROVENANCE",
            "source_provenance": "nse_mcp_alias_zomato",
            "reason": "Pure corporate name change from Zomato Ltd to Eternal Ltd (same ISIN: INE758T01015, circular NSE/CMTR/66782/2025)."
        },
        "TMPV": {
            "historical_symbol": "TATAMOTORS",
            "isin": "INE155A01022",
            "effective_date": "2025-10-24",
            "nature": "CORPORATE_DEMERGER",
            "is_economically_comparable": False,
            "normalization_strategy": "DISTINCT_SERIES_DO_NOT_SPLICE",
            "source_provenance": "nse_mcp",
            "reason": "Demerger of Tata Motors commercial vehicle and passenger vehicle businesses. Pre-demerger prices represent combined entity and are economically incomparable to post-demerger TMPV."
        }
    }

    def __init__(
        self,
        db: DatabaseManager,
        mcp_client: Optional[NseMcpClient] = None,
        min_required_records: int = 480
    ):
        self.db = db
        self.mcp_client = mcp_client or NseMcpClient()
        self.validator = RecordValidator()
        self.min_required_records = min_required_records

    def get_active_universe(self) -> List[str]:
        """Returns the authoritative list of active symbols from securities_master."""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT symbol FROM securities_master WHERE is_active = 1 ORDER BY symbol"
            )
            return [row[0] for row in cursor.fetchall()]

    def get_watchlist_universe(self) -> List[str]:
        """Returns the list of onboarded user watchlist symbols."""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT symbol FROM user_watchlists ORDER BY symbol"
            )
            return [row[0] for row in cursor.fetchall()]

    def get_all_universe(self) -> List[str]:
        """Returns all tracked instruments across active index constituents and user watchlists."""
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT symbol FROM securities_master WHERE is_active = 1
                UNION
                SELECT symbol FROM user_watchlists
                ORDER BY symbol
                """
            )
            return [row[0] for row in cursor.fetchall()]

    def verify_symbol_coverage(
        self,
        symbol: str,
        benchmark_index: str = "NIFTY 50",
        start_date: str = "2024-10-21",
        end_date: str = "2026-10-23"
    ) -> Dict[str, Any]:
        """
        Validates actual post-ingestion database coverage for a symbol.
        Coverage is evaluated strictly within the target benchmark evaluation window [start_date, end_date].
        Out-of-window records in ohlcv_daily are preserved but do not inflate window metrics.
        """
        with self.db.get_connection() as conn:
            # 1. Query stock sessions strictly within the target evaluation window
            cursor = conn.execute(
                """
                SELECT trading_date FROM ohlcv_daily 
                WHERE symbol = ? AND series = 'EQ' AND trading_date BETWEEN ? AND ?
                ORDER BY trading_date ASC
                """,
                (symbol, start_date, end_date)
            )
            stock_window_dates = [r[0] for r in cursor.fetchall()]

            # 2. Query total stock sessions across all time in database (for lifetime diagnostics)
            cursor = conn.execute(
                """
                SELECT COUNT(*), MIN(trading_date), MAX(trading_date) 
                FROM ohlcv_daily WHERE symbol = ? AND series = 'EQ'
                """,
                (symbol,)
            )
            total_db_count, earliest_db_date, latest_db_date = cursor.fetchone()

            # 3. Query benchmark trading dates in evaluation window
            cursor = conn.execute(
                """
                SELECT trading_date FROM index_daily 
                WHERE index_name = ? AND index_type = 'PRI' AND trading_date BETWEEN ? AND ?
                ORDER BY trading_date ASC
                """,
                (benchmark_index, start_date, end_date)
            )
            benchmark_dates = [r[0] for r in cursor.fetchall()]

        session_count = len(stock_window_dates)
        min_date = stock_window_dates[0] if stock_window_dates else None
        max_date = stock_window_dates[-1] if stock_window_dates else None

        benchmark_set = set(benchmark_dates)
        stock_set = set(stock_window_dates)
        missing_benchmark_dates = sorted(list(benchmark_set - stock_set))

        # Check documented ticker exceptions (e.g. TMPV corporate demerger)
        alias_info = self.TICKER_ALIASES.get(symbol)
        if alias_info and not alias_info.get("is_economically_comparable", True):
            effective_date = alias_info["effective_date"]
            # For TMPV, expect coverage from effective_date to end_date
            expected_dates = [d for d in benchmark_dates if d >= effective_date]
            actual_in_period = [d for d in stock_window_dates if d >= effective_date]
            if len(actual_in_period) >= len(expected_dates) - 5 and min_date and min_date <= "2025-10-25":
                return {
                    "symbol": symbol,
                    "status": "COVERAGE_EXCEPTION_TICKER_RENAME",
                    "session_count": session_count,
                    "total_db_sessions": total_db_count,
                    "target": self.min_required_records,
                    "earliest_date": min_date,
                    "latest_date": max_date,
                    "earliest_db_date": earliest_db_date,
                    "latest_db_date": latest_db_date,
                    "missing_benchmark_dates_count": len(missing_benchmark_dates),
                    "missing_benchmark_dates": missing_benchmark_dates,
                    "exception_reason": alias_info["reason"],
                    "meets_acceptance": True
                }

        # Standard coverage criteria within evaluation window
        has_min_sessions = session_count >= self.min_required_records
        spans_full_window = (min_date is not None and min_date <= "2024-10-25" and 
                             max_date is not None and max_date >= end_date)

        if has_min_sessions and spans_full_window:
            status = "COVERAGE_MET"
            meets_acceptance = True
        elif session_count > 0:
            status = "PARTIAL_COVERAGE"
            meets_acceptance = False
        else:
            status = "FAILED"
            meets_acceptance = False

        return {
            "symbol": symbol,
            "status": status,
            "session_count": session_count,
            "total_db_sessions": total_db_count,
            "target": self.min_required_records,
            "earliest_date": min_date,
            "latest_date": max_date,
            "earliest_db_date": earliest_db_date,
            "latest_db_date": latest_db_date,
            "missing_benchmark_dates_count": len(missing_benchmark_dates),
            "missing_benchmark_dates": missing_benchmark_dates,
            "exception_reason": None,
            "meets_acceptance": meets_acceptance
        }

    def get_symbols_needing_backfill(self, symbols: Optional[List[str]] = None) -> List[str]:
        """Identifies active symbols that do NOT meet coverage acceptance criteria."""
        if symbols is None:
            symbols = self.get_active_universe()

        needing_backfill = []
        for sym in symbols:
            cov = self.verify_symbol_coverage(sym)
            if not cov["meets_acceptance"]:
                needing_backfill.append(sym)
        return needing_backfill

    def backfill_symbol(
        self,
        symbol: str,
        total_months: int = 24,
        end_date: str = "2026-10-23"
    ) -> Dict[str, Any]:
        """
        Backfills a single symbol using chunked MCP calls and persists validated records.
        Idempotent: skips network calls if coverage criteria are already met.
        Handles ticker rename stitching (ZOMATO -> ETERNAL) with source provenance.
        """
        # Preflight coverage check
        pre_cov = self.verify_symbol_coverage(symbol)
        if pre_cov["meets_acceptance"]:
            return {
                "symbol": symbol,
                "status": pre_cov["status"],
                "records_retrieved": 0,
                "records_upserted": 0,
                "records_rejected": 0,
                "date_range": f"{pre_cov['earliest_date']} to {pre_cov['latest_date']}",
                "coverage": pre_cov,
                "duration_seconds": 0.0,
                "skipped_already_met": True
            }

        self.validator.reset_dedup()
        t0 = time.time()
        alias_info = self.TICKER_ALIASES.get(symbol)

        all_raw_records: List[Dict[str, Any]] = []
        raw_paths: List[str] = []

        try:
            # 1. Fetch under current ticker
            records_curr, path_curr = self.mcp_client.fetch_stock_history_chunked(
                symbol=symbol,
                total_months=total_months,
                end_date=end_date
            )
            all_raw_records.extend(records_curr)
            raw_paths.append(path_curr)

            # 2. If symbol is an economically comparable pure-name-change (e.g. ZOMATO -> ETERNAL)
            if alias_info and alias_info.get("is_economically_comparable", False):
                hist_sym = alias_info["historical_symbol"]
                eff_date = alias_info["effective_date"]
                # Calculate days prior to effective date
                eff_dt = datetime.datetime.strptime(eff_date, "%Y-%m-%d").date()
                prev_day = (eff_dt - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

                records_hist, path_hist = self.mcp_client.fetch_stock_history_chunked(
                    symbol=hist_sym,
                    total_months=total_months,
                    end_date=prev_day
                )
                raw_paths.append(path_hist)

                # Filter records strictly before effective_date and normalize ticker to current
                seen_dates = {r.get("date") for r in records_curr if r.get("date")}
                for rec in records_hist:
                    rec_date = rec.get("date")
                    if rec_date and rec_date < eff_date and rec_date not in seen_dates:
                        rec_copy = dict(rec)
                        rec_copy["symbol"] = symbol  # Map to current security identity
                        rec_copy["_provenance_source"] = alias_info["source_provenance"]
                        all_raw_records.append(rec_copy)
                        seen_dates.add(rec_date)

        except Exception as e:
            return {
                "symbol": symbol,
                "status": "FAILED",
                "error": f"MCP fetch error: {str(e)}",
                "records_upserted": 0,
                "duration_seconds": round(time.time() - t0, 2),
                "coverage": self.verify_symbol_coverage(symbol)
            }

        accepted: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        for rec in all_raw_records:
            source = rec.get("_provenance_source", "nse_mcp")
            val_ok, cleaned, err = self.validator.validate_record(rec, source=source)
            if val_ok and cleaned:
                accepted.append(cleaned)
            else:
                rejected.append({"record": rec, "error": err})

        upserted_count = self.db.upsert_ohlcv_records(accepted)

        # Audit logging
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        date_start = accepted[0]["trading_date"] if accepted else None
        date_end = accepted[-1]["trading_date"] if accepted else None

        self.db.record_audit_log(
            source="nse_mcp",
            endpoint="https://mcp.nseindia.in/bhavcopy/cm/mcp",
            symbol=symbol,
            date_range_start=date_start,
            date_range_end=date_end,
            records_retrieved=len(all_raw_records),
            records_accepted=len(accepted),
            records_rejected=len(rejected),
            validation_summary={
                "total_input": len(all_raw_records),
                "accepted_count": len(accepted),
                "rejected_count": len(rejected),
                "has_alias_history": bool(alias_info and alias_info.get("is_economically_comparable", False))
            },
            raw_payload_path=";".join(raw_paths),
            status="SUCCESS" if len(accepted) > 0 else "FAILED",
            created_at=now_ts
        )

        post_cov = self.verify_symbol_coverage(symbol)

        return {
            "symbol": symbol,
            "status": post_cov["status"],
            "records_retrieved": len(all_raw_records),
            "records_upserted": upserted_count,
            "records_rejected": len(rejected),
            "date_range": f"{date_start} to {date_end}",
            "coverage": post_cov,
            "duration_seconds": round(time.time() - t0, 2)
        }

    def backfill_universe(
        self,
        symbols: Optional[List[str]] = None,
        total_months: int = 24,
        end_date: str = "2026-10-23",
        max_symbols: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Backfills active universe symbols that do not yet meet acceptance criteria.
        """
        if symbols is None:
            symbols = self.get_active_universe()

        to_process = self.get_symbols_needing_backfill(symbols)
        if max_symbols:
            to_process = to_process[:max_symbols]

        results = []
        total_upserted = 0

        for idx, sym in enumerate(to_process, 1):
            res = self.backfill_symbol(sym, total_months=total_months, end_date=end_date)
            results.append(res)
            total_upserted += res.get("records_upserted", 0)
            time.sleep(0.1)  # Polite pacing

        coverage_met = [r for r in results if r["status"] == "COVERAGE_MET"]
        coverage_exceptions = [r for r in results if r["status"] == "COVERAGE_EXCEPTION_TICKER_RENAME"]
        partial_cov = [r for r in results if r["status"] == "PARTIAL_COVERAGE"]
        failed = [r for r in results if r["status"] == "FAILED"]

        return {
            "total_requested": len(symbols),
            "needed_backfill": len(to_process),
            "coverage_met_count": len(coverage_met),
            "coverage_exceptions_count": len(coverage_exceptions),
            "partial_coverage_count": len(partial_cov),
            "failed_count": len(failed),
            "total_records_upserted": total_upserted,
            "details": results
        }
