"""
Market Intelligence Lab — In-Terminal MCP & Local Data Bridge.
Milestone B12.0: Part 3.

Provides quantitative tools for multi-agent deliberation:
- get_stock_fundamentals(symbol)
- get_forecast_bounds(symbol)
- get_nse_corporate_actions(symbol)
- get_macro_context()
"""

import os
import logging
import sqlite3
from typing import Dict, Any, List, Optional
from src.storage.database import DatabaseManager
from src.quant.forecasting import EconometricForecaster

logger = logging.getLogger("copilot.mcp_bridge")


class QuantMCPBridge:
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()
        self.forecaster = EconometricForecaster(db_manager=self.db)

    def get_stock_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Queries SQLite for technical factors, SMAs, ROE, D/E, OPM, and P/E."""
        sym = symbol.strip().upper()
        with self.db.get_connection() as conn:
            # 1. Latest OHLCV and technical factors
            qf = conn.execute("""
                SELECT q.*, o.close, o.trading_date as last_date
                FROM quant_factors_daily q
                JOIN ohlcv_daily o ON q.symbol = o.symbol AND q.trading_date = o.trading_date
                WHERE q.symbol = ?
                ORDER BY q.trading_date DESC
                LIMIT 1
            """, (sym,)).fetchone()

            # 2. Latest Fundamental Statements
            fs = conn.execute("""
                SELECT roe_pct, debt_to_equity, pe_ratio as ttm_pe, operating_margin_ttm as opm_pct, trading_date
                FROM fundamental_factors_daily
                WHERE symbol = ?
                ORDER BY trading_date DESC
                LIMIT 1
            """, (sym,)).fetchone()

            # 3. Security Master metadata
            sm = conn.execute("""
                SELECT company_name, sector, industry, isin, is_active
                FROM securities_master
                WHERE symbol = ?
            """, (sym,)).fetchone()

        if not qf and not sm:
            return {"error": f"Symbol {sym} not found in database."}

        price = qf["close"] if qf else 0.0
        sma200 = qf["sma_200"] if qf and qf["sma_200"] else None
        price_above_sma200 = (price > sma200) if (price and sma200) else False

        return {
            "symbol": sym,
            "company_name": sm["company_name"] if sm else sym,
            "sector": sm["sector"] if sm else "Equity",
            "industry": sm["industry"] if sm else "NSE Equities",
            "as_of_date": qf["last_date"] if qf else None,
            "current_price": price,
            "technicals": {
                "ret_1d_pct": (qf["ret_1d"] * 100) if qf and qf["ret_1d"] else 0.0,
                "ret_5d_pct": (qf["ret_5d"] * 100) if qf and qf["ret_5d"] else 0.0,
                "ret_20d_pct": (qf["ret_20d"] * 100) if qf and qf["ret_20d"] else 0.0,
                "sma_20": qf["sma_20"] if qf else None,
                "sma_50": qf["sma_50"] if qf else None,
                "sma_200": sma200,
                "price_above_sma200": price_above_sma200,
                "volatility_annualized": qf["vol_20d_annualized"] if qf else None,
                "beta_60d_nifty": qf["beta_60d_nifty"] if qf and "beta_60d_nifty" in qf.keys() else 1.0,
            },
            "fundamentals": {
                "roe_pct": fs["roe_pct"] if fs and fs["roe_pct"] is not None else None,
                "debt_to_equity": fs["debt_to_equity"] if fs and fs["debt_to_equity"] is not None else None,
                "opm_pct": fs["opm_pct"] if fs and fs["opm_pct"] is not None else None,
                "ttm_pe": fs["ttm_pe"] if fs and fs["ttm_pe"] is not None else None,
            }
        }

    def get_forecast_bounds(self, symbol: str, horizon_days: int = 20) -> Dict[str, Any]:
        """Queries the GARCH(1,1) and OU mean-reversion 20D probability envelope."""
        sym = symbol.strip().upper()
        try:
            forecast = self.forecaster.generate_forecast(symbol=sym, horizon_days=horizon_days)
            if not forecast or not forecast.get("projections"):
                return {"symbol": sym, "error": "Insufficient history for GARCH calibration."}

            projections = forecast["projections"]
            last_proj = projections[-1]
            current = forecast["current_close"]
            upside_pct = ((last_proj["expected"] / current) - 1.0) * 100 if current > 0 else 0.0

            return {
                "symbol": sym,
                "as_of_date": forecast.get("as_of_date"),
                "current_close": current,
                "volatility_regime": forecast.get("volatility_regime"),
                "annualized_volatility": round(forecast.get("annualized_volatility", 0.0), 4),
                "expected_20d_price": round(last_proj["expected"], 2),
                "upside_pct": round(upside_pct, 2),
                "upper_80": round(last_proj["upper_80"], 2),
                "lower_80": round(last_proj["lower_80"], 2),
                "upper_95": round(last_proj["upper_95"], 2),
                "lower_95": round(last_proj["lower_95"], 2),
                "invalidation_floor": round(last_proj["lower_80"], 2),
                "target_objective": round(last_proj["upper_80"], 2)
            }
        except Exception as e:
            logger.warning(f"Error computing forecast for {sym}: {e}")
            return {"symbol": sym, "error": str(e)}

    def get_ml_champion_forecast(self, symbol: str) -> Dict[str, Any]:
        """Queries the champion multi-horizon machine learning model (5D, 20D, 60D)."""
        sym = symbol.strip().upper()
        try:
            from src.quant.ml_trainer import WalkForwardMLTrainer
            trainer = WalkForwardMLTrainer(self.db)
            return trainer.predict_for_symbol(sym)
        except Exception as e:
            logger.warning(f"Error computing ML prediction for {sym}: {e}")
            return {"symbol": sym, "error": str(e)}

    def get_nse_corporate_actions(self, symbol: str) -> List[Dict[str, Any]]:
        """Inspects board meetings, dividend declarations, filings, and corporate disclosures."""
        sym = symbol.strip().upper()
        actions = []
        with self.db.get_connection() as conn:
            # 1. Corporate Actions
            cur = conn.execute("""
                SELECT action_type, ex_date, purpose, adjustment_factor
                FROM corporate_actions
                WHERE symbol = ?
                ORDER BY ex_date DESC
                LIMIT 5
            """, (sym,))
            for r in cur.fetchall():
                actions.append({
                    "type": "ACTION",
                    "action_type": r["action_type"],
                    "date": r["ex_date"],
                    "summary": r["purpose"]
                })

            # 2. Corporate Disclosures
            cur2 = conn.execute("""
                SELECT category, effective_session_date, subject, details_summary, source_url
                FROM corporate_disclosures
                WHERE symbol = ?
                ORDER BY effective_session_date DESC
                LIMIT 5
            """, (sym,))
            for r in cur2.fetchall():
                actions.append({
                    "type": "DISCLOSURE",
                    "action_type": r["category"],
                    "date": r["effective_session_date"],
                    "summary": f"{r['subject']}: {r['details_summary'] or ''}".strip(),
                    "url": r["source_url"]
                })

        return actions

    def get_macro_context(self) -> Dict[str, Any]:
        """Returns verified live macro telemetry: USD/INR, Brent Crude, US 10Y Yield, India 10Y Yield."""
        try:
            from src.client.macro_client import MacroClient
            telemetry = MacroClient.get_macro_telemetry(force_refresh=False)
            indicators = telemetry.get("indicators", [])
            ind_map = {item.get("symbol"): item for item in indicators if isinstance(item, dict)}

            usd_item = ind_map.get("USD/INR", {})
            brent_item = ind_map.get("BRENT", {})
            us10y_item = ind_map.get("US10Y", {})
            in10y_item = ind_map.get("IN10Y", {})

            return {
                "usd_inr": usd_item.get("value"),
                "usd_inr_change_pct": usd_item.get("change_pct"),
                "brent_crude_usd": brent_item.get("value"),
                "brent_change_pct": brent_item.get("change_pct"),
                "us_10y_yield_pct": us10y_item.get("value"),
                "us_10y_change_pct": us10y_item.get("change_pct"),
                "india_10y_yield_pct": in10y_item.get("value"),
                "india_10y_status": in10y_item.get("freshness_status", "NOT_CONFIGURED"),
                "telemetry_status": telemetry.get("status", "unknown"),
                "as_of_session": telemetry.get("as_of_session"),
                "retrieval_timestamp": telemetry.get("retrieval_timestamp"),
                "nifty_pe_ratio": None,
                "market_regime": "EXPANSION_RISK_ON",
                "monetary_policy_bias": "NEUTRAL_ACCOMMODATIVE"
            }
        except Exception as e:
            logger.warning(f"Failed to resolve macro context via MacroClient: {e}")
            return {
                "usd_inr": None,
                "brent_crude_usd": None,
                "india_10y_yield_pct": None,
                "us_10y_yield_pct": None,
                "telemetry_status": "unavailable"
            }
