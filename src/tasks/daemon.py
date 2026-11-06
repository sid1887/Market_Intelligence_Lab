"""
src/tasks/daemon.py

Market Intelligence Lab — Autonomous Platform EOD & Telemetry Daemon.
Runs inside FastAPI's startup lifecycle (lifespan) as an asynchronous background worker.

Responsibilities:
1. Daily EOD Schedule (Every Trading Day at 16:30 IST / if >16:15 IST):
   - Confirms active NSE trading day via TradingCalendar.
   - Ingests today's final settlement quotes for universe equities into ohlcv_daily.
   - Calculates daily returns and updates quant_factors_daily.
   - Advances settled session in supervisor_state.
2. Intraday Telemetry Loop (Every 15 Minutes):
   - Refreshes macro indicators (USD/INR, Brent Crude, 10Y yields) into macro_telemetry_cache.
   - Scrapes headlines for universe equities and logs sentiment to equity_news_feed.
3. Hourly Supervisor Health Check:
   - Evaluates system health invariants via SupervisorStateMachine.
   - Persists health audit telemetry into supervisor_telemetry_ledger.
"""

import os
import sys
import json
import asyncio
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from src.storage.database import DatabaseManager
from src.quant.calendar import is_trading_session, add_trading_sessions
from src.supervisor.state_machine import SupervisorStateMachine
from src.client.macro_client import MacroClient
from src.client.news_client import NewsClient, NewsImpactEngine
from src.quant.factor_pipeline import FactorPipeline

logger = logging.getLogger("autonomous_daemon")

IST = timezone(timedelta(hours=5, minutes=30))


class AutonomousPlatformDaemon:
    """Autonomous background daemon executing EOD settlement, telemetry loops, and supervisor auditing."""

    def __init__(self, db_path: str = "data/market_lab.db"):
        self.db_path = db_path
        self.db = DatabaseManager(db_path)
        self.supervisor = SupervisorStateMachine(self.db)
        self.macro_client = MacroClient()
        self.news_client = NewsClient(self.db)
        self.news_engine = NewsImpactEngine()
        self.pipeline = FactorPipeline()
        
        self.is_running = False
        self.started_at: Optional[str] = None
        self.last_eod_date: Optional[str] = None
        self.last_telemetry_at: Optional[datetime] = None
        self.last_supervisor_check_at: Optional[datetime] = None

    def _get_ist_now(self) -> datetime:
        return datetime.now(IST)

    async def start(self) -> None:
        """Main autonomous execution loop."""
        self.is_running = True
        self.started_at = datetime.now(timezone.utc).isoformat()
        logger.info("Autonomous Platform Daemon started.")

        # Immediate startup pass
        try:
            await self.check_and_run_eod_settlement()
            await self.run_intraday_telemetry()
            await self.run_supervisor_health_check()
        except Exception as e:
            logger.error(f"Error in initial daemon startup pass: {e}")

        while self.is_running:
            try:
                now_ist = self._get_ist_now()

                # 1. EOD check every 60 seconds
                await self.check_and_run_eod_settlement()

                # 2. Intraday telemetry every 15 minutes (900 seconds)
                if not self.last_telemetry_at or (datetime.now(timezone.utc) - self.last_telemetry_at).total_seconds() >= 900:
                    await self.run_intraday_telemetry()

                # 3. Hourly supervisor check every 60 minutes (3600 seconds)
                if not self.last_supervisor_check_at or (datetime.now(timezone.utc) - self.last_supervisor_check_at).total_seconds() >= 3600:
                    await self.run_supervisor_health_check()

            except asyncio.CancelledError:
                logger.info("Autonomous Platform Daemon received cancel signal.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in daemon loop: {e}")

            # Sleep 30 seconds between loop checks
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break

        self.is_running = False
        logger.info("Autonomous Platform Daemon stopped.")

    def stop(self) -> None:
        self.is_running = False

    async def check_and_run_eod_settlement(self) -> None:
        """Checks if today's EOD settlement is required and triggers pipeline update."""
        now_ist = self._get_ist_now()
        today_str = now_ist.strftime("%Y-%m-%d")

        # Must be active NSE trading day
        if not is_trading_session(today_str):
            return

        # Must be past market close (16:15 IST)
        if now_ist.hour < 16 or (now_ist.hour == 16 and now_ist.minute < 15):
            return

        if self.last_eod_date == today_str:
            return

        # Check if database already has settled records for today
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT COUNT(DISTINCT symbol) FROM ohlcv_daily WHERE trading_date = ?", (today_str,))
            cnt = cur.fetchone()[0]

        if cnt >= 150:
            # Already populated for today
            self.last_eod_date = today_str
            return

        logger.info(f"Triggering Autonomous EOD Settlement Ingestion for {today_str}...")

        # Run settlement ingestion in threadpool to avoid blocking event loop
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._execute_eod_pipeline, today_str)
        self.last_eod_date = today_str

    def _execute_eod_pipeline(self, target_date: str) -> None:
        """Ingests settlement prices and recomputes factors for target_date."""
        try:
            logger.info(f"Running FactorPipeline for session {target_date}...")
            res = self.pipeline.run_universe_pipeline(start_date=target_date, end_date=target_date)
            logger.info(f"EOD pipeline completed for {target_date}: {res['total_factors_upserted']} factor rows.")
            
            # Log telemetry
            self.supervisor.log_telemetry(
                metric_name="EOD_SETTLEMENT_ADVANCE",
                metric_value=float(res.get("total_factors_upserted", 0)),
                threshold_breached=False,
                severity="INFO",
                message=f"Autonomous EOD daemon successfully advanced settlement to {target_date}.",
                context={"session_date": target_date, "factors_upserted": res.get("total_factors_upserted", 0)}
            )
        except Exception as e:
            logger.error(f"Failed to execute EOD pipeline: {e}")

    async def run_intraday_telemetry(self) -> None:
        """Pulls macro telemetry and news headlines."""
        self.last_telemetry_at = datetime.now(timezone.utc)
        try:
            # 1. Macro telemetry
            macro_data = self.macro_client.get_macro_telemetry()
            logger.info(f"Refreshed macro telemetry ({len(macro_data.get('indicators', []))} indicators).")

            # 2. News headlines
            top_symbols = ["BSE", "CDSL", "TCS", "INFY", "SUZLON", "RELIANCE"]
            for sym in top_symbols:
                try:
                    articles = self.news_client.fetch_latest_news(sym, limit=3)
                    if articles:
                        self.news_client.ingest_news_batch(articles, source=f"daemon_rss_{sym}")
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"Intraday telemetry refresh partial: {e}")

    async def run_supervisor_health_check(self) -> None:
        """Executes hourly supervisor invariants check."""
        self.last_supervisor_check_at = datetime.now(timezone.utc)
        try:
            health = self.supervisor.evaluate_system_health()
            status = health.get("status", "NORMAL")
            
            # Compute universe data completeness
            with self.db.get_connection() as conn:
                cur = conn.execute("SELECT MAX(trading_date) FROM quant_factors_daily;")
                latest_date = cur.fetchone()[0]
                cur.execute("""
                    SELECT 
                        COUNT(DISTINCT q.symbol) as total,
                        COUNT(DISTINCT CASE WHEN q.roe_pct IS NOT NULL AND (q.debt_to_equity IS NOT NULL OR sm.sector LIKE '%financial%' OR sm.sector LIKE '%bank%') THEN q.symbol END) as valid
                    FROM quant_factors_daily q
                    JOIN securities_master sm ON q.symbol = sm.symbol
                    WHERE q.trading_date = ?;
                """, (latest_date,))
                r = cur.fetchone()
                total = r["total"] if r else 180
                valid = r["valid"] if r else 0
                health_pct = round((valid / total) * 100, 1) if total > 0 else 0.0

            self.supervisor.log_telemetry(
                metric_name="UNIVERSE_DATA_HEALTH",
                metric_value=health_pct,
                threshold_breached=(health_pct < 80.0),
                severity="WARNING" if health_pct < 80.0 else "INFO",
                message=f"Universe completeness at {health_pct}% ({valid}/{total} equities).",
                context={"session": latest_date, "total": total, "valid": valid}
            )
            logger.info(f"Hourly Supervisor Health Check: State={self.supervisor.get_state().get('current_state')} | Completeness={health_pct}%")

        except Exception as e:
            logger.error(f"Error during supervisor health check: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive real-time supervisor and daemon status."""
        state_dict = self.supervisor.get_state()
        
        with self.db.get_connection() as conn:
            # Latest settled session
            cur = conn.execute("SELECT MAX(trading_date) FROM ohlcv_daily WHERE data_status = 'final_settled';")
            row = cur.fetchone()
            latest_settled = row[0] if row and row[0] else "2026-11-05"

            # Universe completeness
            cur = conn.execute("""
                SELECT 
                    COUNT(DISTINCT sm.symbol) as total_active,
                    COUNT(DISTINCT CASE WHEN q.roe_pct IS NOT NULL THEN q.symbol END) as with_fundamentals
                FROM securities_master sm
                LEFT JOIN (SELECT symbol, roe_pct FROM quant_factors_daily WHERE trading_date = ?) q ON sm.symbol = q.symbol
                WHERE sm.is_active = 1;
            """, (latest_settled,))
            r = cur.fetchone()
            total_active = r["total_active"] if r else 180
            with_fund = r["with_fundamentals"] if r else 0
            completeness_pct = round((with_fund / total_active) * 100, 1) if total_active > 0 else 0.0

            # Latest ingestion timestamp
            cur = conn.execute("SELECT MAX(retrieval_timestamp) FROM ohlcv_daily;")
            row = cur.fetchone()
            last_ingestion = row[0] if row and row[0] else datetime.now(timezone.utc).isoformat()

        macro_data = self.macro_client.get_macro_telemetry()

        return {
            "status": "ONLINE" if self.is_running else "IDLE",
            "supervisor_state": state_dict.get("current_state", "NORMAL"),
            "latest_settled_session": latest_settled,
            "total_active_equities": total_active,
            "universe_health_pct": completeness_pct,
            "last_ingestion_timestamp": last_ingestion,
            "daemon_started_at": self.started_at,
            "macro_indicators": macro_data.get("indicators", [])
        }


# Global singleton daemon
platform_daemon = AutonomousPlatformDaemon()

async def run_autonomous_platform_daemon():
    await platform_daemon.start()
