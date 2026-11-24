"""
src/copilot/trader_dna.py
Dynamic Trader DNA Behavioral Profiler & Personal Execution Coach.
Phase 4 Deliverable — Incorporates rolling behavioral telemetry, post-loss cooldown / half-size guards,
horizon mismatch warnings, and persistent episodic memory recording.

Behavioral Coaching Invariants:
1. Hard Minimum Net-Target Gate (>= 3.5% gross upside):
   - On ₹1,500–₹2,000 retail tickets, ₹23.60 DP fee + taxes costs 1.4%–1.9% round-trip.
   - Blocks or warns on taking profit below +2.5% gross to prevent negative net returns.
2. Post-Loss Cooldown & Half-Size Guard (>= 3 consecutive losses or drawdown > pain threshold):
   - Enforces defensive cooldown, capping next position size to ₹1,500 or half-sizing.
3. Hold-Window Discipline & Horizon Mismatch Detection:
   - Tracks median holding duration and early-exit rate (< 3 days).
   - Flags horizon mismatches when candidate Triple-Barrier horizon H exceeds historical median hold.
4. Persistent Memory & Cloud State Sync:
   - Records suitability interventions into copilot_memory_episodes and calls mark_state_dirty().
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import numpy as np

from src.storage.database import DatabaseManager
from src.storage.durable_state import mark_state_dirty
from src.copilot.memory_store import CopilotMemoryStore
from src.portfolio.fee_engine import (
    calculate_roundtrip_friction,
    calculate_order_charges,
    ANGEL_ONE_DP_CHARGE
)

logger = logging.getLogger("MIL.TraderDNA")

DEFAULT_ANGEL_ONE_DP_CHARGE = ANGEL_ONE_DP_CHARGE


class TraderDNAEngine:
    """
    Analyzes personal trade history directly from SQLite tradebook tables
    (real_closed_roundtrips, real_open_holdings, real_capital_ledger)
    and enforces behavioral guardrails inside Copilot deliberation.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.memory_store = CopilotMemoryStore(db)

    def _ensure_tradebook_tables(self, conn) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS real_capital_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                posting_date TEXT NOT NULL,
                credit REAL DEFAULT 0.0,
                debit REAL DEFAULT 0.0,
                balance REAL DEFAULT 0.0,
                particulars TEXT,
                voucher_no TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS real_closed_roundtrips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                isin TEXT,
                scrip_name TEXT,
                qty INTEGER NOT NULL,
                buy_date TEXT,
                sell_date TEXT,
                hold_days INTEGER DEFAULT 0,
                avg_buy_price REAL,
                buy_value REAL,
                avg_sell_price REAL,
                sell_value REAL,
                gross_pnl REAL,
                trade_charges REAL DEFAULT 0.0,
                dp_charge REAL DEFAULT 23.60,
                net_pnl REAL,
                net_return_pct REAL,
                outcome TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS real_open_holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                isin TEXT,
                scrip_name TEXT,
                qty INTEGER NOT NULL,
                avg_buy_price REAL,
                buy_value REAL,
                closing_rate REAL,
                current_value REAL,
                unrealized_pnl REAL,
                unrealized_pnl_pct REAL
            )
        """)

    def get_live_execution_profile(self) -> Dict[str, Any]:
        """
        Recomputes live behavioral scorecard directly from SQLite tradebook tables.
        Returns a compact, structured dictionary.
        """
        with self.db.get_connection() as conn:
            self._ensure_tradebook_tables(conn)
            # 1. Capital added
            cap_row = conn.execute("SELECT SUM(credit) FROM real_capital_ledger").fetchone()
            total_capital = float(cap_row[0] or 0.0)

            # 2. Closed roundtrips
            trades_rows = conn.execute("""
                SELECT 
                    id, symbol, isin, scrip_name, qty, buy_date, sell_date, hold_days,
                    avg_buy_price, buy_value, avg_sell_price, sell_value, gross_pnl,
                    trade_charges, dp_charge, net_pnl, net_return_pct, outcome
                FROM real_closed_roundtrips
                ORDER BY sell_date DESC, id DESC
            """).fetchall()

            total_trades = len(trades_rows)
            realized_gross = sum(float(r["gross_pnl"] or 0.0) for r in trades_rows)
            realized_taxes = sum(float(r["trade_charges"] or 0.0) for r in trades_rows)
            realized_dp = sum(float(r["dp_charge"] or 0.0) for r in trades_rows)
            realized_net = sum(float(r["net_pnl"] or 0.0) for r in trades_rows)
            total_buy_val = sum(float(r["buy_value"] or 0.0) for r in trades_rows)

            winners = [r for r in trades_rows if float(r["net_pnl"] or 0.0) > 0]
            losers = [r for r in trades_rows if float(r["net_pnl"] or 0.0) <= 0]
            win_count = len(winners)
            loss_count = len(losers)
            win_rate_pct = round((win_count / total_trades * 100.0), 2) if total_trades > 0 else 0.0

            avg_ticket = round(total_buy_val / total_trades, 2) if total_trades > 0 else 1600.0
            avg_breakeven_pct = round(((realized_taxes + realized_dp) / (total_buy_val + 1e-6) * 100.0), 2) if total_buy_val > 0 else 1.65

            # Holding period & Behavioral Telemetry metrics
            all_hold_days = [int(r["hold_days"] or 0) for r in trades_rows]
            median_hold_days = float(np.median(all_hold_days)) if all_hold_days else 7.0
            avg_hold_winners = round(sum(int(r["hold_days"] or 0) for r in winners) / max(win_count, 1), 1)
            avg_hold_losers = round(sum(int(r["hold_days"] or 0) for r in losers) / max(loss_count, 1), 1)

            trades_under_3d = [r for r in trades_rows if int(r["hold_days"] or 0) < 3]
            trades_5_to_15d = [r for r in trades_rows if 5 <= int(r["hold_days"] or 0) <= 15]

            win_rate_under_3d = round(
                (sum(1 for r in trades_under_3d if float(r["net_pnl"] or 0.0) > 0) / max(len(trades_under_3d), 1) * 100.0), 1
            ) if trades_under_3d else 0.0

            win_rate_5_to_15d = round(
                (sum(1 for r in trades_5_to_15d if float(r["net_pnl"] or 0.0) > 0) / max(len(trades_5_to_15d), 1) * 100.0), 1
            ) if trades_5_to_15d else 0.0

            early_exits = [r for r in trades_rows if int(r["hold_days"] or 0) <= 2]
            early_exit_rate_pct = round((len(early_exits) / max(total_trades, 1)) * 100.0, 1) if total_trades > 0 else 0.0

            # Drawdown calculation across closed trades
            cumulative_net = 0.0
            peak_net = 0.0
            max_drawdown = 0.0
            for r in reversed(trades_rows):  # chronological order
                cumulative_net += float(r["net_pnl"] or 0.0)
                if cumulative_net > peak_net:
                    peak_net = cumulative_net
                dd = peak_net - cumulative_net
                if dd > max_drawdown:
                    max_drawdown = dd

            # Streak & Cooldown analysis
            consecutive_losses = 0
            for r in trades_rows:
                if float(r["net_pnl"] or 0.0) <= 0:
                    consecutive_losses += 1
                else:
                    break

            last_loss_date = losers[0]["sell_date"] if losers else None
            last_loss_amount = abs(float(losers[0]["net_pnl"] or 0.0)) if losers else 0.0

            # Defensive cooldown trigger: consecutive losses >= 2 or last loss > 75 or drawdown > 150
            cooldown_active = False
            cooldown_reasons = []
            if consecutive_losses >= 2:
                cooldown_active = True
                cooldown_reasons.append(f"{consecutive_losses}-trade losing streak")
            if last_loss_amount > 75.0:
                cooldown_active = True
                cooldown_reasons.append(f"Recent stop-loss > ₹75 (₹{last_loss_amount:.2f})")
            if max_drawdown > 150.0:
                cooldown_reasons.append(f"Peak-to-trough closed drawdown ₹{max_drawdown:.2f}")

            # Half-size guard trigger if consecutive losses >= 3
            half_size_guard = consecutive_losses >= 3 or max_drawdown >= 200.0

            # 3. Open Holdings
            open_rows = conn.execute("""
                SELECT symbol, isin, scrip_name, qty, avg_buy_price, buy_value,
                       closing_rate, current_value, unrealized_pnl, unrealized_pnl_pct
                FROM real_open_holdings
            """).fetchall()

            open_positions = []
            total_unrealized_pnl = 0.0
            for h in open_rows:
                qty = int(h["qty"] or 0)
                buy_val = float(h["buy_value"] or 0.0)
                ltp = float(h["closing_rate"] or h["avg_buy_price"] or 0.0)
                unreal_pnl = float(h["unrealized_pnl"] or 0.0)
                total_unrealized_pnl += unreal_pnl

                # Exact breakeven price including ₹23.60 sell DP charge + 0.1% sell STT
                estimated_sell_taxes = round(0.001 * buy_val, 2)
                breakeven_total_cost = buy_val + estimated_sell_taxes + DEFAULT_ANGEL_ONE_DP_CHARGE
                breakeven_price = round(breakeven_total_cost / qty, 2) if qty > 0 else 0.0

                open_positions.append({
                    "symbol": h["symbol"],
                    "isin": h["isin"],
                    "scrip_name": h["scrip_name"],
                    "qty": qty,
                    "quantity": qty,
                    "avg_buy_price": float(h["avg_buy_price"] or 0.0),
                    "buy_value": buy_val,
                    "live_ltp": ltp,
                    "unrealized_pnl": unreal_pnl,
                    "unrealized_pct": float(h["unrealized_pnl_pct"] or 0.0),
                    "breakeven_price": breakeven_price,
                    "points_to_breakeven": round(breakeven_price - ltp, 2),
                })

        fee_drag_pct = round(((realized_taxes + realized_dp) / (abs(realized_gross) + 1e-6) * 100.0), 2) if realized_gross != 0 else 0.0

        # Coaching badge text
        if cooldown_active:
            coaching_badge = f"Defensive Cooldown ({consecutive_losses}L Streak · Cap ₹1,500)"
        elif open_positions:
            coaching_badge = f"Active Hold: {open_positions[0]['symbol']} ({open_positions[0]['qty']} sh)"
        else:
            coaching_badge = "Discipline Normal (Min +3.5% Target)"

        return {
            "total_capital": total_capital,
            "realized_net_pnl": round(realized_net, 2),
            "realized_gross_pnl": round(realized_gross, 2),
            "total_trade_taxes": round(realized_taxes, 2),
            "total_dp_charges": round(realized_dp, 2),
            "fee_drag_pct": fee_drag_pct,
            "total_trades": total_trades,
            "win_count": win_count,
            "winning_trades": win_count,
            "loss_count": loss_count,
            "losing_trades": loss_count,
            "win_rate_pct": win_rate_pct,
            "avg_ticket_size": avg_ticket,
            "avg_breakeven_pct": avg_breakeven_pct,
            "median_hold_days": median_hold_days,
            "early_exit_rate_pct": early_exit_rate_pct,
            "max_drawdown": round(max_drawdown, 2),
            "half_size_guard": half_size_guard,
            "size_multiplier": 0.5 if half_size_guard else 1.0,
            "avg_hold_days_winners": avg_hold_winners,
            "avg_hold_days_losers": avg_hold_losers,
            "holding_window_bias": "5-12 sessions (Micro-Swing)",
            "win_rate_under_3d": win_rate_under_3d,
            "win_rate_5_to_15d": win_rate_5_to_15d,
            "consecutive_losses": consecutive_losses,
            "last_loss_amount": last_loss_amount,
            "last_loss_date": last_loss_date,
            "defensive_cooldown_active": cooldown_active,
            "in_defensive_cooldown": cooldown_active,
            "cooldown_reasons": cooldown_reasons,
            "max_ticket_allowed": 1500.0 if cooldown_active else 2000.0,
            "open_positions": open_positions,
            "open_holdings": open_positions,
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "coaching_badge": coaching_badge,
        }

    def evaluate_proposed_trade(
        self,
        symbol: str,
        entry_price: Optional[float] = None,
        target_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        budget: float = 1600.0,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        holding_horizon_days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Evaluates a proposed trade ticket against the user's micro-capital constraints
        and strict coaching rules:
        1. Exact integer share count.
        2. Exact round-trip friction (STT + GST + ₹23.60 DP).
        3. Hard Minimum Net-Target Gate (>= 3.5% gross upside).
        4. Post-loss cooldown budget cap and half-size guard.
        5. Horizon mismatch warning if setup horizon H exceeds median discipline.
        """
        entry_p = float(entry_price if entry_price is not None else (price or 0.0))
        target_p = float(target_price if target_price is not None else 0.0)
        stop_p = float(stop_price if stop_price is not None else (stop_loss or 0.0))

        profile = self.get_live_execution_profile()
        effective_budget = min(budget, profile["max_ticket_allowed"])

        shares = int(effective_budget // entry_p) if entry_p > 0 else 0
        invested = round(shares * entry_p, 2)

        # Round-trip statutory friction for delivery equity via canonical fee engine
        sell_turnover = round(shares * target_p, 2)
        rt = calculate_roundtrip_friction(invested, sell_turnover, dp_override=DEFAULT_ANGEL_ONE_DP_CHARGE)
        total_friction = rt.total_friction
        dp_charge = rt.total_dp_charges

        breakeven_exit = round(rt.breakeven_sell_turnover / max(shares, 1), 2) if shares > 0 else entry_p
        breakeven_pct = rt.breakeven_upside_pct

        gross_upside_pct = round(((target_p - entry_p) / entry_p * 100.0), 2) if entry_p > 0 else 0.0
        gross_downside_pct = round(((entry_p - stop_p) / entry_p * 100.0), 2) if entry_p > 0 else 0.0

        target_gross_pnl = round(shares * (target_p - entry_p), 2)
        target_net_pnl = round(target_gross_pnl - total_friction, 2)

        stop_gross_loss = round(shares * (entry_p - stop_p), 2)
        stop_net_loss = round(stop_gross_loss + total_friction, 2)

        net_reward_risk = round(target_net_pnl / max(stop_net_loss, 0.01), 2)

        # Rule checks
        violations = []
        warnings = []

        if profile["defensive_cooldown_active"]:
            warnings.append(
                f"POST-LOSS COOLDOWN ACTIVE: {', '.join(profile['cooldown_reasons'])}. "
                f"Max ticket capped at ₹1,500 (allocated: ₹{invested:.2f})."
            )

        if gross_upside_pct < 2.5:
            violations.append(
                f"GROSS UPSIDE TOO SMALL (+{gross_upside_pct:.1f}%): ₹23.60 DP fee requires +{breakeven_pct:.1f}% "
                f"just to break even. Profit-taking below +2.5% guarantees negative net returns."
            )
        elif gross_upside_pct < 3.5:
            warnings.append(
                f"MARGINAL TARGET (+{gross_upside_pct:.1f}%): Below recommended +3.5% threshold. "
                f"Net profit will be only ₹{target_net_pnl:.2f} after ₹{total_friction:.2f} friction."
            )

        if net_reward_risk < 1.3:
            warnings.append(
                f"POOR NET R:R ({net_reward_risk:.2f}x): Target net profit ₹{target_net_pnl:.2f} "
                f"vs net stop risk ₹{stop_net_loss:.2f}."
            )

        # Horizon mismatch check
        median_hold = profile.get("median_hold_days", 7.0)
        h_setup = int(holding_horizon_days) if holding_horizon_days is not None else 20
        if h_setup > max(15, int(median_hold * 2.0)):
            warnings.append(
                f"HORIZON_MISMATCH: Setup horizon ({h_setup} sessions) exceeds trader's historical "
                f"median hold discipline ({median_hold:.1f} days). Early exit probability is elevated ({profile['early_exit_rate_pct']}%), "
                f"threatening trade plan execution."
            )

        verdict = "APPROVED"
        if violations:
            verdict = "BLOCKED_FEE_DRAG"
        elif profile["defensive_cooldown_active"] and warnings:
            verdict = "CAUTION_COOLDOWN"

        net_upside_pct = round(((target_net_pnl / invested) * 100.0), 2) if invested > 0 else gross_upside_pct
        net_risk_pct = round(((stop_net_loss / invested) * 100.0), 2) if invested > 0 else gross_downside_pct
        can_trade = len(violations) == 0 and not profile["defensive_cooldown_active"]
        coaching_status = "COOLDOWN_ACTIVE" if profile["defensive_cooldown_active"] else ("FEE_DRAG_BLOCK" if violations else ("WARNING" if warnings else "NORMAL"))
        advice = warnings[0] if warnings else (violations[0] if violations else "Execution parameters aligned with trader rules.")

        # Persist behavioral suitability adjustment to episodic memory & mark state dirty
        if violations or profile["defensive_cooldown_active"] or warnings:
            try:
                self.memory_store.record_episode(
                    symbols=[symbol],
                    category="RISK_RULE",
                    summary=f"Trader DNA evaluated {symbol}: Status={coaching_status}, Verdict={verdict}. {advice}",
                    importance=1.5 if violations or profile["defensive_cooldown_active"] else 1.0
                )
                mark_state_dirty()
            except Exception as mem_err:
                logger.debug(f"[TRADER_DNA] Memory logging non-fatal notice: {mem_err}")

        return {
            "symbol": symbol,
            "shares": shares,
            "recommended_shares": shares,
            "invested_capital": invested,
            "max_capital_allowed": effective_budget,
            "entry_price": entry_p,
            "target_price": target_p,
            "stop_price": stop_p,
            "breakeven_exit_price": breakeven_exit,
            "breakeven_price": breakeven_exit,
            "breakeven_move_pct": breakeven_pct,
            "fee_drag_pct": breakeven_pct,
            "total_roundtrip_friction": total_friction,
            "dp_charge": dp_charge,
            "target_gross_pnl": target_gross_pnl,
            "target_net_pnl": target_net_pnl,
            "stop_net_loss": stop_net_loss,
            "net_reward_risk": net_reward_risk,
            "gross_upside_pct": gross_upside_pct,
            "gross_downside_pct": gross_downside_pct,
            "net_upside_pct": net_upside_pct,
            "net_risk_pct": net_risk_pct,
            "verdict": verdict,
            "violations": violations,
            "warnings": warnings,
            "can_trade": can_trade,
            "cooldown_active": profile["defensive_cooldown_active"],
            "coaching_status": coaching_status,
            "advice": advice,
            "median_hold_days": median_hold,
            "early_exit_rate_pct": profile.get("early_exit_rate_pct", 0.0),
            "size_multiplier": profile.get("size_multiplier", 1.0)
        }

    def format_dna_for_prompt(self) -> str:
        """
        Formats a high-density, zero-PII personal execution profile
        for injection into the Copilot system prompt.
        """
        p = self.get_live_execution_profile()

        open_str = "None"
        if p["open_positions"]:
            pos_strs = [
                f"{pos['symbol']} ({pos['qty']} sh @ ₹{pos['avg_buy_price']:.2f}, Live: ₹{pos['live_ltp']:.2f}, "
                f"Unrealized: {pos['unrealized_pnl']:+.2f}, Breakeven Exit: ₹{pos['breakeven_price']:.2f})"
                for pos in p["open_positions"]
            ]
            open_str = "; ".join(pos_strs)

        cooldown_status = "ACTIVE" if p["defensive_cooldown_active"] else "INACTIVE"
        cooldown_detail = f" ({', '.join(p['cooldown_reasons'])})" if p["defensive_cooldown_active"] else ""

        return f"""[TRADER DNA & LIVE BEHAVIORAL SCORECARD]
- Realized Net P&L: ₹{p['realized_net_pnl']:+.2f} across {p['total_trades']} closed swings (Fee Drag: {p['fee_drag_pct']:.1f}%, including ₹{p['total_dp_charges']:.2f} sell DP fees).
- Personal Win Rate: {p['win_rate_pct']:.1f}% ({p['win_count']}W / {p['loss_count']}L) | Avg Ticket: ₹{p['avg_ticket_size']:.2f}.
- Median Holding Discipline: {p.get('median_hold_days', 7.0):.1f} days (Early-Exit Rate: {p.get('early_exit_rate_pct', 0.0):.1f}% on <3d exits).
- Round-Trip Friction: ₹23.60 DP + taxes costs {p['avg_breakeven_pct']:.1f}% on average position size.
- Post-Loss Defensive Cooldown: {cooldown_status}{cooldown_detail}. Max ticket cap: ₹{p['max_ticket_allowed']:.0f} (Size Multiplier: {p.get('size_multiplier', 1.0):.1f}x).
- Active Demat Open Positions: {open_str}.

[MANDATORY PERSONAL COACHING INVARIANTS]
1. HARD MINIMUM NET-TARGET: Never endorse taking profit below +2.5% gross upside. Require >= 3.5% target to guarantee meaningful net return after ₹23.60 DP + taxes.
2. POST-LOSS COOLDOWN: If defensive cooldown is active, cap new trades to <= ₹1,500, apply half-sizing on 3+ losses, and warn against emotional revenge trades.
3. HOLD-WINDOW DISCIPLINE: Emphasize 5-12 trading day swing horizon. Discourage hasty 1-2 day exits that get chopped up by fee drag.
4. LIVE BREAKEVEN RESPECT: Always state the exact breakeven exit price including ₹23.60 DP fee for any proposed ticket."""
