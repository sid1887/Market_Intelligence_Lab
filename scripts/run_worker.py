#!/usr/bin/env python3
"""
scripts/run_worker.py
Production CLI entry point for Market Intelligence Lab durable asynchronous job worker daemon.
Runs DurableJobWorker with signal handling and lease management.
"""

import os
import sys
import argparse
import logging
import signal
import time

# Ensure repository root is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.storage.database import DatabaseManager
from src.workers.runner import DurableJobWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Worker] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("MIL.WorkerCLI")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Market Intelligence Lab Durable Job Worker Daemon"
    )
    parser.add_argument(
        "--db-path",
        default=os.getenv("MIL_DB_PATH", "data/market_lab.db"),
        help="Path to SQLite database (default: data/market_lab.db)"
    )
    parser.add_argument(
        "--worker-id",
        default=None,
        help="Unique identifier for this worker instance (default: worker-{pid}-{random})"
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="Interval in seconds between lease claim attempts when queue is idle (default: 1.0s)"
    )
    parser.add_argument(
        "--lease-ttl",
        type=int,
        default=30,
        help="Lease duration in seconds before a running job is declared a zombie (default: 30s)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Execute at most one claimed job and exit immediately"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    logger.info(f"Connecting to database at {args.db_path}...")
    db = DatabaseManager(args.db_path)

    worker = DurableJobWorker(
        db=db,
        worker_id=args.worker_id,
        poll_interval=args.poll_interval,
        lease_ttl=args.lease_ttl
    )

    if args.once:
        logger.info(f"Single-execution mode enabled for worker [{worker.worker_id}]")
        worker._reap_expired_leases()
        job = worker._claim_next_job()
        if job:
            logger.info(f"Claimed job {job['job_id']} ({job['job_type']}). Executing...")
            worker._execute_job(job)
            logger.info(f"Job {job['job_id']} execution finished.")
        else:
            logger.info("No queued jobs available for execution.")
        return 0

    logger.info(f"Starting DurableJobWorker daemon [{worker.worker_id}]...")
    try:
        worker.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker daemon terminated cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
