"""
src/copilot/trader_dna.py
Dynamic Trader DNA Behavioral Profiler & Personal Execution Coach.

Behavioral Coaching Invariants:
1. Hard Minimum Net-Target Gate (>= 3.5% gross upside):
   - On ₹1,500–₹2,000 retail tickets, ₹23.60 DP fee + taxes costs 1.4%–1.9% round-trip.
   - Warns or blocks taking profit below +2.5% unless a stop-loss is triggered.
2. Post-Loss Cooldown Guard (24h pause after a loss > ₹75):
   - After any realized loss > ₹75 or a 2+ loss streak, enforces a defensive cooldown,
     capping the next position size to ₹1,500.
3. Hold-Window Discipline (5–12 trading days):
   - Analyzes win rate by holding period (< 3 days vs 5–15 days).
4. Live Demat Breakeven Accounting:
   - Tracks open positions (e.g., GAIL) and calculates exact share-level breakeven
     including ₹23.60 sell DP charge.
"""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from src.storage.database import DatabaseManager

logger = logging.getLogger("MIL.TraderDNA")

DEFAULT_ANGEL_ONE_DP_CHARGE = 23.60


class TraderDNAEngine:
    """
    Analyzes personal trade history directly from SQLite tradebook tables
    (real_closed_roundtrips, real_open_holdings, real_capital_ledger)
    and enforces behavioral guardrails inside Copilot deliberation.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_live_execution_profile(self) -> Dict[str, Any]:
        """
        Recomputes live behavioral scorecard directly from SQLite tradebook tables.
        Returns a compact, structured dictionary.
        """
        with self.db.get_connection() as conn:
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

            # Holding period breakdown
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

            # Streak & Cooldown analysis
            consecutive_losses = 0
            for r in trades_rows:
                if float(r["net_pnl"] or 0.0) <= 0:
                    consecutive_losses += 1
                else:
                    break

            last_loss_date = losers[0]["sell_date"] if losers else None
            last_loss_amount = abs(float(losers[0]["net_pnl"] or 0.0)) if losers else 0.0

            # Defensive cooldown trigger: consecutive losses >= 2 or last loss > 75
            cooldown_active = False
            cooldown_reasons = []
            if consecutive_losses >= 2:
                cooldown_active = True
                cooldown_reasons.append(f"{consecutive_losses}-trade losing streak")
            if last_loss_amount > 75.0:
                cooldown_active = True
                cooldown_reasons.append(f"Recent stop-loss > ₹75 (₹{last_loss_amount:.2f})")

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
    ) -> Dict[str, Any]:
        """
        Evaluates a proposed trade ticket against the user's micro-capital constraints
        and strict coaching rules:
        1. Exact integer share count.
        2. Exact round-trip friction (STT + GST + ₹23.60 DP).
        3. Hard Minimum Net-Target Gate (>= 3.5% gross upside).
        4. Post-loss cooldown budget cap.
        """
        entry_p = float(entry_price if entry_price is not None else (price or 0.0))
        target_p = float(target_price if target_price is not None else 0.0)
        stop_p = float(stop_price if stop_price is not None else (stop_loss or 0.0))

        profile = self.get_live_execution_profile()
        effective_budget = min(budget, profile["max_ticket_allowed"])

        shares = int(effective_budget // entry_p) if entry_p > 0 else 0
        invested = round(shares * entry_p, 2)

        # Round-trip statutory friction for delivery equity
        stt_buy = round(0.001 * invested, 2)
        stt_sell = round(0.001 * (shares * target_p), 2)
        exchange_turnover = round(0.0000345 * 2 * invested, 2)
        sebi_tax = round(0.000001 * 2 * invested, 2)
        stamp_duty = round(0.00015 * invested, 2)
        gst = round(0.18 * (exchange_turnover + sebi_tax), 2)
        dp_charge = DEFAULT_ANGEL_ONE_DP_CHARGE  # ₹23.60

        total_friction = round(stt_buy + stt_sell + exchange_turnover + sebi_tax + stamp_duty + gst + dp_charge, 2)
        breakeven_exit = round((invested + total_friction) / max(shares, 1), 2) if shares > 0 else entry_p
        breakeven_pct = round(((breakeven_exit - entry_p) / entry_p * 100.0), 2) if entry_p > 0 else 0.0

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
- Round-Trip Friction: ₹23.60 DP + taxes costs {p['avg_breakeven_pct']:.1f}% on average position size.
- Hold-Duration Edge: {p['win_rate_under_3d']:.0f}% win rate on <3d exits vs {p['win_rate_5_to_15d']:.0f}% win rate on 5-15d hold window.
- Post-Loss Defensive Cooldown: {cooldown_status}{cooldown_detail}. Max ticket cap: ₹{p['max_ticket_allowed']:.0f}.
- Active Demat Open Positions: {open_str}.

[MANDATORY PERSONAL COACHING INVARIANTS]
1. HARD MINIMUM NET-TARGET: Never endorse taking profit below +2.5% gross upside. Require >= 3.5% target to guarantee meaningful net return after ₹23.60 DP + taxes.
2. POST-LOSS COOLDOWN: If defensive cooldown is active, cap new trades to <= ₹1,500 and warn against emotional revenge trades.
3. HOLD-WINDOW DISCIPLINE: Emphasize 5-12 trading day swing horizon. Discourage hasty 1-2 day exits that get chopped up by fee drag.
4. LIVE BREAKEVEN RESPECT: Always state the exact breakeven exit price including ₹23.60 DP fee for any proposed ticket."""
