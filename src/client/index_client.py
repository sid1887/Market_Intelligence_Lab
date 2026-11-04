import os
import ssl
import json
import time
import urllib.request
import datetime
from typing import List, Dict, Any, Optional, Tuple
from src.storage.database import DatabaseManager
from src.config import is_network_allowed

class IndexClient:
    """
    Client for retrieving and storing official Nifty Indices daily data:
    - Mode 1: Price Return Index (PRI) - OHLCV, PE, PB, Div Yield.
    - Mode 2: Total Return Index (TRI) - Closing index value only (OHLC strictly NULL).
    """

    PRI_URL = "https://www.niftyindices.com/BackPage/getHistoricaldatatabletoString"
    TRI_URL = "https://www.niftyindices.com/BackPage/getTotalReturnIndexString"

    SECTORAL_INDICES = [
        "Nifty Bank",
        "Nifty IT",
        "Nifty Auto",
        "Nifty FMCG",
        "Nifty Pharma",
        "Nifty Metal",
        "Nifty Financial Services",
        "Nifty Realty"
    ]

    def __init__(self, db: DatabaseManager, raw_dir: str = "data/raw/indices"):
        self.db = db
        self.raw_dir = raw_dir
        os.makedirs(self.raw_dir, exist_ok=True)

    @staticmethod
    def _format_date_for_api(dt: datetime.date) -> str:
        """Formats date as 'DD-Mon-YYYY' (e.g. '23-Oct-2026')."""
        return dt.strftime("%d-%b-%Y")

    @staticmethod
    def _parse_api_date(d_str: str) -> str:
        """Parses '23 Oct 2026' or '23-Oct-2026' into ISO '2026-10-23'."""
        cleaned = d_str.replace("-", " ").strip()
        dt = datetime.datetime.strptime(cleaned, "%d %b %Y").date()
        return dt.strftime("%Y-%m-%d")

    def fetch_historical_tri(
        self,
        index_name: str = "Nifty 50",
        start_date_iso: str = "2024-10-21",
        end_date_iso: str = "2026-10-23"
    ) -> Tuple[List[Dict[str, Any]], str, int]:
        """
        Fetches official Total Return Index (TRI) series from Nifty Indices.
        Enforces: open, high, low are strictly None (SQL NULL), never fabricated.
        Returns (records, raw_backup_path, raw_item_count).
        """
        if not is_network_allowed():
            raise RuntimeError("Network access disabled: offline_mode is enabled in settings.json.")

        d_start = datetime.datetime.strptime(start_date_iso, "%Y-%m-%d").date()
        d_end = datetime.datetime.strptime(end_date_iso, "%Y-%m-%d").date()

        # Nifty Indices API accepts batches up to 2 years
        payload = json.dumps({
            "cinfo": json.dumps({
                "name": index_name.upper().strip(),
                "startDate": self._format_date_for_api(d_start),
                "endDate": self._format_date_for_api(d_end),
                "indexName": index_name
            }).replace('"', "'")
        }).encode("utf-8")

        ctx = ssl.create_default_context()

        req = urllib.request.Request(
            self.TRI_URL,
            data=payload,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/json; charset=UTF-8",
                "Accept": "application/json, text/plain, */*"
            }
        )

        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                raw_text = resp.read().decode("utf-8")
        except Exception as e:
            raise RuntimeError(f"Error fetching TRI for {index_name}: {str(e)}")

        # Save raw backup
        raw_backup_path = os.path.join(
            self.raw_dir,
            f"TRI_{index_name.replace(' ', '_')}_{start_date_iso}_{end_date_iso}.json"
        )
        with open(raw_backup_path, "w", encoding="utf-8") as f:
            f.write(raw_text)

        items = json.loads(raw_text)
        raw_item_count = len(items)
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        records: List[Dict[str, Any]] = []

        for item in items:
            raw_d = item.get("Date", "").strip()
            tri_val_str = item.get("TotalReturnsIndex", "").strip()
            if not raw_d or not tri_val_str:
                continue

            iso_date = self._parse_api_date(raw_d)
            tri_close = float(tri_val_str.replace(",", ""))

            # Validate positive close
            if tri_close <= 0:
                continue

            records.append({
                "index_name": index_name.upper(),
                "trading_date": iso_date,
                "index_type": "TRI",
                "open": None,   # Strictly NULL: TRI does not have open
                "high": None,   # Strictly NULL: TRI does not have high
                "low": None,    # Strictly NULL: TRI does not have low
                "close": tri_close,
                "volume": None,
                "pe_ratio": None,
                "pb_ratio": None,
                "div_yield": None,
                "source": "nifty_indices_archive",
                "retrieval_timestamp": now_ts
            })

        # Sort chronologically
        records.sort(key=lambda r: r["trading_date"])
        return records, raw_backup_path, raw_item_count

    def fetch_historical_pri(
        self,
        index_name: str = "Nifty 50",
        start_date_iso: str = "2024-10-21",
        end_date_iso: str = "2026-10-23"
    ) -> Tuple[List[Dict[str, Any]], str, int]:
        """
        Fetches official Price Return Index (PRI) historical series.
        Stores Open, High, Low, Close.
        Returns (records, raw_backup_path, raw_item_count).
        """
        if not is_network_allowed():
            raise RuntimeError("Network access disabled: offline_mode is enabled in settings.json.")

        d_start = datetime.datetime.strptime(start_date_iso, "%Y-%m-%d").date()
        d_end = datetime.datetime.strptime(end_date_iso, "%Y-%m-%d").date()

        payload = json.dumps({
            "cinfo": json.dumps({
                "name": index_name.upper().strip(),
                "startDate": self._format_date_for_api(d_start),
                "endDate": self._format_date_for_api(d_end),
                "indexName": index_name
            }).replace('"', "'")
        }).encode("utf-8")

        ctx = ssl.create_default_context()

        req = urllib.request.Request(
            self.PRI_URL,
            data=payload,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/json; charset=UTF-8",
                "Accept": "application/json, text/plain, */*"
            }
        )

        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                raw_text = resp.read().decode("utf-8")
        except Exception as e:
            raise RuntimeError(f"Error fetching PRI for {index_name}: {str(e)}")

        raw_backup_path = os.path.join(
            self.raw_dir,
            f"PRI_{index_name.replace(' ', '_')}_{start_date_iso}_{end_date_iso}.json"
        )
        with open(raw_backup_path, "w", encoding="utf-8") as f:
            f.write(raw_text)

        items = json.loads(raw_text)
        raw_item_count = len(items)
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        records: List[Dict[str, Any]] = []

        for item in items:
            raw_d = item.get("HistoricalDate", "").strip()
            if not raw_d:
                continue

            iso_date = self._parse_api_date(raw_d)
            try:
                op = float(item.get("OPEN", "0").replace(",", ""))
                hp = float(item.get("HIGH", "0").replace(",", ""))
                lp = float(item.get("LOW", "0").replace(",", ""))
                cp = float(item.get("CLOSE", "0").replace(",", ""))
            except (ValueError, TypeError):
                continue

            # Invariant checks
            if op <= 0 or hp <= 0 or lp <= 0 or cp <= 0:
                continue
            if hp < lp:
                continue
            if op > hp + 0.05 or cp > hp + 0.05:
                continue
            if op < lp - 0.05 or cp < lp - 0.05:
                continue

            records.append({
                "index_name": index_name.upper(),
                "trading_date": iso_date,
                "index_type": "PRI",
                "open": op,
                "high": hp,
                "low": lp,
                "close": cp,
                "volume": None,
                "pe_ratio": None,
                "pb_ratio": None,
                "div_yield": None,
                "source": "nifty_indices_archive",
                "retrieval_timestamp": now_ts
            })

        records.sort(key=lambda r: r["trading_date"])
        return records, raw_backup_path

    def sync_index_history(
        self,
        index_name: str = "Nifty 50",
        start_date_iso: str = "2024-10-21",
        end_date_iso: str = "2026-10-23"
    ) -> Dict[str, Any]:
        """Fetches and persists both PRI and TRI historical series into the database with audit logging."""
        tri_records, tri_raw_path, tri_raw_count = self.fetch_historical_tri(index_name, start_date_iso, end_date_iso)
        tri_count = self.db.upsert_index_daily(tri_records)
        tri_rejected = max(0, tri_raw_count - len(tri_records))

        pri_records, pri_raw_path, pri_raw_count = self.fetch_historical_pri(index_name, start_date_iso, end_date_iso)
        pri_count = self.db.upsert_index_daily(pri_records)
        pri_rejected = max(0, pri_raw_count - len(pri_records))

        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Audit log for PRI
        if pri_records or pri_raw_count > 0:
            date_start = pri_records[0]["trading_date"] if pri_records else start_date_iso
            date_end = pri_records[-1]["trading_date"] if pri_records else end_date_iso
            self.db.record_audit_log(
                source="nifty_indices_archive",
                endpoint=self.PRI_URL,
                symbol=index_name.upper(),
                date_range_start=date_start,
                date_range_end=date_end,
                records_retrieved=pri_raw_count,
                records_accepted=pri_count,
                records_rejected=pri_rejected,
                validation_summary={
                    "type": "PRI",
                    "raw_count": pri_raw_count,
                    "accepted_count": pri_count,
                    "rejected_count": pri_rejected,
                    "invariants_enforced": True
                },
                raw_payload_path=pri_raw_path,
                status="SUCCESS" if pri_count > 0 and pri_rejected == 0 else ("PARTIAL" if pri_count > 0 else "FAILED"),
                created_at=now_ts
            )

        # Audit log for TRI
        if tri_records or tri_raw_count > 0:
            date_start = tri_records[0]["trading_date"] if tri_records else start_date_iso
            date_end = tri_records[-1]["trading_date"] if tri_records else end_date_iso
            self.db.record_audit_log(
                source="nifty_indices_archive",
                endpoint=self.TRI_URL,
                symbol=index_name.upper(),
                date_range_start=date_start,
                date_range_end=date_end,
                records_retrieved=tri_raw_count,
                records_accepted=tri_count,
                records_rejected=tri_rejected,
                validation_summary={
                    "type": "TRI",
                    "raw_count": tri_raw_count,
                    "accepted_count": tri_count,
                    "rejected_count": tri_rejected,
                    "open_high_low_strictly_null": True
                },
                raw_payload_path=tri_raw_path,
                status="SUCCESS" if tri_count > 0 and tri_rejected == 0 else ("PARTIAL" if tri_count > 0 else "FAILED"),
                created_at=now_ts
            )

        return {
            "index_name": index_name.upper(),
            "tri_records_synced": tri_count,
            "pri_records_synced": pri_count,
            "tri_records_rejected": tri_rejected,
            "pri_records_rejected": pri_rejected,
            "date_range": f"{start_date_iso} to {end_date_iso}"
        }

    def sync_all_sectoral_indices(
        self,
        start_date_iso: str = "2024-10-21",
        end_date_iso: str = "2026-10-23",
        delay_seconds: float = 0.5
    ) -> Dict[str, Any]:
        """
        Synchronizes all 8 official sectoral indices for both PRI and TRI series.
        """
        results = {}
        total_pri = 0
        total_tri = 0
        for idx_name in self.SECTORAL_INDICES:
            res = self.sync_index_history(idx_name, start_date_iso, end_date_iso)
            results[idx_name] = res
            total_pri += res.get("pri_records_synced", 0)
            total_tri += res.get("tri_records_synced", 0)
            time.sleep(delay_seconds)

        return {
            "indices_synced": len(results),
            "total_pri_synced": total_pri,
            "total_tri_synced": total_tri,
            "details": results
        }
