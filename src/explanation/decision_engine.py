"""
Market Intelligence Lab — Institutional Investment Decision Engine (Milestone B9.0).

Synthesizes technical trend structures, point-in-time fundamentals, news catalysts,
and walk-forward GARCH econometric cones into an institutional-grade Investment Decision Memo:
- Business Profile (sector, operating segments, core revenue drivers, geographic concentration)
- Deterministic Verdict (STRONG_BUY_COMPOUNDER, TACTICAL_SWING_LONG, HOLD_FAIRLY_VALUED, AVOID_CAPITAL_PRESERVATION)
- Target Investment Horizon
- Quantified Bull Case (3 catalysts) vs Bear Case (3 risks)
- Key Red Flags & Health Checklist (4 diagnostics: Solvency/Leverage, Capital Dilution, Structural Trend, Valuation)
- Institutional Conviction Score (0-100) dynamically tuned by compounding realization feedback.
"""

import math
import datetime
import logging
from typing import Dict, Any, List, Optional, Tuple

from src.storage.database import DatabaseManager
from src.quant.forecasting import EconometricForecaster
from src.quant.feedback_evaluator import FeedbackEvaluator
from src.api.utils import sanitize_for_json, safe_float

logger = logging.getLogger(__name__)


class InvestmentDecisionEngine:
    """
    Synthesizes multi-factor analytics into a definitive institutional tearsheet memo.
    Completely deterministic, mathematical, and grounded in point-in-time market data.
    """

    BUSINESS_PROFILES = {
        "INFY": {
            "operating_segments": "Digital Services & Enterprise Cloud Platforms (Infosys Cobalt), AI Platforms (Infosys Topaz), Core IT Operations.",
            "core_revenue_drivers": "Enterprise digital transformation, cloud migrations, AI modernization, and multi-year large deal TCV conversions.",
            "geographic_concentration": "North America (~59%), Europe (~26%), Rest of the World (~12%), India (~3%)."
        },
        "TCS": {
            "operating_segments": "Banking, Financial Services & Insurance (BFSI), Consumer Business, Life Sciences & Healthcare, Manufacturing, Technology & Services.",
            "core_revenue_drivers": "End-to-end IT services, digital consulting, cognitive operations, cyber security, and enterprise cloud adoption.",
            "geographic_concentration": "North America (~51%), United Kingdom & Europe (~32%), India & Asia Pacific (~17%)."
        },
        "SUZLON": {
            "operating_segments": "Wind Turbine Generator (WTG) Manufacturing (S120/S144 platforms), Operation and Maintenance Services (OMS), Foundry & Forging.",
            "core_revenue_drivers": "New WTG deliveries for utility-scale and C&I IPP projects, high-margin long-term OMS annuity contracts.",
            "geographic_concentration": "India (>96% installed fleet and domestic order book execution)."
        },
        "TRIDENT": {
            "operating_segments": "Textiles (Home Textiles, Terry Towels, Bed Linen), Wheat-Straw Paper Manufacturing, Chemicals.",
            "core_revenue_drivers": "Export market volume growth in terry towels and sheeting, eco-friendly agro-waste paper pricing, captive chemical supplies.",
            "geographic_concentration": "USA & Europe export markets (~62%), Domestic Indian retail & institutional (~38%)."
        },
        "DRONACHRYA": {
            "operating_segments": "DGCA-Certified Drone Pilot Training, UAV Defense & Enterprise Hardware Sales, Geospatial & Inspection Services.",
            "core_revenue_drivers": "Commercial & defense drone pilot certifications, institutional procurement of surveying and loitering munitions platforms.",
            "geographic_concentration": "India (>95% domestic defense, agriculture, and infrastructure surveying)."
        },
        "MOREPENLAB": {
            "operating_segments": "Active Pharmaceutical Ingredients (APIs), Home Health Diagnostics (Dr. Morepen), Formulations & OTC.",
            "core_revenue_drivers": "Global export sales of Montelukast and Loratadine APIs, point-of-care glucometer and BP monitor device expansion.",
            "geographic_concentration": "Domestic India (~56%), International Export Markets across Europe, APAC, Americas (~44%)."
        }
    }

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()
        self.forecaster = EconometricForecaster(self.db)
        self.feedback_evaluator = FeedbackEvaluator(self.db)

    def generate_memo(self, symbol: str) -> Dict[str, Any]:
        """
        Synthesizes all platform analytics into a structured one-page Investment Decision Memo.
        """
        sym = symbol.strip().upper()

        # 1. Fetch Security Master Info
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT symbol, company_name, industry, sector, macro_sector
                FROM securities_master WHERE symbol = ?
                """,
                (sym,)
            )
            sec_row = cur.fetchone()

        if not sec_row:
            company_name = sym
            industry = "Diversified"
            sector = "Equities"
            macro_sector = "Broad Market"
        else:
            company_name = sec_row["company_name"] or sym
            industry = sec_row["industry"] or "Diversified"
            sector = sec_row["sector"] or "Equities"
            macro_sector = sec_row["macro_sector"] or "Broad Market"

        # 2. Fetch Latest Factor Snapshot
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT * FROM quant_factors_daily
                WHERE symbol = ?
                ORDER BY trading_date DESC LIMIT 1;
                """,
                (sym,)
            )
            factor_row = cur.fetchone()

            # Latest price from ohlcv_daily
            cur_p = conn.execute(
                """
                SELECT close, trading_date FROM ohlcv_daily
                WHERE symbol = ? AND series = 'EQ'
                ORDER BY trading_date DESC LIMIT 1;
                """,
                (sym,)
            )
            price_row = cur_p.fetchone()

        if not factor_row and not price_row:
            raise ValueError(f"No historical price or factor data found for symbol '{sym}'.")

        as_of_date = price_row["trading_date"] if price_row else factor_row["trading_date"]
        current_price = float(price_row["close"]) if price_row else float(factor_row.get("sma_20") or 100.0)

        # Extract factor values
        sma_20 = safe_float(factor_row["sma_20"]) if factor_row else None
        sma_50 = safe_float(factor_row["sma_50"]) if factor_row else None
        sma_200 = safe_float(factor_row["sma_200"]) if factor_row else None
        vol_ann = safe_float(factor_row["volatility_annualized"]) if factor_row else 0.25
        beta_60d = safe_float(factor_row["beta_60d_nifty"]) if factor_row else 1.0
        ttm_pe = safe_float(factor_row["ttm_pe"]) if factor_row else None
        roe_pct = safe_float(factor_row["roe_pct"]) if factor_row else None
        debt_to_equity = safe_float(factor_row["debt_to_equity"]) if factor_row else None
        opm_pct = safe_float(factor_row["opm_pct"]) if factor_row else None

        # 3. Fetch Forecast Cone Summary (Read-Only: No audit ledger writes, P0-08, ADR-0011)
        try:
            fc_res = self.forecaster.generate_forecast(sym, horizon_days=20, cutoff_date=as_of_date)
            projections = fc_res.get("projections", [])
            last_proj = projections[-1] if projections else {}
            exp_20d = safe_float(last_proj.get("expected"), 2) or current_price
            upper_80 = safe_float(last_proj.get("upper_80"), 2)
            lower_80 = safe_float(last_proj.get("lower_80"), 2)
            upper_95 = safe_float(last_proj.get("upper_95"), 2)
            lower_95 = safe_float(last_proj.get("lower_95"), 2)
            upside_pct = round(((exp_20d - current_price) / current_price) * 100.0, 2)
        except Exception as e:
            logger.warning(f"Econometric forecast unavailable for {sym}: {e}")
            exp_20d = current_price
            upper_80 = None
            lower_80 = None
            upper_95 = None
            lower_95 = None
            upside_pct = 0.0

        # 4. Fetch Recent News Feed & Catalysts
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT id, title, source, published_at, impact_direction, confidence_score, impact_drivers
                FROM equity_news_feed
                WHERE symbol = ?
                ORDER BY published_at DESC LIMIT 5;
                """,
                (sym,)
            )
            news_rows = [dict(r) for r in cur.fetchall()]

        bullish_news_count = sum(1 for n in news_rows if n.get("impact_direction") == "BULLISH")
        bearish_news_count = sum(1 for n in news_rows if n.get("impact_direction") == "BEARISH")

        # 5. Component Scoring
        # Technical score (0 to 100)
        tech_points = 0
        if sma_200 and current_price > sma_200:
            tech_points += 35
        if sma_50 and sma_200 and sma_50 > sma_200:
            tech_points += 25
        if sma_50 and current_price > sma_50:
            tech_points += 25
        if sma_20 and current_price > sma_20:
            tech_points += 15
        tech_score = float(tech_points)

        # Fundamental score (0 to 100)
        fund_points = 0
        if roe_pct is not None:
            if roe_pct >= 20.0:
                fund_points += 30
            elif roe_pct >= 12.0:
                fund_points += 20
            elif roe_pct >= 6.0:
                fund_points += 10

        if debt_to_equity is not None:
            if debt_to_equity <= 0.3:
                fund_points += 30
            elif debt_to_equity <= 0.8:
                fund_points += 20
            elif debt_to_equity <= 1.5:
                fund_points += 10

        if opm_pct is not None:
            if opm_pct >= 20.0:
                fund_points += 25
            elif opm_pct >= 12.0:
                fund_points += 18
            elif opm_pct >= 6.0:
                fund_points += 10

        if ttm_pe is not None and 0.0 < ttm_pe <= 35.0:
            fund_points += 15
        elif ttm_pe is not None and 35.0 < ttm_pe <= 55.0:
            fund_points += 8

        fund_score = float(fund_points)

        # Forecast cone score (0 to 100)
        fc_score = 50.0 + min(50.0, max(-50.0, upside_pct * 5.0))

        # News catalyst score (0 to 100)
        if news_rows:
            net_news = bullish_news_count - bearish_news_count
            news_score = 50.0 + (net_news * 15.0)
            news_score = min(100.0, max(0.0, news_score))
        else:
            news_score = 50.0

        # Calculate Institutional Conviction via compounding dynamic weights
        conviction_calc = self.feedback_evaluator.calculate_institutional_conviction(
            symbol=sym,
            tech_score=tech_score,
            fund_score=fund_score,
            news_score=news_score,
            forecast_score=fc_score
        )
        conviction_score = conviction_calc["institutional_conviction_score"]

        # 6. Health Checklist Diagnostics (4 diagnostics)
        checklist: List[Dict[str, Any]] = []

        # Diagnostic 1: Solvency & Leverage (P0-01, ADR-0006: Null debt is never claimed as zero)
        if debt_to_equity is None:
            solv_status = "DATA_MISSING"
            solv_detail = "Solvency Data Unavailable: Balance sheet debt/equity has not been ingested for this issuer."
        elif debt_to_equity <= 0.10:
            solv_status = "PASS"
            solv_detail = f"Prudent capital structure. Debt-to-Equity is {debt_to_equity:.2f}x (Low / Negligible Debt Profile)."
        elif debt_to_equity <= 0.5:
            solv_status = "PASS"
            solv_detail = f"Prudent capital structure. Debt-to-Equity is {debt_to_equity:.2f}x (Threshold <= 0.50x)."
        elif debt_to_equity <= 1.2:
            solv_status = "CAUTION"
            solv_detail = f"Moderate leverage. Debt-to-Equity is {debt_to_equity:.2f}x (Monitored range 0.50x - 1.20x)."
        else:
            solv_status = "FAIL"
            solv_detail = f"Elevated balance sheet risk. Debt-to-Equity is {debt_to_equity:.2f}x exceeds safe ceiling of 1.20x."
        checklist.append({
            "id": "solvency_leverage",
            "name": "Solvency & Leverage Health",
            "status": solv_status,
            "detail": solv_detail
        })

        # Diagnostic 2: Capital Dilution & Promoter Integrity
        # Evaluates return on capital and capital retention stability
        if roe_pct is None:
            dil_status = "DATA_MISSING"
            dil_detail = "Capital efficiency data unavailable: ROE has not been reported for this reporting period."
        elif roe_pct >= 15.0:
            dil_status = "PASS"
            dil_detail = f"Strong capital stewardship. High ROE ({roe_pct:.1f}%) enables self-funded organic expansion without equity dilution."
        elif roe_pct >= 8.0:
            dil_status = "CAUTION"
            dil_detail = f"Moderate capital efficiency. ROE of {roe_pct:.1f}% requires disciplined capex oversight."
        else:
            dil_status = "FAIL"
            dil_detail = f"Weak return on invested capital ({roe_pct:.1f}%) signals risk of shareholder dilution."
        checklist.append({
            "id": "dilution_promoters",
            "name": "Capital Efficiency & Dilution Risk",
            "status": dil_status,
            "detail": dil_detail
        })

        # Diagnostic 3: Structural Price Trend
        if sma_200 and sma_50:
            if current_price > sma_200 and sma_50 > sma_200:
                trend_status = "PASS"
                trend_detail = f"Classic Golden Cross regime. Price (₹{current_price:,.2f}) > 50 SMA (₹{sma_50:,.2f}) > 200 SMA (₹{sma_200:,.2f})."
            elif current_price > sma_200:
                trend_status = "CAUTION"
                trend_detail = f"Above 200 SMA (₹{sma_200:,.2f}), but 50 SMA consolidation underway."
            else:
                trend_status = "FAIL"
                trend_detail = f"Structural downtrend. Price (₹{current_price:,.2f}) trades below 200 SMA (₹{sma_200:,.2f})."
        else:
            trend_status = "CAUTION"
            trend_detail = "Warm-up period active for full 200-day moving average confirmation."
        checklist.append({
            "id": "structural_trend",
            "name": "Structural Trend Regime",
            "status": trend_status,
            "detail": trend_detail
        })

        # Diagnostic 4: Valuation Percentile
        if ttm_pe is None:
            val_status = "CAUTION"
            val_detail = "TTM P/E not applicable (transitional profitability cycle)."
        elif ttm_pe <= 0:
            val_status = "FAIL"
            val_detail = f"Negative earnings base (P/E {ttm_pe:.1f}x indicates net losses)."
        elif ttm_pe <= 35.0:
            val_status = "PASS"
            val_detail = f"Attractively valued at {ttm_pe:.1f}x TTM P/E with margin of safety."
        elif ttm_pe <= 65.0:
            val_status = "CAUTION"
            val_detail = f"Valuation is fully priced at {ttm_pe:.1f}x TTM P/E, requiring execution consistency."
        else:
            val_status = "FAIL"
            val_detail = f"Rich valuation multiple of {ttm_pe:.1f}x TTM P/E leaves zero room for operational missteps."
        checklist.append({
            "id": "valuation_percentile",
            "name": "Valuation Multiple & Percentile",
            "status": val_status,
            "detail": val_detail
        })

        # 7. Deterministic Verdict Assignment (P0-01: Insufficient data forces transparent posture)
        num_fails = sum(1 for c in checklist if c["status"] == "FAIL")
        num_passes = sum(1 for c in checklist if c["status"] == "PASS")
        num_missing = sum(1 for c in checklist if c["status"] == "DATA_MISSING")

        if num_missing >= 2:
            verdict = "INSUFFICIENT_DATA"
            target_horizon = "AWAITING_STATEMENTS"
        elif num_fails >= 2 or (debt_to_equity is not None and debt_to_equity > 1.8):
            verdict = "AVOID_CAPITAL_PRESERVATION"
            target_horizon = "CAPITAL_PRESERVATION_EXIT"
        elif conviction_score >= 72 and num_passes >= 3 and trend_status == "PASS":
            verdict = "STRONG_BUY_COMPOUNDER"
            target_horizon = "12_TO_24_MONTHS"
        elif conviction_score >= 58 and current_price > (sma_50 or 0):
            verdict = "TACTICAL_SWING_LONG"
            target_horizon = "2_TO_8_WEEKS"
        elif conviction_score >= 42:
            verdict = "HOLD_FAIRLY_VALUED"
            target_horizon = "3_TO_6_MONTHS"
        else:
            verdict = "AVOID_CAPITAL_PRESERVATION"
            target_horizon = "CAPITAL_PRESERVATION_EXIT"

        # 8. Bull Case Catalysts (3 quantified points)
        bull_case: List[str] = []
        if sma_200 and current_price > sma_200:
            spread_200 = round(((current_price - sma_200) / sma_200) * 100.0, 1)
            bull_case.append(f"Institutional Momentum: Operating in a robust multi-year bull structure, trading +{spread_200}% above the 200-day moving average (₹{sma_200:,.2f}).")
        else:
            bull_case.append(f"Short-Term Mean Reversion: GARCH conditional forecast models an expected 20-day target of ₹{exp_20d:,.2f} ({upside_pct:+.1f}% drift).")

        if roe_pct is not None and roe_pct >= 10.0:
            bull_case.append(f"Capital Compounding: Generates superior capital efficiency with TTM Return on Equity of {roe_pct:.1f}% and healthy operating margins ({opm_pct or 0.0:.1f}% OPM).")
        elif debt_to_equity is not None:
            bull_case.append(f"Balance Sheet Safety: Total Debt-to-Equity maintained at {debt_to_equity:.2f}x, preserving solvency through market cycles.")
        else:
            bull_case.append("Capital Efficiency: Operating fundamentals currently awaiting next quarterly publication cycle.")

        if news_rows:
            top_catalyst = news_rows[0]["title"]
            bull_case.append(f"Regulatory & Operational Catalyst: Recent corporate disclosures highlight positive operational tailwinds — '{top_catalyst[:85]}...'.")
        else:
            bull_case.append(f"Market Breadth Resilience: 60-day rolling beta vs NIFTY 50 stands at {beta_60d:.2f}, demonstrating disciplined risk absorption.")

        # 9. Bear Case Risks (3 quantified points)
        bear_case: List[str] = []
        if ttm_pe is not None and ttm_pe > 40.0:
            bear_case.append(f"Valuation Multiples: Current TTM P/E multiple of {ttm_pe:.1f}x demands pristine earnings execution and leaves minimal margin of safety against macro shocks.")
        else:
            bear_case.append(f"Lower Econometric Cone Buffer: 95% probabilistic confidence boundary dips to ₹{lower_95:,.2f}, representing a potential downside testing zone in adverse liquidity.")

        if vol_ann and vol_ann > 0.35:
            bear_case.append(f"Elevated Volatility Regime: Annualized volatility of {vol_ann * 100:.1f}% indicates wide intraday swings and sensitivity to broad-market risk-off rotations.")
        else:
            bear_case.append(f"Systematic Beta Exposure: Rolling 60-day beta of {beta_60d:.2f} leaves the security susceptible to broader NIFTY index drawdowns.")

        if debt_to_equity is not None and debt_to_equity > 0.7:
            bear_case.append(f"Debt Servicing Overhead: Financial leverage of {debt_to_equity:.2f}x D/E elevates interest coverage sensitivity during high repo-rate environments.")
        else:
            bear_case.append(f"Execution & Cyclical Headwinds: Margin compression risk if raw material costs or operating expenses expand faster than top-line revenues.")

        # 10. Business Profile
        b_profile = self.BUSINESS_PROFILES.get(sym, {
            "operating_segments": f"Primary operations in {industry} with core product and service delivery lines across {sector}.",
            "core_revenue_drivers": f"Expansion in enterprise and consumer demand within {industry}, institutional volume execution, and market share compounding.",
            "geographic_concentration": "Predominantly domestic Indian market presence with expanding institutional distribution."
        })

        memo = {
            "symbol": sym,
            "company_name": company_name,
            "as_of_date": as_of_date,
            "verdict": verdict,
            "target_horizon": target_horizon,
            "institutional_conviction_score": conviction_score,
            "conviction_breakdown": conviction_calc,
            "business_profile": {
                "sector": sector,
                "industry": industry,
                "macro_sector": macro_sector,
                "operating_segments": b_profile["operating_segments"],
                "core_revenue_drivers": b_profile["core_revenue_drivers"],
                "geographic_concentration": b_profile["geographic_concentration"]
            },
            "bull_case": bull_case[:3],
            "bear_case": bear_case[:3],
            "health_checklist": checklist,
            "key_metrics": {
                "current_price": current_price,
                "sma_20": sma_20,
                "sma_50": sma_50,
                "sma_200": sma_200,
                "ttm_pe": ttm_pe,
                "roe_pct": roe_pct,
                "debt_to_equity": debt_to_equity,
                "opm_pct": opm_pct,
                "beta_60d_nifty": beta_60d,
                "volatility_annualized": vol_ann
            },
            "forecast_cone_summary": {
                "expected_20d_price": exp_20d,
                "upper_80": upper_80,
                "lower_80": lower_80,
                "upper_95": upper_95,
                "lower_95": lower_95,
                "upside_pct": upside_pct
            },
            "recent_news_count": len(news_rows),
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

        return sanitize_for_json(memo)
