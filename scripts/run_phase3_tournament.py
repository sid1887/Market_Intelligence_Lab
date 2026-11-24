#!/usr/bin/env python3
"""
scripts/run_phase3_tournament.py
CLI Runner for MIL 2.0 Phase 3 Model Tournament Engine.
Runs Combinatorial Purged Cross-Validation (CPCV) and Bailey-López de Prado Deflated Sharpe Ratio (DSR)
evaluations across candidate models against the mandatory deterministic baseline.

Designed to execute on local workstation, GitHub Actions (16 GB runner), or Deepnote lake tier (5 GiB).
"""

import sys
import os
import argparse
import logging
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.database import DatabaseManager
from src.quant.ml_trainer import TwoStageTournamentRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("MIL.Phase3Tournament")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run MIL 2.0 Phase 3 Triple-Barrier & Purged CPCV Model Tournament"
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=20,
        help="Prediction & holding horizon in trading sessions (default: 20)"
    )
    parser.add_argument(
        "--n-splits",
        type=int,
        default=6,
        help="Total number of CPCV chronological splits (default: 6)"
    )
    parser.add_argument(
        "--n-test-splits",
        type=int,
        default=2,
        help="Number of test splits per combination (default: 2 -> binom(6,2)=15)"
    )
    parser.add_argument(
        "--min-meta-prob",
        type=float,
        default=0.55,
        help="Stage 2 meta-calibrator probability threshold for execution (default: 0.55)"
    )
    parser.add_argument(
        "--reference-ticket",
        type=float,
        default=5000.0,
        help="Reference order ticket size in INR for fee engine calculation (default: 5000.0)"
    )
    parser.add_argument(
        "--holdout-sessions",
        type=int,
        default=252,
        help="Number of final untouched holdout trading sessions (default: 252)"
    )
    parser.add_argument(
        "--summary-path",
        type=str,
        default="data/models/tournament_summary.json",
        help="Output path for tournament summary JSON (default: data/models/tournament_summary.json)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    logger.info("=" * 70)
    logger.info("MARKET INTELLIGENCE LAB 2.0 — PHASE 3 MODEL TOURNAMENT ENGINE")
    logger.info("=" * 70)
    logger.info(f"Configuration: Horizon={args.horizon}d | Splits={args.n_splits} | TestSplits={args.n_test_splits}")
    logger.info(f"Meta-Gating Hurdle={args.min_meta_prob:.2f} | Ref Ticket=₹{args.reference_ticket:,.2f} | Holdout={args.holdout_sessions}d")

    db = DatabaseManager()
    runner = TwoStageTournamentRunner(
        db=db,
        horizon_days=args.horizon,
        n_splits=args.n_splits,
        n_test_splits=args.n_test_splits,
        min_meta_prob=args.min_meta_prob,
        reference_ticket=args.reference_ticket,
        holdout_sessions=args.holdout_sessions,
        summary_path=args.summary_path
    )

    logger.info("Initiating dataset extraction and feature matrix preparation...")
    try:
        summary = runner.run_full_tournament()
    except Exception as e:
        logger.error(f"Tournament execution encountered error: {e}", exc_info=True)
        sys.exit(1)

    # Print Formatted Markdown Tournament Results Table
    baseline = summary.get("baseline", {})
    candidates = summary.get("candidates", [])
    champion = summary.get("champion", {})

    print("\n" + "=" * 80)
    print("PHASE 3 TOURNAMENT EXECUTION REPORT SUMMARY")
    print("=" * 80)
    print(f"Run ID:                {summary.get('run_id')}")
    print(f"CPCV Combinations:     {summary.get('cpcv_combinations')} splits (5 complete out-of-sample paths)")
    print(f"Holdout Net Sharpe:    {summary.get('holdout_net_sharpe')}")
    print(f"Promotion Verdict:     {summary.get('promotion_verdict')}")
    print("-" * 80)
    print(f"{'Model Name':<35} | {'Net Sharpe':<11} | {'DSR':<7} | {'SR* Hurdle':<11} | {'Abstention':<10} | {'Status'}")
    print("-" * 80)

    # Baseline Row
    b_name = baseline.get("name", "Baseline (Momentum+LowVol+PIT)")
    b_sharpe = baseline.get("mean_net_sharpe", 0.0)
    print(f"{b_name:<35} | {b_sharpe:<11.4f} | {'N/A':<7} | {'N/A':<11} | {'0.0%':<10} | BENCHMARK")

    # Candidates Rows
    for cand in candidates:
        c_name = cand.get("candidate_name")
        c_sharpe = cand.get("cpcv_mean_sharpe", 0.0)
        c_dsr = cand.get("deflated_sharpe_ratio", 0.0)
        c_star = cand.get("sharpe_star_hurdle", 0.0)
        c_abst = f"{cand.get('abstention_rate', 0.0) * 100.0:.1f}%"
        c_status = cand.get("promotion_status")
        print(f"{c_name:<35} | {c_sharpe:<11.4f} | {c_dsr:<7.4f} | {c_star:<11.4f} | {c_abst:<10} | {c_status}")

    print("=" * 80)
    print(f"Champion Selected:     {champion.get('candidate_name')} ({champion.get('promotion_status')})")
    print(f"Summary Written:       {args.summary_path}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
