import os
import io
import ssl
import csv
import zipfile
import urllib.request
import datetime
from typing import List, Dict, Any, Optional, Set, Tuple
from src.config import is_network_allowed

class UDiffClientError(Exception):
    """Base exception for CM-UDiFF Bhavcopy client operations."""
    pass

class UDiffClient:
    """
    Downloads, extracts, validates, and parses the official exchange
    CM-UDiFF Common Bhavcopy Final ZIP (BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv.zip).
    """

    BASE_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"

    def __init__(self, raw_dir: str = "data/raw/udiff"):
        self.raw_dir = raw_dir
        os.makedirs(self.raw_dir, exist_ok=True)

    def download_udiff_zip(self, trading_date_iso: str, timeout_seconds: int = 15) -> Tuple[Optional[str], Optional[str]]:
        """
        Downloads CM-UDiFF Bhavcopy Final ZIP for a given ISO date (YYYY-MM-DD).
        Returns (saved_zip_path, error_message).
        """
        date_str = trading_date_iso.replace("-", "")
        url = self.BASE_URL.format(date_str=date_str)
        zip_path = os.path.join(self.raw_dir, f"BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip")

        # If already cached locally and valid, reuse
        if os.path.exists(zip_path) and zipfile.is_zipfile(zip_path):
            return zip_path, None

        if not is_network_allowed():
            raise RuntimeError(f"Network access disabled: offline_mode is enabled in settings.json. Missing local file: {zip_path}")

        ctx = ssl.create_default_context()

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/zip, application/octet-stream, */*"
            }
        )

        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout_seconds) as resp:
                if resp.status != 200:
                    return None, f"HTTP Error {resp.status} fetching CM-UDiFF zip for {trading_date_iso}"
                data = resp.read()

            if not data or len(data) < 100:
                return None, f"Empty or truncated response ({len(data)} bytes) for {trading_date_iso}"

            # Validate zip magic bytes before saving
            if not zipfile.is_zipfile(io.BytesIO(data)):
                return None, f"Corrupted payload (not a valid zip file) for {trading_date_iso}"

            with open(zip_path, "wb") as f:
                f.write(data)

            return zip_path, None

        except urllib.error.HTTPError as e:
            return None, f"HTTP {e.code}: {e.reason} for {url}"
        except Exception as e:
            return None, f"Network or I/O error fetching {url}: {str(e)}"

    def parse_udiff_archive(
        self,
        zip_path_or_bytes: Any,
        universe_symbols: Optional[Set[str]] = None,
        series_filter: str = "EQ"
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Parses CM-UDiFF Bhavcopy ZIP into validated OHLCV records.
        Returns (accepted_records, validation_summary).
        """
        summary = {
            "total_rows_read": 0,
            "accepted_count": 0,
            "rejected_count": 0,
            "rejections": []
        }

        try:
            z = zipfile.ZipFile(zip_path_or_bytes)
        except Exception as e:
            summary["rejections"].append({"reason": "Invalid or corrupted zip archive", "error": str(e)})
            return [], summary

        namelist = z.namelist()
        if not namelist:
            summary["rejections"].append({"reason": "Zip archive contains no files"})
            return [], summary

        csv_name = namelist[0]
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        accepted: List[Dict[str, Any]] = []

        with z.open(csv_name) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, "utf-8"))
            for row in reader:
                summary["total_rows_read"] += 1
                sym = row.get("TckrSymb", "").strip()
                srs = row.get("SctySrs", "").strip()

                if series_filter and srs != series_filter:
                    continue

                if universe_symbols and sym not in universe_symbols:
                    continue

                # Parse numerical columns
                try:
                    trading_date = row.get("TradDt", "").strip()
                    op = float(row.get("OpnPric", 0))
                    hp = float(row.get("HghPric", 0))
                    lp = float(row.get("LwPric", 0))
                    cp = float(row.get("ClsPric", 0))
                    ltp = float(row.get("LastPric", 0)) if row.get("LastPric") else cp
                    prev_c = float(row.get("PrvsClsgPric", 0)) if row.get("PrvsClsgPric") else None
                    vol = int(float(row.get("TtlTradgVol", 0)))
                    turnover = float(row.get("TtlTrfVal", 0)) if row.get("TtlTrfVal") else None
                    trades = int(float(row.get("TtlNbOfTxsExctd", 0))) if row.get("TtlNbOfTxsExctd") else None
                except (ValueError, TypeError) as e:
                    summary["rejected_count"] += 1
                    summary["rejections"].append({"symbol": sym, "reason": "Numerical conversion error", "error": str(e)})
                    continue

                # Invariant checks
                if hp < lp:
                    summary["rejected_count"] += 1
                    summary["rejections"].append({"symbol": sym, "reason": f"High {hp} < Low {lp}"})
                    continue

                if op < 0 or hp < 0 or lp < 0 or cp < 0 or vol < 0:
                    summary["rejected_count"] += 1
                    summary["rejections"].append({"symbol": sym, "reason": "Negative price or volume"})
                    continue

                rec = {
                    "symbol": sym,
                    "trading_date": trading_date,
                    "series": srs,
                    "open": op,
                    "high": hp,
                    "low": lp,
                    "close": cp,
                    "ltp": ltp,
                    "prev_close": prev_c,
                    "volume": vol,
                    "turnover": turnover,
                    "delivery_qty": None,  # CM-UDiFF standard bhavcopy does not include delivery breakdown; recorded as NULL
                    "trades_count": trades,
                    "source": "cm_udiff",
                    "data_status": "final_settled",
                    "retrieval_timestamp": now_ts
                }
                accepted.append(rec)
                summary["accepted_count"] += 1

        return accepted, summary
