"""
src/workers/dispatcher.py
Dispatches execution to domain managers while feeding granular event telemetry to the worker.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from src.storage.database import DatabaseManager

logger = logging.getLogger("MIL.Dispatcher")


class TaskDispatcher:
    def __init__(self, db: DatabaseManager, worker):
        self.db = db
        self.worker = worker

    def dispatch(self, job_id: str, job_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if job_type == "UNIVERSE_EOD":
            return self._run_universe_eod(job_id, payload)
        elif job_type == "MODEL_TOURNAMENT":
            return self._run_model_tournament(job_id, payload)
        elif job_type == "MULTI_HORIZON_TOURNAMENT":
            return self._run_multi_horizon_tournament(job_id, payload)
        elif job_type == "GENERATE_REBALANCE_PROPOSAL":
            return self._run_generate_rebalance_proposal(job_id, payload)
        elif job_type == "FACTOR_RECOMPUTE":
            return self._run_factor_recompute(job_id, payload)
        elif job_type in ("EXECUTE_HISTORICAL_BACKFILL_2020_2024", "HISTORICAL_BACKFILL"):
            return self._run_historical_backfill(job_id, payload)
        else:
            raise ValueError(f"Unsupported job_type: {job_type}")

    def _run_universe_eod(self, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        from src.pipeline.universe_ingestion import UniverseIngestionManager
        target_date = payload.get("target_date")

        manager = UniverseIngestionManager(self.db)
        symbols = manager.get_active_universe()
        total_syms = len(symbols)

        # 1. Check for existing intermediate checkpoint in job_checkpoints
        start_idx = 0
        persisted_bars = 0
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT cursor_json FROM job_checkpoints
                WHERE job_id = ? AND stage = 'INGESTING_SYMBOLS' AND checkpoint_key = 'RESUME_INDEX'
                ORDER BY created_at DESC LIMIT 1
            """, (job_id,))
            chk_row = cur.fetchone()
            if chk_row:
                try:
                    chk_str = chk_row[0] if isinstance(chk_row, tuple) else chk_row["cursor_json"]
                    chk_data = json.loads(chk_str)
                    last_idx = chk_data.get("last_index", -1)
                    persisted_bars = chk_data.get("bars_persisted", 0)
                    if 0 <= last_idx < total_syms - 1:
                        start_idx = last_idx + 1
                        logger.info(
                            f"Job {job_id}: Resuming from checkpoint at index {start_idx} "
                            f"(last symbol: {chk_data.get('last_symbol')})"
                        )
                except Exception as e:
                    logger.warning(f"Failed to parse checkpoint for job {job_id}: {e}")

        self.worker.emit_progress(
            job_id,
            "INITIALIZED" if start_idx == 0 else "RESUMED_FROM_CHECKPOINT",
            start_idx,
            total_syms,
            {"target_date": target_date, "resumed_index": start_idx}
        )

        for idx in range(start_idx, total_syms):
            sym = symbols[idx]
            bars = manager.fetch_and_persist_symbol(sym, target_date)
            persisted_bars += len(bars)

            if (idx + 1) % 10 == 0 or (idx + 1) == total_syms:
                self.worker.emit_progress(
                    job_id,
                    "INGESTING_SYMBOLS",
                    idx + 1,
                    total_syms,
                    {"current_symbol": sym, "bars_persisted": persisted_bars}
                )
                now_iso = datetime.now(timezone.utc).isoformat()
                with self.db.get_connection() as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO job_checkpoints (checkpoint_id, job_id, stage, checkpoint_key, cursor_json, created_at)
                        VALUES (?, ?, 'INGESTING_SYMBOLS', 'RESUME_INDEX', ?, ?)
                    """, (
                        f"{job_id}_chk",
                        job_id,
                        json.dumps({
                            "last_index": idx,
                            "last_symbol": sym,
                            "processed_count": idx + 1,
                            "bars_persisted": persisted_bars
                        }),
                        now_iso
                    ))
                    conn.commit()

        # Factor execution
        self.worker.emit_progress(job_id, "COMPUTING_FACTORS", total_syms, total_syms)
        factor_count = manager.factor_pipeline.compute_universe_factors(target_date)

        # Final checkpoint update
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO job_checkpoints (checkpoint_id, job_id, stage, checkpoint_key, cursor_json, created_at)
                VALUES (?, ?, 'COMPLETED', 'SUMMARY', ?, ?)
            """, (
                f"{job_id}_chk",
                job_id,
                json.dumps({
                    "status": "COMPLETED",
                    "symbols_processed": total_syms,
                    "bars_persisted": persisted_bars,
                    "factors_computed": factor_count
                }),
                now_iso
            ))
            conn.commit()

        return {
            "target_date": target_date,
            "symbols_processed": total_syms,
            "bars_persisted": persisted_bars,
            "factors_computed": factor_count
        }

    def _run_model_tournament(self, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        from src.ml.training.tournament import run_purged_walk_forward_tournament
        from src.ml.registry.manager import ModelRegistryManager

        registry_manager = ModelRegistryManager(self.db)

        def fold_callback(fold_idx: int, total_folds: int, metrics: Dict[str, Any]):
            self.worker.emit_progress(
                job_id,
                f"EVALUATING_FOLD_{fold_idx}",
                fold_idx,
                total_folds,
                metrics
            )

        champion_id = run_purged_walk_forward_tournament(
            self.db,
            registry_manager,
            progress_callback=fold_callback
        )

        return {
            "status": "COMPLETED",
            "champion_model_id": champion_id,
            "promoted": champion_id is not None
        }

    def _run_multi_horizon_tournament(self, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        from src.ml.training.tournament import run_multi_horizon_tournament
        from src.ml.registry.manager import ModelRegistryManager

        horizons = payload.get("horizons", [5, 20, 60])
        registry_manager = ModelRegistryManager(self.db)
        results = {}

        total_horizons = len(horizons)
        for idx, h in enumerate(horizons):
            self.worker.emit_progress(
                job_id,
                f"STARTING_TOURNAMENT_{h}D",
                idx,
                total_horizons,
                {"horizon_days": h}
            )

            def fold_cb(fold_idx: int, total_folds: int, metrics: Dict[str, Any]):
                self.worker.emit_progress(
                    job_id,
                    f"EVALUATING_HORIZON_{h}D_FOLD_{fold_idx}",
                    fold_idx,
                    total_folds,
                    metrics
                )

            champion_id = run_multi_horizon_tournament(
                self.db,
                registry_manager=registry_manager,
                horizon_days=h,
                progress_callback=fold_cb
            )
            results[f"{h}d"] = champion_id

            now_iso = datetime.now(timezone.utc).isoformat()
            with self.db.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO job_checkpoints (checkpoint_id, job_id, stage, checkpoint_key, cursor_json, created_at)
                    VALUES (?, ?, 'MULTI_HORIZON', ?, ?, ?)
                """, (
                    f"{job_id}_{h}d_chk",
                    job_id,
                    f"HORIZON_{h}D",
                    json.dumps({"horizon_days": h, "champion_model_id": champion_id}),
                    now_iso
                ))
                conn.commit()

        return {
            "status": "COMPLETED",
            "horizons_evaluated": horizons,
            "champions": results
        }

    def _run_generate_rebalance_proposal(self, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        from src.quant.rebalance_engine import RebalanceEngine
        session_date = payload.get("session_date")
        top_n = payload.get("top_n", 15)

        self.worker.emit_progress(job_id, "GENERATING_PROPOSAL", 0, 1, {"session_date": session_date})
        engine = RebalanceEngine(self.db)
        proposal = engine.generate_daily_rebalance_proposal(session_date=session_date, top_n=top_n)
        self.worker.emit_progress(job_id, "PROPOSAL_GENERATED", 1, 1, {"proposal_id": proposal["proposal_id"]})

        return proposal

    def _run_factor_recompute(self, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        from src.quant.factor_pipeline import FactorPipeline
        pipeline = FactorPipeline(self.db)
        date = payload.get("trading_date")
        count = pipeline.compute_universe_factors(date)
        return {"trading_date": date, "factors_computed": count}

    def _run_historical_backfill(self, job_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes chunked historical backfill (2020-2024) with checkpoint matrix tracking,
        cancellation / pause hooks, and SSE progress telemetry.
        """
        from src.data.historical_backfill import HistoricalBackfillCoordinator

        start_year = payload.get("start_year", 2020)
        end_year = payload.get("end_year", 2024)
        end_month = payload.get("end_month", 10)
        batch_size = payload.get("batch_size_months", 20)
        symbols = payload.get("symbols", None)

        coordinator = HistoricalBackfillCoordinator(self.db)

        # 1. Ensure checkpoint matrix is initialized
        stats = coordinator.get_checkpoint_stats()
        if stats["total_work_units"] == 0:
            coordinator.initialize_checkpoint_matrix(
                symbols=symbols,
                start_year=start_year,
                end_year=end_year,
                end_month=end_month
            )
            stats = coordinator.get_checkpoint_stats()

        self.worker.emit_progress(
            job_id,
            "INITIALIZED",
            stats["completed_units"],
            stats["total_work_units"],
            stats
        )

        # 2. Iterate batches while monitoring cancellation/pause hooks
        max_batches = payload.get("max_batches", 500)
        batch_idx = 0

        while batch_idx < max_batches:
            batch_idx += 1

            # Check if job was cancelled or paused
            with self.db.get_connection() as conn:
                cur = conn.execute("SELECT status FROM job_runs WHERE job_id = ?", (job_id,))
                row = cur.fetchone()
                job_status = row[0] if row else "RUNNING"

            if job_status in ("CANCELLED", "PAUSED"):
                now_iso = datetime.now(timezone.utc).isoformat()
                with self.db.get_connection() as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO job_checkpoints (
                            checkpoint_id, job_id, stage, checkpoint_key, cursor_json, created_at
                        ) VALUES (?, ?, 'HISTORICAL_BACKFILL', 'PAUSE_HOOK', ?, ?)
                    """, (
                        f"{job_id}_paused_chk",
                        job_id,
                        json.dumps({"status": job_status, "stats": stats}),
                        now_iso
                    ))
                    conn.commit()
                return {"status": job_status, "job_id": job_id, "stats": stats}

            # Execute batch
            res = coordinator.execute_backfill_batch(
                batch_size_months=batch_size,
                job_id=job_id
            )
            stats = res["stats"]

            # Save progress checkpoint
            now_iso = datetime.now(timezone.utc).isoformat()
            with self.db.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO job_checkpoints (
                        checkpoint_id, job_id, stage, checkpoint_key, cursor_json, created_at
                    ) VALUES (?, ?, 'HISTORICAL_BACKFILL', 'RESUME_MATRIX', ?, ?)
                """, (
                    f"{job_id}_progress_chk",
                    job_id,
                    json.dumps(stats),
                    now_iso
                ))
                conn.commit()

            self.worker.emit_progress(
                job_id,
                "INGESTING_HISTORICAL_MONTHS",
                stats["completed_units"],
                stats["total_work_units"],
                stats
            )

            if res["status"] == "IDLE" or res["processed_chunks"] == 0:
                break

        return {
            "status": "COMPLETED",
            "job_id": job_id,
            "final_stats": stats
        }

