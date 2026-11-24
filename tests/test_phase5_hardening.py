"""
tests/test_phase5_hardening.py
Verification suite for MIL 2.0 Phase 5: Production Hardening, Runtime Memory Guard, and Institutional UX.
"""

import os
import json
import pytest
from pathlib import Path
from starlette.testclient import TestClient

from src.api.main import app
from src.storage.cache import app_cache, get_current_process_rss_mb, enforce_rss_memory_guard
from src.copilot.deliberation import MultiAgentDeliberationEngine


@pytest.fixture
def client():
    return TestClient(app)


def test_health_telemetry_fields(client):
    """Verifies that /api/v1/health exposes live container memory telemetry and model status."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()

    # Core required Phase 5 health fields
    assert "status" in data
    assert data["status"] in ("healthy", "ok", "degraded")
    assert "rss_mb" in data
    assert isinstance(data["rss_mb"], (int, float))
    assert data["rss_mb"] > 0

    assert "memory_headroom_mb" in data
    assert isinstance(data["memory_headroom_mb"], (int, float))
    assert data["memory_headroom_mb"] > 0

    assert "cgroup_memory_limit_mb" in data
    assert data["cgroup_memory_limit_mb"] == 512.0

    assert "durable_state_status" in data
    assert isinstance(data["durable_state_status"], str)
    assert len(data["durable_state_status"]) > 0

    assert "active_champion_model" in data
    assert isinstance(data["active_champion_model"], str)
    assert len(data["active_champion_model"]) > 0


def test_rss_memory_guard_eviction():
    """Verifies that enforce_rss_memory_guard evicts LRU cache and executes cleanup when threshold is crossed."""
    # Seed app_cache
    app_cache.set("test_key_1", {"data": "x" * 1000})
    app_cache.set("test_key_2", {"data": "y" * 1000})
    assert len(app_cache) >= 2

    # Call guard with guaranteed-to-trigger low threshold
    res = enforce_rss_memory_guard(threshold_mb=1.0)
    assert res["evicted"] is True
    assert len(app_cache) == 0

    # Normal threshold should not evict if process RSS is below it
    app_cache.set("test_key_safe", {"data": 123})
    res_safe = enforce_rss_memory_guard(threshold_mb=10000.0)
    assert res_safe["evicted"] is False
    assert len(app_cache) >= 1
    app_cache.clear()


def test_benchmark_results_file_and_memory_ceiling():
    """Verifies that data/benchmark_results.json exists and strictly satisfies the < 410 MB cgroup ceiling."""
    bench_path = Path("data/benchmark_results.json")
    assert bench_path.exists(), "data/benchmark_results.json must exist from benchmark execution"

    with open(bench_path, "r", encoding="utf-8") as f:
        bench = json.load(f)

    assert "peak_cgroup_memory_mb" in bench
    peak_mem = bench["peak_cgroup_memory_mb"]
    assert peak_mem < 410.0, f"Observed peak memory {peak_mem} MB exceeds the 410.0 MB Render ceiling!"

    assert "memory_ceiling_check" in bench
    assert bench["memory_ceiling_check"]["status"] == "PASS (VERIFIED SAFE)"
    assert bench["port_bind_ms"] > 0
    assert bench["background_hydration_ms"] > 0
    assert bench["p50_latency_ms"] > 0


@pytest.mark.asyncio
async def test_copilot_institutional_transparency_payload(monkeypatch):
    """Verifies that Copilot deliberation exposes friction math, hard vetoes, and regime analogs."""
    import src.copilot.deliberation as copilot_module
    monkeypatch.setattr(copilot_module, "is_live_llm_configured", lambda: False)

    engine = MultiAgentDeliberationEngine()
    
    # Run deterministic deliberation turn
    res = await engine.deliberate_json(
        symbol="RELIANCE",
        user_prompt="Debate Bull vs Bear Thesis"
    )

    assert res["stage"] == "complete"
    assert "result" in res
    r = res["result"]

    assert "symbol" in r
    assert "verdict" in r
    assert "can_trade" in r
    assert isinstance(r["can_trade"], bool)
    assert "hard_veto_reasons" in r
    assert isinstance(r["hard_veto_reasons"], list)

    assert "position_sizing" in r
    ps = r["position_sizing"]
    assert "allocated_capital" in ps
    assert "shares" in ps
    assert "fee_drag_pct" in ps
    assert "net_rr" in ps
    assert "gross_rr" in ps
    assert "win_friction" in ps or "roundtrip_friction" in ps

    assert "trader_dna_eval" in r
    assert "regime_analogs" in r
    if r["regime_analogs"] is not None:
        reg = r["regime_analogs"]
        assert "regime_bias" in reg
        assert "mean_forward_20d_return_pct" in reg
        assert "win_rate_20d_pct" in reg


def test_deterministic_baseline_promotion_gating():
    """Verifies that models with Sharpe below 0.4322 baseline are gated from active deployment."""
    summary_path = Path("data/models/tournament_summary.json")
    if not summary_path.exists():
        pytest.skip("Tournament summary not yet generated")

    with open(summary_path, "r", encoding="utf-8") as f:
        summary = json.load(f)

    baseline_sharpe = summary.get("baseline", {}).get("mean_net_sharpe", 0.4322)
    promotion_verdict = summary.get("promotion_verdict")

    # If any candidate failed to beat baseline, verdict must be REJECTED_BELOW_BASELINE
    for cand in summary.get("candidates", []):
        if cand.get("cpcv_mean_sharpe", 0.0) < baseline_sharpe:
            assert cand.get("promotion_status") == "REJECTED_BELOW_BASELINE"
