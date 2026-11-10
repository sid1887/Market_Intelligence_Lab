#!/usr/bin/env python3
"""
scripts/run_universe_daemon.py
Entry point for the Autonomous Full-Universe Market Ingestion, Factor Continuum,
and ML Tournament Daemon.
Can be executed directly or run continuously as a systemd user service.
"""

import os
import sys
import argparse
import logging

# Ensure project root in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.tasks.universe_daemon import AutonomousUniversePipeline

def main():
    parser = argparse.ArgumentParser(description="Autonomous Market Universe Daemon")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    parser.add_argument("--batch-size", type=int, default=35, help="Symbols per download chunk")
    parser.add_argument("--poll-interval", type=int, default=1800, help="Seconds to sleep between cycles (default: 1800s)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    logger = logging.getLogger("UniverseDaemonRunner")
    logger.info(f"Starting Autonomous Universe Daemon (once={args.once}, batch_size={args.batch_size}, poll={args.poll_interval}s)")

    pipeline = AutonomousUniversePipeline(batch_size=args.batch_size)

    if args.once:
        summary = pipeline.execute_cycle()
        logger.info(f"Single cycle completed: {summary}")
    else:
        pipeline.run_forever(poll_interval_seconds=args.poll_interval)

if __name__ == "__main__":
    main()
