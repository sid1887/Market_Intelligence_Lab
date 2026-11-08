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


@router.get("/summary")
def get_portfolio_summary(account_id: str = Query("paper_alpha_1", description="Account identifier")):
    """Returns top-level mark-to-market NAV, cash balance, invested value, and P&L metrics."""
    try:
        db = DatabaseManager(DATABASE_PATH)
        engine = PaperTradingEngine(db)
        summary = engine.get_account_summary(account_id=account_id)
        return sanitize_for_json(summary)
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
