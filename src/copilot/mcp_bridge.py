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
import math
import logging
import sqlite3
import pandas as pd
from typing import Dict, Any, List, Optional
from src.storage.database import DatabaseManager
from src.quant.forecasting import EconometricForecaster

logger = logging.getLogger("copilot.mcp_bridge")


class QuantMCPBridge:
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()
        self.forecaster = EconometricForecaster(db_manager=self.db)

    def get_stock_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """Queries SQLite for live price, technical factors, SMAs, non-null ROE, D/E, OPM, and P/E."""
        sym = symbol.strip().upper()
        with self.db.get_connection() as conn:
            # 1. Absolute latest settled price from ohlcv_daily (truth source)
            latest_ohlcv = conn.execute("""
                SELECT close, trading_date
                FROM ohlcv_daily
                WHERE symbol = ? AND (series = 'EQ' OR series IS NULL OR series = '')
                ORDER BY trading_date DESC, retrieval_timestamp DESC
                LIMIT 1
            """, (sym,)).fetchone()

            # 2. Latest technical factors
            qf = conn.execute("""
                SELECT *
                FROM quant_factors_daily
                WHERE symbol = ?
                ORDER BY trading_date DESC
                LIMIT 1
            """, (sym,)).fetchone()

            # 3. Latest non-null Fundamental values from quant_factors_daily
            qf_fund = conn.execute("""
                SELECT roe_pct, debt_to_equity, opm_pct, ttm_pe, trading_date
                FROM quant_factors_daily
                WHERE symbol = ? AND roe_pct IS NOT NULL
                ORDER BY trading_date DESC
                LIMIT 1
            """, (sym,)).fetchone()

            # 4. Latest non-null Fundamental Statements from fundamental_factors_daily
            ff_fund = conn.execute("""
                SELECT roe_pct, debt_to_equity, pe_ratio as ttm_pe, operating_margin_ttm as opm_pct, trading_date
                FROM fundamental_factors_daily
                WHERE symbol = ? AND roe_pct IS NOT NULL
                ORDER BY trading_date DESC
                LIMIT 1
            """, (sym,)).fetchone()

            # 5. Security Master metadata
            sm = conn.execute("""
                SELECT company_name, sector, industry, isin, is_active
                FROM securities_master
                WHERE symbol = ?
            """, (sym,)).fetchone()

        if not qf and not latest_ohlcv and not sm:
            return {"error": f"Symbol {sym} not found in database."}

        price = float(latest_ohlcv["close"]) if latest_ohlcv else (float(qf["close"]) if qf and "close" in qf.keys() else 0.0)
        last_date = str(latest_ohlcv["trading_date"]) if latest_ohlcv else (str(qf["trading_date"]) if qf else None)
        sma200 = float(qf["sma_200"]) if qf and qf["sma_200"] else None
        price_above_sma200 = (price > sma200) if (price and sma200) else False

        # Resolve fundamentals prioritizing non-null values
        roe = None
        for src in (qf_fund, ff_fund):
            if src and src["roe_pct"] is not None and not pd.isna(src["roe_pct"]):
                roe = round(float(src["roe_pct"]), 2)
                break

        opm = None
        for src in (qf_fund, ff_fund):
            if src and "opm_pct" in src.keys() and src["opm_pct"] is not None and not pd.isna(src["opm_pct"]):
                opm = round(float(src["opm_pct"]), 2)
                break

        de = None
        for src in (qf_fund, ff_fund):
            if src and "debt_to_equity" in src.keys() and src["debt_to_equity"] is not None and not pd.isna(src["debt_to_equity"]):
                de = round(float(src["debt_to_equity"]), 2)
                break

        pe = None
        for src in (qf_fund, ff_fund):
            if src and "ttm_pe" in src.keys() and src["ttm_pe"] is not None and not pd.isna(src["ttm_pe"]):
                pe = round(float(src["ttm_pe"]), 2)
                break

        return {
            "symbol": sym,
            "company_name": sm["company_name"] if sm else sym,
            "sector": sm["sector"] if sm else "Equity",
            "industry": sm["industry"] if sm else "NSE Equities",
            "as_of_date": last_date,
            "current_price": price,
            "technicals": {
                "ret_1d_pct": round(float(qf["ret_1d"] * 100), 2) if qf and qf["ret_1d"] is not None else 0.0,
                "ret_5d_pct": round(float(qf["ret_5d"] * 100), 2) if qf and qf["ret_5d"] is not None else 0.0,
                "ret_20d_pct": round(float(qf["ret_20d"] * 100), 2) if qf and qf["ret_20d"] is not None else 0.0,
                "sma_20": round(float(qf["sma_20"]), 2) if qf and qf["sma_20"] else None,
                "sma_50": round(float(qf["sma_50"]), 2) if qf and qf["sma_50"] else None,
                "sma_200": round(sma200, 2) if sma200 else None,
                "price_above_sma200": price_above_sma200,
                "volatility_annualized": round(float(qf["vol_20d_annualized"]), 4) if qf and "vol_20d_annualized" in qf.keys() and qf["vol_20d_annualized"] else None,
                "beta_60d_nifty": round(float(qf["beta_60d_nifty"]), 2) if qf and "beta_60d_nifty" in qf.keys() and qf["beta_60d_nifty"] is not None else 1.0,
            },
            "fundamentals": {
                "roe_pct": roe,
                "debt_to_equity": de,
                "opm_pct": opm,
                "ttm_pe": pe,
            }
        }

    def get_historical_drawdown_telemetry(self, symbol: str) -> Dict[str, Any]:
        """
        Computes 52W high/low, 60D peak pullback, last major peak-to-trough dip (>= 8%),
        and worst/best single-day moves across last 750 daily bars (~3 years).
        """
        sym = symbol.strip().upper()
        with self.db.get_connection() as conn:
            df = pd.read_sql_query("""
                SELECT trading_date, open, high, low, close, volume
                FROM ohlcv_daily
                WHERE symbol = ? AND (series = 'EQ' OR series IS NULL OR series = '')
                ORDER BY trading_date ASC, retrieval_timestamp ASC
            """, conn, params=(sym,))

        if df.empty or len(df) < 5:
            return {"symbol": sym, "error": "Insufficient historical bars."}

        # Deduplicate multiple series/retrievals on same trading_date by keeping latest
        df = df.drop_duplicates(subset=["trading_date"], keep="last").reset_index(drop=True)

        df_3y = df.tail(750).reset_index(drop=True)
        current_price = float(df_3y.iloc[-1]["close"])
        current_date = str(df_3y.iloc[-1]["trading_date"])

        # 52-Week High & Low (~252 bars)
        df_52w = df_3y.tail(252)
        h52_idx = df_52w["high"].idxmax()
        l52_idx = df_52w["low"].idxmin()
        h52_price = round(float(df_52w.loc[h52_idx, "high"]), 2)
        h52_date = str(df_52w.loc[h52_idx, "trading_date"])
        l52_price = round(float(df_52w.loc[l52_idx, "low"]), 2)
        l52_date = str(df_52w.loc[l52_idx, "trading_date"])

        # 60-Day Peak & Pullback
        df_60d = df_3y.tail(60)
        p60_idx = df_60d["high"].idxmax()
        p60_price = round(float(df_60d.loc[p60_idx, "high"]), 2)
        p60_date = str(df_60d.loc[p60_idx, "trading_date"])
        pullback_60d_pct = round(((current_price / p60_price) - 1.0) * 100, 2)

        # Single-day worst drops and best rallies
        df_3y["daily_ret_pct"] = df_3y["close"].pct_change() * 100
        worst_3 = [
            {"date": str(r["trading_date"]), "return_pct": round(float(r["daily_ret_pct"]), 2), "close": round(float(r["close"]), 2)}
            for _, r in df_3y.sort_values("daily_ret_pct").head(3).iterrows()
            if not pd.isna(r["daily_ret_pct"])
        ]
        best_3 = [
            {"date": str(r["trading_date"]), "return_pct": round(float(r["daily_ret_pct"]), 2), "close": round(float(r["close"]), 2)}
            for _, r in df_3y.sort_values("daily_ret_pct", ascending=False).head(3).iterrows()
            if not pd.isna(r["daily_ret_pct"])
        ]

        # Major peak-to-trough dips (drop >= 8%)
        dips = []
        p_val = float(df_3y.iloc[0]["close"])
        p_date = str(df_3y.iloc[0]["trading_date"])
        p_idx = 0
        t_val = p_val
        t_date = p_date
        t_idx = 0

        for i in range(1, len(df_3y)):
            c = float(df_3y.iloc[i]["close"])
            d = str(df_3y.iloc[i]["trading_date"])
            if c >= p_val:
                drop = ((t_val / p_val) - 1.0) * 100
                if drop <= -8.0:
                    dips.append({
                        "peak_date": p_date,
                        "peak_price": round(p_val, 2),
                        "trough_date": t_date,
                        "trough_price": round(t_val, 2),
                        "drop_pct": round(drop, 2),
                        "days_to_trough": t_idx - p_idx,
                        "recovery_status": f"Fully recovered by {d}"
                    })
                p_val, p_date, p_idx = c, d, i
                t_val, t_date, t_idx = c, d, i
            else:
                if c < t_val:
                    t_val, t_date, t_idx = c, d, i

        # Ongoing dip if any
        drop = ((t_val / p_val) - 1.0) * 100
        if drop <= -8.0:
            rebound = ((current_price / t_val) - 1.0) * 100
            dips.append({
                "peak_date": p_date,
                "peak_price": round(p_val, 2),
                "trough_date": t_date,
                "trough_price": round(t_val, 2),
                "drop_pct": round(drop, 2),
                "days_to_trough": t_idx - p_idx,
                "recovery_status": f"Rebounded +{round(rebound, 1)}% from trough (₹{t_val:.2f}) to current ₹{current_price:.2f}"
            })

        last_major_dip = dips[-1] if dips else None

        return {
            "symbol": sym,
            "current_price": current_price,
            "as_of_date": current_date,
            "high_52w": {"price": h52_price, "date": h52_date, "distance_pct": round(((current_price / h52_price) - 1.0) * 100, 2)},
            "low_52w": {"price": l52_price, "date": l52_date, "distance_pct": round(((current_price / l52_price) - 1.0) * 100, 2)},
            "peak_60d": {"price": p60_price, "date": p60_date, "pullback_pct": pullback_60d_pct},
            "last_major_dip": last_major_dip,
            "worst_single_day_drops": worst_3,
            "best_single_day_rallies": best_3,
            "total_historical_dips_count": len(dips)
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
