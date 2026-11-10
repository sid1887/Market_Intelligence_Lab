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
    Simulates institutional execution of quantitative rebalance proposals and discretionary sandbox trading.
    Guarantees:
    1. SELL-before-BUY sequencing: Sell proceeds credit cash before buy orders debit cash.
    2. Strict cash solvency guards: Orders that exceed available cash balance are capped to
       the maximum affordable whole integer shares.
    3. Comprehensive friction accounting: Tiered retail/institutional rates (STT, slippage/fees, DP fee).
    4. Mark-to-market portfolio NAV updates and dynamic user-defined capital tracking.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.ensure_default_accounts()

    def ensure_default_accounts(self) -> None:
        """Provisions default accounts (paper_alpha_2, paper_manual_1, paper_alpha_1) if absent."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            # Check if columns exist
            cur = conn.execute("PRAGMA table_info(portfolio_accounts)")
            cols = {r[1] for r in cur.fetchall()}
            if "initial_capital" not in cols:
                return  # Schema migration pending

            # 1. paper_alpha_2: Systematic V2 Micro-Capital Engine
            conn.execute("""
                INSERT OR IGNORE INTO portfolio_accounts (
                    account_id, cash_balance, total_nav, updated_at,
                    initial_capital, net_capital_deployed, account_type, engine_version, fee_tier
                ) VALUES ('paper_alpha_2', 1600.0, 1600.0, ?, 1600.0, 1600.0, 'SYSTEMATIC', 'alpha_v2', 'RETAIL_MICRO');
            """, (now_iso,))

            # 2. paper_manual_1: Discretionary FrontPage-style Sandbox
            conn.execute("""
                INSERT OR IGNORE INTO portfolio_accounts (
                    account_id, cash_balance, total_nav, updated_at,
                    initial_capital, net_capital_deployed, account_type, engine_version, fee_tier
                ) VALUES ('paper_manual_1', 1600.0, 1600.0, ?, 1600.0, 1600.0, 'MANUAL', 'manual_v1', 'RETAIL_MICRO');
            """, (now_iso,))

            # 3. paper_alpha_1: Legacy Systematic Institutional
            conn.execute("""
                INSERT OR IGNORE INTO portfolio_accounts (
                    account_id, cash_balance, total_nav, updated_at,
                    initial_capital, net_capital_deployed, account_type, engine_version, fee_tier
                ) VALUES ('paper_alpha_1', 1000000.0, 1000000.0, ?, 1000000.0, 1000000.0, 'SYSTEMATIC', 'alpha_v1', 'INSTITUTIONAL');
            """, (now_iso,))
            conn.execute("""
                UPDATE portfolio_accounts
                SET fee_tier = 'INSTITUTIONAL'
                WHERE account_id = 'paper_alpha_1' AND fee_tier = 'RETAIL_MICRO';
            """)

    def _calculate_friction(self, action: str, order_value: float, fee_tier: str = "RETAIL_MICRO") -> float:
        """
        Computes statutory and exchange friction based on account fee tier.
        RETAIL_MICRO: 12 bps (0.0012) + flat/capped DP fee min(5.0, 0.5% order_val) on SELLs.
        INSTITUTIONAL: 15 bps (0.0015) + flat ₹15.00 DP fee on SELLs.
        """
        if order_value <= 0:
            return 0.0

        if fee_tier == "RETAIL_MICRO":
            base_rate = 0.0012  # 12 bps
            base_friction = order_value * base_rate
            if action.upper() == "SELL":
                dp_fee = min(5.0, round(order_value * 0.005, 2))
                return round(base_friction + dp_fee, 2)
            return round(base_friction, 2)
        else:
            base_rate = 0.0015  # 15 bps
            base_friction = order_value * base_rate
            if action.upper() == "SELL":
                return round(base_friction + FLAT_SELL_DP_CHARGE, 2)
            return round(base_friction, 2)

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
        """Calculates real-time MTM portfolio valuation, cash balance, and dynamic P&L from custom user capital."""
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT account_id, cash_balance, total_nav, updated_at,
                       COALESCE(initial_capital, 1600.0) as initial_capital,
                       COALESCE(net_capital_deployed, 1600.0) as net_capital_deployed,
                       COALESCE(account_type, 'SYSTEMATIC') as account_type,
                       COALESCE(engine_version, 'alpha_v2') as engine_version,
                       COALESCE(fee_tier, 'RETAIL_MICRO') as fee_tier
                FROM portfolio_accounts
                WHERE account_id = ?
            """, (account_id,))
            acct_row = cur.fetchone()
            if not acct_row:
                raise ValueError(f"Account '{account_id}' does not exist.")

            cash_balance = float(acct_row["cash_balance"])
            initial_capital = float(acct_row["initial_capital"])
            net_capital_deployed = float(acct_row["net_capital_deployed"])
            account_type = str(acct_row["account_type"])
            engine_version = str(acct_row["engine_version"])
            fee_tier = str(acct_row["fee_tier"])

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

        # Dynamic capital P&L strictly derived from user's custom net_capital_deployed
        total_pnl = total_nav - net_capital_deployed
        total_pnl_pct = (total_pnl / net_capital_deployed * 100.0) if net_capital_deployed > 0 else 0.0

        # Sync total_nav back to portfolio_accounts if drifted
        with self.db.get_connection() as conn:
            conn.execute("""
                UPDATE portfolio_accounts
                SET total_nav = ?
                WHERE account_id = ?
            """, (round(total_nav, 2), account_id))

        return {
            "account_id": account_id,
            "cash_balance": round(cash_balance, 2),
            "invested_value": round(invested_value, 2),
            "equity_value": round(invested_value, 2),  # Frontend compatibility alias
            "cost_basis": round(total_cost_basis, 2),
            "total_nav": round(total_nav, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
            "total_pnl": round(total_pnl, 2),
            "net_total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "net_total_pnl_pct": round(total_pnl_pct, 2),
            "total_friction_paid": round(total_friction, 2),
            "positions_count": len(positions),
            "position_count": len(positions),  # Frontend compatibility alias
            "initial_capital": round(initial_capital, 2),
            "net_capital_deployed": round(net_capital_deployed, 2),
            "account_type": account_type,
            "engine_version": engine_version,
            "fee_tier": fee_tier,
            "updated_at": acct_row["updated_at"] if isinstance(acct_row, sqlite3.Row) else acct_row[3]
        }

    def set_or_reset_capital(
        self,
        account_id: str,
        new_capital: float,
        fee_tier: str = "RETAIL_MICRO"
    ) -> Dict[str, Any]:
        """
        Validates new_capital >= 100.0 and atomically resets the account's capital seed,
        clearing active positions and trade history for a fresh quantitative run.
        """
        if new_capital < 100.0:
            raise ValueError(f"Initial capital must be at least ₹100.00. Received: ₹{new_capital:.2f}")

        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            # 1. Clear active positions & orders for this account
            conn.execute("DELETE FROM portfolio_positions WHERE account_id = ?", (account_id,))
            conn.execute("DELETE FROM portfolio_orders WHERE account_id = ?", (account_id,))

            # 2. Update account record with fresh capital seed
            cur = conn.execute("SELECT account_id FROM portfolio_accounts WHERE account_id = ?", (account_id,))
            if cur.fetchone():
                conn.execute("""
                    UPDATE portfolio_accounts
                    SET initial_capital = ?,
                        net_capital_deployed = ?,
                        cash_balance = ?,
                        total_nav = ?,
                        fee_tier = ?,
                        updated_at = ?
                    WHERE account_id = ?
                """, (new_capital, new_capital, new_capital, new_capital, fee_tier, now_iso, account_id))
            else:
                conn.execute("""
                    INSERT INTO portfolio_accounts (
                        account_id, cash_balance, total_nav, updated_at,
                        initial_capital, net_capital_deployed, account_type, engine_version, fee_tier
                    ) VALUES (?, ?, ?, ?, ?, ?, 'SYSTEMATIC', 'alpha_v2', ?)
                """, (account_id, new_capital, new_capital, now_iso, new_capital, new_capital, fee_tier))

        logger.info(f"Account '{account_id}' capital reset to ₹{new_capital:,.2f} ({fee_tier})")
        return self.get_account_summary(account_id)

    def adjust_cash(self, account_id: str, delta_cash: float) -> Dict[str, Any]:
        """
        Allows depositing (delta_cash > 0) or withdrawing (delta_cash < 0, up to cash_balance)
        funds without wiping active positions, adjusting net_capital_deployed so P&L remains exact.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT cash_balance, net_capital_deployed, total_nav
                FROM portfolio_accounts
                WHERE account_id = ?
            """, (account_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"Account '{account_id}' does not exist.")

            curr_cash = float(row["cash_balance"])
            curr_net = float(row["net_capital_deployed"])
            curr_nav = float(row["total_nav"])

            if delta_cash < 0 and (curr_cash + delta_cash) < 0:
                raise ValueError(
                    f"Insufficient cash balance for withdrawal of ₹{abs(delta_cash):,.2f}. "
                    f"Available cash: ₹{curr_cash:,.2f}"
                )

            new_cash = round(curr_cash + delta_cash, 2)
            new_net = round(curr_net + delta_cash, 2)
            new_nav = round(curr_nav + delta_cash, 2)

            conn.execute("""
                UPDATE portfolio_accounts
                SET cash_balance = ?,
                    net_capital_deployed = ?,
                    total_nav = ?,
                    updated_at = ?
                WHERE account_id = ?
            """, (new_cash, new_net, new_nav, now_iso, account_id))

        logger.info(f"Adjusted cash for '{account_id}' by {delta_cash:+.2f} (New cash: ₹{new_cash:,.2f})")
        return self.get_account_summary(account_id)

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
        """Returns chronological trade execution blotter with dynamic gross value and thesis note."""
        with self.db.get_connection() as conn:
            cur = conn.execute("PRAGMA table_info(portfolio_orders)")
            cols = {r["name"] if isinstance(r, sqlite3.Row) else r[1] for r in cur.fetchall()}
            has_thesis = "thesis_note" in cols
            has_realized = "realized_pnl" in cols

            select_extra = ""
            if has_thesis:
                select_extra += ", thesis_note"
            if has_realized:
                select_extra += ", realized_pnl"

            cur = conn.execute(f"""
                SELECT order_id, account_id, proposal_id, symbol, action, quantity,
                       fill_price, friction_paid, executed_at{select_extra}
                FROM portfolio_orders
                WHERE account_id = ?
                ORDER BY executed_at DESC, rowid DESC
                LIMIT ?
            """, (account_id, limit))
            rows = cur.fetchall()

        result = []
        for r in rows:
            qty = int(r["quantity"] if isinstance(r, sqlite3.Row) else r[5])
            fill_p = round(float(r["fill_price"] if isinstance(r, sqlite3.Row) else r[6]), 2)
            gross_val = round(qty * fill_p, 2)
            fric = round(float(r["friction_paid"] if isinstance(r, sqlite3.Row) else r[7]), 2)
            thesis = None
            realized = 0.0
            if isinstance(r, sqlite3.Row):
                thesis = r["thesis_note"] if "thesis_note" in r.keys() else None
                realized = float(r["realized_pnl"]) if "realized_pnl" in r.keys() and r["realized_pnl"] is not None else 0.0

            result.append({
                "order_id": r["order_id"] if isinstance(r, sqlite3.Row) else r[0],
                "account_id": r["account_id"] if isinstance(r, sqlite3.Row) else r[1],
                "proposal_id": r["proposal_id"] if isinstance(r, sqlite3.Row) else r[2],
                "symbol": r["symbol"] if isinstance(r, sqlite3.Row) else r[3],
                "action": r["action"] if isinstance(r, sqlite3.Row) else r[4],
                "quantity": qty,
                "fill_price": fill_p,
                "gross_value": gross_val,
                "friction_paid": fric,
                "thesis_note": thesis,
                "realized_pnl": realized,
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
                SELECT account_id, cash_balance, total_nav, COALESCE(fee_tier, 'RETAIL_MICRO') as fee_tier
                FROM portfolio_accounts
                WHERE account_id = ?
            """, (account_id,))
            acct_row = cur.fetchone()
            if not acct_row:
                raise ValueError(f"Account '{account_id}' not found.")

            cash_balance = float(acct_row["cash_balance"] if isinstance(acct_row, sqlite3.Row) else acct_row[1])
            total_nav = float(acct_row["total_nav"] if isinstance(acct_row, sqlite3.Row) else acct_row[2])
            fee_tier = str(acct_row["fee_tier"] if isinstance(acct_row, sqlite3.Row) else acct_row[3])

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
                ratio = target_allocation_val / ltp if ltp > 0 else 0
                target_qty = int(round(ratio)) if ratio >= 0.75 else int(math.floor(ratio))
                target_qty = max(1, target_qty)
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
                friction = self._calculate_friction("SELL", gross_val, fee_tier)
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
                buy_fric_rate = 0.0012 if fee_tier == "RETAIL_MICRO" else 0.0015
                effective_cost_per_share = fill_price * (1.0 + buy_fric_rate)
                max_affordable_qty = math.floor(cash_balance / effective_cost_per_share) if effective_cost_per_share > 0 else 0
                executable_qty = min(desired_qty, max_affordable_qty)

                if executable_qty <= 0:
                    logger.warning(
                        f"Solvency limit reached: Skipping BUY for {sym}. "
                        f"Desired={desired_qty}, Affordable={max_affordable_qty}, Cash=₹{cash_balance:.2f}"
                    )
                    continue

                gross_val = executable_qty * fill_price
                friction = self._calculate_friction("BUY", gross_val, fee_tier)
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

    def _compute_frontpage_analysis_card(self, symbol: str, ltp: float) -> Dict[str, Any]:
        """
        Generates FrontPage-style system analysis card:
        - alpha_rank: Rank out of active universe
        - blended_score: Score [0, 100]
        - factor_breakdown: {tactical_20d, trend_60d, structural_200d, rsi_14, volatility_20d, sentiment_score}
        - regime_alignment: whether price is above 50D and 200D SMA
        - portfolio_impact: post-trade weight, new cash, sector warning
        - system_verdict: 'STRONG_BUY' | 'ACCUMULATE' | 'HOLD_NEUTRAL' | 'AVOID_WEAK_TREND' + 2-sentence explanation
        """
        sym = symbol.strip().upper()
        with self.db.get_connection() as conn:
            has_factors_daily = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='factors_daily'").fetchone()[0] > 0
            has_quant_factors = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='quant_factors_daily'").fetchone()[0] > 0

            fac_row = None
            if has_factors_daily:
                fac_row = conn.execute("""
                    SELECT f.sma_50, f.sma_200, f.rsi_14, f.volatility_20d, f.ret_20d, 
                           COALESCE(f.momentum_1y, f.ret_20d * 3.0) as ret_60d,
                           COALESCE(s.company_name, f.symbol) as company_name,
                           COALESCE(s.sector, 'Unclassified') as sector
                    FROM factors_daily f
                    LEFT JOIN securities_master s ON f.symbol = s.symbol
                    WHERE f.symbol = ?
                    ORDER BY f.trading_date DESC LIMIT 1
                """, (sym,)).fetchone()

            if not fac_row and has_quant_factors:
                fac_row = conn.execute("""
                    SELECT q.sma_50, q.sma_200, 50.0 as rsi_14, COALESCE(q.vol_20d_annualized, 0.25) as volatility_20d,
                           q.ret_20d, 0.05 as ret_60d,
                           COALESCE(s.company_name, q.symbol) as company_name,
                           COALESCE(s.sector, 'Unclassified') as sector
                    FROM quant_factors_daily q
                    LEFT JOIN securities_master s ON q.symbol = s.symbol
                    WHERE q.symbol = ?
                    ORDER BY q.trading_date DESC LIMIT 1
                """, (sym,)).fetchone()

            news_row = conn.execute("""
                SELECT AVG(sentiment_score) as avg_sent, COUNT(*) as article_count
                FROM stock_news_articles
                WHERE symbol = ?
            """, (sym,)).fetchone()

            total_active = conn.execute("SELECT COUNT(DISTINCT symbol) FROM ohlcv_daily WHERE series = 'EQ'").fetchone()[0] or 181

        sma_50 = float(fac_row["sma_50"]) if fac_row and fac_row["sma_50"] else (ltp * 0.98)
        sma_200 = float(fac_row["sma_200"]) if fac_row and fac_row["sma_200"] else (ltp * 0.95)
        rsi_14 = float(fac_row["rsi_14"]) if fac_row and fac_row["rsi_14"] else 55.0
        vol_20d = float(fac_row["volatility_20d"]) if fac_row and fac_row["volatility_20d"] else 0.22
        ret_20d = float(fac_row["ret_20d"]) if fac_row and fac_row["ret_20d"] else 0.03
        ret_60d = float(fac_row["ret_60d"]) if fac_row and fac_row["ret_60d"] else 0.08
        comp_name = str(fac_row["company_name"]) if fac_row and fac_row["company_name"] else sym
        sector = str(fac_row["sector"]) if fac_row and fac_row["sector"] else "Equities"

        sent_score = round(float(news_row[0]), 3) if news_row and news_row[0] is not None else 0.0
        news_count = int(news_row[1]) if news_row and news_row[1] else 0

        above_50d = bool(ltp > sma_50)
        above_200d = bool(ltp > sma_200)

        tactical_score = max(0.0, min(100.0, round(50.0 + (ret_20d / max(0.05, vol_20d)) * 25.0, 1)))
        trend_score = max(0.0, min(100.0, round(50.0 + (ret_60d / max(0.05, vol_20d)) * 20.0, 1)))
        dist_200_pct = round(((ltp - sma_200) / sma_200) * 100.0, 2) if sma_200 > 0 else 0.0
        structural_score = max(0.0, min(100.0, round(50.0 + dist_200_pct * 1.5, 1)))
        rsi_score = max(0.0, min(100.0, round(100.0 - abs(rsi_14 - 60.0) * 2.0, 1)))
        low_vol_score = max(0.0, min(100.0, round(100.0 - (vol_20d * 150.0), 1)))
        news_sentiment_score = max(0.0, min(100.0, round(50.0 + (sent_score * 50.0), 1)))

        blended_score = round(
            0.25 * tactical_score +
            0.20 * trend_score +
            0.15 * structural_score +
            0.15 * rsi_score +
            0.15 * low_vol_score +
            0.10 * news_sentiment_score,
            1
        )

        alpha_rank = max(1, min(total_active, int(round((1.0 - (blended_score / 100.0)) * total_active))))

        if above_200d and rsi_14 >= 50.0 and ret_20d > 0.02:
            system_verdict = "STRONG_BUY"
            explanation = (
                f"{sym} displays strong structural accumulation (+{dist_200_pct:.1f}% above 200 SMA) "
                f"with bullish 20D risk-adjusted momentum (+{ret_20d*100:.1f}%). "
                f"Factor alignment (Blended {blended_score}/100, Rank #{alpha_rank}/{total_active}) favors asymmetric capital compounding."
            )
        elif above_200d or ret_20d > 0.0:
            system_verdict = "ACCUMULATE"
            explanation = (
                f"{sym} is maintaining positive trend persistence above key structural moving averages. "
                f"Recent 7D news sentiment is {('positive' if sent_score > 0.1 else 'neutral')} with healthy volume absorption."
            )
        elif not above_200d and ret_20d < -0.05:
            system_verdict = "AVOID_WEAK_TREND"
            explanation = (
                f"{sym} is currently consolidating below its 200 SMA with negative short-term momentum. "
                f"Elevated downside dispersion indicates institutional risk-off behavior; avoid until structural breakout."
            )
        else:
            system_verdict = "HOLD_NEUTRAL"
            explanation = (
                f"{sym} exhibits balanced risk/reward dynamics near median volatility levels. "
                f"Hold current allocation and await catalyst confirmation."
            )

        trend_regime = "ABOVE_200_SMA" if above_200d else "BELOW_200_SMA"

        return {
            "symbol": sym,
            "company_name": comp_name,
            "sector": sector,
            "ltp": round(ltp, 2),
            "alpha_rank": alpha_rank,
            "universe_total": total_active,
            "blended_score": blended_score,
            "system_verdict": system_verdict,
            "momentum_verdict": system_verdict,
            "verdict_explanation": explanation,
            "signal_summary": explanation,
            "trend_regime": trend_regime,
            "rsi_14": round(rsi_14, 1),
            "volatility_ann_pct": round(vol_20d * 100, 2),
            "regime_alignment": {
                "above_50d_sma": above_50d,
                "above_200d_sma": above_200d,
                "dist_sma200_pct": dist_200_pct,
                "sma_50": round(sma_50, 2),
                "sma_200": round(sma_200, 2)
            },
            "factor_breakdown": {
                "tactical_20d": tactical_score,
                "trend_60d": trend_score,
                "structural_200d": structural_score,
                "rsi_14": round(rsi_14, 1),
                "rsi_regime": rsi_score,
                "volatility_20d": round(vol_20d, 3),
                "low_vol_quality": low_vol_score,
                "news_sentiment_score": news_sentiment_score,
                "news_sentiment_raw": sent_score,
                "recent_articles_count": news_count
            }
        }

    def preview_manual_order(
        self,
        account_id: str,
        symbol: str,
        action: str,
        amount_inr: Optional[float] = None,
        quantity: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Pre-Trade Intelligence & Order Preview (GET /api/v1/portfolio/manual/preview).
        Resolves latest market price, computes whole shares, cash solvency, portfolio impact,
        and generates FrontPage-style system analysis card.
        """
        sym = symbol.strip().upper()
        act = action.strip().upper()
        if act not in ("BUY", "SELL"):
            raise ValueError(f"Invalid action '{action}'. Must be 'BUY' or 'SELL'.")

        acct_sum = self.get_account_summary(account_id)
        fee_tier = acct_sum.get("fee_tier", "RETAIL_MICRO")
        cash_balance = acct_sum["cash_balance"]

        ltp = self._get_latest_price(sym)
        if not ltp or ltp <= 0:
            raise ValueError(f"Unable to resolve valid market price for symbol '{sym}'.")

        can_afford = True
        min_required_inr = round(ltp * (1.0012 if fee_tier == "RETAIL_MICRO" else 1.0015), 2)

        if amount_inr is not None and (quantity is None or quantity <= 0):
            if amount_inr <= 0:
                raise ValueError("amount_inr must be strictly positive.")
            cost_per_share = ltp * (1.0012 if fee_tier == "RETAIL_MICRO" else 1.0015)
            q = int(math.floor(amount_inr / cost_per_share)) if act == "BUY" else int(math.floor(amount_inr / ltp))
            if q <= 0:
                can_afford = False
                needed = round(min_required_inr - amount_inr, 2) if amount_inr < min_required_inr else min_required_inr
                analysis_card = self._compute_frontpage_analysis_card(sym, ltp)
                return {
                    "account_id": account_id,
                    "symbol": sym,
                    "action": act,
                    "ltp": round(ltp, 2),
                    "current_price": round(ltp, 2),
                    "requested_amount_inr": amount_inr,
                    "shares": 0,
                    "quantity": 0,
                    "calculated_quantity": 0,
                    "gross_value": 0.0,
                    "estimated_friction": 0.0,
                    "net_total_inr": 0.0,
                    "net_cash_required": 0.0,
                    "can_afford": False,
                    "is_solvency_approved": False,
                    "min_required_inr": min_required_inr,
                    "message": f"₹{amount_inr:.2f} is insufficient to buy 1 whole share of {sym} (Price: ₹{ltp:.2f} + friction). Need an additional ₹{needed:.2f}.",
                    "current_cash_balance": cash_balance,
                    "account_cash_balance": cash_balance,
                    "post_trade_cash_balance": cash_balance,
                    "system_analysis": analysis_card,
                    "frontpage_card": analysis_card
                }
            shares = q
        elif quantity is not None:
            if quantity <= 0:
                raise ValueError("quantity must be a positive integer.")
            shares = int(quantity)
        else:
            shares = 1

        gross_value = round(shares * ltp, 2)
        friction = self._calculate_friction(act, gross_value, fee_tier)
        net_required = round(gross_value + friction, 2) if act == "BUY" else round(gross_value - friction, 2)

        is_solvent = (net_required <= cash_balance) if act == "BUY" else True

        with self.db.get_connection() as conn:
            cur = conn.execute(
                "SELECT quantity, average_entry_price FROM portfolio_positions WHERE account_id = ? AND symbol = ?",
                (account_id, sym)
            )
            pos_row = cur.fetchone()
            curr_qty = int(pos_row["quantity"]) if pos_row else 0

        if act == "SELL" and shares > curr_qty:
            raise ValueError(f"Cannot SELL {shares} shares of {sym}. Active holding is {curr_qty} shares.")

        curr_pos_val = curr_qty * ltp
        new_qty = (curr_qty + shares) if act == "BUY" else (curr_qty - shares)
        new_pos_val = new_qty * ltp
        new_cash = round(cash_balance - net_required, 2) if act == "BUY" else round(cash_balance + net_required, 2)
        new_nav = round(new_cash + (acct_sum["invested_value"] - curr_pos_val + new_pos_val), 2)
        post_trade_weight_pct = round((new_pos_val / new_nav * 100.0), 2) if new_nav > 0 else 0.0
        concentration_warning = post_trade_weight_pct > 35.0

        analysis_card = self._compute_frontpage_analysis_card(sym, ltp)

        return {
            "account_id": account_id,
            "symbol": sym,
            "action": act,
            "shares": shares,
            "quantity": shares,
            "calculated_quantity": shares,
            "ltp": round(ltp, 2),
            "current_price": round(ltp, 2),
            "gross_value": gross_value,
            "estimated_friction": friction,
            "net_total_inr": net_required,
            "net_cash_required": net_required,
            "can_afford": is_solvent,
            "is_solvency_approved": is_solvent,
            "min_required_inr": min_required_inr,
            "current_cash_balance": cash_balance,
            "account_cash_balance": cash_balance,
            "post_trade_cash_balance": new_cash,
            "current_shares_held": curr_qty,
            "post_trade_shares_held": new_qty,
            "post_trade_weight_pct": post_trade_weight_pct,
            "concentration_warning": concentration_warning,
            "system_analysis": analysis_card,
            "frontpage_card": analysis_card
        }

    def execute_manual_order(
        self,
        account_id: str,
        symbol: str,
        action: str,
        amount_inr: Optional[float] = None,
        quantity: Optional[int] = None,
        thesis_note: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes atomic BUY or SELL on paper_manual_1 (or any account).
        Updates cash_balance, portfolio_positions (weighted average entry price on BUY),
        calculates realized P&L on SELL, and logs order with fill + thesis_note + analysis snapshot.
        """
        prev = self.preview_manual_order(
            account_id=account_id,
            symbol=symbol,
            action=action,
            amount_inr=amount_inr,
            quantity=quantity
        )

        if not prev.get("can_afford", False):
            raise ValueError(prev.get("message") or "Insufficient cash balance to execute order.")

        sym = prev["symbol"]
        act = prev["action"]
        shares = prev["shares"]
        ltp = prev["ltp"]
        gross_val = prev["gross_value"]
        friction = prev["estimated_friction"]
        now_iso = datetime.now(timezone.utc).isoformat()
        order_id = f"ord_man_{act}_{sym}_{uuid.uuid4().hex[:6]}"

        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT cash_balance, total_nav FROM portfolio_accounts WHERE account_id = ?", (account_id,))
            acct_row = cur.fetchone()
            cash_balance = float(acct_row["cash_balance"])

            cur_pos = conn.execute(
                "SELECT position_id, quantity, average_entry_price FROM portfolio_positions WHERE account_id = ? AND symbol = ?",
                (account_id, sym)
            )
            pos_row = cur_pos.fetchone()
            curr_qty = int(pos_row["quantity"]) if pos_row else 0
            curr_entry = float(pos_row["average_entry_price"]) if pos_row else 0.0

            realized_pnl = 0.0

            if act == "BUY":
                net_debit = gross_val + friction
                if cash_balance < net_debit:
                    raise ValueError(f"Solvency limit: Need ₹{net_debit:.2f}, available cash is ₹{cash_balance:.2f}.")

                cash_balance -= net_debit
                new_qty = curr_qty + shares
                new_entry = ((curr_qty * curr_entry) + (shares * ltp)) / new_qty if new_qty > 0 else ltp

                pos_id = f"pos_{account_id}_{sym}"
                conn.execute("""
                    INSERT INTO portfolio_positions (
                        position_id, account_id, symbol, quantity, average_entry_price, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_id, symbol) DO UPDATE SET
                        quantity = excluded.quantity,
                        average_entry_price = excluded.average_entry_price,
                        updated_at = excluded.updated_at
                """, (pos_id, account_id, sym, new_qty, round(new_entry, 2), now_iso))

            else:  # SELL
                if shares > curr_qty:
                    raise ValueError(f"Insufficient shares to SELL: requested {shares}, holding {curr_qty}.")

                net_credit = gross_val - friction
                cash_balance += net_credit
                realized_pnl = round((shares * (ltp - curr_entry)) - friction, 2)
                new_qty = curr_qty - shares

                if new_qty <= 0:
                    conn.execute("DELETE FROM portfolio_positions WHERE account_id = ? AND symbol = ?", (account_id, sym))
                else:
                    conn.execute("""
                        UPDATE portfolio_positions
                        SET quantity = ?, updated_at = ?
                        WHERE account_id = ? AND symbol = ?
                    """, (new_qty, now_iso, account_id, sym))

            conn.execute("""
                INSERT INTO portfolio_orders (
                    order_id, account_id, proposal_id, symbol, action,
                    quantity, fill_price, friction_paid, executed_at,
                    thesis_note, realized_pnl, analysis_json
                ) VALUES (?, ?, 'MANUAL_DISCRETIONARY', ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_id, account_id, sym, act, shares, ltp, friction, now_iso,
                thesis_note, realized_pnl, json.dumps(prev["system_analysis"])
            ))

            cur_all_pos = conn.execute(
                "SELECT symbol, quantity, average_entry_price FROM portfolio_positions WHERE account_id = ? AND quantity > 0",
                (account_id,)
            )
            all_pos = cur_all_pos.fetchall()
            invested_val = sum(int(p["quantity"]) * (self._get_latest_price(p["symbol"]) or float(p["average_entry_price"])) for p in all_pos)
            final_nav = round(cash_balance + invested_val, 2)

            conn.execute("""
                UPDATE portfolio_accounts
                SET cash_balance = ?, total_nav = ?, updated_at = ?
                WHERE account_id = ?
            """, (round(cash_balance, 2), final_nav, now_iso, account_id))

        summary = self.get_account_summary(account_id)
        return {
            "success": True,
            "order_id": order_id,
            "account_id": account_id,
            "symbol": sym,
            "action": act,
            "quantity": shares,
            "fill_price": ltp,
            "gross_value": gross_val,
            "friction_paid": friction,
            "net_cash_impact": round(gross_val + friction, 2) if act == "BUY" else round(gross_val - friction, 2),
            "realized_pnl": realized_pnl,
            "remaining_cash": summary["cash_balance"],
            "total_nav": summary["total_nav"],
            "thesis_note": thesis_note,
            "system_analysis": prev["system_analysis"],
            "analysis_card": prev["system_analysis"],
            "account_summary": summary,
            "executed_at": now_iso
        }
