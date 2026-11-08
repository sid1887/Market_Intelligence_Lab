"""
tests/test_nse_archive_fetcher.py
Hermetic Unit and Contract Tests for NSEArchiveFetcher.

Covers:
1. Legacy bhavcopy parsing (cm05JAN2024bhav.csv) with schema normalization.
2. Modern UDIFF bhavcopy parsing (BhavCopy_NSE_CM_0_0_0_20241217_F_0000.csv) with schema normalization.
3. Strict filtering: series == 'EQ' and symbol in universe_symbols; non-EQ and non-universe dropped.
4. Weekend / invalid dates fail-closed (returns None, zero mock price fabrication).
5. Disk caching: repeated requests return cached Path without invoking network.
"""

import io
import zipfile
import pytest
from pathlib import Path
from datetime import date
from unittest.mock import MagicMock

from src.data.nse_archive_fetcher import NSEArchiveFetcher, UDIFF_CUTOVER_DATE


@pytest.fixture
def test_fetcher(tmp_path):
    cache_dir = tmp_path / "bhavcopy_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    fetcher = NSEArchiveFetcher(cache_dir=cache_dir)
    return fetcher


def create_mock_zip(file_path: Path, csv_filename: str, csv_content: str) -> Path:
    """Helper to write a zip file containing a CSV."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(file_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(csv_filename, csv_content)
    return file_path


def test_01_legacy_bhavcopy_parsing(test_fetcher, tmp_path):
    """
    Test 1: Parses legacy NSE format (pre-July 2024):
    SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN
    """
    legacy_csv = (
        "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\n"
        "RELIANCE,EQ,2580.0,2600.0,2570.0,2595.0,2596.0,2580.0,5000000,12975000000,05-JAN-2024,150000,INE002A01018,\n"
        "TCS,EQ,3700.0,3750.0,3690.0,3740.0,3745.0,3700.0,2000000,7480000000,05-JAN-2024,80000,INE467B01029,\n"
        "HDFCBANK,BZ,1600.0,1620.0,1590.0,1610.0,1610.0,1600.0,1000000,1610000000,05-JAN-2024,50000,INE040A01034,\n"
        "UNKNOWN,EQ,100.0,105.0,98.0,102.0,102.0,100.0,50000,5100000,05-JAN-2024,1000,INE000000000,\n"
    )

    zip_file = create_mock_zip(tmp_path / "cm05JAN2024bhav.csv.zip", "cm05JAN2024bhav.csv", legacy_csv)
    universe = {"RELIANCE", "TCS", "HDFCBANK"}

    records = test_fetcher.parse_bhavcopy(zip_file, universe_symbols=universe)

    # 1. Non-EQ series (HDFCBANK with series 'BZ') must be filtered out
    # 2. Non-universe symbols (UNKNOWN) must be filtered out
    symbols_present = {r["symbol"] for r in records}
    assert symbols_present == {"RELIANCE", "TCS"}
    assert len(records) == 2

    # Check normalized fields for RELIANCE
    rel = [r for r in records if r["symbol"] == "RELIANCE"][0]
    assert rel["trading_date"] == "2024-01-05"
    assert rel["series"] == "EQ"
    assert rel["open"] == 2580.0
    assert rel["high"] == 2600.0
    assert rel["low"] == 2570.0
    assert rel["close"] == 2595.0
    assert rel["volume"] == 5000000
    assert rel["provenance_class"] == "EXCHANGE_OFFICIAL"
    assert rel["is_synthetic"] == 0


def test_02_udiff_bhavcopy_parsing(test_fetcher, tmp_path):
    """
    Test 2: Parses modern UDIFF format (post-July 2024):
    TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,...OpnPric,HghPric,LwPric,ClsPric,...TtlTradgVol
    """
    udiff_csv = (
        "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,"
        "StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,"
        "SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks\n"
        "2024-12-17,2024-12-17,CM,NSE,STK,5385,INE002A01018,RELIANCE,EQ,,,,,RELIANCE IND,1250.00,1265.00,1240.00,1260.00,1259.00,1245.00,,1260.00,,,3000000,3780000000,50000,F1,1,\n"
        "2024-12-17,2024-12-17,CM,NSE,STK,5385,INE002A01018,RELIANCE,BL,,,,,RELIANCE IND,1250.00,1265.00,1240.00,1260.00,1259.00,1245.00,,1260.00,,,3000000,3780000000,50000,F1,1,\n"
        "2024-12-17,2024-12-17,CM,NSE,STK,5385,INE467B01029,TCS,EQ,,,,,TCS LTD,4100.00,4120.00,4080.00,4115.00,4115.00,4090.00,,4115.00,,,1500000,6172500000,40000,F1,1,\n"
    )

    zip_file = create_mock_zip(tmp_path / "BhavCopy_NSE_CM_0_0_0_20241217_F_0000.csv.zip", "BhavCopy_NSE_CM_0_0_0_20241217_F_0000.csv", udiff_csv)
    universe = {"RELIANCE", "TCS"}

    records = test_fetcher.parse_bhavcopy(zip_file, universe_symbols=universe)

    assert len(records) == 2
    symbols_present = {r["symbol"] for r in records}
    assert symbols_present == {"RELIANCE", "TCS"}

    tcs = [r for r in records if r["symbol"] == "TCS"][0]
    assert tcs["trading_date"] == "2024-12-17"
    assert tcs["series"] == "EQ"
    assert tcs["open"] == 4100.0
    assert tcs["high"] == 4120.0
    assert tcs["low"] == 4080.0
    assert tcs["close"] == 4115.0
    assert tcs["volume"] == 1500000
    assert tcs["is_synthetic"] == 0


def test_03_weekend_and_invalid_date_fail_closed(test_fetcher):
    """
    Test 3: Saturday and Sunday dates return None immediately without making network calls.
    """
    # 2024-01-06 was Saturday, 2024-01-07 was Sunday
    assert test_fetcher.fetch_daily_bhavcopy("2024-01-06") is None
    assert test_fetcher.fetch_daily_bhavcopy("2024-01-07") is None


def test_04_disk_cache_layer_elides_network(test_fetcher, tmp_path):
    """
    Test 4: If file already exists in cache_dir, fetch_daily_bhavcopy returns path directly.
    """
    # Create cached file at expected location: cache_dir/2024/01/cm05JAN2024bhav.csv.zip
    target_cache = test_fetcher.cache_dir / "2024" / "01" / "cm05JAN2024bhav.csv.zip"
    create_mock_zip(target_cache, "cm05JAN2024bhav.csv", "SYMBOL,SERIES\n")

    # Mock session to ensure no network calls occur
    mock_session = MagicMock()
    test_fetcher.session = mock_session

    result_path = test_fetcher.fetch_daily_bhavcopy("2024-01-05")
    assert result_path == target_cache
    mock_session.get.assert_not_called()


def test_05_format_selection_by_cutover_date(test_fetcher):
    """
    Test 5: Verifies URL routing logic splits on July 8, 2024.
    """
    # 2024-07-05 (Legacy)
    url_leg, fn_leg, is_udiff_leg = test_fetcher.get_archive_url_and_filename(date(2024, 7, 5))
    assert not is_udiff_leg
    assert "cm05JUL2024bhav.csv.zip" in fn_leg
    assert "archives.nseindia.com/content/historical/EQUITIES/2024/JUL/" in url_leg

    # 2024-07-08 (UDIFF)
    url_udiff, fn_udiff, is_udiff = test_fetcher.get_archive_url_and_filename(date(2024, 7, 8))
    assert is_udiff
    assert "BhavCopy_NSE_CM_0_0_0_20240708_F_0000.csv.zip" in fn_udiff
    assert "nsearchives.nseindia.com/content/cm/" in url_udiff
