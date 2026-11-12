"""
src/quant/rebalance_engine.py
Multi-Horizon Blended Composite Ranking & Automated Portfolio Rebalance Engine.
Workstream 7.3: Combines 5D, 20D, and 60D active models with transaction friction constraints.
"""

import json
import math
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
    if not path.is_absolute():
        alt_path = Path(__file__).resolve().parent.parent.parent / model_summary_path
        if alt_path.exists():
            path = alt_path

    if not path.exists():
        # Dynamic fallback: check SQLite ml_training_runs for champion weights
        try:
            from src.storage.database import DatabaseManager
            db_path = Path(__file__).resolve().parent.parent.parent / "data" / "market_lab.db"
            if db_path.exists():
                db = DatabaseManager(str(db_path))
                with db.get_connection() as conn:
                    cur = conn.execute("SELECT feature_weights_json FROM ml_training_runs WHERE is_champion = 1 ORDER BY horizon_days DESC LIMIT 1")
                    row = cur.fetchone()
                    if row and row[0]:
                        fw = json.loads(row[0])
                        if fw and isinstance(fw, dict):
                            valid = {k: float(v) for k, v in fw.items() if isinstance(v, (int, float)) and v > 0}
                            total = sum(valid.values())
                            if total > 0:
                                logger.info("Loaded champion weights dynamically from ml_training_runs SQLite table.")
                                return {k: round(v / total, 4) for k, v in valid.items()}
        except Exception as e:
            logger.debug(f"SQLite champion weight lookup fallback failed: {e}")

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
        account_id: str = "paper_alpha_1",
        top_n: int = 15,
        hysteresis_buffer: float = 5.0,
        horizon_weights: Optional[Dict[int, float]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generates daily portfolio rebalance proposal with authentic account inspection,
        universe market breadth calculation, dynamic cash gating, and concrete share-level orders.
        """
        if not session_date:
            session_date = self.get_latest_session_date()

        # ---------------------------------------------------------
        # Step 1: Universe Market Breadth & Dynamic Cash Gating
        # ---------------------------------------------------------
        with self.db.get_connection() as conn:
            has_factors_daily = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='factors_daily'"
            ).fetchone()[0] > 0

            if has_factors_daily:
                row = conn.execute("""
                SELECT 
                    COUNT(*) as total_symbols,
                    SUM(CASE WHEN o.close > COALESCE(f.sma_200, q.sma_200) THEN 1 ELSE 0 END) as above_sma200
                FROM ohlcv_daily o
                LEFT JOIN factors_daily f ON o.symbol = f.symbol AND o.trading_date = f.trading_date
                LEFT JOIN quant_factors_daily q ON o.symbol = q.symbol AND o.trading_date = q.trading_date
                WHERE o.trading_date = ? AND COALESCE(f.sma_200, q.sma_200) IS NOT NULL
                """, (session_date,)).fetchone()
            else:
                row = conn.execute("""
                SELECT 
                    COUNT(*) as total_symbols,
                    SUM(CASE WHEN o.close > q.sma_200 THEN 1 ELSE 0 END) as above_sma200
                FROM ohlcv_daily o
                JOIN quant_factors_daily q ON o.symbol = q.symbol AND o.trading_date = q.trading_date
                WHERE o.trading_date = ? AND q.sma_200 IS NOT NULL
                """, (session_date,)).fetchone()

        tot_syms = row[0] if (row and row[0]) else 0
        above_sma = row[1] if (row and row[1]) else 0
        breadth_pct = float((above_sma / tot_syms) * 100.0) if tot_syms > 0 else 50.0

        if breadth_pct >= 50.0:
            target_cash_pct = 0.0
        elif breadth_pct >= 35.0:
            target_cash_pct = 20.0
        else:
            target_cash_pct = 40.0

        # Inspect account for dynamic capital sizing & fee tier
        with self.db.get_connection() as conn:
            has_accounts = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='portfolio_accounts'"
            ).fetchone()[0] > 0
            has_positions = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='portfolio_positions'"
            ).fetchone()[0] > 0

            cash_balance = 1600.0
            total_nav = 1600.0
            fee_tier = "RETAIL_MICRO"
            if has_accounts:
                acc_row = conn.execute(
                    "SELECT cash_balance, total_nav, COALESCE(fee_tier, 'RETAIL_MICRO') FROM portfolio_accounts WHERE account_id = ?",
                    (account_id,)
                ).fetchone()
                if acc_row:
                    cash_balance = float(acc_row[0])
                    total_nav = float(acc_row[1]) if acc_row[1] and float(acc_row[1]) > 0 else 1600.0
                    fee_tier = str(acc_row[2])

            pos_rows = []
            if has_positions:
                pos_rows = conn.execute("""
                SELECT p.symbol, p.quantity, p.average_entry_price, 
                       COALESCE(o.close, p.average_entry_price) as current_price
                FROM portfolio_positions p
                LEFT JOIN ohlcv_daily o ON p.symbol = o.symbol AND o.trading_date = ?
                WHERE p.account_id = ?
                """, (session_date, account_id)).fetchall()

        # Dynamic Slot Scaling (K_eff) based on account capital
        if total_nav < 3000.0:
            k_eff = min(top_n, 4)
        elif total_nav < 10000.0:
            k_eff = min(top_n, 6)
        elif total_nav < 50000.0:
            k_eff = min(top_n, 10)
        else:
            k_eff = top_n

        investable_equity = max(100.0, total_nav * (1.0 - (target_cash_pct / 100.0)))
        slot_budget = investable_equity / k_eff
        p_max = slot_budget

        # ---------------------------------------------------------
        # Step 2: Candidate Ranking via Tournament Scores + Hysteresis
        # ---------------------------------------------------------
        cand_df = self.score_candidate_universe(
            trading_date=session_date,
            account_id=account_id,
            hysteresis_buffer=hysteresis_buffer
        )
        if cand_df.empty:
            raise RuntimeError(f"Failed to score candidates for session {session_date}")

        score_col = "effective_score" if "effective_score" in cand_df.columns else "blended_score"
        cand_df = cand_df.sort_values(by=score_col, ascending=False).reset_index(drop=True)

        # Price-Affordability Gate (Whole-Share Constraint)
        affordable_candidates = []
        capital_constrained_skips = []
        for _, row in cand_df.iterrows():
            sym = str(row["symbol"])
            px = float(row.get("close") or 0.0)
            if px <= 0:
                continue
            if px <= p_max:
                affordable_candidates.append(row)
                if len(affordable_candidates) == k_eff:
                    break
            else:
                capital_constrained_skips.append({
                    "symbol": sym,
                    "close": round(px, 2),
                    "slot_budget": round(p_max, 2),
                    "reason": f"Share price ₹{px:,.2f} exceeds slot budget ₹{p_max:,.2f}"
                })

        # Relax p_max if insufficient affordable compounders found
        if len(affordable_candidates) < k_eff:
            p_max_relaxed = (2.0 * investable_equity) / k_eff
            for _, row in cand_df.iterrows():
                sym = str(row["symbol"])
                if any(r["symbol"] == sym for r in affordable_candidates):
                    continue
                px = float(row.get("close") or 0.0)
                if 0 < px <= p_max_relaxed:
                    affordable_candidates.append(row)
                    if len(affordable_candidates) >= k_eff:
                        break
            k_eff = max(1, len(affordable_candidates))
            slot_budget = investable_equity / k_eff

        top_candidates = pd.DataFrame(affordable_candidates).reset_index(drop=True)
        target_symbols = set(top_candidates["symbol"])

        top_candidates_summary = [
            {"symbol": r["symbol"], "score": round(float(r[score_col]), 2)}
            for _, r in top_candidates.iterrows()
        ]

        # ---------------------------------------------------------
        # Step 3: Inspect Authentic Holdings Map
        # ---------------------------------------------------------
        holdings_map: Dict[str, Dict[str, Any]] = {}
        for r in pos_rows:
            qty = int(r["quantity"])
            px = float(r["current_price"]) if r["current_price"] and float(r["current_price"]) > 0 else float(r["average_entry_price"])
            if qty > 0:
                val = qty * px
                w = val / total_nav if total_nav > 0 else 0.0
                holdings_map[r["symbol"]] = {"quantity": qty, "price": px, "weight": w}

        holdings_before = {sym: round(h["weight"], 4) for sym, h in holdings_map.items()}

        # ---------------------------------------------------------
        # Step 4: Greedy Residual Cash Sweeper & Two-Phase Order Generation
        # ---------------------------------------------------------
        buy_fric_rate = 0.0012 if fee_tier == "RETAIL_MICRO" else 0.0015
        target_shares_map: Dict[str, int] = {}
        for _, row in top_candidates.iterrows():
            sym = str(row["symbol"])
            px = float(row.get("close") or 0.0)
            target_shares_map[sym] = max(1, int(math.floor(slot_budget / px))) if px > 0 else 0

        # Remaining investable cash
        allocated_capital = sum(target_shares_map[r["symbol"]] * float(r["close"]) for _, r in top_candidates.iterrows())
        estimated_buy_fric = sum(target_shares_map[r["symbol"]] * float(r["close"]) * buy_fric_rate for _, r in top_candidates.iterrows())
        c_rem = investable_equity - allocated_capital - estimated_buy_fric

        # Greedy sweep residual cash to maximize capital utilization
        max_weight_per_stock = min(0.40, 1.5 / k_eff)
        cand_ranks_desc = [r for _, r in top_candidates.iterrows()]
        swept = True
        while swept and c_rem > 0:
            swept = False
            for r in cand_ranks_desc:
                sym = str(r["symbol"])
                px = float(r["close"])
                cost_1_share = px * (1.0 + buy_fric_rate)
                curr_q = target_shares_map[sym]
                if cost_1_share <= c_rem:
                    potential_weight = ((curr_q + 1) * px) / total_nav
                    if potential_weight <= max_weight_per_stock or k_eff <= 2:
                        target_shares_map[sym] += 1
                        c_rem -= cost_1_share
                        swept = True

        orders: List[Dict[str, Any]] = []
        trade_deltas: List[Dict[str, Any]] = []
        total_friction = 0.0
        holdings_after: Dict[str, float] = {}

        cand_score_map = {r["symbol"]: round(float(r[score_col]), 2) for _, r in cand_df.iterrows()}

        # Phase A (SELL Departures): For every holding where symbol not in target_symbols
        for sym, h in holdings_map.items():
            if sym not in target_symbols:
                qty = h["quantity"]
                px = round(h["price"], 2)
                val = round(qty * px, 2)
                if fee_tier == "RETAIL_MICRO":
                    fric = round((val * 0.0012) + min(5.0, val * 0.005), 2)
                else:
                    fric = round((val * 0.0015) + 15.0, 2)
                total_friction += fric
                orders.append({
                    "action": "SELL",
                    "symbol": sym,
                    "quantity": qty,
                    "ref_price": px,
                    "fill_price": px,
                    "order_value": val,
                    "estimated_friction": fric,
                    "reason": "Ejected: Score rank fell below Top-N threshold or price exceeds slot budget"
                })
                trade_deltas.append({
                    "symbol": sym,
                    "current_weight": round(h["weight"], 4),
                    "target_weight": 0.0,
                    "delta": round(0.0 - h["weight"], 4),
                    "action": "SELL",
                    "blended_score": cand_score_map.get(sym)
                })

        # Phase B (BUY New Entries & Re-weight Incumbents)
        for rank, (_, row) in enumerate(top_candidates.iterrows(), start=1):
            sym = row["symbol"]
            cand_score = round(float(row[score_col]), 2)
            px = float(row.get("close") or 0.0)
            target_shares = target_shares_map[sym]
            target_w = round((target_shares * px) / total_nav, 4) if total_nav > 0 else 0.0
            holdings_after[sym] = target_w

            if sym in holdings_map:
                curr_q = holdings_map[sym]["quantity"]
                curr_w = holdings_map[sym]["weight"]
                delta_q = target_shares - curr_q
                drift_val = abs(delta_q * px)
                if drift_val > (total_nav * 0.015):
                    if delta_q > 0:
                        qty_buy = delta_q
                        val = round(qty_buy * px, 2)
                        fric = round(val * buy_fric_rate, 2)
                        total_friction += fric
                        orders.append({
                            "action": "BUY",
                            "symbol": sym,
                            "quantity": qty_buy,
                            "ref_price": round(px, 2),
                            "fill_price": round(px, 2),
                            "order_value": val,
                            "estimated_friction": fric,
                            "reason": f"Re-weight expansion (Drift: {(drift_val / total_nav) * 100:.1f}%)"
                        })
                        delta_w = round(target_w - curr_w, 4)
                        trade_deltas.append({
                            "symbol": sym,
                            "current_weight": round(curr_w, 4),
                            "target_weight": target_w,
                            "delta": delta_w,
                            "action": "BUY",
                            "blended_score": cand_score
                        })
                    elif delta_q < 0:
                        qty_sell = abs(delta_q)
                        val = round(qty_sell * px, 2)
                        if fee_tier == "RETAIL_MICRO":
                            fric = round((val * 0.0012) + min(5.0, val * 0.005), 2)
                        else:
                            fric = round((val * 0.0015) + 15.0, 2)
                        total_friction += fric
                        orders.append({
                            "action": "SELL",
                            "symbol": sym,
                            "quantity": qty_sell,
                            "ref_price": round(px, 2),
                            "fill_price": round(px, 2),
                            "order_value": val,
                            "estimated_friction": fric,
                            "reason": f"Re-weight trim (Drift: {(drift_val / total_nav) * 100:.1f}%)"
                        })
                        delta_w = round(target_w - curr_w, 4)
                        trade_deltas.append({
                            "symbol": sym,
                            "current_weight": round(curr_w, 4),
                            "target_weight": target_w,
                            "delta": delta_w,
                            "action": "SELL",
                            "blended_score": cand_score
                        })
                else:
                    delta_w = round(target_w - curr_w, 4)
                    trade_deltas.append({
                        "symbol": sym,
                        "current_weight": round(curr_w, 4),
                        "target_weight": target_w,
                        "delta": delta_w,
                        "action": "HOLD",
                        "blended_score": cand_score
                    })
            else:
                if target_shares > 0:
                    val = round(target_shares * px, 2)
                    fric = round(val * buy_fric_rate, 2)
                    total_friction += fric
                    orders.append({
                        "action": "BUY",
                        "symbol": sym,
                        "quantity": target_shares,
                        "ref_price": round(px, 2),
                        "fill_price": round(px, 2),
                        "order_value": val,
                        "estimated_friction": fric,
                        "reason": f"New entry (Rank #{rank}, Score: {cand_score})"
                    })
                trade_deltas.append({
                    "symbol": sym,
                    "current_weight": 0.0,
                    "target_weight": target_w,
                    "delta": target_w,
                    "action": "BUY",
                    "blended_score": cand_score
                })

        # Turnover percentage: half the sum of absolute delta weights
        turnover_sum = sum(abs(d["delta"]) for d in trade_deltas)
        turnover_pct = round((turnover_sum / 2.0) * 100.0, 2)
        projected_cost_bps = round((turnover_pct / 100.0) * ROUND_TRIP_FRICTION_BPS, 2)

        # Multi-horizon model registry metadata integration
        deployments = self.registry.get_horizon_deployments() if self.registry else {}
        avail_horizons: List[int] = []
        norm_weights: Dict[int, float] = {}
        model_composite_parts: List[str] = []
        if deployments:
            weights_cfg = horizon_weights or DEFAULT_HORIZON_WEIGHTS
            valid_weights: Dict[int, float] = {}
            for h, base_w in weights_cfg.items():
                dep = deployments.get(h)
                if dep and dep.get("active_model_id") and float(dep.get("validation_ic") or 0.0) >= MIN_VALIDATION_IC_HURDLE:
                    valid_weights[h] = float(base_w)
            tot_w = sum(valid_weights.values())
            if tot_w > 0:
                norm_weights = {h: w / tot_w for h, w in valid_weights.items()}
                avail_horizons = list(norm_weights.keys())
                for h in avail_horizons:
                    m_id = deployments[h]["active_model_id"]
                    model_composite_parts.append(f"{h}D:{m_id[:16]}")

        if model_composite_parts:
            model_composite_id = "BLENDED_" + "_".join(model_composite_parts)
        else:
            model_composite_id = f"TOURNAMENT_BREADTH_{round(breadth_pct, 1)}"
            avail_horizons = [20, 60]
            norm_weights = {20: 0.625, 60: 0.375}

        proposal_id = f"reb_{session_date.replace('-', '')}_{uuid.uuid4().hex[:6]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # ---------------------------------------------------------
        # Step 5: Ledger Commit & Return Payload
        # ---------------------------------------------------------
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
            f"Generated Rebalance Proposal '{proposal_id}' for {session_date} (Account: {account_id}): "
            f"Breadth={breadth_pct:.2f}%, Cash={target_cash_pct}%, Orders={len(orders)}, "
            f"Turnover={turnover_pct}%, Friction=₹{total_friction:,.2f}"
        )

        return {
            "proposal_id": proposal_id,
            "session_date": session_date,
            "account_id": account_id,
            "status": "PROPOSED",
            "market_breadth_pct": round(breadth_pct, 2),
            "target_cash_pct": target_cash_pct,
            "turnover_pct": turnover_pct,
            "projected_cost_bps": projected_cost_bps,
            "orders": orders,                     # Full order list
            "trade_deltas": trade_deltas,         # Allocation delta list
            "holdings_before": holdings_before,
            "holdings_after": holdings_after,
            "target_holdings": holdings_after,
            "estimated_friction_inr": round(total_friction, 2),
            "top_candidates": top_candidates_summary,
            "capital_constrained_skips": capital_constrained_skips,
            "effective_k": k_eff,
            "slot_budget": round(slot_budget, 2),
            "investable_equity_inr": round(investable_equity, 2),
            "fee_tier": fee_tier,
            "active_horizons": avail_horizons,
            "effective_weights": norm_weights,
            "model_composite_id": model_composite_id,
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
            # Check for champion weights from ml_training_runs
            has_ml = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='ml_training_runs'").fetchone()[0] > 0
            if has_ml:
                champ_row = conn.execute(
                    "SELECT feature_weights_json FROM ml_training_runs WHERE is_champion = 1 ORDER BY horizon_days DESC LIMIT 1"
                ).fetchone()
                if champ_row and champ_row[0]:
                    try:
                        parsed_w = json.loads(champ_row[0])
                        if parsed_w and isinstance(parsed_w, dict):
                            weights = {k: float(v) for k, v in parsed_w.items() if float(v) > 0}
                    except Exception:
                        pass

            has_factors_daily = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='factors_daily'"
            ).fetchone()[0] > 0
            has_positions = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='portfolio_positions'"
            ).fetchone()[0] > 0

            # 7-day news sentiment lookup
            news_sentiment_map = {}
            has_news = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='stock_news_articles'").fetchone()[0] > 0
            if has_news:
                n_rows = conn.execute("""
                    SELECT symbol, AVG(sentiment_score) as avg_sent
                    FROM stock_news_articles
                    WHERE published_at >= date(?, '-7 days')
                    GROUP BY symbol
                """, (trading_date,)).fetchall()
                for r in n_rows:
                    news_sentiment_map[r[0]] = float(r[1])

            # NIFTY 50 20D benchmark return for relative strength
            nifty_20d_ret = 0.02
            has_index = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='index_daily'").fetchone()[0] > 0
            if has_index:
                nifty_row = conn.execute("""
                    SELECT (c.close / p.close) - 1.0
                    FROM index_daily c
                    JOIN index_daily p ON c.index_name = p.index_name
                    WHERE c.index_name = 'NIFTY 50' AND c.trading_date = ?
                    ORDER BY p.trading_date DESC LIMIT 1 OFFSET 20
                """, (trading_date,)).fetchone()
                if nifty_row and nifty_row[0] is not None:
                    nifty_20d_ret = float(nifty_row[0])

            df = pd.DataFrame()
            if has_factors_daily:
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
            if has_positions:
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
            with self.db.get_connection() as conn:
                fallback_sql = """
                SELECT 
                    q.symbol,
                    q.trading_date,
                    o.close,
                    q.sma_50,
                    q.sma_200,
                    q.ret_20d as momentum_20d,
                    q.ret_5d as momentum_5d,
                    0.10 as momentum_252d,
                    COALESCE(q.vol_20d_annualized, 0.20) as volatility_20d,
                    50.0 as rsi_14,
                    CASE WHEN q.sma_200 > 0 THEN (q.sma_50 / q.sma_200) ELSE 1.0 END as sma_ratio_50_200,
                    q.opm_pct as operating_margin,
                    q.debt_to_equity,
                    q.roe_pct,
                    COALESCE(s.company_name, q.symbol) as company_name,
                    COALESCE(s.sector, 'Unclassified') as sector
                FROM quant_factors_daily q
                JOIN ohlcv_daily o ON q.symbol = o.symbol AND q.trading_date = o.trading_date
                LEFT JOIN securities_master s ON q.symbol = s.symbol
                WHERE q.trading_date = ?
                  AND o.close IS NOT NULL
                  AND o.close > 0
                """
                df = pd.read_sql_query(fallback_sql, conn, params=[trading_date])

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

        # 8-Factor Quant & News Sentiment Matrix
        safe_vol = np.maximum(df["volatility_20d"].fillna(0.20), 0.05)
        tactical_raw = df["momentum_20d"].fillna(0.0) / safe_vol
        trend_raw = df["momentum_252d"].fillna(0.0) / safe_vol
        safe_sma200 = np.maximum(df["sma_200"].fillna(df["close"]), 1.0)
        structural_raw = (df["close"] - safe_sma200) / safe_sma200
        rsi_curve = 100.0 - np.abs(df["rsi_14"].fillna(50.0) - 62.0) * 2.0
        low_vol_raw = 1.0 / safe_vol
        vol_accum_raw = df["momentum_5d"].fillna(0.0) * np.sign(df["momentum_5d"].fillna(0.0))
        rel_strength_raw = df["momentum_20d"].fillna(0.0) - nifty_20d_ret
        news_sent_series = df["symbol"].map(news_sentiment_map).fillna(0.0)

        factor_ranks["tactical_20d"] = _rank(tactical_raw, ascending=True)
        factor_ranks["trend_60d"] = _rank(trend_raw, ascending=True)
        factor_ranks["structural_200d"] = _rank(structural_raw, ascending=True)
        factor_ranks["rsi_regime"] = _rank(rsi_curve, ascending=True)
        factor_ranks["low_vol_quality"] = _rank(low_vol_raw, ascending=True)
        factor_ranks["volume_accumulation"] = _rank(vol_accum_raw, ascending=True)
        factor_ranks["relative_strength_nifty"] = _rank(rel_strength_raw, ascending=True)
        factor_ranks["news_sentiment_7d"] = _rank(news_sent_series, ascending=True)

        # Legacy factor compatibility aliases
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
        df["effective_score"] = df["blended_score"]

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
