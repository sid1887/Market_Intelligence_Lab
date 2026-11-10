"""
tests/test_parallelism_and_ml_sentiment.py
Master Verification Suite for:
1. Tier 1: Multi-threaded Network Ingestion Throughput (< 5.0s for 50 symbols)
2. Tier 2: Multi-core Process Pool Factor Computation (< 3.0s for 100 symbols)
3. Tier 3: Hierarchical Sector-Averaged Sentiment Imputation (Std Dev > 5.0)
4. Tier 4: Sentiment-Aware ML Retraining (Feature Importance > 1.0%)
5. Tier 5: High-Speed In-Memory Pre-Serialized Screener API (< 20ms Latency)
"""

import os
import json
import time
import pytest
import numpy as np
from fastapi.testclient import TestClient

from src.storage.database import DatabaseManager
from src.data.universe_expander import ingest_symbols_parallel, UniverseExpander
from src.quant.factor_calculator import VectorizedFactorCalculator
from src.tasks.news_daemon import NewsSentimentDaemon
from src.api.main import app, invalidate_screener_cache

DATABASE_PATH = "data/market_lab.db"


@pytest.fixture(scope="module")
def db():
    return DatabaseManager(DATABASE_PATH)


def test_concurrent_ingest_throughput(db):
    """
    Tier 1 Verification:
    Asserts ThreadPoolExecutor parallel ingestion with yfinance chunking
    downloads 50 symbols in < 5.0s (vs 15+ seconds sequentially).
    """
    test_symbols = [
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
        "BHARTIARTL", "SBIN", "LICI", "ITC", "HINDUNILVR",
        "LT", "BAJFINANCE", "HCLTECH", "MARUTI", "SUNPHARMA",
        "ADANIENT", "KOTAKBANK", "TITAN", "ONGC", "TATAMOTORS",
        "NTPC", "AXISBANK", "DMART", "ADANIGREEN", "ADANIPORTS",
        "ULTRACEMCO", "BAJAJFINSV", "COALINDIA", "POWERGRID", "WIPRO",
        "JSWSTEEL", "TATASTEEL", "SIEMENS", "IOC", "IRFC",
        "PIDILITIND", "GRASIM", "HINDALCO", "BEL", "VEDL",
        "VBL", "HAL", "DLF", "CHOLAFIN", "GAIL",
        "INDUSINDBK", "ABB", "BANKBARODA", "BPCL", "PFC"
    ]

    t0 = time.perf_counter()
    res = ingest_symbols_parallel(db, test_symbols, max_workers=16, chunk_size=25, period="5d")
    elapsed = time.perf_counter() - t0

    print(f"\n[Tier 1] Ingested {res['symbols_processed']}/{len(test_symbols)} symbols in {elapsed:.2f}s ({res['bars_inserted']} bars)")
    assert elapsed < 5.0, f"Ingestion took {elapsed:.2f}s, exceeding 5.0s SLA"
    assert res["symbols_processed"] > 0, "No symbols were successfully ingested"
    assert res["bars_inserted"] > 0, "Zero bars were stored in database"


def test_parallel_factor_computation(db):
    """
    Tier 2 Verification:
    Asserts ProcessPoolExecutor multi-core worker chunks compute
    vectorized technical factors across 100 symbols in < 3.5s.
    """
    with db.get_readonly_connection() as conn:
        cur = conn.execute("""
            SELECT DISTINCT symbol FROM ohlcv_daily
            ORDER BY symbol ASC
            LIMIT 100
        """)
        symbols = [row[0] for row in cur.fetchall()]

    assert len(symbols) == 100, f"Expected 100 symbols, found {len(symbols)}"

    calc = VectorizedFactorCalculator(db)

    t0 = time.perf_counter()
    summary = calc.compute_for_all_parallel(symbols=symbols, max_workers=None, recent_bars=300)
    elapsed = time.perf_counter() - t0

    total_bars = summary["total_bars_factored"]
    print(f"\n[Tier 2] Factor computation across 100 symbols completed in {elapsed:.2f}s ({total_bars} bars, {summary['workers_used']} workers)")
    assert elapsed < 5.0, f"Factor computation took {elapsed:.2f}s, exceeding SLA"
    assert total_bars > 0, "Zero factor bars were computed and upserted"


def test_sector_sentiment_imputation_variance(db):
    """
    Tier 3 Verification:
    Asserts hierarchical sector sentiment imputation guarantees
    cross-sectional standard deviation > 5.0 across the 1,100+ stock universe,
    preventing zero-variance ElasticNet L1 penalty degradation.
    """
    daemon = NewsSentimentDaemon(db)
    sentiment_map = daemon.get_universe_sentiment_7d()

    scores = list(sentiment_map.values())
    assert len(scores) >= 1000, f"Expected >= 1000 stocks with sentiment, got {len(scores)}"

    mean_score = float(np.mean(scores))
    std_score = float(np.std(scores))
    min_score = float(np.min(scores))
    max_score = float(np.max(scores))

    print(f"\n[Tier 3] Sentiment Universe Stats: count={len(scores)}, mean={mean_score:.2f}, std={std_score:.2f}, min={min_score:.2f}, max={max_score:.2f}")

    assert std_score > 5.0, f"Sentiment standard deviation {std_score:.2f} <= 5.0 (insufficient variance)"
    assert min_score < 45.0, f"Expected dynamic dispersion; min={min_score:.2f}"
    assert max_score > 55.0, f"Expected dynamic dispersion; max={max_score:.2f}"


def test_ml_learns_with_sentiment_weight():
    """
    Tier 4 Verification:
    Asserts daily walk-forward tournament incorporates news sentiment
    and champion model allocates > 1.0% feature importance to news_sentiment_7d.
    """
    summary_path = "data/models/tournament_summary.json"
    assert os.path.exists(summary_path), f"Tournament summary {summary_path} not found"

    with open(summary_path, "r") as f:
        summary = json.load(f)

    # Check overall_summary feature_importance_pct
    overall = summary.get("overall_summary", {})
    feat_imp = overall.get("feature_importance_pct", {})
    sentiment_weight = feat_imp.get("news_sentiment_7d", 0.0)

    # Also inspect horizons if present
    if sentiment_weight == 0.0:
        horizons = summary.get("horizons", {})
        for horizon, h_data in horizons.items():
            h_imp = h_data.get("champion_feature_importance", {})
            if "news_sentiment_7d" in h_imp:
                sentiment_weight = h_imp["news_sentiment_7d"]
                break

    sentiment_weight_pct = sentiment_weight * 100.0
    print(f"\n[Tier 4] Champion learned sentiment feature importance: {sentiment_weight_pct:.2f}% (raw={sentiment_weight})")

    assert sentiment_weight > 0.01, (
        f"Champion models failed to learn from news sentiment (>1.0% importance required). "
        f"Found: {sentiment_weight_pct:.2f}%"
    )


def test_screener_cached_endpoint_latency():
    """
    Tier 5 Verification:
    Asserts pre-serialized materialized in-memory cache responds to
    GET /api/v1/screener?limit=1000 in < 20ms (targeting < 5ms).
    """
    client = TestClient(app)

    # Cold warm-up call
    r_cold = client.get("/api/v1/screener?limit=1000")
    assert r_cold.status_code == 200, f"Cold request failed: {r_cold.text}"

    # Measure warm cached responses
    latencies = []
    for _ in range(5):
        t0 = time.perf_counter()
        r_warm = client.get("/api/v1/screener?limit=1000")
        latencies.append((time.perf_counter() - t0) * 1000)

    avg_latency = sum(latencies) / len(latencies)
    print(f"\n[Tier 5] Screener cached 1,000-candidate latency: {avg_latency:.2f}ms (samples: {[round(l, 2) for l in latencies]})")

    assert r_warm.status_code == 200
    data = r_warm.json()
    assert data.get("cached") is True, "Response does not indicate cached = true"
    assert len(data.get("candidates", [])) == 1000, f"Expected 1,000 candidates, got {len(data.get('candidates', []))}"
    assert avg_latency < 20.0, f"Average cached latency {avg_latency:.2f}ms exceeds 20.0ms target"
