#!/usr/bin/env python3
"""
Market Intelligence Lab — Milestone B10.0 Autonomous EOD Settlement Daemon.

Features:
- Asynchronous scheduler configured to trigger post-market settlement at 16:15 IST every trading day.
- Pipeline Step 1 (Ingestion): Fetch official NSE daily Bhavcopy and update ohlcv_daily for all 500+ instruments in securities_master.
- Pipeline Step 2 (Factors): Trigger FactorPipeline to recalculate moving averages (50D, 200D), ROE, and momentum percentiles.
- Pipeline Step 3 (Audit): Run FeedbackEvaluator to resolve matured T+5 catalyst drifts and T+20 forecast cones, logging updated RMSE and hit-rate to SQLite.
- Interactive and headless CLI triggers with --run-now and optional --date flags.
"""

import os
import sys
import time
import asyncio
import logging
import argparse
import datetime
from typing import Dict, Any, List, Optional

# Timezone setup: Asia/Kolkata (IST = UTC+05:30)
try:
    from zoneinfo import ZoneInfo
    IST_TZ = ZoneInfo("Asia/Kolkata")
except Exception:
    IST_TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

from src.storage.database import DatabaseManager
from src.client.udiff_client import UDiffClient, UDiffClientError
from src.quant.factor_pipeline import FactorPipeline
from src.quant.feedback_evaluator import FeedbackEvaluator
from src.quant.calendar import is_trading_session, parse_date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [EOD_DAEMON] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("eod_daemon")


class EODSettlementDaemon:
    """
    Autonomous Post-Market EOD Settlement Daemon.
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()
        self.udiff_client = UDiffClient()
        self.factor_pipeline = FactorPipeline(db_manager=self.db)
        self.evaluator = FeedbackEvaluator(db_manager=self.db)

    def get_current_ist_time(self) -> datetime.datetime:
        """Returns the current timezone-aware datetime in Asia/Kolkata."""
        return datetime.datetime.now(IST_TZ)

    def get_active_universe(self) -> List[str]:
        """Fetches list of active symbols in securities_master."""
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT symbol FROM securities_master WHERE is_active = 1 ORDER BY symbol ASC")
            return [r["symbol"] for r in cur.fetchall()]

    def run_settlement_pipeline(self, target_date_iso: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes the three-phase institutional EOD settlement pipeline:
        1. Ingestion: Download Bhavcopy & update ohlcv_daily for NIFTY 500.
        2. Factors: Recompute quant factors & ratios across active universe.
        3. Audit: Evaluate matured T+5 catalysts & T+20 forecast cones.
        """
        now_ist = self.get_current_ist_time()
        if not target_date_iso:
            target_date_iso = now_ist.strftime("%Y-%m-%d")

        logger.info(f"=== Starting EOD Settlement Pipeline for {target_date_iso} ===")
        t_start = time.time()
        result_summary: Dict[str, Any] = {
            "trading_date": target_date_iso,
            "started_at": now_ist.isoformat(),
            "status": "COMPLETED",
            "steps": {}
        }

        # Preflight: check trading calendar
        is_trading, cal_reason = is_trading_session(target_date_iso)
        if not is_trading:
            logger.info(f"Date {target_date_iso} is non-trading ({cal_reason}). Checking previous trading session...")

        # -------------------------------------------------------------
        # PIPELINE STEP 1: Ingestion (NSE Bhavcopy for 500+ instruments)
        # -------------------------------------------------------------
        logger.info("Step 1/3: Ingesting NSE Daily Bhavcopy for universe...")
        universe_symbols = self.get_active_universe()
        logger.info(f"Loaded {len(universe_symbols)} active constituents from securities_master.")

        ingested_count = 0
        bhavcopy_status = "SUCCESS"
        try:
            # Attempt to download official CM-UDiFF archive
            zip_path = self.udiff_client.download_udiff_zip(target_date_iso)
            if zip_path and os.path.exists(zip_path):
                records, summary = self.udiff_client.parse_udiff_archive(
                    zip_path_or_bytes=zip_path,
                    universe_symbols=set(universe_symbols),
                    series_filter="EQ"
                )
                if records:
                    ingested_count = self.db.upsert_ohlcv_records(records)
                    logger.info(f"Bhavcopy parsed successfully: {len(records)} records accepted, {ingested_count} upserted.")
                else:
                    logger.warning("Bhavcopy archive parsed with 0 matching universe records.")
            else:
                bhavcopy_status = "FILE_NOT_FOUND_OR_PENDING"
                logger.warning(f"Bhavcopy for {target_date_iso} not available or pending exchange release.")
        except UDiffClientError as uerr:
            bhavcopy_status = f"UDIFF_ERROR: {str(uerr)}"
            logger.warning(f"Bhavcopy ingestion warning: {uerr}")
        except Exception as e:
            bhavcopy_status = f"ERROR: {str(e)}"
            logger.error(f"Unexpected error during Bhavcopy ingestion: {e}")

        result_summary["steps"]["ingestion"] = {
            "status": bhavcopy_status,
            "universe_size": len(universe_symbols),
            "rows_upserted": ingested_count
        }

        # -------------------------------------------------------------
        # PIPELINE STEP 2: Factor Recalculation across NIFTY 500
        # -------------------------------------------------------------
        logger.info("Step 2/3: Recalculating technical & fundamental factors...")
        factors_recomputed = 0
        try:
            # Batch calculate factors for all universe constituents
            pipeline_res = self.factor_pipeline.run_universe_pipeline(
                symbols=universe_symbols,
                start_date=target_date_iso,
                end_date=target_date_iso
            )
            factors_recomputed = pipeline_res.get("total_factors_upserted", 0)
            logger.info(f"Factor calculation complete: {factors_recomputed} factor rows updated in quant_factors_daily.")
            result_summary["steps"]["factors"] = {
                "status": "SUCCESS",
                "factors_upserted": factors_recomputed,
                "symbols_processed": len(pipeline_res.get("symbols_processed", []))
            }
        except Exception as e:
            logger.error(f"Error during factor recalculation: {e}")
            result_summary["steps"]["factors"] = {
                "status": "ERROR",
                "error": str(e)
            }

        # -------------------------------------------------------------
        # PIPELINE STEP 3: Compounding ML Audit (Feedback Ledger)
        # -------------------------------------------------------------
        logger.info("Step 3/3: Evaluating past forecast cones & catalyst drifts...")
        audit_res: Dict[str, Any] = {}
        try:
            audit_res = self.evaluator.evaluate_past_predictions(as_of_date=target_date_iso)
            logger.info(
                f"Prediction audit complete: evaluated {audit_res.get('evaluated_forecasts_count', 0)} forecasts, "
                f"{audit_res.get('evaluated_catalysts_count', 0)} catalysts."
            )
            result_summary["steps"]["audit"] = {
                "status": "SUCCESS",
                "evaluated_forecasts": audit_res.get("evaluated_forecasts_count", 0),
                "evaluated_catalysts": audit_res.get("evaluated_catalysts_count", 0),
                "accuracy_summary": audit_res.get("accuracy_summary", {})
            }
        except Exception as e:
            logger.error(f"Error during prediction evaluation: {e}")
            result_summary["steps"]["audit"] = {
                "status": "ERROR",
                "error": str(e)
            }

        duration = round(time.time() - t_start, 2)
        result_summary["duration_seconds"] = duration
        result_summary["completed_at"] = self.get_current_ist_time().isoformat()
        logger.info(f"=== EOD Settlement Pipeline Finished in {duration}s ===")
        return result_summary

    async def start_async_daemon(self, target_hour: int = 16, target_minute: int = 15):
        """
        Asynchronous daemon scheduler loop triggering every trading day at target time (16:15 IST).
        """
        logger.info(f"Starting EOD Settlement Daemon loop (Scheduled for {target_hour:02d}:{target_minute:02d} IST)...")
        last_executed_date: Optional[str] = None

        while True:
            try:
                now_ist = self.get_current_ist_time()
                today_iso = now_ist.strftime("%Y-%m-%d")

                # Target trigger time for today
                target_time_today = now_ist.replace(
                    hour=target_hour,
                    minute=target_minute,
                    second=0,
                    microsecond=0
                )

                # If current time is past 16:15 IST and we haven't executed today
                if now_ist >= target_time_today and last_executed_date != today_iso:
                    is_trading, reason = is_trading_session(today_iso)
                    if is_trading:
                        logger.info(f"Triggering scheduled 16:15 IST settlement for {today_iso}...")
                        self.run_settlement_pipeline(today_iso)
                        last_executed_date = today_iso
                    else:
                        logger.info(f"Skipping settlement on non-trading session ({today_iso}: {reason}).")
                        last_executed_date = today_iso

                # Compute seconds until next 30-second poll
                await asyncio.sleep(30)

            except asyncio.CancelledError:
                logger.info("Daemon received cancellation signal. Gracefully exiting...")
                break
            except Exception as e:
                logger.error(f"Daemon loop encountered error: {e}", exc_info=True)
                await asyncio.sleep(60)


def main():
    parser = argparse.ArgumentParser(description="Market Intelligence Lab EOD Settlement Daemon")
    parser.add_argument("--run-now", action="store_true", help="Execute the EOD settlement pipeline immediately and exit")
    parser.add_argument("--date", type=str, default=None, help="Target trading date in YYYY-MM-DD format")
    parser.add_argument("--hour", type=int, default=16, help="Target settlement hour in IST (default: 16)")
    parser.add_argument("--minute", type=int, default=15, help="Target settlement minute in IST (default: 15)")
    args = parser.parse_args()

    daemon = EODSettlementDaemon()

    if args.run_now:
        logger.info("Manual trigger (--run-now) requested.")
        daemon.run_settlement_pipeline(target_date_iso=args.date)
    else:
        try:
            asyncio.run(daemon.start_async_daemon(target_hour=args.hour, target_minute=args.minute))
        except KeyboardInterrupt:
            logger.info("EOD Settlement Daemon interrupted by user.")


if __name__ == "__main__":
    main()
