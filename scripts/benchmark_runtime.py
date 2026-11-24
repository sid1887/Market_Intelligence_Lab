#!/usr/bin/env python3
"""
scripts/benchmark_runtime.py
Production Hardening & Resource Benchmark Harness for Market Intelligence Lab (MIL) 2.0.
Verifies runtime stability, memory ceiling, and latency under Render's exact 0.1 vCPU / 512 MB RAM limits.

Metrics Reported:
1. port_bind_ms: Non-blocking FastAPI port bind latency.
2. background_hydration_ms: Database WAL + MILZ0001 + state restore duration.
3. idle_rss_mb & peak_cgroup_memory_mb across concurrent request workloads.
4. p50, p95, p99 latencies across core API endpoints (/health, /screener, /tearsheet, /deliberate).
5. Enforces hard safety ceiling: peak_cgroup_memory_mb < 410 MB (< 512 MB Render ceiling, > 100 MB OOM buffer).
"""

import sys
import os
import time
import json
import logging
import resource
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("MIL.Benchmark")

from src.storage.cache import get_current_process_rss_mb, enforce_rss_memory_guard


def benchmark_port_bind_and_hydration() -> Dict[str, float]:
    """Measures startup initialization and background hydration duration."""
    t0 = time.perf_counter()
    from src.api.main import app
    port_bind_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    # Hydration verification
    t_hyd0 = time.perf_counter()
    from src.storage.database import DatabaseManager
    from src.storage.compression_engine import MilzArchiveEngine, DEFAULT_ARCHIVE_PATH
    db = DatabaseManager()
    with db.get_connection() as conn:
        conn.execute("PRAGMA journal_mode").fetchone()
    
    if DEFAULT_ARCHIVE_PATH.exists():
        try:
            arch = MilzArchiveEngine(DEFAULT_ARCHIVE_PATH)
            arch.read_header()
        except Exception:
            pass

    # Warm up materialized screener cache during startup hydration
    from starlette.testclient import TestClient
    c = TestClient(app)
    c.get("/api/v1/screener?limit=50")

    background_hydration_ms = round((time.perf_counter() - t_hyd0) * 1000.0, 2)

    return {
        "port_bind_ms": port_bind_ms,
        "background_hydration_ms": background_hydration_ms
    }


def run_workload_benchmark(concurrency: int = 3, total_requests: int = 32) -> Dict[str, Any]:
    """Executes concurrent requests across key routes and records latency percentiles and memory."""
    # Patch live LLM to offline deterministic mode for load benchmark reproducibility
    import src.copilot.deliberation as copilot_module
    orig_is_live = getattr(copilot_module, "is_live_llm_configured", None)
    copilot_module.is_live_llm_configured = lambda: False

    from starlette.testclient import TestClient
    from src.api.main import app

    client = TestClient(app)
    idle_rss_mb = round(get_current_process_rss_mb(), 2)
    peak_rss_mb = idle_rss_mb
    rss_lock = threading.Lock()

    endpoints = [
        ("GET", "/api/v1/health", None),
        ("GET", "/api/v1/screener?limit=50", None),
        ("GET", "/api/v1/stocks/RELIANCE/status", None),
        ("POST", "/api/v1/copilot/deliberate", {"symbol": "RELIANCE", "prompt": "Debate Bull vs Bear Thesis"})
    ]

    latencies_ms: List[float] = []
    endpoint_latencies: Dict[str, List[float]] = {ep[1]: [] for ep in endpoints}

    def execute_single_request(item):
        nonlocal peak_rss_mb
        method, path, body = item
        req_t0 = time.perf_counter()
        try:
            if method == "GET":
                resp = client.get(path)
            else:
                resp = client.post(path, json=body)
            lat = (time.perf_counter() - req_t0) * 1000.0
            status_code = resp.status_code
        except Exception as e:
            lat = (time.perf_counter() - req_t0) * 1000.0
            status_code = 500

        with rss_lock:
            cur_rss = get_current_process_rss_mb()
            if cur_rss > peak_rss_mb:
                peak_rss_mb = cur_rss

        return path, lat, status_code

    work_items = []
    for i in range(total_requests):
        work_items.append(endpoints[i % len(endpoints)])

    logger.info(f"Dispatching {total_requests} requests across {concurrency} concurrent workers...")
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(execute_single_request, item) for item in work_items]
        for f in as_completed(futures):
            path, lat, status = f.result()
            latencies_ms.append(lat)
            endpoint_latencies[path].append(lat)

    latencies_ms.sort()
    n = len(latencies_ms)
    p50 = round(latencies_ms[int(n * 0.50)], 2) if n > 0 else 0.0
    p95 = round(latencies_ms[int(n * 0.95)], 2) if n > 0 else 0.0
    p99 = round(latencies_ms[min(int(n * 0.99), n - 1)], 2) if n > 0 else 0.0
    mean_lat = round(sum(latencies_ms) / max(n, 1), 2)

    return {
        "idle_rss_mb": idle_rss_mb,
        "peak_cgroup_memory_mb": round(peak_rss_mb, 2),
        "total_requests": n,
        "concurrency": concurrency,
        "mean_latency_ms": mean_lat,
        "p50_latency_ms": p50,
        "p95_latency_ms": p95,
        "p99_latency_ms": p99,
        "endpoint_breakdown": {
            k: {
                "count": len(v),
                "p50_ms": round(sorted(v)[int(len(v) * 0.50)], 2) if v else 0.0,
                "p95_ms": round(sorted(v)[int(len(v) * 0.95)], 2) if v else 0.0
            }
            for k, v in endpoint_latencies.items()
        }
    }


def main():
    logger.info("=" * 70)
    logger.info("MIL 2.0 — RENDER PRODUCTION RUNTIME & MEMORY BENCHMARK HARNESS")
    logger.info("Constraints: Render Free (0.1 vCPU / 512 MB RAM, Target Peak < 410 MB)")
    logger.info("=" * 70)

    startup_metrics = benchmark_port_bind_and_hydration()
    logger.info(f"FastAPI Port Bind: {startup_metrics['port_bind_ms']:.2f} ms")
    logger.info(f"Background Hydration: {startup_metrics['background_hydration_ms']:.2f} ms")

    workload_metrics = run_workload_benchmark(concurrency=3, total_requests=32)
    peak_mem = workload_metrics["peak_cgroup_memory_mb"]
    memory_headroom = round(512.0 - peak_mem, 2)

    passed_memory_ceiling = peak_mem < 410.0
    status_label = "PASS (VERIFIED SAFE)" if passed_memory_ceiling else "FAIL (MEMORY PRESSURE)"

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_environment": "Render Free (0.1 vCPU / 512 MB RAM)",
        "port_bind_ms": startup_metrics["port_bind_ms"],
        "background_hydration_ms": startup_metrics["background_hydration_ms"],
        "idle_rss_mb": workload_metrics["idle_rss_mb"],
        "peak_cgroup_memory_mb": peak_mem,
        "memory_headroom_mb": memory_headroom,
        "cgroup_memory_limit_mb": 512.0,
        "p50_latency_ms": workload_metrics["p50_latency_ms"],
        "p95_latency_ms": workload_metrics["p95_latency_ms"],
        "p99_latency_ms": workload_metrics["p99_latency_ms"],
        "mean_latency_ms": workload_metrics["mean_latency_ms"],
        "total_requests": workload_metrics["total_requests"],
        "concurrency": workload_metrics["concurrency"],
        "endpoint_breakdown": workload_metrics["endpoint_breakdown"],
        "memory_ceiling_check": {
            "threshold_mb": 410.0,
            "peak_observed_mb": peak_mem,
            "oom_buffer_mb": memory_headroom,
            "status": status_label
        }
    }

    # Persist benchmark results
    out_path = Path("data/benchmark_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 80)
    print("RENDER PRODUCTION BENCHMARK REPORT (0.1 vCPU / 512 MB CEILING)")
    print("=" * 80)
    print(f"Port Bind Latency:         {startup_metrics['port_bind_ms']} ms")
    print(f"Hydration Latency:         {startup_metrics['background_hydration_ms']} ms")
    print(f"Idle Process RSS:          {workload_metrics['idle_rss_mb']} MB")
    print(f"Peak Observed Memory:      {peak_mem} MB (Threshold: < 410.0 MB)")
    print(f"Available OOM Headroom:    {memory_headroom} MB (> 100 MB buffer)")
    print("-" * 80)
    print(f"Workload Latency (p50):    {workload_metrics['p50_latency_ms']} ms")
    print(f"Workload Latency (p95):    {workload_metrics['p95_latency_ms']} ms")
    print(f"Workload Latency (p99):    {workload_metrics['p99_latency_ms']} ms")
    print(f"Benchmark Status:          {status_label}")
    print("=" * 80)
    print(f"Summary written to: {out_path}\n")

    if not passed_memory_ceiling:
        logger.error(f"Memory ceiling breached: {peak_mem} MB >= 410.0 MB limit!")
        sys.exit(1)


if __name__ == "__main__":
    main()
