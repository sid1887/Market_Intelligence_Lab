"""
src/api/routes_portfolio.py
Paper Trading Portfolio & Virtual Ledger REST API Endpoints.
Workstream 8.1: Real-time portfolio summaries, position matrices, execution blotters,
and rebalance execution triggers.
"""

import os
import hmac
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, Body, Header, Request, Depends, UploadFile, File, Response
from pydantic import BaseModel, Field

from src.storage.database import DatabaseManager
from src.api.utils import DATABASE_PATH, sanitize_for_json, get_database_manager
from src.quant.execution_engine import PaperTradingEngine
from src.storage.durable_state import mark_state_dirty

logger = logging.getLogger("MIL.PortfolioAPI")

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


def verify_portfolio_mutation_auth(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
) -> bool:
    """
    Guards mutating portfolio operations against unauthorized public modification (P0 security).
    Accepts:
    1. X-API-Key header matching MIL_API_KEY
    2. Authorization: Bearer <key> matching MIL_API_KEY
    3. X-Internal-Token matching MIL_INTERNAL_SYNC_SECRET or INTERNAL_SYNC_TOKEN
    4. Local development loopback (127.0.0.1/localhost) when running in non-production mode without configured key.
    """
    configured_key = (os.getenv("MIL_API_KEY") or os.getenv("MIL_INTERNAL_SYNC_SECRET") or os.getenv("INTERNAL_SYNC_TOKEN", "")).strip()
    is_cloud_prod = bool(os.getenv("RENDER") or os.getenv("ENVIRONMENT") == "production")

    client_ip = request.client.host if (request and request.client) else "unknown"

    # Local loopback bypass only when running locally without explicit security configuration
    if not is_cloud_prod and not configured_key and client_ip in ("127.0.0.1", "localhost", "::1", "testclient"):
        return True

    # In production, or whenever an API key is configured, strict auth is required
    if not configured_key:
        logger.error("[PORTFOLIO-SECURITY] Mutating request rejected: No MIL_API_KEY or MIL_INTERNAL_SYNC_SECRET configured on server.")
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Server portfolio mutation security token is not configured."
        )

    provided = (x_api_key or x_internal_token or "").strip()
    if not provided and authorization and authorization.startswith("Bearer "):
        provided = authorization[7:].strip()

    if not provided or not hmac.compare_digest(provided, configured_key):
        logger.warning(f"[PORTFOLIO-SECURITY] Rejected unauthorized portfolio mutation attempt from {client_ip}.")
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid or missing API key for portfolio mutation."
        )

    return True


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
        db = get_database_manager(DATABASE_PATH)
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
        db = get_database_manager(DATABASE_PATH)
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
        db = get_database_manager(DATABASE_PATH)
        engine = PaperTradingEngine(db)
        orders = engine.get_orders(account_id=account_id, limit=limit)
        return sanitize_for_json(orders)
    except Exception as e:
        logger.error(f"Error fetching portfolio orders for {account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch portfolio orders: {str(e)}")


@router.post("/execute", dependencies=[Depends(verify_portfolio_mutation_auth)])
def execute_rebalance(req: ExecuteProposalRequest = Body(...)):
    """Executes a rebalance proposal against the virtual account applying SELL-before-BUY sequencing and friction."""
    try:
        db = get_database_manager(DATABASE_PATH)
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
        mark_state_dirty()
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
        db = get_database_manager(DATABASE_PATH)
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


@router.post("/manual/execute", dependencies=[Depends(verify_portfolio_mutation_auth)])
def execute_manual_trade(req: ManualOrderRequest = Body(...)):
    """Executes discretionary trade on paper_manual_1, persisting thesis note and FrontPage analysis."""
    try:
        db = get_database_manager(DATABASE_PATH)
        engine = PaperTradingEngine(db)
        result = engine.execute_manual_order(
            account_id=req.account_id,
            symbol=req.symbol,
            action=req.action,
            amount_inr=req.amount_inr,
            quantity=req.quantity,
            thesis_note=req.thesis_note
        )
        mark_state_dirty()
        return sanitize_for_json(result)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error executing manual order for {req.symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Manual execution failed: {str(e)}")


@router.post("/capital/reset", dependencies=[Depends(verify_portfolio_mutation_auth)])
def reset_account_capital(req: ResetCapitalRequest = Body(...)):
    """Resets account capital seed to user-defined amount (e.g. ₹1,600), clearing past positions."""
    try:
        db = get_database_manager(DATABASE_PATH)
        engine = PaperTradingEngine(db)
        result = engine.set_or_reset_capital(
            account_id=req.account_id,
            new_capital=req.initial_capital,
            fee_tier=req.fee_tier
        )
        mark_state_dirty()
        return sanitize_for_json(result)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error resetting capital for {req.account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Capital reset failed: {str(e)}")


@router.post("/capital/adjust", dependencies=[Depends(verify_portfolio_mutation_auth)])
def adjust_account_cash(req: AdjustCashRequest = Body(...)):
    """Deposits or withdraws cash from account without wiping active positions."""
    try:
        db = get_database_manager(DATABASE_PATH)
        engine = PaperTradingEngine(db)
        result = engine.adjust_cash(
            account_id=req.account_id,
            delta_cash=req.delta_cash
        )
        mark_state_dirty()
        return sanitize_for_json(result)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error adjusting cash for {req.account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cash adjustment failed: {str(e)}")


@router.post("/rebalance/execute", dependencies=[Depends(verify_portfolio_mutation_auth)])
def execute_rebalance_flow(req: RebalanceExecuteRequest = Body(...)):
    """One-click generation and execution of capital-aware rebalance for paper_alpha_2 (or any account)."""
    try:
        from src.quant.rebalance_engine import RebalanceEngine
        db = get_database_manager(DATABASE_PATH)
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
        mark_state_dirty()
        return sanitize_for_json(exec_res)
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error executing rebalance flow for {req.account_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Rebalance execution failed: {str(e)}")


# =========================================================================
# ZERO-PII ENCRYPTED ANGEL ONE TRADEBOOK ENGINE ENDPOINTS
# =========================================================================

@router.post("/tradebook/upload")
async def upload_angelone_tradebook(
    files: List[UploadFile] = File(...),
    _auth: bool = Depends(verify_portfolio_mutation_auth),
):
    """
    Ingests one or more Angel One Excel files directly from RAM (io.BytesIO).
    Strict Zero-PII: ignores all top rows above section headers, deduplicates fills,
    reconciles exact ₹23.60 DP charges, enriches live LTP, and updates master_tradebook.enc.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for tradebook ingestion.")

    try:
        from src.portfolio.tradebook_engine import EncryptedTradebookEngine
        db = get_database_manager(DATABASE_PATH)
        engine = EncryptedTradebookEngine(db)

        total_executions = 0
        total_closed = 0
        total_open = 0
        total_dp = 0
        total_capital = 0

        for f in files:
            content = await f.read()
            if not content:
                continue
            summary = engine.parse_angelone_workbook(content, filename=f.filename)
            stats = summary.get("merge_stats", {})
            total_executions += stats.get("executions_merged", 0)
            total_closed += stats.get("closed_roundtrips_merged", 0)
            total_open += stats.get("open_holdings_merged", 0)
            total_dp += stats.get("dp_charges_merged", 0)
            total_capital += stats.get("capital_entries_merged", 0)
            logger.info(
                f"[TRADEBOOK-UPLOAD] Merged '{f.filename}': executions={stats.get('executions_merged', 0)}, "
                f"closed={stats.get('closed_roundtrips_merged', 0)}, open={stats.get('open_holdings_merged', 0)}, "
                f"dp={stats.get('dp_charges_merged', 0)}, capital={stats.get('capital_entries_merged', 0)}"
            )

        # Return latest summary with cumulative merge stats
        final_summary = engine.get_tradebook_summary()
        final_summary["merge_stats"] = {
            "files_processed": len(files),
            "executions_merged": total_executions,
            "closed_roundtrips_merged": total_closed,
            "open_holdings_merged": total_open,
            "dp_charges_merged": total_dp,
            "capital_entries_merged": total_capital,
        }
        logger.info(
            f"[TRADEBOOK-UPLOAD-SUCCESS] Completed batch of {len(files)} file(s). "
            f"Total closed trades={final_summary.get('total_trades', 0)}, "
            f"Open count={final_summary.get('open_count', 0)}, "
            f"Net P&L=₹{final_summary.get('true_net_pnl', 0.0)}"
        )
        mark_state_dirty()
        return sanitize_for_json(final_summary)
    except Exception as e:
        logger.error(f"[TRADEBOOK-UPLOAD-ERROR] Failed to parse Angel One tradebook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process tradebook: {str(e)}")


@router.get("/tradebook/summary")
def get_angelone_tradebook_summary(_auth: bool = Depends(verify_portfolio_mutation_auth)):
    """
    Returns zero-PII tradebook metrics, closed round-trips with ₹23.60 DP reconciliation,
    open demat holdings with live LTP, and scrip attribution.
    """
    try:
        from src.portfolio.tradebook_engine import EncryptedTradebookEngine
        db = get_database_manager(DATABASE_PATH)
        engine = EncryptedTradebookEngine(db)
        summary = engine.get_tradebook_summary()
        return sanitize_for_json(summary)
    except Exception as e:
        logger.error(f"[TRADEBOOK-SUMMARY-ERROR] Error fetching tradebook summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch tradebook summary: {str(e)}")


@router.get("/tradebook/export")
def export_master_tradebook_excel(_auth: bool = Depends(verify_portfolio_mutation_auth)):
    """
    Decrypts master_tradebook.enc in RAM and streams MIL_Master_Trading_Record.xlsx.
    Guaranteed zero PII, 5 institutional tabs, and full DP friction reconciliation.
    """
    try:
        from src.portfolio.tradebook_engine import EncryptedTradebookEngine
        db = get_database_manager(DATABASE_PATH)
        engine = EncryptedTradebookEngine(db)
        excel_bytes = engine.export_decrypted_master_excel()

        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=MIL_Master_Trading_Record.xlsx",
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            }
        )
    except Exception as e:
        logger.error(f"[TRADEBOOK-EXPORT-ERROR] Error exporting master Excel: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to export master Excel: {str(e)}")


@router.get("/trader-dna")
def get_trader_dna_profile(_auth: bool = Depends(verify_portfolio_mutation_auth)):
    """
    Returns live Trader DNA behavioral discipline scorecard, consecutive loss streak,
    cooldown status, hold horizon comparison, and Angel One ₹23.60 DP fee friction audit.
    """
    try:
        from src.copilot.trader_dna import TraderDNAEngine
        db = get_database_manager(DATABASE_PATH)
        dna_engine = TraderDNAEngine(db)
        profile = dna_engine.get_live_execution_profile()

        # Add aliases and normalized fields for consumer compatibility
        profile["cooldown_active"] = profile.get("defensive_cooldown_active", False)
        profile["consecutive_loss_streak"] = profile.get("consecutive_losses", 0)
        profile["total_friction"] = round(
            profile.get("total_dp_charges", 0.0) + profile.get("total_trade_taxes", 0.0), 2
        )
        return sanitize_for_json(profile)
    except Exception as e:
        logger.error(f"[TRADER-DNA-ERROR] Error fetching Trader DNA profile: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch Trader DNA profile: {str(e)}")


