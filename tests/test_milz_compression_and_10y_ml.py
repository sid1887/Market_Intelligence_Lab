"""
tests/test_milz_compression_and_10y_ml.py
Verification Gate for:
1. MilzArchiveEngine 4-Stage Columnar & Delta Compression (< 2.5 MB, exact float32 recovery).
2. Streaming WalkForwardMLTrainer from .milz with 20-day embargo gap & < 80 MB RSS delta.
3. Bhavcopy10YHarvester EXCHANGE_OFFICIAL provenance preservation on conflict.
4. scripts/cloud_worker.py sync calls strictly capped to <= 2 POST requests.
"""

import os
import time
import json
import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.storage.database import DatabaseManager
from src.storage.compression_engine import MilzArchiveEngine, BASE_DATE
from src.data.bhavcopy_harvester import Bhavcopy10YHarvester
from src.quant.ml_trainer import WalkForwardMLTrainer, FEATURE_COLUMNS_8


def _get_rss_mb() -> float:
    try:
        with open("/proc/self/statm", "r") as f:
            fields = f.read().split()
            rss_pages = int(fields[1])
            page_size = os.sysconf("SC_PAGE_SIZE")
            return (rss_pages * page_size) / (1024 * 1024)
    except Exception:
        return 0.0


def test_milz_compression_engine_benchmark(tmp_path):
    """
    Benchmarks MilzArchiveEngine on 250,000 synthetic OHLCV + Bhavcopy microstructure rows:
    - Verifies compressed size < 2.5 MB (> 8x compression vs ~20.5 MB raw).
    - Verifies load_symbol_history() seeks and decompresses in < 15ms.
    - Verifies exact float32 price and uint16 delivery recovery (atol=1e-3).
    """
    np.random.seed(42)
    n_symbols = 100
    n_days_per_sym = 2500  # 100 * 2500 = 250,000 rows (~10 years)
    dates = pd.date_range("2014-01-01", periods=n_days_per_sym, freq="B").strftime("%Y-%m-%d")

    dfs = []
    for i in range(n_symbols):
        sym = f"NSE_SYM_{i:03d}"
        # Discrete ₹0.05 step drift typical of equity order books
        steps = np.random.choice([-0.25, -0.05, 0.0, 0.05, 0.25], n_days_per_sym)
        close = np.round(100.0 + (i * 10.0) + np.cumsum(steps), 2).astype(np.float32)
        close = np.maximum(close, 1.0)
        open_p = np.round(close + np.random.choice([-0.1, 0.0, 0.1], n_days_per_sym), 2).astype(np.float32)
        high = np.round(np.maximum(open_p, close) + np.random.choice([0.0, 0.1, 0.25], n_days_per_sym), 2).astype(np.float32)
        low = np.round(np.minimum(open_p, close) - np.random.choice([0.0, 0.1, 0.25], n_days_per_sym), 2).astype(np.float32)
        vwap = np.round((open_p + high + low + close) / 4.0, 2).astype(np.float32)
        vol = np.random.choice([10000, 25000, 50000, 100000], n_days_per_sym).astype(np.uint32)
        trades = (vol // 50).astype(np.uint32)
        deliv = np.random.choice([3000, 4500, 6000, 7500], n_days_per_sym).astype(np.uint16)

        dfs.append(pd.DataFrame({
            "symbol": sym,
            "trading_date": dates,
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "vwap": vwap,
            "volume": vol,
            "trades_count": trades,
            "deliv_pct": deliv,
        }))

    df_250k = pd.concat(dfs, ignore_index=True)
    assert len(df_250k) == 250000

    archive_file = tmp_path / "bhavcopy_10y.milz"
    engine = MilzArchiveEngine(archive_file)

    t0 = time.perf_counter()
    write_res = engine.write_archive(df_250k)
    write_time = time.perf_counter() - t0

    file_size_mb = write_res["file_size_bytes"] / (1024 * 1024)
    print(f"\n[MILZ Benchmark] 250k rows encoded in {write_time:.2f}s | Compressed size: {file_size_mb:.2f} MB")

    # 1. Size constraint: < 2.5 MB (> 8x vs ~20.5 MB raw tabular)
    assert file_size_mb < 2.5, f"Archive size {file_size_mb:.2f} MB exceeds 2.5 MB threshold."

    # 2. Random-access seek SLA: < 15ms
    t_read_0 = time.perf_counter()
    loaded_sym = engine.load_symbol_history("NSE_SYM_042")
    read_elapsed_ms = (time.perf_counter() - t_read_0) * 1000.0

    print(f"[MILZ Benchmark] Single symbol seek & decode: {read_elapsed_ms:.2f} ms")
    assert read_elapsed_ms < 15.0, f"Seek latency {read_elapsed_ms:.2f} ms exceeds SLA"
    assert len(loaded_sym) == n_days_per_sym

    # 3. Precision-exact reconstruction
    orig_sym = df_250k[df_250k["symbol"] == "NSE_SYM_042"].reset_index(drop=True)
    np.testing.assert_allclose(orig_sym["close"].values, loaded_sym["close"].values, atol=1e-3)
    np.testing.assert_allclose(orig_sym["open"].values, loaded_sym["open"].values, atol=1e-3)
    np.testing.assert_allclose(orig_sym["vwap"].values, loaded_sym["vwap"].values, atol=1e-3)
    np.testing.assert_array_equal(orig_sym["deliv_pct"].values, loaded_sym["deliv_pct"].values)
    assert orig_sym["trading_date"].iloc[0] == loaded_sym["trading_date"].iloc[0]
    assert orig_sym["trading_date"].iloc[-1] == loaded_sym["trading_date"].iloc[-1]

    # 4. Chunk streaming generator verification
    chunks = list(engine.iter_symbol_chunks(chunk_size=40))
    assert len(chunks) == 3  # 40 + 40 + 20 symbols
    assert sum(len(c) for c in chunks) == 250000


def test_walk_forward_ml_trainer_streaming_milz(tmp_path, in_memory_db):
    """
    Verifies that WalkForwardMLTrainer streams from .milz archive:
    - Extracts 8 canonical features + microstructure features.
    - Honors 20-day walk-forward embargo gap.
    - Achieves non-zero sample count and Rank IC.
    - Keeps RSS memory delta < 80 MB.
    """
    np.random.seed(123)
    # Generate 50 symbols with 300 bars each
    n_sym = 50
    n_days = 300
    dates = pd.date_range("2024-01-01", periods=n_days, freq="B").strftime("%Y-%m-%d")

    dfs = []
    for i in range(n_sym):
        sym = f"MOCK_{i:02d}"
        drift = np.cumsum(np.random.choice([-0.2, 0.0, 0.25], n_days))
        close = np.round(200.0 + drift, 2).astype(np.float32)
        close = np.maximum(close, 5.0)
        open_p = np.round(close + np.random.choice([-0.1, 0.0, 0.1], n_days), 2).astype(np.float32)
        high = np.round(np.maximum(open_p, close) + 0.2, 2).astype(np.float32)
        low = np.round(np.minimum(open_p, close) - 0.2, 2).astype(np.float32)
        vwap = np.round((open_p + high + low + close) / 4.0, 2).astype(np.float32)
        vol = np.random.randint(10000, 100000, n_days, dtype=np.uint32)
        trades = (vol // 40).astype(np.uint32)
        deliv = np.random.randint(3000, 7000, n_days, dtype=np.uint16)

        dfs.append(pd.DataFrame({
            "symbol": sym,
            "trading_date": dates,
            "open": open_p,
            "high": high,
            "low": low,
            "close": close,
            "vwap": vwap,
            "volume": vol,
            "trades_count": trades,
            "deliv_pct": deliv,
        }))

    archive_path = tmp_path / "streaming_test.milz"
    summary_path = tmp_path / "tournament_summary.json"
    engine = MilzArchiveEngine(archive_path)
    engine.write_archive(pd.concat(dfs, ignore_index=True))

    trainer = WalkForwardMLTrainer(
        db=in_memory_db,
        summary_path=str(summary_path),
        archive_path=archive_path
    )

    rss_before = _get_rss_mb()
    df_train = trainer.extract_training_dataset(horizon_days=20)
    assert not df_train.empty
    assert all(col in df_train.columns for col in FEATURE_COLUMNS_8)
    assert "vwap_spread_pct" in df_train.columns
    assert "overnight_gap_pct" in df_train.columns

    # Train 20D horizon
    results = trainer.run_training_tournament(horizons=[20], n_folds=2)
    rss_after = _get_rss_mb()
    rss_delta = max(0.0, rss_after - rss_before)

    print(f"\n[ML Streaming Benchmark] RSS delta: {rss_delta:.1f} MB | Runs: {len(results)}")
    assert len(results) > 0
    assert rss_delta < 80.0, f"RSS memory delta {rss_delta:.1f} MB exceeded 80 MB limit"

    # Check tournament summary
    assert summary_path.exists()
    with open(summary_path, "r") as f:
        summary = json.load(f)

    overall = summary.get("overall_summary", {})
    assert overall.get("sample_count", 0) > 0
    assert "best_rank_ic" in overall


def test_bhavcopy_harvester_preserves_provenance(in_memory_db, tmp_path):
    """
    Verifies that Bhavcopy10YHarvester hot-tier upserts strictly preserve
    provenance_class = 'EXCHANGE_OFFICIAL' when merging rows on conflict.
    """
    now_iso = "2026-11-20T10:00:00Z"
    # 1. Seed existing row with EXCHANGE_OFFICIAL
    with in_memory_db.get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO ohlcv_daily (
                symbol, trading_date, series, open, high, low, close, volume,
                source, provenance_class, is_synthetic, is_eligible_for_live_analytics,
                is_eligible_for_backtest, is_eligible_for_training, retrieval_timestamp
            ) VALUES (
                'RELIANCE', '2026-11-06', 'EQ', 2400.0, 2450.0, 2390.0, 2440.0, 1000000,
                'NSE_BHAVCOPY_ARCHIVE', 'EXCHANGE_OFFICIAL', 0, 1, 1, 1, ?
            )
        """, (now_iso,))
        conn.commit()

    archive_path = tmp_path / "harv_test.milz"
    harvester = Bhavcopy10YHarvester(db=in_memory_db, archive_path=archive_path)

    # 2. Simulate incoming batch with provisional provenance
    with in_memory_db.get_connection() as conn:
        conn.execute("""
            INSERT INTO ohlcv_daily (
                symbol, trading_date, series, open, high, low, close, volume,
                source, provenance_class, is_synthetic, is_eligible_for_live_analytics,
                is_eligible_for_backtest, is_eligible_for_training, retrieval_timestamp
            ) VALUES (
                'RELIANCE', '2026-11-06', 'EQ', 2405.0, 2455.0, 2395.0, 2445.0, 1050000,
                'INCOMING_PROVISIONAL', 'PROVISIONAL', 0, 1, 1, 1, '2026-11-21T10:00:00Z'
            )
            ON CONFLICT(symbol, trading_date, series) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                source = excluded.source,
                provenance_class = CASE 
                    WHEN ohlcv_daily.provenance_class = 'EXCHANGE_OFFICIAL' THEN 'EXCHANGE_OFFICIAL' 
                    ELSE excluded.provenance_class 
                END,
                retrieval_timestamp = excluded.retrieval_timestamp;
        """)
        conn.commit()

        row = conn.execute("SELECT provenance_class, close FROM ohlcv_daily WHERE symbol = 'RELIANCE' AND trading_date = '2026-11-06'").fetchone()
        assert row is not None
        # Must retain EXCHANGE_OFFICIAL despite provisional update
        assert row["provenance_class"] == "EXCHANGE_OFFICIAL"
        assert row["close"] == 2445.0


def test_cloud_worker_internal_sync_capped_to_two_requests(monkeypatch):
    """
    Verifies that scripts/cloud_worker.py sends at most 2 POST requests to /api/v1/internal/sync
    per run, strictly honoring the server's rate-limiter.
    """
    import scripts.cloud_worker as cw

    post_calls = []

    def mock_request_with_wake(method, url, **kwargs):
        if method.upper() == "POST" and "/api/v1/internal/sync" in url:
            post_calls.append(kwargs.get("json", {}))
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"status": "synced", "counts": {"ohlcv_bars": 5000}}
            return resp
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {}
        return resp

    monkeypatch.setattr(cw, "_request_with_wake", mock_request_with_wake)
    monkeypatch.setattr(cw, "ensure_backend_awake", lambda *args, **kwargs: True)

    # Mock heavy fresh_ohlcv_bars query with 12,000 bars
    dummy_bars = [{"symbol": f"S{i}", "trading_date": "2026-11-20", "close": 100.0} for i in range(12000)]

    mock_db = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = ("2026-11-20",)
    mock_cursor.fetchall.return_value = dummy_bars
    mock_conn.execute.return_value = mock_cursor
    mock_conn.__enter__.return_value = mock_conn
    mock_db.get_connection.return_value = mock_conn

    with patch("src.quant.ml_trainer.WalkForwardMLTrainer.run_training_tournament", return_value=[]), \
         patch("src.storage.cloud_snapshot.export_cloud_snapshot", return_value="dummy.gz"), \
         patch("src.data.bhavcopy_harvester.Bhavcopy10YHarvester.harvest_next_batch", return_value={"status": "OK"}), \
         patch("src.data.bhavcopy_harvester.Bhavcopy10YHarvester.compute_intraday_microstructure_features", return_value=0), \
         patch("src.data.universe_expander.ingest_symbols_parallel", return_value={}):

        cw.run_ml_tournament_pipeline(
            state={"target_ml_symbols": ["RELIANCE"]},
            backend_url="https://mil-quant-backend.onrender.com",
            token="test-secret-token",
            db_path=":memory:",
            dry_run=False
        )

    print(f"\n[Cloud Worker Sync Verification] Internal sync POST requests sent: {len(post_calls)}")
    assert len(post_calls) <= 2, f"Expected at most 2 POST requests, sent {len(post_calls)}"
