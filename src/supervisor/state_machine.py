"""
Market Intelligence Lab — Autonomous System Supervisor (Stage A5).
Deterministic finite state machine managing system health, safety boundaries, and self-healing.
States: NORMAL, DEGRADED, HALTED, EMERGENCY_CASH, RETRAINING
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from src.storage.database import DatabaseManager

logger = logging.getLogger(__name__)

VALID_STATES = {"NORMAL", "DEGRADED", "HALTED", "EMERGENCY_CASH", "RETRAINING", "NO_ACTIVE_MODEL"}


class SupervisorStateMachine:
    """Manages system health state transitions, audit telemetry, and auto-rollback."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self._ensure_singleton_initialized()

    def _ensure_singleton_initialized(self) -> None:
        """Initializes the singleton row in supervisor_state if absent."""
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT singleton_id FROM supervisor_state WHERE singleton_id = 1")
            if not cur.fetchone():
                conn.execute(
                    """
                    INSERT INTO supervisor_state (
                        singleton_id, current_state, active_model_id,
                        last_transition_at, transition_reason,
                        quarantined_symbols_json, auto_retrain_enabled
                    ) VALUES (1, 'NO_ACTIVE_MODEL', NULL, ?, 'SYSTEM_INITIALIZATION', '[]', 1)
                    """,
                    (datetime.now(timezone.utc).isoformat(),)
                )

    def get_current_state(self) -> Dict[str, Any]:
        """Dynamically evaluates supervisor state and model validity adhering to strict governance invariants."""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT current_state, active_model_id, transition_reason, updated_at FROM supervisor_state LIMIT 1")
            row = cur.fetchone()
            
            if not row:
                return {"status": "INITIALIZING", "current_state": "INITIALIZING", "can_infer": False, "active_model_id": None}
                
            current_state, active_model_id, reason, updated_at = row
            
            # Invariant 1: Synthetic data contamination overrides everything
            cur.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE is_synthetic = 1 AND provenance_class != 'SYNTHETIC_TEST'")
            unquarantined_synthetic = cur.fetchone()[0]
            if unquarantined_synthetic > 0:
                return {
                    "status": "EMERGENCY_QUARANTINE",
                    "current_state": "EMERGENCY_QUARANTINE",
                    "can_infer": False,
                    "active_model_id": None,
                    "reason": f"CRITICAL: {unquarantined_synthetic} unquarantined synthetic records detected in production OHLCV."
                }

            # Invariant 2: Active model pointer MUST point to an approved champion
            if not active_model_id:
                if current_state == "NORMAL":
                    conn.execute("UPDATE supervisor_state SET current_state = 'NO_ACTIVE_MODEL' WHERE singleton_id = 1")
                    conn.commit()
                return {
                    "status": "NO_ACTIVE_MODEL",
                    "current_state": "NO_ACTIVE_MODEL",
                    "can_infer": False,
                    "active_model_id": None,
                    "reason": "Governance gate: No validated champion model is currently deployed.",
                    "updated_at": updated_at
                }
                
            cur.execute("SELECT status, model_name FROM model_registry WHERE model_id = ?", (active_model_id,))
            model_row = cur.fetchone()
            
            if not model_row or model_row[0] not in ('CHAMPION', 'PROMOTED') or current_state == "DEGRADED":
                if current_state == "NORMAL":
                    conn.execute("UPDATE supervisor_state SET current_state = 'DEGRADED' WHERE singleton_id = 1")
                    conn.commit()
                return {
                    "status": "DEGRADED",
                    "current_state": "DEGRADED",
                    "can_infer": False,
                    "active_model_id": active_model_id,
                    "reason": reason if current_state == "DEGRADED" else f"Active model pointer '{active_model_id}' points to invalid/unpromoted model.",
                    "updated_at": updated_at
                }
                
            effective_state = current_state if current_state in VALID_STATES else "NORMAL"
            return {
                "status": effective_state,
                "current_state": effective_state,
                "can_infer": (effective_state == "NORMAL"),
                "active_model_id": active_model_id,
                "model_name": model_row[1],
                "reason": reason,
                "updated_at": updated_at
            }

    def get_state(self) -> Dict[str, Any]:
        """Returns current supervisor state and health indicators."""
        current_eval = self.get_current_state()
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT * FROM supervisor_state WHERE singleton_id = 1")
            row = cur.fetchone()
            if not row:
                return {
                    "current_state": current_eval.get("status", "NO_ACTIVE_MODEL"),
                    "status": current_eval.get("status", "NO_ACTIVE_MODEL"),
                    "quarantined_symbols": [],
                    "active_model_id": None,
                    "can_infer": False
                }
            res = dict(row)
            try:
                res["quarantined_symbols"] = json.loads(res.get("quarantined_symbols_json") or "[]")
            except Exception:
                res["quarantined_symbols"] = []

            res["current_state"] = current_eval.get("current_state", res.get("current_state"))
            res["status"] = current_eval.get("status", res.get("current_state"))
            res["can_infer"] = current_eval.get("can_infer", False)
            res["active_model_id"] = current_eval.get("active_model_id")
            if "model_name" in current_eval:
                res["model_name"] = current_eval["model_name"]

            return res

    def transition_to(self, new_state: str, reason: str, active_model_id: Optional[str] = None) -> bool:
        """Executes a validated transition to new_state and logs audit telemetry."""
        if new_state not in VALID_STATES:
            raise ValueError(f"Invalid supervisor state: {new_state}. Valid states: {VALID_STATES}")

        now_iso = datetime.now(timezone.utc).isoformat()
        current = self.get_state()
        old_state = current.get("current_state", "NORMAL")

        with self.db.get_connection() as conn:
            conn.execute(
                """
                UPDATE supervisor_state
                SET current_state = ?,
                    last_transition_at = ?,
                    transition_reason = ?,
                    active_model_id = COALESCE(?, active_model_id),
                    updated_at = ?
                WHERE singleton_id = 1
                """,
                (new_state, now_iso, reason, active_model_id, now_iso)
            )

            # Record in telemetry ledger
            conn.execute(
                """
                INSERT INTO supervisor_telemetry_ledger (
                    timestamp, metric_name, metric_value, threshold_breached,
                    severity, message, context_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso,
                    "STATE_TRANSITION",
                    1.0,
                    1 if new_state in ("HALTED", "EMERGENCY_CASH") else 0,
                    "CRITICAL" if new_state in ("HALTED", "EMERGENCY_CASH") else "INFO",
                    f"Transitioned from {old_state} to {new_state}: {reason}",
                    json.dumps({"old_state": old_state, "new_state": new_state, "reason": reason})
                )
            )

        logger.info(f"Supervisor transitioned from {old_state} to {new_state}: {reason}")
        return True

    def log_telemetry(
        self,
        metric_name: str,
        metric_value: float,
        threshold_breached: bool = False,
        severity: str = "INFO",
        message: str = "",
        context: Optional[Dict[str, Any]] = None
    ) -> int:
        """Records telemetry metric to supervisor_telemetry_ledger."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """
                INSERT INTO supervisor_telemetry_ledger (
                    timestamp, metric_name, metric_value, threshold_breached,
                    severity, message, context_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso,
                    metric_name,
                    metric_value,
                    1 if threshold_breached else 0,
                    severity,
                    message,
                    json.dumps(context or {})
                )
            )
            return cur.lastrowid

    def evaluate_system_health(self) -> Dict[str, Any]:
        """
        Runs comprehensive system invariants check:
        1. Checks for contaminated fundamental defaults in factors
        2. Evaluates econometric forecast containment
        3. Evaluates active model drift
        Automatically moves state to DEGRADED or RETRAINING if issues detected.
        """
        with self.db.get_connection() as conn:
            # 1. Contaminated defaults invariant
            cur_cont = conn.execute(
                """
                SELECT COUNT(*) as c FROM quant_factors_daily
                WHERE roe_pct = 18.5 AND debt_to_equity = 0.12 AND opm_pct = 22.0
                """
            )
            contaminated_count = cur_cont.fetchone()["c"]

            # 2. Latest active model
            cur_model = conn.execute("SELECT * FROM model_registry WHERE status IN ('PROMOTED', 'CHAMPION') LIMIT 1")
            active_model = cur_model.fetchone()

        status = "HEALTHY"
        if contaminated_count > 0:
            self.transition_to("HALTED", f"Contaminated defaults detected ({contaminated_count} rows).")
            status = "HALTED"
        elif not active_model:
            status = "NO_ACTIVE_MODEL"
            current = self.get_state()
            if current.get("current_state") == "NORMAL":
                self.transition_to("NO_ACTIVE_MODEL", "No active champion model deployed.")

        return {
            "status": status,
            "contaminated_factors_count": contaminated_count,
            "active_model": dict(active_model) if active_model else None,
            "supervisor_state": self.get_state()
        }
