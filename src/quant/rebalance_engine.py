"""
src/quant/rebalance_engine.py
Multi-Horizon Blended Composite Ranking & Automated Portfolio Rebalance Engine.
Workstream 7.3: Combines 5D, 20D, and 60D active models with transaction friction constraints.
"""

import json
import uuid
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd

from src.storage.database import DatabaseManager
from src.ml.registry.manager import ModelRegistryManager
from src.ml.features.builder import PITFeatureExtractor, FEATURE_COLUMNS

logger = logging.getLogger("MIL.Rebalance")

DEFAULT_HORIZON_WEIGHTS = {
    5: 0.20,
    20: 0.50,
    60: 0.30
}

DEFAULT_TOURNAMENT_WEIGHTS = {
    "rsi_14": 0.40,
    "volatility_20d": 0.25,
    "momentum_20d": 0.18,
    "momentum_252d": 0.07,
    "sma_ratio": 0.06,
    "fundamental": 0.04
}


def load_tournament_weights(model_summary_path: str = "data/models/tournament_summary.json") -> Dict[str, float]:
    """
    Reads overall_summary["feature_importance_pct"] from tournament_summary.json
    and normalizes weights so sum(w_i) = 1.0.
    Gracefully falls back to deterministic default weights if the file is missing or malformed:
    {
        "rsi_14": 0.40,
        "volatility_20d": 0.25,
        "momentum_20d": 0.18,
        "momentum_252d": 0.07,
        "sma_ratio": 0.06,
        "fundamental": 0.04
    }
    """
    path = Path(model_summary_path)
    if not path.exists():
        logger.warning(f"Tournament summary not found at {model_summary_path}. Falling back to default weights.")
        return DEFAULT_TOURNAMENT_WEIGHTS.copy()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        raw_weights = data.get("overall_summary", {}).get("feature_importance_pct")
        if not raw_weights or not isinstance(raw_weights, dict):
            logger.warning(f"No valid feature_importance_pct in {model_summary_path}. Using fallback defaults.")
            return DEFAULT_TOURNAMENT_WEIGHTS.copy()

        valid_weights = {k: float(v) for k, v in raw_weights.items() if isinstance(v, (int, float)) and v > 0}
        total_w = sum(valid_weights.values())
        if total_w <= 0:
            logger.warning("Sum of tournament weights is non-positive. Using fallback defaults.")
            return DEFAULT_TOURNAMENT_WEIGHTS.copy()

        normalized = {k: round(v / total_w, 4) for k, v in valid_weights.items()}
        diff = round(1.0 - sum(normalized.values()), 4)
        if diff != 0:
            max_k = max(normalized, key=normalized.get)
            normalized[max_k] = round(normalized[max_k] + diff, 4)

        return normalized
    except Exception as e:
        logger.warning(f"Failed to parse tournament summary at {model_summary_path}: {e}. Using fallback defaults.")
        return DEFAULT_TOURNAMENT_WEIGHTS.copy()

# Minimum out-of-sample Rank IC required to participate in composite allocation
MIN_VALIDATION_IC_HURDLE = 0.0150

# Transaction friction estimates (STT 10 bps, brokerage/SEBI 5 bps, slippage 5 bps)
ROUND_TRIP_FRICTION_BPS = 20.0


class RebalanceEngine:
    """Computes multi-horizon ensemble rank scores and generates rebalance trade deltas."""

    def __init__(self, db: DatabaseManager, registry_manager: Optional[ModelRegistryManager] = None):
        self.db = db
        self.registry = registry_manager or ModelRegistryManager(db)
        self.feature_extractor = PITFeatureExtractor(db)

    def get_latest_session_date(self) -> str:
        """Finds the most recent settled session date with available factor rows."""
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT MAX(trading_date) as max_date 
                FROM quant_factors_daily 
                WHERE is_orphaned = 0
            """)
            row = cur.fetchone()
            if row and row[0]:
                return str(row[0])
            cur = conn.execute("SELECT MAX(trading_date) as max_date FROM ohlcv_daily WHERE series = 'EQ'")
            row = cur.fetchone()
            return str(row[0]) if row and row[0] else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def generate_daily_rebalance_proposal(
        self,
        session_date: Optional[str] = None,
        top_n: int = 15,
        horizon_weights: Optional[Dict[int, float]] = None
    ) -> Dict[str, Any]:
        """
        Generates daily portfolio rebalance proposal:
        1. Loads active models across horizons (5, 20, 60).
        2. Computes blended multi-horizon ranking across the active universe.
        3. Identifies Top-N targets and compares against prior session holdings.
        4. Calculates turnover and projected transaction friction.
        5. Commits proposal to rebalance_proposals ledger.
        """
        if not session_date:
            session_date = self.get_latest_session_date()

        weights_cfg = horizon_weights or DEFAULT_HORIZON_WEIGHTS
        deployments = self.registry.get_horizon_deployments()

        if not deployments:
            logger.warning("No active horizon models deployed in model_horizon_deployments.")
            # Fall back to single champion model if available
            active_rec = self.registry.get_active_model_record()
            if active_rec:
                deployments = {20: active_rec}
            else:
                raise ValueError("No active machine learning models registered in system.")

        # Strict Dynamic Hurdle Gating: inspect model_horizon_deployments.validation_ic
        # Any horizon model with active_model_id is NULL or validation_ic < MIN_VALIDATION_IC_HURDLE is disarmed (w_h = 0.0)
        valid_weights: Dict[int, float] = {}
        for h, base_w in weights_cfg.items():
            dep = deployments.get(h)
            if not dep:
                valid_weights[h] = 0.0
                continue

            active_id = dep.get("active_model_id")
            val_ic = float(dep.get("validation_ic") or 0.0)

            if not active_id or val_ic < MIN_VALIDATION_IC_HURDLE:
                logger.info(
                    f"Disarmed horizon {h}D model: active_model_id={active_id}, "
                    f"validation_ic={val_ic:.4f} (Strict hurdle >= {MIN_VALIDATION_IC_HURDLE:.4f})"
                )
                valid_weights[h] = 0.0
            else:
                valid_weights[h] = float(base_w)

        total_valid_weight = sum(valid_weights.values())
        if total_valid_weight <= 0:
            raise ValueError(f"No active horizon model cleared the IC >= {MIN_VALIDATION_IC_HURDLE} governance hurdle.")

        # Renormalize active weights to sum exactly to 1.0
        norm_weights = {h: w / total_valid_weight for h, w in valid_weights.items() if w > 0}
        avail_horizons = list(norm_weights.keys())

        weights_str = ", ".join([f"{h}D: {w:.3f}" for h, w in norm_weights.items()])
        disarmed_str = ", ".join([f"{h}D: 0.0" for h, w in valid_weights.items() if w == 0])
        logger.info(f"Active Blended Weights: {{{weights_str}}}{f', Disarmed: {{{disarmed_str}}}' if disarmed_str else ''}")

        # 2. Extract point-in-time features for session_date
        feats = self.feature_extractor.extract_panel(session_date, session_date)
        if feats.empty:
            logger.warning(f"No point-in-time features for session {session_date}. Fallback to latest available.")
            prev_date = self.get_latest_session_date()
            feats = self.feature_extractor.extract_panel(prev_date, prev_date)
            session_date = prev_date

        if feats.empty:
            raise ValueError(f"Cannot extract features for session {session_date}.")

        # Ensure both raw and factor_ prefixed columns exist to match model conventions
        for c in FEATURE_COLUMNS:
            if c in feats.columns and f"factor_{c}" not in feats.columns:
                feats[f"factor_{c}"] = feats[c]

        raw_feature_cols = [c for c in FEATURE_COLUMNS if c in feats.columns]

        # 3. Predict across each active horizon model
        model_composite_parts = []
        rank_sum = np.zeros(len(feats), dtype=float)

        for h in avail_horizons:
            dep = deployments[h]
            model_id = dep["active_model_id"]
            model_obj, _ = self.registry.load_model_by_id(model_id)

            if model_obj is not None:
                try:
                    if hasattr(model_obj, "feature_names_in_"):
                        expected_cols = list(model_obj.feature_names_in_)
                        X_model = feats[expected_cols]
                    else:
                        X_model = feats[raw_feature_cols]

                    preds = model_obj.predict(X_model)
                    preds_rank = pd.Series(preds).rank(pct=True).values
                    w_h = norm_weights[h]
                    rank_sum += w_h * preds_rank
                    model_composite_parts.append(f"{h}D:{model_id[:16]}")
                except Exception as pred_err:
                    logger.warning(f"Prediction failed for model {model_id} (horizon {h}d): {pred_err}")

        if not model_composite_parts:
            raise RuntimeError("All active models failed prediction on candidate universe.")

        feats["blended_score"] = rank_sum * 100.0
        sorted_candidates = feats.sort_values(by="blended_score", ascending=False).reset_index(drop=True)

        # 4. Form Target Portfolio (Top-N equal-weighted)
        top_candidates = sorted_candidates.head(top_n)
        target_weight = round(1.0 / top_n, 4)
        holdings_after: Dict[str, float] = {
            row["symbol"]: target_weight for _, row in top_candidates.iterrows()
        }

        # 5. Fetch prior portfolio state
        holdings_before: Dict[str, float] = {}
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT holdings_after_json 
                FROM rebalance_proposals 
                WHERE session_date < ? 
                ORDER BY session_date DESC, created_at DESC 
                LIMIT 1
            """, (session_date,))
            row = cur.fetchone()
            if row and row[0]:
                try:
                    holdings_before = json.loads(row[0])
                except Exception:
                    holdings_before = {}

        # 6. Calculate Turnover & Deltas
        all_symbols = sorted(set(list(holdings_before.keys()) + list(holdings_after.keys())))
        trade_deltas: List[Dict[str, Any]] = []
        turnover_sum = 0.0

        for sym in all_symbols:
            w_before = holdings_before.get(sym, 0.0)
            w_after = holdings_after.get(sym, 0.0)
            delta = round(w_after - w_before, 4)
            turnover_sum += abs(delta)

            action = "HOLD"
            if delta > 0.001:
                action = "BUY"
            elif delta < -0.001:
                action = "SELL"

            cand_score = None
            cand_row = sorted_candidates[sorted_candidates["symbol"] == sym]
            if not cand_row.empty:
                cand_score = round(float(cand_row.iloc[0]["blended_score"]), 2)

            trade_deltas.append({
                "symbol": sym,
                "current_weight": w_before,
                "target_weight": w_after,
                "delta": delta,
                "action": action,
                "blended_score": cand_score
            })

        # Turnover percentage: half the sum of absolute delta weights
        turnover_pct = round((turnover_sum / 2.0) * 100.0, 2)
        projected_cost_bps = round((turnover_pct / 100.0) * ROUND_TRIP_FRICTION_BPS, 2)

        proposal_id = f"reb_{session_date.replace('-', '')}_{uuid.uuid4().hex[:6]}"
        model_composite_id = "BLENDED_" + "_".join(model_composite_parts)
        now_iso = datetime.now(timezone.utc).isoformat()

        # 7. Commit to rebalance_proposals ledger
        with self.db.get_connection() as conn:
            conn.execute("""
                INSERT INTO rebalance_proposals (
                    proposal_id, session_date, model_composite_id, status,
                    turnover_pct, projected_cost_bps, holdings_before_json,
                    holdings_after_json, trade_deltas_json, created_at
                ) VALUES (?, ?, ?, 'PROPOSED', ?, ?, ?, ?, ?, ?)
            """, (
                proposal_id,
                session_date,
                model_composite_id,
                turnover_pct,
                projected_cost_bps,
                json.dumps(holdings_before),
                json.dumps(holdings_after),
                json.dumps(trade_deltas),
                now_iso
            ))
            conn.commit()

        logger.info(
            f"Generated Rebalance Proposal '{proposal_id}' for {session_date}: "
            f"Turnover={turnover_pct}%, Cost={projected_cost_bps} bps, Top {top_n} assets."
        )

        return {
            "proposal_id": proposal_id,
            "session_date": session_date,
            "model_composite_id": model_composite_id,
            "status": "PROPOSED",
            "turnover_pct": turnover_pct,
            "projected_cost_bps": projected_cost_bps,
            "top_candidates": [
                {"symbol": r["symbol"], "score": round(float(r["blended_score"]), 2)}
                for _, r in top_candidates.iterrows()
            ],
            "trade_deltas": trade_deltas,
            "active_horizons": avail_horizons,
            "effective_weights": norm_weights,
            "created_at": now_iso
        }

    @staticmethod
    def load_tournament_weights(model_summary_path: str = "data/models/tournament_summary.json") -> Dict[str, float]:
        """Exposes load_tournament_weights as a method on RebalanceEngine."""
        return load_tournament_weights(model_summary_path)

    def score_candidate_universe(
        self,
        trading_date: Optional[str] = None,
        account_id: str = "paper_alpha_1",
        hysteresis_buffer: float = 5.0,
        model_summary_path: str = "data/models/tournament_summary.json"
    ) -> pd.DataFrame:
        """
        Uses dynamic tournament consensus weights to score all active universe symbols on trading_date.
        Applies turnover hysteresis (delta_hyst = 5.0) against currently held assets for account_id.
        """
        if not trading_date:
            trading_date = self.get_latest_session_date()

        weights = load_tournament_weights(model_summary_path)

        with self.db.get_connection() as conn:
            sql = """
            SELECT 
                f.symbol,
                f.trading_date,
                f.close,
                f.sma_50,
                f.sma_200,
                f.ret_20d as momentum_20d,
                f.ret_5d as momentum_5d,
                f.momentum_1y as momentum_252d,
                f.volatility_20d,
                f.rsi_14,
                CASE WHEN f.sma_200 > 0 THEN (f.sma_50 / f.sma_200) ELSE 1.0 END as sma_ratio_50_200,
                q.opm_pct as operating_margin,
                q.debt_to_equity,
                q.roe_pct,
                COALESCE(s.company_name, f.symbol) as company_name,
                COALESCE(s.sector, 'Unclassified') as sector
            FROM factors_daily f
            LEFT JOIN quant_factors_daily q ON f.symbol = q.symbol AND f.trading_date = q.trading_date
            LEFT JOIN securities_master s ON f.symbol = s.symbol
            WHERE f.trading_date = ?
              AND f.close IS NOT NULL
              AND f.close > 0
            """
            df = pd.read_sql_query(sql, conn, params=[trading_date])

            held_symbols = set()
            cur = conn.execute(
                "SELECT symbol FROM portfolio_positions WHERE account_id = ? AND quantity > 0",
                (account_id,)
            )
            for r in cur.fetchall():
                held_symbols.add(r[0])

            if not held_symbols:
                p_cur = conn.execute(
                    "SELECT holdings_after_json FROM rebalance_proposals WHERE session_date <= ? ORDER BY session_date DESC, created_at DESC LIMIT 1",
                    (trading_date,)
                )
                p_row = p_cur.fetchone()
                if p_row and p_row[0]:
                    try:
                        held_dict = json.loads(p_row[0])
                        held_symbols = set(held_dict.keys())
                    except Exception:
                        pass

        if df.empty:
            return pd.DataFrame()

        num_cols = [
            "close", "sma_50", "sma_200", "momentum_20d", "momentum_5d",
            "momentum_252d", "volatility_20d", "rsi_14", "sma_ratio_50_200",
            "operating_margin", "debt_to_equity", "roe_pct"
        ]
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        factor_ranks: Dict[str, pd.Series] = {}

        def _rank(s: pd.Series, ascending: bool = True) -> pd.Series:
            valid = s.dropna()
            if len(valid) <= 1:
                return pd.Series(50.0, index=s.index)
            r = valid.rank(pct=True, ascending=ascending) * 100.0
            return r.reindex(s.index).fillna(50.0)

        factor_ranks["rsi_14"] = _rank(df["rsi_14"], ascending=True)
        factor_ranks["volatility_20d"] = _rank(df["volatility_20d"], ascending=False)
        factor_ranks["momentum_20d"] = _rank(df["momentum_20d"], ascending=True)
        factor_ranks["momentum_252d"] = _rank(df["momentum_252d"], ascending=True)
        factor_ranks["sma_ratio_50_200"] = _rank(df["sma_ratio_50_200"], ascending=True)
        factor_ranks["sma_ratio"] = factor_ranks["sma_ratio_50_200"]
        factor_ranks["operating_margin"] = _rank(df["operating_margin"], ascending=True)
        factor_ranks["debt_to_equity"] = _rank(df["debt_to_equity"], ascending=False)
        factor_ranks["momentum_5d"] = _rank(df["momentum_5d"], ascending=True)

        fund_rank = 0.5 * _rank(df["roe_pct"], ascending=True) + 0.5 * _rank(df["operating_margin"], ascending=True)
        factor_ranks["fundamental"] = fund_rank

        raw_score = np.zeros(len(df), dtype=float)
        total_w = sum(weights.values())
        for f_name, w in weights.items():
            norm_w = w / total_w if total_w > 0 else 0.0
            rank_s = factor_ranks.get(f_name, pd.Series(50.0, index=df.index))
            raw_score += norm_w * rank_s.values

        df["raw_score"] = np.round(raw_score, 2)
        df["is_held"] = df["symbol"].isin(held_symbols)

        blended_score = raw_score.copy()
        if hysteresis_buffer > 0:
            blended_score += np.where(df["is_held"], hysteresis_buffer, 0.0)

        df["blended_score"] = np.round(blended_score, 2)

        s20 = (
            0.50 * factor_ranks["momentum_20d"] +
            0.30 * factor_ranks["rsi_14"] +
            0.20 * factor_ranks["volatility_20d"]
        )
        s60 = (
            0.40 * factor_ranks["momentum_252d"] +
            0.30 * factor_ranks["sma_ratio_50_200"] +
            0.30 * factor_ranks["operating_margin"]
        )
        df["score_20d"] = np.round(s20, 1)
        df["score_60d"] = np.round(s60, 1)

        df = df.sort_values(by="blended_score", ascending=False).reset_index(drop=True)
        df["target_allocation_pct"] = np.where(df.index < 15, round(100.0 / 15.0, 2), 0.0)

        return df

    def compute_universe_blended_scores(
        self,
        session_date: Optional[str] = None,
        account_id: str = "paper_alpha_1"
    ) -> Dict[str, Dict[str, Any]]:
        """
        Computes point-in-time multi-horizon blended scores and horizon attribution across the universe.
        Leverages dynamic tournament weights and applies turnover hysteresis for account holdings.
        """
        if not session_date:
            session_date = self.get_latest_session_date()

        candidate_df = self.score_candidate_universe(trading_date=session_date, account_id=account_id)
        if candidate_df.empty:
            return {}

        results: Dict[str, Dict[str, Any]] = {}
        for _, row in candidate_df.iterrows():
            sym = str(row["symbol"])
            target_pct = float(row.get("target_allocation_pct", 0.0))
            b_score = float(row.get("blended_score", 0.0))
            s20 = float(row.get("score_20d", 50.0))
            s60 = float(row.get("score_60d", 50.0))

            drivers = []
            if target_pct > 0:
                drivers = ["20D", "60D"]
            else:
                if s20 >= 60.0 and s60 >= 60.0:
                    drivers = ["20D", "60D"]
                elif s20 >= 60.0:
                    drivers = ["20D"]
                elif s60 >= 60.0:
                    drivers = ["60D"]

            results[sym] = {
                "blended_score": round(b_score, 2),
                "target_allocation_pct": round(target_pct, 2),
                "horizon_drivers": drivers,
                "score_20d": round(s20, 1),
                "score_60d": round(s60, 1),
                "is_rebalance_target": target_pct > 0
            }

        return results
