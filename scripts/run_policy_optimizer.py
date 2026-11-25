#!/usr/bin/env python3
"""
scripts/run_policy_optimizer.py
CLI runner for MIL 2.0 Phase 9 — 100,000-Path Micro-Capital Execution Policy Optimizer
and Cross-Asset & Sector Spillover Graph builder.
"""

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)

from src.quant.policy_optimizer import run_policy_optimization
from src.quant.spillover_graph import build_spillover_graph


def main():
    parser = argparse.ArgumentParser(description="MIL 2.0 Phase 9 Policy Optimizer & Spillover Graph CLI")
    parser.add_argument("--n-paths", type=int, default=100000, help="Bootstrap paths per HMM regime (default: 100000)")
    parser.add_argument("--skip-spillover", action="store_true", help="Skip spillover graph build")
    args = parser.parse_args()

    if not args.skip_spillover:
        sp = build_spillover_graph()
        print(
            f"[SpilloverGraph] Contagion Index: {sp['systemic_contagion_index']}/100 "
            f"({sp['contagion_regime']}), Estimator: {sp['estimator']}"
        )

    res = run_policy_optimization(n_paths=args.n_paths)
    print(f"[PolicyOptimizer] Completed {res['n_paths_per_regime']:,}-path calibration across 3 HMM regimes.")


if __name__ == "__main__":
    main()
