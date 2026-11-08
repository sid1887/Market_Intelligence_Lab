"""
src/quant/execution_engine.py
Paper Trading Execution Engine & Virtual Portfolio Accounting Ledger.
Workstream 8.1: Executes rebalance proposals against market data, applying realistic
Indian equity friction (STT, DP charges, exchange/SEBI fees, slippage) and enforcing
cash solvency invariants.
"""

import json
import math
import uuid
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from src.storage.database import DatabaseManager

logger = logging.getLogger("MIL.ExecutionEngine")

# Indian Statutory Delivery Friction Parameters (Delivery Equity)
STT_RATE = 0.0010                # 0.10% Securities Transaction Tax on both BUY & SELL
EXCHANGE_TURNOVER_AND_SLIP = 0.0005  # 0.05% Exchange + SEBI turnover fees + slippage penalty
BUY_FRICTION_RATE = STT_RATE + EXCHANGE_TURNOVER_AND_SLIP    # 0.0015 (15 bps)
SELL_FRICTION_RATE = STT_RATE + EXCHANGE_TURNOVER_AND_SLIP   # 0.0015 (15 bps)
FLAT_SELL_DP_CHARGE = 15.00       # Flat ₹15.00 Depository Participant charge per SELL leg


class PaperTradingEngine:
    """
    Simulates institutional execution of quantitative rebalance proposals.
    Guarantees:
    1. SELL-before-BUY sequencing: Sell proceeds credit cash before buy orders debit cash.
    2. Strict cash solvency guards: Orders that exceed available cash balance are capped to
       the maximum affordable whole integer shares.
    3. Comprehensive friction accounting: 0.10% STT, 0.05% slippage/fees, and ₹15 flat DP charge.
    4. Mark-to-market portfolio NAV updates.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    def _get_latest_price(self, symbol: str) -> Optional[float]:
        """Fetches the latest official EOD close price for a symbol."""
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT close FROM ohlcv_daily
                WHERE symbol = ? AND is_synthetic = 0
                ORDER BY trading_date DESC LIMIT 1
            """, (symbol,))
            row = cur.fetchone()
            if row and row[0] and float(row[0]) > 0:
                return float(row[0])
            
            # Fallback if only synthetic / unflagged row exists
            cur = conn.execute("""
                SELECT close FROM ohlcv_daily
                WHERE symbol = ?
                ORDER BY trading_date DESC LIMIT 1
            """, (symbol,))
            row = cur.fetchone()
            if row and row[0] and float(row[0]) > 0:
                return float(row[0])
        return None

    def get_account_summary(self, account_id: str = "paper_alpha_1") -> Dict[str, Any]:
        """Calculates real-time MTM portfolio valuation, cash balance, and unrealized P&L."""
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT account_id, cash_balance, total_nav, updated_at
                FROM portfolio_accounts
                WHERE account_id = ?
            """, (account_id,))
            acct_row = cur.fetchone()
            if not acct_row:
                raise ValueError(f"Account '{account_id}' does not exist.")

            cash_balance = float(acct_row["cash_balance"] if isinstance(acct_row, sqlite3.Row) else acct_row[1])

            # Fetch positions
            cur = conn.execute("""
                SELECT symbol, quantity, average_entry_price
                FROM portfolio_positions
                WHERE account_id = ? AND quantity > 0
            """, (account_id,))
            positions = cur.fetchall()

            # Compute friction paid so far
            cur = conn.execute("""
                SELECT COALESCE(SUM(friction_paid), 0.0)
                FROM portfolio_orders
                WHERE account_id = ?
            """, (account_id,))
            total_friction = float(cur.fetchone()[0])

        invested_value = 0.0
        total_cost_basis = 0.0

        for pos in positions:
            sym = pos["symbol"] if isinstance(pos, sqlite3.Row) else pos[0]
            qty = int(pos["quantity"] if isinstance(pos, sqlite3.Row) else pos[1])
            avg_price = float(pos["average_entry_price"] if isinstance(pos, sqlite3.Row) else pos[2])

            ltp = self._get_latest_price(sym) or avg_price
            invested_value += qty * ltp
            total_cost_basis += qty * avg_price

        total_nav = cash_balance + invested_value
        unrealized_pnl = invested_value - total_cost_basis
        unrealized_pnl_pct = (unrealized_pnl / total_cost_basis * 100.0) if total_cost_basis > 0 else 0.0

        # Initial capital baseline (assumes ₹10,00,000 baseline)
        initial_capital = 1000000.0
        total_pnl = total_nav - initial_capital
        total_pnl_pct = (total_pnl / initial_capital) * 100.0

        return {
            "account_id": account_id,
            "cash_balance": round(cash_balance, 2),
            "invested_value": round(invested_value, 2),
            "total_nav": round(total_nav, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "total_friction_paid": round(total_friction, 2),
            "positions_count": len(positions),
            "updated_at": acct_row["updated_at"] if isinstance(acct_row, sqlite3.Row) else acct_row[3]
        }

    def get_positions(self, account_id: str = "paper_alpha_1") -> List[Dict[str, Any]]:
        """Returns all open positions with live MTM pricing, allocation weight, and unrealized P&L."""
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT position_id, symbol, quantity, average_entry_price, updated_at
                FROM portfolio_positions
                WHERE account_id = ? AND quantity > 0
                ORDER BY quantity * average_entry_price DESC
            """, (account_id,))
            rows = cur.fetchall()

            # Get total NAV to compute portfolio weight
            cur_nav = conn.execute("SELECT total_nav FROM portfolio_accounts WHERE account_id = ?", (account_id,))
            nav_row = cur_nav.fetchone()
            total_nav = float(nav_row[0]) if nav_row and nav_row[0] else 1000000.0

        result = []
        for r in rows:
            pos_id = r["position_id"] if isinstance(r, sqlite3.Row) else r[0]
            sym = r["symbol"] if isinstance(r, sqlite3.Row) else r[1]
            qty = int(r["quantity"] if isinstance(r, sqlite3.Row) else r[2])
            avg_price = float(r["average_entry_price"] if isinstance(r, sqlite3.Row) else r[3])
            upd_at = r["updated_at"] if isinstance(r, sqlite3.Row) else r[4]

            ltp = self._get_latest_price(sym) or avg_price
            market_value = qty * ltp
            cost_basis = qty * avg_price
            pnl = market_value - cost_basis
            pnl_pct = (pnl / cost_basis * 100.0) if cost_basis > 0 else 0.0
            weight_pct = (market_value / total_nav * 100.0) if total_nav > 0 else 0.0

            result.append({
                "position_id": pos_id,
                "symbol": sym,
                "quantity": qty,
                "average_entry_price": round(avg_price, 2),
                "current_price": round(ltp, 2),
                "market_value": round(market_value, 2),
                "cost_basis": round(cost_basis, 2),
                "unrealized_pnl": round(pnl, 2),
                "unrealized_pnl_pct": round(pnl_pct, 2),
                "weight_pct": round(weight_pct, 2),
                "updated_at": upd_at
            })
        return result

    def get_orders(self, account_id: str = "paper_alpha_1", limit: int = 100) -> List[Dict[str, Any]]:
        """Returns chronological trade execution blotter."""
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT order_id, account_id, proposal_id, symbol, action, quantity,
                       fill_price, friction_paid, executed_at
                FROM portfolio_orders
                WHERE account_id = ?
                ORDER BY executed_at DESC, rowid DESC
                LIMIT ?
            """, (account_id, limit))
            rows = cur.fetchall()

        result = []
        for r in rows:
            result.append({
                "order_id": r["order_id"] if isinstance(r, sqlite3.Row) else r[0],
                "account_id": r["account_id"] if isinstance(r, sqlite3.Row) else r[1],
                "proposal_id": r["proposal_id"] if isinstance(r, sqlite3.Row) else r[2],
                "symbol": r["symbol"] if isinstance(r, sqlite3.Row) else r[3],
                "action": r["action"] if isinstance(r, sqlite3.Row) else r[4],
                "quantity": int(r["quantity"] if isinstance(r, sqlite3.Row) else r[5]),
                "fill_price": round(float(r["fill_price"] if isinstance(r, sqlite3.Row) else r[6]), 2),
                "friction_paid": round(float(r["friction_paid"] if isinstance(r, sqlite3.Row) else r[7]), 2),
                "executed_at": r["executed_at"] if isinstance(r, sqlite3.Row) else r[8],
            })
        return result

    def execute_proposal(
        self,
        proposal_id: str,
        account_id: str = "paper_alpha_1"
    ) -> Dict[str, Any]:
        """
        Executes a rebalance proposal against the virtual ledger.
        
        Step-by-step Execution Flow:
        1. Validates that proposal exists and is not already 'EXECUTED'.
        2. Retrieves current account NAV, cash balance, and existing positions.
        3. Parses proposal target holdings and computes required target share quantities.
        4. Calculates trade quantities: separates into SELL orders and BUY orders.
        5. Executes SELL orders FIRST:
           - Credits cash balance with net proceeds: (qty * price) - friction.
           - Friction = (qty * price * 0.0015) + 15.00 DP charge.
           - Updates or closes position in portfolio_positions.
           - Logs SELL order to portfolio_orders.
        6. Executes BUY orders SECOND:
           - Evaluates cash solvency: cost_per_share = price * 1.0015.
           - Caps quantity to max_affordable = floor(available_cash / cost_per_share).
           - Debits cash balance: (qty * price * 1.0015).
           - Updates position in portfolio_positions (updating weighted average entry price).
           - Logs BUY order to portfolio_orders.
        7. Recomputes Mark-to-Market total NAV: cash_balance + sum(qty * latest_price).
        8. Updates portfolio_accounts and marks rebalance_proposals status as 'EXECUTED'.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        with self.db.get_connection() as conn:
            # 1. Fetch proposal
            cur = conn.execute("""
                SELECT proposal_id, session_date, status, holdings_after_json
                FROM rebalance_proposals
                WHERE proposal_id = ?
            """, (proposal_id,))
            prop_row = cur.fetchone()
            if not prop_row:
                raise ValueError(f"Proposal '{proposal_id}' not found.")

            status = prop_row["status"] if isinstance(prop_row, sqlite3.Row) else prop_row[2]
            if status == "EXECUTED":
                raise ValueError(f"Proposal '{proposal_id}' has already been executed.")

            holdings_after_raw = prop_row["holdings_after_json"] if isinstance(prop_row, sqlite3.Row) else prop_row[3]
            target_weights: Dict[str, float] = json.loads(holdings_after_raw) if holdings_after_raw else {}

            # 2. Fetch current account state
            cur = conn.execute("""
                SELECT account_id, cash_balance, total_nav
                FROM portfolio_accounts
                WHERE account_id = ?
            """, (account_id,))
            acct_row = cur.fetchone()
            if not acct_row:
                raise ValueError(f"Account '{account_id}' not found.")

            cash_balance = float(acct_row["cash_balance"] if isinstance(acct_row, sqlite3.Row) else acct_row[1])
            total_nav = float(acct_row["total_nav"] if isinstance(acct_row, sqlite3.Row) else acct_row[2])

            # 3. Fetch existing open positions
            cur = conn.execute("""
                SELECT symbol, quantity, average_entry_price
                FROM portfolio_positions
                WHERE account_id = ? AND quantity > 0
            """, (account_id,))
            existing_positions_rows = cur.fetchall()

        current_positions: Dict[str, Dict[str, Any]] = {}
        invested_mtm = 0.0

        for r in existing_positions_rows:
            sym = r["symbol"] if isinstance(r, sqlite3.Row) else r[0]
            qty = int(r["quantity"] if isinstance(r, sqlite3.Row) else r[1])
            avg_p = float(r["average_entry_price"] if isinstance(r, sqlite3.Row) else r[2])
            ltp = self._get_latest_price(sym) or avg_p
            current_positions[sym] = {
                "quantity": qty,
                "average_entry_price": avg_p,
                "latest_price": ltp
            }
            invested_mtm += qty * ltp

        # True live NAV at execution time
        effective_nav = cash_balance + invested_mtm
        if effective_nav <= 0:
            effective_nav = total_nav

        # 4. Determine target quantities and build SELL vs BUY queues
        all_symbols = sorted(set(list(current_positions.keys()) + list(target_weights.keys())))

        sells_queue: List[Dict[str, Any]] = []
        buys_queue: List[Dict[str, Any]] = []

        for sym in all_symbols:
            w_target = target_weights.get(sym, 0.0)
            curr_info = current_positions.get(sym, {"quantity": 0, "average_entry_price": 0.0, "latest_price": 0.0})
            curr_qty = curr_info["quantity"]

            ltp = self._get_latest_price(sym)
            if not ltp or ltp <= 0:
                ltp = curr_info.get("latest_price") or curr_info.get("average_entry_price") or 100.0

            if w_target > 0:
                target_allocation_val = effective_nav * w_target
                target_qty = math.floor(target_allocation_val / ltp)
            else:
                target_qty = 0

            delta_qty = target_qty - curr_qty

            if delta_qty < 0:
                # Need to SELL abs(delta_qty)
                sells_queue.append({
                    "symbol": sym,
                    "quantity": abs(delta_qty),
                    "fill_price": ltp,
                    "current_qty": curr_qty,
                    "avg_entry_price": curr_info["average_entry_price"]
                })
            elif delta_qty > 0:
                # Need to BUY delta_qty
                buys_queue.append({
                    "symbol": sym,
                    "desired_quantity": delta_qty,
                    "fill_price": ltp,
                    "current_qty": curr_qty,
                    "avg_entry_price": curr_info["average_entry_price"]
                })

        executed_orders: List[Dict[str, Any]] = []
        total_friction_in_run = 0.0

        with self.db.get_connection() as conn:
            # -------------------------------------------------------------
            # STEP 5: EXECUTE SELLS FIRST (Release capital + deduct friction)
            # -------------------------------------------------------------
            for sell_item in sells_queue:
                sym = sell_item["symbol"]
                sell_qty = sell_item["quantity"]
                fill_price = sell_item["fill_price"]
                curr_qty = sell_item["current_qty"]
                avg_entry = sell_item["avg_entry_price"]

                gross_val = sell_qty * fill_price
                friction = (gross_val * SELL_FRICTION_RATE) + FLAT_SELL_DP_CHARGE
                net_proceeds = gross_val - friction

                cash_balance += net_proceeds
                total_friction_in_run += friction

                remaining_qty = curr_qty - sell_qty
                order_id = f"ord_{proposal_id}_SELL_{sym}_{uuid.uuid4().hex[:6]}"

                # Log order
                conn.execute("""
                    INSERT INTO portfolio_orders (
                        order_id, account_id, proposal_id, symbol, action,
                        quantity, fill_price, friction_paid, executed_at
                    ) VALUES (?, ?, ?, ?, 'SELL', ?, ?, ?, ?)
                """, (order_id, account_id, proposal_id, sym, sell_qty, fill_price, friction, now_iso))

                # Update position
                if remaining_qty <= 0:
                    conn.execute("""
                        DELETE FROM portfolio_positions
                        WHERE account_id = ? AND symbol = ?
                    """, (account_id, sym))
                    if sym in current_positions:
                        del current_positions[sym]
                else:
                    conn.execute("""
                        UPDATE portfolio_positions
                        SET quantity = ?, updated_at = ?
                        WHERE account_id = ? AND symbol = ?
                    """, (remaining_qty, now_iso, account_id, sym))
                    current_positions[sym]["quantity"] = remaining_qty

                executed_orders.append({
                    "order_id": order_id,
                    "symbol": sym,
                    "action": "SELL",
                    "quantity": sell_qty,
                    "fill_price": fill_price,
                    "gross_value": round(gross_val, 2),
                    "friction_paid": round(friction, 2),
                    "net_proceeds": round(net_proceeds, 2)
                })

            # -------------------------------------------------------------
            # STEP 6: EXECUTE BUYS SECOND (Use settled cash + solvency guard)
            # -------------------------------------------------------------
            for buy_item in buys_queue:
                sym = buy_item["symbol"]
                desired_qty = buy_item["desired_quantity"]
                fill_price = buy_item["fill_price"]
                curr_qty = buy_item["current_qty"]
                avg_entry = buy_item["avg_entry_price"]

                # Cash Solvency Guard:
                # Each share costs fill_price + (fill_price * BUY_FRICTION_RATE)
                effective_cost_per_share = fill_price * (1.0 + BUY_FRICTION_RATE)
                max_affordable_qty = math.floor(cash_balance / effective_cost_per_share) if effective_cost_per_share > 0 else 0
                executable_qty = min(desired_qty, max_affordable_qty)

                if executable_qty <= 0:
                    logger.warning(
                        f"Solvency limit reached: Skipping BUY for {sym}. "
                        f"Desired={desired_qty}, Affordable={max_affordable_qty}, Cash=₹{cash_balance:.2f}"
                    )
                    continue

                gross_val = executable_qty * fill_price
                friction = gross_val * BUY_FRICTION_RATE
                net_debit = gross_val + friction

                cash_balance -= net_debit
                total_friction_in_run += friction

                new_total_qty = curr_qty + executable_qty
                # Update weighted average entry price
                if curr_qty > 0:
                    new_avg_entry = ((curr_qty * avg_entry) + (executable_qty * fill_price)) / new_total_qty
                else:
                    new_avg_entry = fill_price

                order_id = f"ord_{proposal_id}_BUY_{sym}_{uuid.uuid4().hex[:6]}"

                # Log order
                conn.execute("""
                    INSERT INTO portfolio_orders (
                        order_id, account_id, proposal_id, symbol, action,
                        quantity, fill_price, friction_paid, executed_at
                    ) VALUES (?, ?, ?, ?, 'BUY', ?, ?, ?, ?)
                """, (order_id, account_id, proposal_id, sym, executable_qty, fill_price, friction, now_iso))

                # Update or insert position
                pos_id = f"pos_{account_id}_{sym}"
                conn.execute("""
                    INSERT INTO portfolio_positions (
                        position_id, account_id, symbol, quantity, average_entry_price, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_id, symbol) DO UPDATE SET
                        quantity = excluded.quantity,
                        average_entry_price = excluded.average_entry_price,
                        updated_at = excluded.updated_at
                """, (pos_id, account_id, sym, new_total_qty, new_avg_entry, now_iso))

                current_positions[sym] = {
                    "quantity": new_total_qty,
                    "average_entry_price": new_avg_entry,
                    "latest_price": fill_price
                }

                executed_orders.append({
                    "order_id": order_id,
                    "symbol": sym,
                    "action": "BUY",
                    "quantity": executable_qty,
                    "requested_quantity": desired_qty,
                    "fill_price": fill_price,
                    "gross_value": round(gross_val, 2),
                    "friction_paid": round(friction, 2),
                    "net_debit": round(net_debit, 2),
                    "was_capped": executable_qty < desired_qty
                })

            # -------------------------------------------------------------
            # STEP 7: RECOMPUTE MARK-TO-MARKET NAV & UPDATE ACCOUNT
            # -------------------------------------------------------------
            total_invested = 0.0
            for sym, pos_data in current_positions.items():
                p_qty = pos_data["quantity"]
                p_price = self._get_latest_price(sym) or pos_data["average_entry_price"]
                total_invested += p_qty * p_price

            final_nav = cash_balance + total_invested

            conn.execute("""
                UPDATE portfolio_accounts
                SET cash_balance = ?, total_nav = ?, updated_at = ?
                WHERE account_id = ?
            """, (round(cash_balance, 2), round(final_nav, 2), now_iso, account_id))

            # -------------------------------------------------------------
            # STEP 8: MARK PROPOSAL AS EXECUTED
            # -------------------------------------------------------------
            conn.execute("""
                UPDATE rebalance_proposals
                SET status = 'EXECUTED'
                WHERE proposal_id = ?
            """, (proposal_id,))
            conn.commit()

        logger.info(
            f"Executed proposal {proposal_id} on account {account_id}: "
            f"{len(executed_orders)} orders executed, Total Friction=₹{total_friction_in_run:.2f}, "
            f"Final NAV=₹{final_nav:,.2f}, Final Cash=₹{cash_balance:,.2f}"
        )

        return {
            "proposal_id": proposal_id,
            "account_id": account_id,
            "status": "EXECUTED",
            "orders_count": len(executed_orders),
            "orders": executed_orders,
            "total_friction_paid": round(total_friction_in_run, 2),
            "cash_balance": round(cash_balance, 2),
            "invested_value": round(total_invested, 2),
            "total_nav": round(final_nav, 2),
            "executed_at": now_iso
        }
