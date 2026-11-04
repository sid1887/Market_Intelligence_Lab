"""
Market Intelligence Lab: Unified Evidence Store & Query Engine.
Provides centralized ingestion, storage, point-in-time isolation,
and query access for normalized EvidenceRecords.
"""

import json
from typing import List, Dict, Any, Optional, Set
from src.storage.database import DatabaseManager
from src.evidence.models import (
    EvidenceTier,
    EvidenceCategory,
    EvidenceDirection,
    ExpectationSurprise,
    EvidenceRecord
)
from src.evidence.adapters import (
    CorporateDisclosuresAdapter,
    CorporateActionsAdapter,
    FinancialStatementsAdapter,
    MarketIndexMovementsAdapter,
    VolumeAnomaliesAdapter
)
from src.evidence.constants import resolve_sector_benchmark


class EvidenceStore:
    """
    Central repository for normalized market evidence.
    Coordinates local adapters, executes idempotent upserts into SQLite,
    and provides point-in-time filtered queries for research investigations.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.disclosures_adapter = CorporateDisclosuresAdapter(db)
        self.actions_adapter = CorporateActionsAdapter(db)
        self.statements_adapter = FinancialStatementsAdapter(db)
        self.index_movements_adapter = MarketIndexMovementsAdapter(db)
        self.volume_adapter = VolumeAnomaliesAdapter(db)

    def ingest_all_local_evidence(self, as_of_date: Optional[str] = None) -> Dict[str, int]:
        """
        Runs all local evidence adapters and upserts normalized records into SQLite.
        Strictly idempotent: repeated execution does not duplicate records.
        """
        disclosures = self.disclosures_adapter.extract_evidence(as_of_date=as_of_date)
        actions = self.actions_adapter.extract_evidence(as_of_date=as_of_date)
        statements = self.statements_adapter.extract_evidence(as_of_date=as_of_date)
        index_moves = self.index_movements_adapter.extract_evidence(as_of_date=as_of_date)
        volume_surges = self.volume_adapter.extract_evidence(as_of_date=as_of_date)

        all_records = disclosures + actions + statements + index_moves + volume_surges

        dicts_to_upsert = []
        for r in all_records:
            d = r.to_dict()
            d["details_json"] = json.dumps(r.details)
            dicts_to_upsert.append(d)

        count = self.db.upsert_evidence_records(dicts_to_upsert)

        return {
            "total_extracted": len(all_records),
            "total_upserted": count,
            "disclosures_count": len(disclosures),
            "actions_count": len(actions),
            "statements_count": len(statements),
            "index_movements_count": len(index_moves),
            "volume_anomalies_count": len(volume_surges)
        }

    def get_evidence_for_session(
        self,
        symbol: str,
        session_date: str,
        as_of_date: Optional[str] = None,
        only_verified: bool = True
    ) -> List[EvidenceRecord]:
        """
        Retrieves all evidence relevant to a stock on a target trading session:
        1. Direct company evidence (disclosures, actions, statements, volume spikes).
        2. Broad market evidence (NIFTY 50 moves on that session).
        3. Sector index evidence (official sector index moves on that session).

        Enforces:
        - Point-in-time visibility: effective_session_date <= as_of_date and is_pit_eligible = 1
        - Verification gate: only_verified excludes PENDING/SOURCE_UNVERIFIED
        """
        # Resolve company sector to include sectoral index moves
        sec_info = self.db.get_securities_master(symbol=symbol)
        sector_idx = None
        if sec_info:
            sector = sec_info[0]["sector"]
            ind = sec_info[0]["industry"]
            _, s_idx, _, _, _ = resolve_sector_benchmark(symbol, sector, ind)
            sector_idx = s_idx

        # Fetch records from SQLite
        all_candidate_rows = self.db.get_evidence_records(
            effective_session_date=session_date,
            as_of_date=as_of_date
        )

        relevant_symbols = {symbol, "NIFTY 50"}
        if sector_idx and sector_idx != "NIFTY 50":
            relevant_symbols.add(sector_idx)

        records: List[EvidenceRecord] = []
        for r in all_candidate_rows:
            if r["symbol"] in relevant_symbols:
                # Check verification filter
                if only_verified and r["verification_status"] != "VERIFIED":
                    continue
                # Check PIT eligibility
                if as_of_date and not bool(r["is_pit_eligible"]):
                    continue

                records.append(EvidenceRecord.from_dict(r))

        return records

    def get_evidence_in_window(
        self,
        symbol: str,
        start_session: str,
        end_session: str,
        as_of_date: Optional[str] = None,
        only_verified: bool = True
    ) -> List[EvidenceRecord]:
        """
        Retrieves all evidence in an event window [start_session, end_session] for the symbol.
        """
        sec_info = self.db.get_securities_master(symbol=symbol)
        sector_idx = None
        if sec_info:
            sector = sec_info[0]["sector"]
            ind = sec_info[0]["industry"]
            _, s_idx, _, _, _ = resolve_sector_benchmark(symbol, sector, ind)
            sector_idx = s_idx

        relevant_symbols = {symbol, "NIFTY 50"}
        if sector_idx and sector_idx != "NIFTY 50":
            relevant_symbols.add(sector_idx)

        query = """
        SELECT * FROM evidence_records 
        WHERE effective_session_date >= ? AND effective_session_date <= ?
        """
        params: List[Any] = [start_session, end_session]
        if as_of_date:
            query += " AND effective_session_date <= ?"
            params.append(as_of_date)
        query += " ORDER BY effective_session_date ASC, evidence_tier ASC;"

        with self.db.get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()

        records: List[EvidenceRecord] = []
        for row in rows:
            r = dict(row)
            if r["symbol"] in relevant_symbols:
                if only_verified and r["verification_status"] != "VERIFIED":
                    continue
                if as_of_date and not bool(r["is_pit_eligible"]):
                    continue
                records.append(EvidenceRecord.from_dict(r))

        return records

    def get_evidence_summary(self, as_of_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns auditable breakdown of evidence records currently stored in SQLite:
        - Total count
        - Breakdown by tier
        - Breakdown by category
        - Breakdown by verification status
        - Breakdown by reporting basis
        - Distinct symbols covered
        """
        sql = "SELECT * FROM evidence_records WHERE 1=1"
        params: List[Any] = []
        if as_of_date:
            sql += " AND effective_session_date <= ?"
            params.append(as_of_date)

        with self.db.get_connection() as conn:
            cursor = conn.execute(sql, params)
            rows = [dict(r) for r in cursor.fetchall()]

        total = len(rows)
        by_tier: Dict[int, int] = {}
        by_category: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        by_basis: Dict[str, int] = {}
        symbols: Set[str] = set()

        for r in rows:
            t = r["evidence_tier"]
            by_tier[t] = by_tier.get(t, 0) + 1

            c = r["evidence_category"]
            by_category[c] = by_category.get(c, 0) + 1

            s = r["verification_status"]
            by_status[s] = by_status.get(s, 0) + 1

            b = r["reporting_basis"] or "NONE"
            by_basis[b] = by_basis.get(b, 0) + 1

            symbols.add(r["symbol"])

        return {
            "total_records": total,
            "distinct_symbols_count": len(symbols),
            "by_tier": dict(sorted(by_tier.items())),
            "by_category": dict(sorted(by_category.items())),
            "by_verification_status": dict(sorted(by_status.items())),
            "by_reporting_basis": dict(sorted(by_basis.items()))
        }
