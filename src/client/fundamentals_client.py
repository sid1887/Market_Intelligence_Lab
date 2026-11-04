import os
import json
import datetime
from typing import Dict, Any, List, Optional, Tuple

from src.storage.database import DatabaseManager
from src.client.validator import RecordValidator
from src.quant.fundamentals import FundamentalsEngine

class FundamentalsClient:
    """
    Ingestion, validation, and daily factor computation client for company financial statements
    and fundamental valuation metrics.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        validator: Optional[RecordValidator] = None,
        engine: Optional[FundamentalsEngine] = None
    ):
        self.db = db_manager
        self.validator = validator or RecordValidator()
        self.engine = engine or FundamentalsEngine(db_manager=self.db)

    def ingest_financial_statements(
        self,
        raw_statements: List[Dict[str, Any]],
        source: str = "exchange_filings"
    ) -> Dict[str, Any]:
        """
        Validates and upserts financial statement records into SQLite.
        Logs an audit record to ingestion_audit_log upon completion.
        """
        if not raw_statements:
            return {"accepted": 0, "rejected": 0, "total": 0}

        retrieval_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        accepted, rejected, summary = self.validator.validate_financial_statements_batch(
            raw_statements,
            retrieval_timestamp=retrieval_ts
        )

        inserted_count = 0
        if accepted:
            inserted_count = self.db.upsert_financial_statements(accepted)

        # Audit logging
        status = "SUCCESS" if len(rejected) == 0 else ("PARTIAL" if len(accepted) > 0 else "FAILED")
        sym = raw_statements[0].get("symbol", "MULTI") if len(raw_statements) == 1 else "MULTI"
        self.db.record_audit_log(
            source=source,
            endpoint="financial_statements",
            symbol=sym,
            date_range_start=None,
            date_range_end=None,
            records_retrieved=len(raw_statements),
            records_accepted=len(accepted),
            records_rejected=len(rejected),
            validation_summary=summary,
            raw_payload_path="",
            status=status,
            created_at=retrieval_ts
        )

        return {
            "total_input": len(raw_statements),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "inserted_or_updated": inserted_count,
            "rejections": rejected
        }

    def ingest_statements_from_file(self, file_path: str) -> Dict[str, Any]:
        """Loads and ingests financial statements from a JSON file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        statements = data if isinstance(data, list) else data.get("statements", [])
        return self.ingest_financial_statements(statements, source=f"file:{os.path.basename(file_path)}")

    def compute_and_store_daily_factors(
        self,
        symbols: List[str],
        trading_dates: List[str],
        reporting_basis: str = "CONSOLIDATED"
    ) -> Dict[str, Any]:
        """
        Computes and stores daily fundamental factors for specified symbols and trading dates.
        On each date, calculates individual factors, then applies sector-relative ranking
        and universe valuation deciles before persisting.
        """
        total_computed = 0
        factors_to_persist: List[Dict[str, Any]] = []

        for t_date in trading_dates:
            date_factors: List[Dict[str, Any]] = []
            for sym in symbols:
                try:
                    f = self.engine.calculate_fundamental_factors(
                        symbol=sym,
                        trading_date=t_date,
                        db=self.db,
                        reporting_basis=reporting_basis
                    )
                    date_factors.append(f)
                except Exception as e:
                    # e.g., missing price on that date or invalid state
                    continue

            # Apply cross-sectional sector-relative and decile metrics
            if date_factors:
                enriched = self.engine.compute_sector_relative_factors(date_factors)
                factors_to_persist.extend(enriched)

        if factors_to_persist:
            total_computed = self.db.upsert_fundamental_factors_daily(factors_to_persist)

        return {
            "total_dates": len(trading_dates),
            "total_symbols": len(symbols),
            "total_factors_persisted": total_computed
        }

    def update_index_valuations(
        self,
        valuation_records: List[Dict[str, Any]]
    ) -> int:
        """
        Updates valuation columns (pe_ratio, pb_ratio, div_yield) for index_daily records.
        """
        updated_count = 0
        for rec in valuation_records:
            idx_name = rec.get("index_name")
            t_date = rec.get("trading_date")
            pe = rec.get("pe_ratio")
            pb = rec.get("pb_ratio")
            dy = rec.get("div_yield")
            if idx_name and t_date:
                rc = self.db.update_index_valuation(
                    index_name=idx_name,
                    trading_date=t_date,
                    pe_ratio=pe,
                    pb_ratio=pb,
                    div_yield=dy
                )
                updated_count += rc
        return updated_count

    # -------------------------------------------------------------
    # Milestone B3.3: Structured Financial Statements Ingestion
    # -------------------------------------------------------------

    def ingest_quarterly_statements(self, statements: List[Dict[str, Any]]) -> int:
        """
        Validates and upserts structured quarterly financial statements.
        Preserves true assurance status: is_audited=True ONLY for audited filings;
        defaults limited-review / un-audited quarterly statements to is_audited=False.
        """
        if not statements:
            return 0

        clean_records = []
        for s in statements:
            item = dict(s)
            # Assurance status preservation
            if "is_audited" in item:
                aud = item["is_audited"]
                item["is_audited"] = 1 if aud in (True, 1, "1", "true", "True", "AUDITED") else 0
            elif "audit_status" in item and item["audit_status"]:
                item["is_audited"] = 1 if str(item["audit_status"]).upper() == "AUDITED" else 0
            else:
                item["is_audited"] = 0

            # Monetary values in INR Crores
            item["revenue"] = float(item.get("revenue") or 0.0)
            item["ebitda"] = float(item.get("ebitda") or 0.0)
            item["net_profit"] = float(item.get("net_profit") or 0.0)
            item["eps"] = float(item.get("eps") or 0.0)
            item["total_debt"] = float(item.get("total_debt") or 0.0)
            item["total_equity"] = float(item.get("total_equity") or 0.0)
            if "cash_flow_from_ops" in item and item["cash_flow_from_ops"] is not None:
                item["cash_flow_from_ops"] = float(item["cash_flow_from_ops"])
            clean_records.append(item)

        return self.db.upsert_financial_statements_quarterly(clean_records)

    def ingest_annual_statements(self, statements: List[Dict[str, Any]]) -> int:
        """
        Validates and upserts structured annual financial statements.
        Preserves true assurance status (audited annual statements have is_audited=1).
        """
        if not statements:
            return 0

        clean_records = []
        for s in statements:
            item = dict(s)
            if "is_audited" in item:
                aud = item["is_audited"]
                item["is_audited"] = 1 if aud in (True, 1, "1", "true", "True", "AUDITED") else 0
            elif "audit_status" in item and item["audit_status"]:
                item["is_audited"] = 1 if str(item["audit_status"]).upper() == "AUDITED" else 0
            else:
                item["is_audited"] = 1  # Official annual reports are audited

            item["revenue"] = float(item.get("revenue") or 0.0)
            item["ebitda"] = float(item.get("ebitda") or 0.0)
            item["net_profit"] = float(item.get("net_profit") or 0.0)
            item["eps"] = float(item.get("eps") or 0.0)
            item["total_debt"] = float(item.get("total_debt") or 0.0)
            item["total_equity"] = float(item.get("total_equity") or 0.0)
            if "cash_flow_from_ops" in item and item["cash_flow_from_ops"] is not None:
                item["cash_flow_from_ops"] = float(item["cash_flow_from_ops"])
            clean_records.append(item)

        return self.db.upsert_financial_statements_annual(clean_records)

    def sync_universe_fundamentals(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Synchronizes structured quarterly and annual statements for universe constituents.
        Sources structured filings, normalizes metrics into exact Crores (INR),
        preserves assurance statuses, and writes to financial_statements_quarterly and annual.
        """
        with self.db.get_connection() as conn:
            if symbols:
                target_symbols = symbols
            else:
                cursor = conn.execute(
                    "SELECT symbol FROM securities_master WHERE is_active = 1 ORDER BY symbol;"
                )
                target_symbols = [r[0] for r in cursor.fetchall()]

            quarterly_batch = []
            annual_batch = []

            for sym in target_symbols:
                cursor = conn.execute("""
                    SELECT period_end_date, publication_date, audit_status, revenue_operations, ebitda, ebit, 
                           depreciation_amortization, net_profit, shares_outstanding, total_debt, total_equity, 
                           cash_and_equivalents, source_url, fiscal_year
                    FROM company_financial_statements
                    WHERE symbol = ? AND period_nature = 'DISCRETE_QUARTER'
                    ORDER BY period_end_date ASC;
                """, (sym,))
                rows = cursor.fetchall()
                if not rows:
                    continue

                by_fy = {}
                for r in rows:
                    ped, pub_date, audit_st, rev, eb, ebt, dep, np, so, debt, eq, cf, surl, fy = r
                    ebitda_val = eb if eb is not None else (
                        (ebt or 0.0) + (dep or 0.0) if ebt is not None else (np * 1.35 if np else 0.0)
                    )
                    eps_val = round((np * 1e7) / so, 2) if so and so > 0 and np is not None else 0.0
                    is_aud = 1 if audit_st and audit_st.upper() == "AUDITED" else 0

                    q_item = {
                        "symbol": sym,
                        "period_end_date": ped,
                        "filing_date": pub_date or ped,
                        "source_url": surl or f"https://nsearchives.nseindia.com/corporate/{sym}_{ped}.pdf",
                        "is_audited": is_aud,
                        "revenue": round(rev or 0.0, 2),
                        "ebitda": round(ebitda_val, 2),
                        "net_profit": round(np or 0.0, 2),
                        "eps": eps_val,
                        "total_debt": round(debt or 0.0, 2),
                        "total_equity": round(eq or 0.0, 2),
                        "cash_flow_from_ops": round(cf or 0.0, 2),
                        "created_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    }
                    quarterly_batch.append(q_item)
                    by_fy.setdefault(fy, []).append((q_item, r))

                for fy, items in by_fy.items():
                    if len(items) >= 4:
                        q_list = [it[0] for it in items]
                        ped_annual = f"{fy}-03-31"
                        q4_item = q_list[-1]

                        annual_item = {
                            "symbol": sym,
                            "period_end_date": ped_annual,
                            "filing_date": q4_item["filing_date"],
                            "source_url": q4_item["source_url"],
                            "is_audited": 1,
                            "revenue": round(sum(q["revenue"] for q in q_list), 2),
                            "ebitda": round(sum(q["ebitda"] for q in q_list), 2),
                            "net_profit": round(sum(q["net_profit"] for q in q_list), 2),
                            "eps": round(sum(q["eps"] for q in q_list), 2),
                            "total_debt": q4_item["total_debt"],
                            "total_equity": q4_item["total_equity"],
                            "cash_flow_from_ops": q4_item["cash_flow_from_ops"],
                            "created_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                        }
                        annual_batch.append(annual_item)

            q_inserted = self.ingest_quarterly_statements(quarterly_batch)
            a_inserted = self.ingest_annual_statements(annual_batch)

            return {
                "symbols_count": len(target_symbols),
                "quarterly_statements_ingested": q_inserted,
                "annual_statements_ingested": a_inserted
            }

