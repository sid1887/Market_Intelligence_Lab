"""
src/portfolio/position_sizer.py
Friction-Aware Integer-Share Optimizer & Correlation-Cluster Risk Budgeter.
Phase 4 Deliverable — Translates Meta-Label probabilities and Triple-Barrier levels
into risk-bounded, cost-clearing, correlation-constrained Indian equity orders.

Key Mathematical Invariants:
1. Exact Risk-Bounded Integer Shares:
   Q = floor( (r_max * C) / (P_0 - L) ) subject to single-position allocation cap C * max_pos_pct.
2. Canonical Post-Friction Net R:R:
   Net R:R = ( Q * (U - P_0) - F_win(Q) ) / ( Q * (P_0 - L) + F_loss(Q) )
   where F_win(Q) and F_loss(Q) are exact round-trip statutory + ₹23.60 DP charges via fee_engine.py.
3. Explicit Abstention (NO_TRADE) Vetoes:
   - Q < 1 (insufficient capital or stop distance too wide).
   - Fee drag % > max_fee_drag_pct (default 1.25%).
   - Net R:R < min_net_rr (default 1.6).
   - Calibrated Meta-Probability p_meta < min_meta_prob (default 0.55).
   - Invalid price barriers (L >= P_0 or U <= P_0).
4. Correlation-Cluster Exposure Cap:
   - Open positions and candidate entries belonging to the same cluster (r >= 0.65)
     cannot exceed a combined portfolio allocation cap (default 40% of capital C).
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd

from src.storage.database import DatabaseManager
from src.portfolio.fee_engine import (
    calculate_roundtrip_friction,
    ANGEL_ONE_DP_CHARGE,
    PROFILE_ZERO
)

logger = logging.getLogger("MIL.PositionSizer")


@dataclass(frozen=True)
class PositionSizingResult:
    symbol: str
    entry_price: float
    target_price: float
    stop_loss: float
    meta_prob: float
    available_capital: float
    
    # Sizing
    shares: int
    allocated_capital: float
    allocation_pct: float
    
    # Financial metrics
    gross_reward: float
    gross_risk: float
    gross_rr: float
    win_friction: float
    loss_friction: float
    net_reward: float
    net_risk: float
    net_rr: float
    fee_drag_pct: float
    
    # Decision & Vetoes
    can_trade: bool
    verdict: str  # 'APPROVED', 'NO_TRADE'
    veto_reasons: List[str] = field(default_factory=list)
    cluster_id: Optional[str] = None
    cluster_exposure_pct: float = 0.0


class FrictionAwarePositionSizer:
    """
    Friction-Aware Integer-Share Optimizer & Correlation-Cluster Risk Budgeter.
    Enforces risk budgets, statutory + DP friction breakevens, and correlation cluster caps.
    """

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        max_risk_pct: float = 0.02,        # 2% max risk per trade
        max_position_pct: float = 0.25,    # 25% max capital in single position
        max_fee_drag_pct: float = 1.25,    # 1.25% max round-trip fee drag
        min_net_rr: float = 1.6,           # 1.6 minimum net reward to risk
        min_meta_prob: float = 0.55,       # 0.55 minimum meta-calibrator probability
        cluster_cap_pct: float = 0.40,     # 40% maximum allocation per correlation cluster
        corr_threshold: float = 0.65,      # 0.65 correlation threshold for clustering
        broker_profile: str = PROFILE_ZERO,
        dp_charge: float = ANGEL_ONE_DP_CHARGE,
        use_regime_policy: bool = True,
        regime: Optional[str] = None,
    ):
        self.db = db or DatabaseManager()
        self.max_risk_pct = float(max_risk_pct)
        self.max_position_pct = float(max_position_pct)
        self.max_fee_drag_pct = float(max_fee_drag_pct)
        self.min_net_rr = float(min_net_rr)
        self.min_meta_prob = float(min_meta_prob)
        self.cluster_cap_pct = float(cluster_cap_pct)
        self.corr_threshold = float(corr_threshold)
        self.broker_profile = broker_profile
        self.dp_charge = float(dp_charge)
        self.use_regime_policy = bool(use_regime_policy)
        self.regime = regime

    def get_regime_optimal_policy(
        self,
        ticket_size: float,
        regime: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Loads calibrated optimal execution policy for the active HMM regime & ticket size."""
        if not self.use_regime_policy:
            return None
        try:
            from src.quant.policy_optimizer import load_optimal_execution_policy
            from src.quant.regime_hmm import load_regime_hmm_state

            active_regime = regime or self.regime or load_regime_hmm_state().get("latest_regime", "HIGH_VOL_CHOP")
            return load_optimal_execution_policy(regime=active_regime, ticket_size=ticket_size)
        except Exception as e:
            logger.debug(f"Regime optimal policy lookup fallback: {e}")
            return None

    def compute_trailing_correlation(
        self,
        sym1: str,
        sym2: str,
        lookback_sessions: int = 60
    ) -> float:
        """Computes trailing pairwise daily return correlation between two symbols."""
        if sym1 == sym2:
            return 1.0

        try:
            with self.db.get_connection() as conn:
                df1 = pd.read_sql_query("""
                    SELECT trading_date, close FROM ohlcv_daily 
                    WHERE symbol = ? ORDER BY trading_date DESC LIMIT ?
                """, conn, params=(sym1, lookback_sessions + 5))
                df2 = pd.read_sql_query("""
                    SELECT trading_date, close FROM ohlcv_daily 
                    WHERE symbol = ? ORDER BY trading_date DESC LIMIT ?
                """, conn, params=(sym2, lookback_sessions + 5))

            if df1.empty or df2.empty or len(df1) < 20 or len(df2) < 20:
                return 0.0

            df1 = df1.sort_values("trading_date").copy()
            df2 = df2.sort_values("trading_date").copy()
            df1["ret"] = df1["close"].pct_change()
            df2["ret"] = df2["close"].pct_change()

            merged = pd.merge(df1[["trading_date", "ret"]], df2[["trading_date", "ret"]], on="trading_date", suffixes=("_1", "_2")).dropna()
            if len(merged) < 15:
                return 0.0

            corr = float(np.corrcoef(merged["ret_1"], merged["ret_2"])[0, 1])
            return corr if not np.isnan(corr) else 0.0
        except Exception as e:
            logger.debug(f"[CORRELATION] Pairwise correlation failed for {sym1}-{sym2}: {e}")
            return 0.0

    def solve_position_size(
        self,
        capital: float,
        entry_price: float,
        stop_loss: float,
        target_price: float,
        meta_prob: float = 0.60,
        candidate_symbol: str = "CANDIDATE",
        open_positions: Optional[List[Dict[str, Any]]] = None,
        custom_size_multiplier: float = 1.0
    ) -> PositionSizingResult:
        """
        Solves the exact integer position size, evaluates friction drag, and enforces hard vetoes.
        """
        c = float(capital)
        p0 = float(entry_price)
        l = float(stop_loss)
        u = float(target_price)
        prob = float(meta_prob)
        sym = str(candidate_symbol).strip().upper()
        size_mult = max(0.0, float(custom_size_multiplier))

        veto_reasons: List[str] = []

        # 1. Validation of price barriers
        if p0 <= 0:
            veto_reasons.append("INVALID_PRICE: Entry price must be strictly positive.")
            return self._build_abstain_result(sym, p0, u, l, prob, c, veto_reasons)

        if l >= p0:
            veto_reasons.append(f"INVALID_BARRIERS: Stop-loss (₹{l:.2f}) must be strictly below entry (₹{p0:.2f}).")
        if u <= p0:
            veto_reasons.append(f"INVALID_BARRIERS: Target price (₹{u:.2f}) must be strictly above entry (₹{p0:.2f}).")

        # 2. Meta-Probability Gating
        if prob < self.min_meta_prob:
            veto_reasons.append(
                f"META_PROB_BELOW_HURDLE: Model probability {prob:.3f} < required minimum {self.min_meta_prob:.2f}."
            )

        if veto_reasons:
            return self._build_abstain_result(sym, p0, u, l, prob, c, veto_reasons)

        # 3. Risk-Bounded Integer Share Quantity
        delta_risk = p0 - l
        r_trade = c * self.max_risk_pct * size_mult
        q_risk = int(r_trade // delta_risk) if delta_risk > 0 else 0

        # Capital caps
        max_pos_capital = c * self.max_position_pct * size_mult
        q_cap = int(max_pos_capital // p0)
        q_cash = int(c // p0)

        # Candidate raw integer shares
        q = min(q_risk, q_cap, q_cash)

        if q < 1:
            veto_reasons.append(
                f"INSUFFICIENT_CAPITAL_OR_RISK_CAP: Solved shares Q=0 (Capital ₹{c:,.2f}, Entry ₹{p0:.2f}, Stop Risk ₹{delta_risk:.2f})."
            )
            return self._build_abstain_result(sym, p0, u, l, prob, c, veto_reasons)

        # 4. Correlation-Cluster Exposure Budgeting
        cluster_exposure = 0.0
        correlated_symbols = []
        if open_positions:
            for pos in open_positions:
                pos_sym = str(pos.get("symbol", "")).strip().upper()
                pos_val = float(pos.get("buy_value") or (float(pos.get("qty", 0)) * float(pos.get("avg_buy_price", 0))))
                if pos_sym == sym:
                    cluster_exposure += pos_val
                    correlated_symbols.append(pos_sym)
                else:
                    corr = self.compute_trailing_correlation(sym, pos_sym)
                    if corr >= self.corr_threshold:
                        cluster_exposure += pos_val
                        correlated_symbols.append(f"{pos_sym}(r={corr:.2f})")

        cluster_cap_amount = c * self.cluster_cap_pct
        proposed_investment = q * p0
        total_cluster_after = cluster_exposure + proposed_investment

        if total_cluster_after > cluster_cap_amount:
            remaining_cluster_budget = max(0.0, cluster_cap_amount - cluster_exposure)
            q_cluster = int(remaining_cluster_budget // p0)
            if q_cluster < 1:
                veto_reasons.append(
                    f"CLUSTER_LIMIT_EXCEEDED: Correlated cluster exposure (with {', '.join(correlated_symbols) if correlated_symbols else 'theme'}) "
                    f"reaches ₹{total_cluster_after:,.2f} exceeding {self.cluster_cap_pct*100:.0f}% cap (₹{cluster_cap_amount:,.2f})."
                )
                return self._build_abstain_result(sym, p0, u, l, prob, c, veto_reasons, cluster_exp_pct=(total_cluster_after / c * 100))
            else:
                q = q_cluster

        # 5. Exact Round-Trip Friction & Net R:R Solver
        buy_turnover = round(q * p0, 2)
        win_turnover = round(q * u, 2)
        loss_turnover = round(q * l, 2)

        rt_win = calculate_roundtrip_friction(
            buy_turnover=buy_turnover,
            sell_turnover=win_turnover,
            profile=self.broker_profile,
            dp_override=self.dp_charge
        )
        rt_loss = calculate_roundtrip_friction(
            buy_turnover=buy_turnover,
            sell_turnover=loss_turnover,
            profile=self.broker_profile,
            dp_override=self.dp_charge
        )

        f_win = rt_win.total_friction
        f_loss = rt_loss.total_friction

        gross_reward = round(q * (u - p0), 2)
        gross_risk = round(q * (p0 - l), 2)
        gross_rr = round(gross_reward / max(gross_risk, 0.01), 2)

        net_reward = round(gross_reward - f_win, 2)
        net_risk = round(gross_risk + f_loss, 2)
        net_rr = round(net_reward / max(net_risk, 0.01), 2)

        fee_drag_pct = round((f_win / buy_turnover) * 100.0, 2) if buy_turnover > 0 else 0.0

        # Resolve effective regime-optimal thresholds if enabled
        eff_max_fee_drag = self.max_fee_drag_pct
        eff_min_net_rr = self.min_net_rr
        reg_pol = self.get_regime_optimal_policy(ticket_size=buy_turnover)
        if reg_pol:
            eff_min_net_rr = max(eff_min_net_rr, float(reg_pol.get("min_net_rr", eff_min_net_rr)))
            eff_max_fee_drag = float(reg_pol.get("max_fee_drag_pct", eff_max_fee_drag))

        # 6. Post-Friction Abstention Gates
        if fee_drag_pct > eff_max_fee_drag:
            veto_reasons.append(
                f"FEE_DRAG_EXCEEDS_THRESHOLD: Round-trip friction is {fee_drag_pct:.2f}% (exceeds {eff_max_fee_drag:.2f}% cap). "
                f"₹{self.dp_charge:.2f} DP charge severely penalizes this position size (₹{buy_turnover:,.2f})."
            )

        if net_reward <= 0:
            veto_reasons.append(
                f"NEGATIVE_NET_EXPECTANCY: Net reward after ₹{f_win:.2f} friction is negative (₹{net_reward:.2f})."
            )

        if net_rr < eff_min_net_rr:
            veto_reasons.append(
                f"POOR_NET_RR: Net R:R is {net_rr:.2f}x (required minimum is {eff_min_net_rr:.2f}x). "
                f"Gross R:R was {gross_rr:.2f}x but friction eroded payoff asymmetry."
            )

        can_trade = len(veto_reasons) == 0
        verdict = "APPROVED" if can_trade else "NO_TRADE"
        allocated_capital = buy_turnover if can_trade else 0.0
        allocation_pct = round((allocated_capital / c) * 100.0, 2) if c > 0 else 0.0
        final_cluster_pct = round((cluster_exposure + allocated_capital) / c * 100.0, 2) if c > 0 else 0.0

        return PositionSizingResult(
            symbol=sym,
            entry_price=p0,
            target_price=u,
            stop_loss=l,
            meta_prob=prob,
            available_capital=c,
            shares=q if can_trade else 0,
            allocated_capital=allocated_capital,
            allocation_pct=allocation_pct,
            gross_reward=gross_reward,
            gross_risk=gross_risk,
            gross_rr=gross_rr,
            win_friction=f_win,
            loss_friction=f_loss,
            net_reward=net_reward,
            net_risk=net_risk,
            net_rr=net_rr,
            fee_drag_pct=fee_drag_pct,
            can_trade=can_trade,
            verdict=verdict,
            veto_reasons=veto_reasons,
            cluster_id=correlated_symbols[0] if correlated_symbols else None,
            cluster_exposure_pct=final_cluster_pct
        )

    def _build_abstain_result(
        self,
        sym: str,
        p0: float,
        u: float,
        l: float,
        prob: float,
        c: float,
        veto_reasons: List[str],
        cluster_exp_pct: float = 0.0
    ) -> PositionSizingResult:
        return PositionSizingResult(
            symbol=sym,
            entry_price=p0,
            target_price=u,
            stop_loss=l,
            meta_prob=prob,
            available_capital=c,
            shares=0,
            allocated_capital=0.0,
            allocation_pct=0.0,
            gross_reward=0.0,
            gross_risk=0.0,
            gross_rr=0.0,
            win_friction=0.0,
            loss_friction=0.0,
            net_reward=0.0,
            net_risk=0.0,
            net_rr=0.0,
            fee_drag_pct=0.0,
            can_trade=False,
            verdict="NO_TRADE",
            veto_reasons=veto_reasons,
            cluster_exposure_pct=cluster_exp_pct
        )
