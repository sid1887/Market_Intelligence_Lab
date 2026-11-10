"""
src/api/routes_portfolio.py
Paper Trading Portfolio & Virtual Ledger REST API Endpoints.
Workstream 8.1: Real-time portfolio summaries, position matrices, execution blotters,
and rebalance execution triggers.
"""

import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from src.storage.database import DatabaseManager
from src.api.utils import DATABASE_PATH, sanitize_for_json
from src.quant.execution_engine import PaperTradingEngine

logger = logging.getLogger("MIL.PortfolioAPI")

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


class ExecuteProposalRequest(BaseModel):
    proposal_id: Optional[str] = Field(default=None, description="Proposal ID to execute. If omitted, latest pending proposal will be used.")
    account_id: str = Field(default="paper_alpha_1", description="Target virtual account ID")


class ManualOrderRequest(BaseModel):
    account_id: str = Field(default="paper_manual_1", description="Target account identifier")
    symbol: str = Field(..., description="NSE equity symbol")
    action: str = Field(default="BUY", description="BUY or SELL")
    amount_inr: Optional[float] = Field(default=None, description="Rupee amount to allocate")
    quantity: Optional[int] = Field(default=None, description="Explicit whole shares")
    thesis_note: Optional[str] = Field(default=None, description="Discretionary trader thesis note")


class ResetCapitalRequest(BaseModel):
    account_id: str = Field(..., description="Target account identifier")
    initial_capital: float = Field(..., ge=100.0, description="Starting capital in INR (minimum ₹100.00)")
    fee_tier: str = Field(default="RETAIL_MICRO", description="'RETAIL_MICRO' or 'INSTITUTIONAL'")


class AdjustCashRequest(BaseModel):
    account_id: str = Field(..., description="Target account identifier")
    delta_cash: float = Field(..., description="Deposit (+) or withdrawal (-) in INR")


class RebalanceExecuteRequest(BaseModel):
    account_id: str = Field(default="paper_alpha_2", description="Target account identifier")
    session_date: Optional[str] = Field(default=None, description="Session date YYYY-MM-DD")
    proposal_id: Optional[str] = Field(default=None, description="Optional existing proposal ID")


@router.get("/summary")
def get_portfolio_summary(account_id: str = Query("paper_alpha_1", description="Account identifier")):
    """Returns top-level mark-to-market NAV, cash balance, invested value, and P&L metrics."""
    try:
        db = DatabaseManager(DATABASE_PATH)
        engine = PaperTradingEngine(db)
        summary = engine.get_account_summary(account_id=account_id)
        # Provide canonical quant keys and frontend aliases
        enriched = dict(summary)
        enriched["equity_value"] = summary.get("invested_value", 0.0)
        enriched["position_count"] = summary.get("positions_count", 0)
        return sanitize_for_json(enriched)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Error fetching portfolio summary for {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch portfolio summary: {str(e)}")


@router.get("/positions")
def get_portfolio_positions(account_id: str = Query("paper_alpha_1", description="Account identifier")):
    """Returns open positions joined with latest MTM market prices, cost basis, and unrealized P&L."""
    try:
        db = DatabaseManager(DATABASE_PATH)
        engine = PaperTradingEngine(db)
        positions = engine.get_positions(account_id=account_id)
        return sanitize_for_json(positions)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Error fetching portfolio positions for {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch portfolio positions: {str(e)}")


@router.get("/orders")
def get_portfolio_orders(
    account_id: str = Query("paper_alpha_1", description="Account identifier"),
    limit: int = Query(100, ge=1, le=500, description="Max orders to fetch")
):
    """Returns chronological trade blotter with fill prices and statutory friction paid."""
    try:
        db = DatabaseManager(DATABASE_PATH)
        engine = PaperTradingEngine(db)
        orders = engine.get_orders(account_id=account_id, limit=limit)
        return sanitize_for_json(orders)
    except Exception as e:
        logger.error(f"Error fetching portfolio orders for {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch portfolio orders: {str(e)}")


@router.post("/execute")
def execute_rebalance(req: ExecuteProposalRequest = Body(...)):
    """Executes a rebalance proposal against the virtual account applying SELL-before-BUY sequencing and friction."""
    try:
        db = DatabaseManager(DATABASE_PATH)
        engine = PaperTradingEngine(db)

        proposal_id = req.proposal_id
        if not proposal_id:
            with db.get_connection() as conn:
                cur = conn.execute("""
                    SELECT proposal_id FROM rebalance_proposals
                    WHERE status = 'PROPOSED'
                    ORDER BY session_date DESC, created_at DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
                if not row or not row[0]:
                    raise HTTPException(
                        status_code=404,
                        detail="No pending rebalance proposals available for execution."
                    )
                proposal_id = str(row[0])

        result = engine.execute_proposal(proposal_id=proposal_id, account_id=req.account_id)
        return sanitize_for_json(result)
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error executing rebalance proposal: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")


@router.get("/manual/preview")
def preview_manual_order(
    account_id: str = Query("paper_manual_1", description="Account identifier"),
    symbol: str = Query(..., description="NSE Equity Symbol"),
    action: str = Query("BUY", description="BUY or SELL"),
    amount_inr: Optional[float] = Query(None, description="Rupee allocation amount"),
    quantity: Optional[int] = Query(None, description="Share count")
):
    """Pre-trade intelligence card, whole-share math, solvency check, and FrontPage system verdict."""
    try:
        db = DatabaseManager(DATABASE_PATH)
        engine = PaperTradingEngine(db)
        result = engine.preview_manual_order(
            account_id=account_id,
            symbol=symbol,
            action=action,
            amount_inr=amount_inr,
            quantity=quantity
        )
        return sanitize_for_json(result)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error previewing manual order for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")


@router.post("/manual/execute")
def execute_manual_trade(req: ManualOrderRequest = Body(...)):
    """Executes discretionary trade on paper_manual_1, persisting thesis note and FrontPage analysis."""
    try:
        db = DatabaseManager(DATABASE_PATH)
        engine = PaperTradingEngine(db)
        result = engine.execute_manual_order(
            account_id=req.account_id,
            symbol=req.symbol,
            action=req.action,
            amount_inr=req.amount_inr,
            quantity=req.quantity,
            thesis_note=req.thesis_note
        )
        return sanitize_for_json(result)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error executing manual order for {req.symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Manual execution failed: {str(e)}")


@router.post("/capital/reset")
def reset_account_capital(req: ResetCapitalRequest = Body(...)):
    """Resets account capital seed to user-defined amount (e.g. ₹1,600), clearing past positions."""
    try:
        db = DatabaseManager(DATABASE_PATH)
        engine = PaperTradingEngine(db)
        result = engine.set_or_reset_capital(
            account_id=req.account_id,
            new_capital=req.initial_capital,
            fee_tier=req.fee_tier
        )
        return sanitize_for_json(result)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error resetting capital for {req.account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Capital reset failed: {str(e)}")


@router.post("/capital/adjust")
def adjust_account_cash(req: AdjustCashRequest = Body(...)):
    """Deposits or withdraws cash from account without wiping active positions."""
    try:
        db = DatabaseManager(DATABASE_PATH)
        engine = PaperTradingEngine(db)
        result = engine.adjust_cash(
            account_id=req.account_id,
            delta_cash=req.delta_cash
        )
        return sanitize_for_json(result)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error adjusting cash for {req.account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cash adjustment failed: {str(e)}")


@router.post("/rebalance/execute")
def execute_rebalance_flow(req: RebalanceExecuteRequest = Body(...)):
    """One-click generation and execution of capital-aware rebalance for paper_alpha_2 (or any account)."""
    try:
        from src.quant.rebalance_engine import RebalanceEngine
        db = DatabaseManager(DATABASE_PATH)
        rebal_engine = RebalanceEngine(db)
        exec_engine = PaperTradingEngine(db)

        proposal_id = req.proposal_id
        if not proposal_id:
            prop = rebal_engine.generate_daily_rebalance_proposal(
                session_date=req.session_date,
                account_id=req.account_id
            )
            proposal_id = prop["proposal_id"]

        exec_res = exec_engine.execute_proposal(proposal_id=proposal_id, account_id=req.account_id)
        return sanitize_for_json(exec_res)
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error executing rebalance flow for {req.account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Rebalance execution failed: {str(e)}")
