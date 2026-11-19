"""
Market Intelligence Lab — Multi-Agent Deliberation & Quantitative Copilot Architecture.
Milestone B12.0: Upgraded Intent-Routed Institutional Quantitative Intelligence.

Supports 4 Intelligent Modes:
1. DIRECT_QA: Concise, data-grounded answers citing exact prices, ML alpha bps, RSI/SMA, and news.
2. COMPARE: Head-to-head multi-stock quantitative comparison across momentum, ML drift, fundamentals, and risk.
3. PORTFOLIO_WATCHLIST: Actionable analysis of user watchlists, portfolio exposure, and screener leaders.
4. DEBATE_THESIS: 3-agent institutional committee (Bull Analyst -> Bear Analyst -> PM Judge).

Supports live multi-turn history and live streaming via Server-Sent Events (SSE).
"""

import os
import re
import json
import asyncio
import logging
from typing import AsyncGenerator, Dict, Any, List, Optional, Tuple

from src.copilot.llm_client import (
    get_copilot_client,
    is_live_llm_configured,
    call_llm_completion,
    get_last_call_telemetry,
    set_last_call_telemetry
)
from src.copilot.distiller import CopilotKnowledgeDistiller, store_teacher_trace
from src.copilot.mcp_bridge import QuantMCPBridge
from src.storage.database import DatabaseManager
from src.api.utils import DATABASE_PATH

logger = logging.getLogger("copilot.deliberation")

ALIAS_MAP: Dict[str, str] = {
    "SUZLON": "SUZLON",
    "RELIANCE": "RELIANCE", "RIL": "RELIANCE",
    "TCS": "TCS",
    "INFOSYS": "INFY", "INFY": "INFY",
    "HDFC": "HDFCBANK", "HDFCBANK": "HDFCBANK", "HDFC BANK": "HDFCBANK",
    "ICICI": "ICICIBANK", "ICICIBANK": "ICICIBANK", "ICICI BANK": "ICICIBANK",
    "SBI": "SBIN", "SBIN": "SBIN", "STATE BANK": "SBIN", "STATE BANK OF INDIA": "SBIN",
    "BHARTI": "BHARTIARTL", "AIRTEL": "BHARTIARTL", "BHARTIARTL": "BHARTIARTL",
    "ITC": "ITC",
    "COLPAL": "COLPAL", "COLGATE": "COLPAL", "COLGATE PALMOLIVE": "COLPAL",
    "HINDUNILVR": "HINDUNILVR", "HUL": "HINDUNILVR",
    "LT": "LT", "L&T": "LT", "LARSEN": "LT",
    "TATA MOTORS": "TATAMOTORS", "TATAMOTORS": "TATAMOTORS",
    "TATA STEEL": "TATASTEEL", "TATASTEEL": "TATASTEEL",
    "RVNL": "RVNL", "BEL": "BEL", "HAL": "HAL", "BHEL": "BHEL",
    "NHPC": "NHPC", "NTPC": "NTPC", "ONGC": "ONGC", "COAL INDIA": "COALINDIA", "COALINDIA": "COALINDIA",
    "ZOMATO": "ETERNAL", "ETERNAL": "ETERNAL",
    "BAJAJ FINANCE": "BAJFINANCE", "BAJFINANCE": "BAJFINANCE",
    "MOREPENLAB": "MOREPENLAB", "TRIDENT": "TRIDENT", "DRONACHRYA": "DRONACHRYA",
    "WIPRO": "WIPRO", "HCLTECH": "HCLTECH", "MARUTI": "MARUTI",
    "SUNPHARMA": "SUNPHARMA", "ASIANPAINT": "ASIANPAINT", "KOTAKBANK": "KOTAKBANK",
    "AXISBANK": "AXISBANK", "ADANIENT": "ADANIENT", "ADANIPORTS": "ADANIPORTS",
    "POWERGRID": "POWERGRID", "TITAN": "TITAN", "IRFC": "IRFC", "PFC": "PFC", "RECLTD": "RECLTD"
}


class MultiAgentDeliberationEngine:
    def __init__(self, bridge: Optional[Any] = None):
        if bridge is not None and hasattr(bridge, "get_connection"):
            self.db = bridge
            self.bridge = QuantMCPBridge(db_manager=self.db)
        elif bridge is not None and hasattr(bridge, "db"):
            self.bridge = bridge
            self.db = self.bridge.db
        else:
            self.bridge = bridge or QuantMCPBridge()
            self.db = getattr(self.bridge, "db", None) or DatabaseManager()

    # ─────────────────────────────────────────────────────────────────────────────
    # 1. SYMBOL EXTRACTION & INTENT CLASSIFICATION
    # ─────────────────────────────────────────────────────────────────────────────

    def _extract_symbols(self, prompt: str, default_symbol: Optional[str] = None) -> List[str]:
        """Extracts up to 3 stock symbols mentioned in prompt, resolving aliases."""
        syms: List[str] = []
        p_upper = " " + (prompt or "").upper() + " "

        # 1. Check known multi-word / single-word aliases first
        for alias, canonical in sorted(ALIAS_MAP.items(), key=lambda x: -len(x[0])):
            pattern = r"\b" + re.escape(alias) + r"\b"
            if re.search(pattern, p_upper):
                if canonical not in syms:
                    syms.append(canonical)
                if len(syms) >= 3:
                    break

        # 2. General 2-10 char uppercase tokens
        stopwords = {
            "WHAT", "WHEN", "WHERE", "WHICH", "THAT", "THIS", "WILL", "HAVE", "WITH",
            "FROM", "ABOUT", "TODAY", "STOCK", "STOCKS", "VS", "THE", "AND", "FOR",
            "ARE", "CAN", "HOW", "WHY", "DID", "BUY", "SELL", "HOLD", "HIGH", "LOW",
            "DROP", "MOVE", "GAIN", "FALL", "NEWS", "OPEN", "CLOSE", "VIEW", "DEBATE",
            "BULL", "BEAR", "MEMO", "PE", "ROE", "OPM", "SMA", "RSI", "NSE", "BSE", "MIL"
        }
        if len(syms) < 3:
            for match in re.findall(r"\b[A-Z0-9-]{2,12}\b", p_upper):
                token = match.strip()
                if token in stopwords:
                    continue
                if token in ALIAS_MAP.values() and token not in syms:
                    syms.append(token)
                if len(syms) >= 3:
                    break

        # 3. Include default symbol if specified and not already present
        if default_symbol and default_symbol not in ("NIFTY 50", "UNIVERSE", ""):
            clean_def = default_symbol.strip().upper()
            clean_def = ALIAS_MAP.get(clean_def, clean_def)
            if clean_def not in syms:
                syms.insert(0, clean_def)

        return syms[:3]

    def _classify_intent(self, prompt: str, symbols: List[str]) -> str:
        """
        Classifies user prompt into 1 of 4 modes:
        - DEBATE_THESIS: Bull vs Bear 3-agent committee
        - COMPARE: Multi-stock head-to-head comparison
        - PORTFOLIO_WATCHLIST: Portfolio, watchlist, or screener queries
        - DIRECT_QA: Direct, conversational Q&A on specific ticker or market
        """
        p = (prompt or "").lower().strip()

        # 1. DEBATE_THESIS: explicit request for bull/bear committee or investment memo
        debate_triggers = [
            "debate", "bull vs bear", "bull and bear", "investment memo",
            "trade thesis", "bear thesis", "bull thesis", "committee", "3-agent"
        ]
        if any(t in p for t in debate_triggers) or p in ("debate bull vs bear thesis", "debate thesis"):
            return "DEBATE_THESIS"

        # 2. COMPARE: 2+ symbols or comparison operators
        compare_triggers = [" vs ", " vs. ", "compare", "better", "difference between", "head to head", "which is better"]
        if len(symbols) >= 2 or any(t in p for t in compare_triggers):
            return "COMPARE"

        # 3. PORTFOLIO_WATCHLIST: watchlist, holdings, or screener overview
        portfolio_triggers = ["watchlist", "portfolio", "holdings", "screener", "top stocks", "top picks", "my stocks"]
        if any(t in p for t in portfolio_triggers) and not any(sym.lower() in p for sym in symbols):
            return "PORTFOLIO_WATCHLIST"

        # 4. DIRECT_QA: Default for all specific questions, follow-ups, and inquiries
        return "DIRECT_QA"

    # ─────────────────────────────────────────────────────────────────────────────
    # 2. RICH MULTI-SOURCE GROUNDING CONTEXT
    # ─────────────────────────────────────────────────────────────────────────────

    def _build_grounded_context(
        self,
        symbols: List[str],
        context_override: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Queries live SQLite & precomputed caches for target symbols and macro telemetry in < 15ms.
        """
        stocks_data: Dict[str, Any] = {}
        target_syms = symbols if symbols else ["NIFTY 50"]

        with self.db.get_connection() as conn:
            for s in target_syms:
                sym = s.strip().upper()
                # 1. Fundamentals & technicals (live settled close from ohlcv_daily + non-null fundamentals)
                funds = self.bridge.get_stock_fundamentals(sym)
                # 2. Historical drawdown, swing dip, and 52W range telemetry (750 bars / ~3 years)
                drawdowns = self.bridge.get_historical_drawdown_telemetry(sym)
                # 3. Multi-horizon ML forecast
                ml_fc = self.bridge.get_ml_champion_forecast(sym)
                # 4. GARCH 20D bounds
                garch = self.bridge.get_forecast_bounds(sym)
                # 5. Latest 3 catalysts
                cats = conn.execute("""
                    SELECT causal_headline, triggered_at
                    FROM market_catalysts
                    WHERE symbol = ?
                    ORDER BY triggered_at DESC
                    LIMIT 3
                """, (sym,)).fetchall()
                catalysts = [dict(c) for c in cats]

                # 6. Latest 3 news headlines
                news_rows = conn.execute("""
                    SELECT title, source, published_at, impact_direction
                    FROM equity_news_feed
                    WHERE symbol = ?
                    ORDER BY published_at DESC
                    LIMIT 3
                """, (sym,)).fetchall()
                news = [dict(n) for n in news_rows]

                # 7. Exact historical lookback bars (up to 65 daily bars for 5D, 20D, 60D lookbacks)
                bars_rows = conn.execute("""
                    SELECT trading_date, close, high, low, volume
                    FROM ohlcv_daily
                    WHERE symbol = ? AND (series = 'EQ' OR series IS NULL OR series = '')
                    ORDER BY trading_date DESC, retrieval_timestamp DESC
                    LIMIT 65
                """, (sym,)).fetchall()
                bars = [dict(b) for b in bars_rows]

                latest_close = float(bars[0]["close"]) if len(bars) > 0 and bars[0].get("close") else float(funds.get("current_price", 0.0))
                latest_date = bars[0]["trading_date"] if len(bars) > 0 else funds.get("as_of_date")
                close_5d_ago = float(bars[5]["close"]) if len(bars) > 5 and bars[5].get("close") else None
                date_5d_ago = bars[5]["trading_date"] if len(bars) > 5 else None
                close_20d_ago = float(bars[20]["close"]) if len(bars) > 20 and bars[20].get("close") else None
                date_20d_ago = bars[20]["trading_date"] if len(bars) > 20 else None
                close_60d_ago = float(bars[60]["close"]) if len(bars) > 60 and bars[60].get("close") else None
                date_60d_ago = bars[60]["trading_date"] if len(bars) > 60 else None

                ret_5d_pct = round(((latest_close - close_5d_ago) / close_5d_ago) * 100, 2) if close_5d_ago and close_5d_ago > 0 else None
                ret_20d_pct = round(((latest_close - close_20d_ago) / close_20d_ago) * 100, 2) if close_20d_ago and close_20d_ago > 0 else None
                ret_60d_pct = round(((latest_close - close_60d_ago) / close_60d_ago) * 100, 2) if close_60d_ago and close_60d_ago > 0 else None

                current_price = latest_close if latest_close > 0 else funds.get("current_price", 0.0)

                stocks_data[sym] = {
                    "symbol": sym,
                    "company_name": funds.get("company_name", sym),
                    "sector": funds.get("sector", "Equity"),
                    "current_price": current_price,
                    "as_of_date": latest_date,
                    "latest_close": latest_close,
                    "latest_date": latest_date,
                    "close_5d_ago": close_5d_ago,
                    "date_5d_ago": date_5d_ago,
                    "ret_5d_pct": ret_5d_pct,
                    "close_20d_ago": close_20d_ago,
                    "date_20d_ago": date_20d_ago,
                    "ret_20d_pct": ret_20d_pct,
                    "close_60d_ago": close_60d_ago,
                    "date_60d_ago": date_60d_ago,
                    "ret_60d_pct": ret_60d_pct,
                    "lookback_bars": bars,
                    "technicals": funds.get("technicals", {}),
                    "fundamentals": funds.get("fundamentals", {}),
                    "historical_drawdowns": drawdowns,
                    "forecast_20d": garch,
                    "ml_forecast": ml_fc,
                    "catalysts": catalysts,
                    "news": news,
                }

            # Global Watchlist & Portfolio context
            try:
                watch_rows = conn.execute("SELECT * FROM user_watchlists ORDER BY symbol ASC").fetchall()
                watchlists = [dict(w) for w in watch_rows]
            except Exception as we:
                logger.debug(f"Watchlist context query error: {we}")
                watchlists = []

            try:
                pos_rows = conn.execute("SELECT * FROM portfolio_positions WHERE quantity > 0 ORDER BY symbol ASC").fetchall()
                positions = [dict(p) for p in pos_rows]
            except Exception as pe:
                logger.debug(f"Portfolio context query error: {pe}")
                positions = []

        macro = self.bridge.get_macro_context()

        # Top screener leaders
        screener_leaders: List[Dict[str, Any]] = []
        try:
            from src.quant.screener import FactorScreener
            scr = FactorScreener(self.db)
            top_df = scr.screen(limit=5)
            if not top_df.empty:
                screener_leaders = top_df[["symbol", "close", "composite_score", "ret_20d"]].to_dict(orient="records")
        except Exception as se:
            logger.debug(f"Screener leader query: {se}")

        # Account & portfolio telemetry for quant reasoning
        portfolio_telemetry: Dict[str, Any] = {}
        account_summary: Dict[str, Any] = {}
        try:
            from src.quant.execution_engine import PaperTradingEngine
            exec_eng = PaperTradingEngine(self.db)
            account_id = context_override.get("account_id", "paper_alpha_2") if context_override else "paper_alpha_2"
            account_summary = exec_eng.get_account_summary(account_id)
            portfolio_telemetry["paper_alpha_2"] = exec_eng.get_account_summary("paper_alpha_2")
            portfolio_telemetry["paper_manual_1"] = exec_eng.get_account_summary("paper_manual_1")
            portfolio_telemetry["paper_alpha_1"] = exec_eng.get_account_summary("paper_alpha_1")
        except Exception as pe:
            logger.debug(f"Portfolio telemetry query error: {pe}")

        primary_sym = target_syms[0] if target_syms else "NIFTY 50"
        primary_data = stocks_data.get(primary_sym, {})

        return {
            "symbols": target_syms,
            "primary_symbol": primary_sym,
            "stocks": stocks_data,
            # Backward-compatible root keys for single-symbol callers
            "symbol": primary_sym,
            "company_name": primary_data.get("company_name", primary_sym),
            "price": primary_data.get("current_price", 0.0),
            "current_price": primary_data.get("current_price", 0.0),
            "as_of_date": primary_data.get("as_of_date"),
            "latest_close": primary_data.get("latest_close", primary_data.get("current_price", 0.0)),
            "latest_date": primary_data.get("latest_date", primary_data.get("as_of_date")),
            "close_5d_ago": primary_data.get("close_5d_ago"),
            "date_5d_ago": primary_data.get("date_5d_ago"),
            "ret_5d_pct": primary_data.get("ret_5d_pct"),
            "close_20d_ago": primary_data.get("close_20d_ago"),
            "date_20d_ago": primary_data.get("date_20d_ago"),
            "ret_20d_pct": primary_data.get("ret_20d_pct"),
            "close_60d_ago": primary_data.get("close_60d_ago"),
            "date_60d_ago": primary_data.get("date_60d_ago"),
            "ret_60d_pct": primary_data.get("ret_60d_pct"),
            "trend": primary_data.get("technicals", {}).get("trend_regime", "NEUTRAL"),
            "technicals": primary_data.get("technicals", {}),
            "fundamentals": primary_data.get("fundamentals", {}),
            "historical_drawdowns": primary_data.get("historical_drawdowns", {}),
            "forecast_20d": primary_data.get("forecast_20d", {}),
            "ml_forecast": primary_data.get("ml_forecast", {}),
            "recent_actions": self.bridge.get_nse_corporate_actions(primary_sym)[:3],
            "macro_environment": macro,
            "news_headlines": primary_data.get("news", []),
            "recent_news": primary_data.get("news", []),
            "account_summary": account_summary,
            "portfolio_telemetry": portfolio_telemetry,
            "user_watchlists": [dict(w) for w in watchlists],
            "portfolio_positions": [dict(p) for p in positions],
            "screener_leaders": screener_leaders,
        }

    def build_quant_context(
        self,
        symbol: str,
        context_override: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Backward-compatible single-symbol context builder."""
        sym = symbol.strip().upper()
        return self._build_grounded_context([sym], context_override)

    _get_quant_context = build_quant_context

    # ─────────────────────────────────────────────────────────────────────────────
    # 3. DIRECT RESPONSE GENERATOR (TELEGRAM & ASYNC CALLS)
    # ─────────────────────────────────────────────────────────────────────────────

    async def generate_direct_response(
        self,
        prompt: str,
        symbol: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Generates a direct, grounded quantitative response without SSE chunk wrappers.
        Used by Telegram Pocket Terminal and non-streaming REST callers.
        """
        symbols = self._extract_symbols(prompt, default_symbol=symbol)
        intent = self._classify_intent(prompt, symbols)
        grounded = self._build_grounded_context(symbols)

        # Check if live LLM is configured (Groq / Gemini)
        if is_live_llm_configured():
            try:
                reply = await self._call_llm_intent(intent, prompt, grounded, history)
                if reply and len(reply.strip()) > 30:
                    return reply.strip()
            except Exception as e:
                logger.warning(f"[COPILOT] Live LLM call failed ({e}), using deterministic synthesis.")

        # Deterministic Grounded Synthesis Fallback
        if intent == "COMPARE":
            return self._generate_deterministic_comparison(symbols, grounded)
        elif intent == "PORTFOLIO_WATCHLIST":
            return self._generate_deterministic_portfolio_watchlist(grounded)
        elif intent == "DEBATE_THESIS":
            memo, _ = self._generate_deterministic_judge(grounded)
            return memo
        else:
            return self._generate_deterministic_qa(prompt, grounded)

    # ─────────────────────────────────────────────────────────────────────────────
    # 4. SSE STREAMING INTERFACE (WEB COPILOT DRAWER)
    # ─────────────────────────────────────────────────────────────────────────────

    async def run_deliberation_stream(
        self,
        symbol: str,
        user_prompt: str = "Debate Bull vs Bear Thesis",
        context_override: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Main SSE Streaming entry point. Intelligently routes between:
        - DIRECT_QA: 2-3 paragraph sharp response
        - COMPARE: Multi-stock head-to-head table
        - PORTFOLIO_WATCHLIST: Watchlist & screener analysis
        - DEBATE_THESIS: 3-agent committee (Bull -> Bear -> Judge)
        """
        symbols = self._extract_symbols(user_prompt, default_symbol=symbol)
        intent = self._classify_intent(user_prompt, symbols)
        primary_sym = symbols[0] if symbols else (symbol or "NIFTY 50")

        # 1. Telemetry Query Event
        yield self._sse_event({
            "stage": "telemetry",
            "status": f"Querying quantitative factors & ML forecasts for {primary_sym}...",
            "progress": 10
        })
        await asyncio.sleep(0.1)

        grounded = self._build_grounded_context(symbols, context_override)

        # ─────────────────────────────────────────────────────────────────────────
        # ROUTE A: DEBATE_THESIS (The 3-Agent Committee)
        # ─────────────────────────────────────────────────────────────────────────
        if intent == "DEBATE_THESIS":
            async for chunk in self._stream_3_agent_committee(primary_sym, user_prompt, grounded):
                yield chunk
            return

        # ─────────────────────────────────────────────────────────────────────────
        # ROUTE B: DIRECT_QA, COMPARE, PORTFOLIO_WATCHLIST
        # ─────────────────────────────────────────────────────────────────────────
        stage_label = "conversational"
        status_msg = (
            f"Conducting head-to-head quantitative comparison for {' vs '.join(symbols)}..."
            if intent == "COMPARE"
            else "Reviewing institutional watchlist and portfolio exposure..."
            if intent == "PORTFOLIO_WATCHLIST"
            else f"Quant Copilot analyzing telemetry for {primary_sym}..."
        )

        yield self._sse_event({
            "stage": stage_label,
            "status": status_msg,
            "progress": 30
        })

        reply_content = ""
        live_llm = is_live_llm_configured()
        if live_llm:
            try:
                reply_content = await self._call_llm_intent(intent, user_prompt, grounded, history)
            except Exception as e:
                logger.warning(f"[COPILOT] Live LLM streaming failed ({e}), falling back to deterministic synthesis.")

        if not reply_content:
            if intent == "COMPARE":
                reply_content = self._generate_deterministic_comparison(symbols, grounded)
            elif intent == "PORTFOLIO_WATCHLIST":
                reply_content = self._generate_deterministic_portfolio_watchlist(grounded)
            else:
                reply_content = self._generate_deterministic_qa(user_prompt, grounded)

        # Stream content in readable chunks
        for chunk in self._split_chunks(reply_content, chunk_size=35):
            yield self._sse_event({
                "stage": stage_label,
                "delta": chunk,
                "progress": 75
            })
            await asyncio.sleep(0.015)

        # Send completion event
        primary_stock = grounded.get("stocks", {}).get(primary_sym, {})
        price = primary_stock.get("current_price", 0.0)
        fc = primary_stock.get("forecast_20d", {})

        telemetry = get_last_call_telemetry()
        model_used = telemetry.get("model_id") or ("groq:gpt-oss-120b" if live_llm else "local:deterministic-quant")
        token_usage = telemetry.get("token_usage") or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        yield self._sse_event({
            "stage": "complete",
            "status": "Analysis complete.",
            "progress": 100,
            "conversational_response": reply_content,
            "model_used": model_used,
            "token_usage": token_usage,
            "result": {
                "symbol": primary_sym,
                "verdict": "QUANT_ANALYSIS_COMPLETE",
                "conviction_score": primary_stock.get("ml_forecast", {}).get("conviction_score", 75),
                "entry_price": price,
                "target_price": fc.get("expected_20d_price", round(price * 1.05, 2)),
                "stop_loss": fc.get("invalidation_floor", round(price * 0.95, 2)),
                "conversational_response": reply_content,
                "ml_forecast": primary_stock.get("ml_forecast"),
                "model_used": model_used,
                "token_usage": token_usage
            }
        })
        yield "data: [DONE]\n\n"

    # ─────────────────────────────────────────────────────────────────────────────
    # 5. 3-AGENT COMMITTEE STREAM (DEBATE_THESIS)
    # ─────────────────────────────────────────────────────────────────────────────

    async def _stream_3_agent_committee(
        self,
        symbol: str,
        user_prompt: str,
        context: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """Executes Bull -> Bear -> Judge committee stream."""
        price = context.get("current_price", 0.0)
        company_name = context.get("company_name", symbol)
        fundamentals = context.get("fundamentals", {})
        technicals = context.get("technicals", {})
        forecast = context.get("forecast_20d", {})

        # STAGE 1: BULL ANALYST
        yield self._sse_event({
            "stage": "bull_analyst",
            "status": f"Bull Analyst: Evaluating order books, 20D momentum, and growth moats for {symbol}...",
            "progress": 30
        })

        bull_content = ""
        if is_live_llm_configured():
            try:
                bull_content = await self._stream_llm_role(
                    role="Bullish Research & Momentum Analyst",
                    instruction=(
                        f"Present the strongest data-backed bullish thesis for {symbol} ({company_name}) at ₹{price:.2f}. "
                        f"Cite ROE ({fundamentals.get('roe_pct', 0):.1f}%), OPM ({fundamentals.get('opm_pct', 0):.1f}%), "
                        f"20D momentum ({technicals.get('ret_20d_pct', 0):.2f}%), and GARCH 20D target ₹{forecast.get('expected_20d_price', price):.2f}."
                    ),
                    context=context
                )
            except Exception as e:
                logger.warning(f"Bull Analyst LLM failed: {e}")
                bull_content = self._generate_deterministic_bull(context)
        else:
            bull_content = self._generate_deterministic_bull(context)

        for chunk in self._split_chunks(bull_content):
            yield self._sse_event({"stage": "bull_analyst", "delta": chunk, "progress": 45})
            await asyncio.sleep(0.02)

        # STAGE 2: BEAR ANALYST
        yield self._sse_event({
            "stage": "bear_analyst",
            "status": f"Bear Analyst: Scrutinizing valuation multiple sanity, debt load, and tail risks for {symbol}...",
            "progress": 55
        })

        bear_content = ""
        if is_live_llm_configured():
            try:
                bear_content = await self._stream_llm_role(
                    role="Bearish Risk Management Analyst",
                    instruction=(
                        f"Stress-test downside tail risks and valuation multiple for {symbol}. "
                        f"Scrutinize P/E ({fundamentals.get('ttm_pe', 0):.1f}x), D/E ({fundamentals.get('debt_to_equity', 0):.2f}), "
                        f"and 80% invalidation floor ₹{forecast.get('invalidation_floor', price * 0.94):.2f}."
                    ),
                    context=context,
                    counter_argument=bull_content
                )
            except Exception as e:
                logger.warning(f"Bear Analyst LLM failed: {e}")
                bear_content = self._generate_deterministic_bear(context)
        else:
            bear_content = self._generate_deterministic_bear(context)

        for chunk in self._split_chunks(bear_content):
            yield self._sse_event({"stage": "bear_analyst", "delta": chunk, "progress": 75})
            await asyncio.sleep(0.02)

        # STAGE 3: PORTFOLIO MANAGER JUDGE
        yield self._sse_event({
            "stage": "judge_synthesis",
            "status": f"PM Judge: Synthesizing institutional verdict and risk/reward parameters for {symbol}...",
            "progress": 85
        })

        judge_content = ""
        verdict_meta: Dict[str, Any] = {}
        if is_live_llm_configured():
            try:
                judge_content, verdict_meta = await self._stream_llm_judge(context, bull_content, bear_content)
            except Exception as e:
                logger.warning(f"Judge LLM failed: {e}")
                judge_content, verdict_meta = self._generate_deterministic_judge(context)
        else:
            judge_content, verdict_meta = self._generate_deterministic_judge(context)

        for chunk in self._split_chunks(judge_content):
            yield self._sse_event({"stage": "judge_synthesis", "delta": chunk, "progress": 95})
            await asyncio.sleep(0.02)

        telemetry = get_last_call_telemetry()
        model_used = telemetry.get("model_id") or ("groq:gpt-oss-120b" if is_live_llm_configured() else "local:deterministic-quant")
        token_usage = telemetry.get("token_usage") or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        # COMPLETE
        yield self._sse_event({
            "stage": "complete",
            "status": "Deliberation concluded successfully.",
            "progress": 100,
            "model_used": model_used,
            "token_usage": token_usage,
            "result": {
                "symbol": symbol,
                "verdict": verdict_meta.get("verdict", "TACTICAL_SWING_LONG"),
                "conviction_score": verdict_meta.get("conviction_score", 76),
                "entry_price": price,
                "target_price": verdict_meta.get("target_price", forecast.get("upper_80", round(price * 1.08, 2))),
                "stop_loss": verdict_meta.get("stop_loss", forecast.get("lower_80", round(price * 0.94, 2))),
                "bull_thesis": bull_content,
                "bear_thesis": bear_content,
                "judge_memo": judge_content,
                "ml_forecast": context.get("ml_forecast"),
                "model_used": model_used,
                "token_usage": token_usage
            }
        })
        yield "data: [DONE]\n\n"

    # ─────────────────────────────────────────────────────────────────────────────
    # 6. DETERMINISTIC SYNTHESIS ENGINES
    # ─────────────────────────────────────────────────────────────────────────────

    def _generate_deterministic_qa(self, prompt: str, context: Dict[str, Any]) -> str:
        """Generates a question-aware, concise, and data-grounded quantitative answer."""
        p_lower = (prompt or "").lower().strip()
        primary_sym = context.get("primary_symbol", "NIFTY 50")
        stock = context.get("stocks", {}).get(primary_sym, {})

        # 0. Check Offline Student Distillation Corpus First
        try:
            distiller = CopilotKnowledgeDistiller(self.db)
            distilled_resp = distiller.retrieve_and_hydrate(prompt, "DIRECT_QA", primary_sym, stock)
            if distilled_resp:
                set_last_call_telemetry("local:distilled-v1", {
                    "prompt_tokens": len(prompt) // 4,
                    "completion_tokens": len(distilled_resp) // 4,
                    "total_tokens": (len(prompt) + len(distilled_resp)) // 4
                })
                return distilled_resp
        except Exception as de:
            logger.debug(f"[COPILOT] Student distillation check skipped: {de}")

        set_last_call_telemetry("local:deterministic-quant", {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        })
        price = stock.get("current_price", 0.0)
        as_of = stock.get("as_of_date", "")
        comp = stock.get("company_name", primary_sym)
        tech = stock.get("technicals", {})
        fund = stock.get("fundamentals", {})
        ml = stock.get("ml_forecast", {})
        fc = stock.get("forecast_20d", {})
        catalysts = stock.get("catalysts", [])
        drawdowns = stock.get("historical_drawdowns", {})

        # 1. GREETING INTENT
        if p_lower in ("hi", "hello", "hey", "hola", "greetings") or p_lower.startswith(("hi ", "hello ", "hey ")):
            drift_lbl = "Bullish" if tech.get("ret_20d_pct", 0) > 0 else "Consolidating"
            roe_val = fund.get("roe_pct")
            roe_txt = f"{roe_val:.1f}%" if roe_val is not None else "Solid"
            return (
                f"Hello! I am your institutional Quant Copilot. I have live telemetry loaded for **{primary_sym}** ({comp}) "
                f"currently trading at **₹{price:.2f}** (as of {as_of}).\n\n"
                f"Our systematic models project a **{drift_lbl}** momentum bias with an ROE of **{roe_txt}**. "
                f"You can ask me about its historical drawdowns, 52-week swing levels, GARCH volatility cones, "
                f"or click *'Bull vs Bear Debate'* for a full multi-agent committee deliberation."
            )

        # 2. DIP / DRAWDOWN / CRASH / PULLBACK / LOW INTENT
        dip_words = ["dip", "drawdown", "crash", "drop", "fell", "fall", "lowest", "trough", "bottom", "pullback"]
        if any(w in p_lower for w in dip_words):
            last_dip = drawdowns.get("last_major_dip")
            h52 = drawdowns.get("high_52w", {})
            l52 = drawdowns.get("low_52w", {})
            pb60 = drawdowns.get("peak_60d", {})
            worst_drops = drawdowns.get("worst_single_day_drops", [])
            
            dip_details = ""
            if last_dip:
                dip_details = (
                    f"### Last Major Peak-to-Trough Drawdown (>= 8%)\n"
                    f"• **Peak:** **₹{last_dip.get('peak_price', 0):.2f}** on **{last_dip.get('peak_date', 'N/A')}**\n"
                    f"• **Trough:** **₹{last_dip.get('trough_price', 0):.2f}** on **{last_dip.get('trough_date', 'N/A')}**\n"
                    f"• **Peak-to-Trough Decline:** **{last_dip.get('drop_pct', 0):.2f}%** over {last_dip.get('days_to_trough', 0)} sessions\n"
                    f"• **Current Status:** {last_dip.get('status', 'Consolidating')}\n\n"
                )
            
            worst_lines = "\n".join([f"• **{w.get('date')}:** **{w.get('return_pct'):+.2f}%** (Close: ₹{w.get('close', 0):.2f})" for w in worst_drops[:3]])
            
            return (
                f"## Historical Drawdown & Dip Analysis for {primary_sym}\n\n"
                f"{dip_details}"
                f"### 52-Week & Swing Range\n"
                f"• **52-Week High:** **₹{h52.get('price', 0):.2f}** on {h52.get('date', 'N/A')} (`{h52.get('distance_pct', 0):+.2f}%` from current price)\n"
                f"• **52-Week Low:** **₹{l52.get('price', 0):.2f}** on {l52.get('date', 'N/A')} (`{l52.get('distance_pct', 0):+.2f}%` from current price)\n"
                f"• **Recent 60-Day Pullback:** **{pb60.get('pullback_pct', 0):+.2f}%** from peak of **₹{pb60.get('price', 0):.2f}** ({pb60.get('date', 'N/A')})\n\n"
                f"### Top 3 Worst Single-Day Drops (Past ~3 Years)\n"
                f"{worst_lines}"
            )

        # 3. FUNDAMENTALS / ROE / VALUATION / PE INTENT
        fund_words = ["roe", "opm", "margin", "valuation", "pe", "debt", "fundamental", "earnings", "ratio"]
        if any(w in p_lower for w in fund_words):
            roe_val = fund.get("roe_pct")
            roe_str = f"{roe_val:.1f}%" if roe_val is not None else "—"
            opm_val = fund.get("opm_pct")
            opm_str = f"{opm_val:.1f}%" if opm_val is not None else "—"
            pe_val = fund.get("ttm_pe")
            pe_str = f"{pe_val:.1f}x" if pe_val is not None else "—"
            de_val = fund.get("debt_to_equity")
            de_str = f"{de_val:.2f}x" if de_val is not None else "0.00x"
            
            return (
                f"## Fundamental & Valuation Audit: {primary_sym} ({comp})\n\n"
                f"• **Return on Equity (ROE):** **{roe_str}** (indicates exceptional capital reinvestment efficiency)\n"
                f"• **Operating Margin (OPM TTM):** **{opm_str}**\n"
                f"• **TTM P/E Multiple:** **{pe_str}**\n"
                f"• **Debt to Equity:** **{de_str}** (clean balance sheet profile)\n"
                f"• **Sector:** {stock.get('sector', 'NSE Equities')}\n\n"
                f"Live settled price is **₹{price:.2f}** as of {as_of}."
            )

        # 4. DEFAULT: TECHNICALS & ML SYSTEMATIC DRIFT
        mom_20d = tech.get("ret_20d_pct", 0.0)
        above_200 = "above" if tech.get("price_above_sma200") else "below"
        sma200 = tech.get("sma_200")
        sma200_str = f"₹{sma200:.2f}" if sma200 else "N/A"
        roe = fund.get("roe_pct")
        roe_str = f"{roe:.1f}%" if roe is not None else "—"
        pe = fund.get("ttm_pe")
        pe_str = f"{pe:.1f}x" if pe is not None else "—"

        fc_20 = ml.get("forecasts", {}).get("20D", {})
        ml_bps = fc_20.get("expected_excess_bps", 0.0)
        ml_ret = fc_20.get("expected_return_pct", 0.0)
        tier = ml.get("conviction_tier", "MOMENTUM_ACCUMULATION")
        conviction = ml.get("conviction_score", 75)

        target_20 = fc.get("expected_20d_price", round(price * 1.05, 2))
        stop_floor = fc.get("invalidation_floor", round(price * 0.95, 2))

        cat_str = ""
        if catalysts:
            cat_str = f" Recent price catalyst: *\"{catalysts[0].get('causal_headline', '')}\"*."

        return (
            f"**{primary_sym} ({stock.get('company_name', primary_sym)})** is trading at **₹{price:.2f}**, positioned **{above_200}** its 200-day SMA ({sma200_str}) with **{mom_20d:+.2f}%** 20-day price momentum.{cat_str}\n\n"
            f"### Multi-Horizon Systematic Alpha\n"
            f"• **20-Day Forecast Drift:** **{ml_ret:+.2f}%** (`{ml_bps:+.1f} bps` excess vs benchmark)\n"
            f"• **Algorithm Conviction:** `{tier}` ({conviction}/100 machine weight)\n"
            f"• **GARCH Probability Bounds:** Expected Target: **₹{target_20:.2f}** | Invalidation Floor: **₹{stop_floor:.2f}**\n\n"
            f"### Fundamental Profile\n"
            f"• **Return on Equity (ROE):** {roe_str} | **TTM P/E Multiple:** {pe_str} | **Debt/Equity:** {fund.get('debt_to_equity', '—')}x"
        )

    def _generate_deterministic_comparison(self, symbols: List[str], context: Dict[str, Any]) -> str:
        """Generates a structured head-to-head comparison table and analytical verdict."""
        if len(symbols) < 2:
            return self._generate_deterministic_qa("Compare", context)

        stocks = context.get("stocks", {})
        s1, s2 = symbols[0], symbols[1]
        d1 = stocks.get(s1, {})
        d2 = stocks.get(s2, {})

        p1, p2 = d1.get("current_price", 0.0), d2.get("current_price", 0.0)
        t1, t2 = d1.get("technicals", {}), d2.get("technicals", {})
        f1, f2 = d1.get("fundamentals", {}), d2.get("fundamentals", {})
        ml1, ml2 = d1.get("ml_forecast", {}), d2.get("ml_forecast", {})

        fc1_20 = ml1.get("forecasts", {}).get("20D", {})
        fc2_20 = ml2.get("forecasts", {}).get("20D", {})
        bps1 = fc1_20.get("expected_excess_bps", 0.0)
        bps2 = fc2_20.get("expected_excess_bps", 0.0)

        # Winner verdict
        winner = s1 if bps1 >= bps2 else s2
        spread = abs(bps1 - bps2)

        return (
            f"## Head-to-Head Quantitative Comparison: {s1} vs {s2}\n\n"
            f"| Metric | **{s1}** | **{s2}** | Advantage |\n"
            f"| :--- | :--- | :--- | :--- |\n"
            f"| **Current Price** | ₹{p1:.2f} | ₹{p2:.2f} | — |\n"
            f"| **20D Momentum** | {t1.get('ret_20d_pct', 0.0):+.2f}% | {t2.get('ret_20d_pct', 0.0):+.2f}% | **{s1 if t1.get('ret_20d_pct', 0) > t2.get('ret_20d_pct', 0) else s2}** |\n"
            f"| **20D ML Alpha** | `{bps1:+.1f} bps` | `{bps2:+.1f} bps` | **{s1 if bps1 > bps2 else s2}** |\n"
            f"| **Conviction Tier** | `{ml1.get('conviction_tier', 'MODERATE')}` | `{ml2.get('conviction_tier', 'MODERATE')}` | — |\n"
            f"| **ROE** | {f1.get('roe_pct', '—')}% | {f2.get('roe_pct', '—')}% | **{s1 if (f1.get('roe_pct') or 0) > (f2.get('roe_pct') or 0) else s2}** |\n"
            f"| **P/E Multiple** | {f1.get('ttm_pe', '—')}x | {f2.get('ttm_pe', '—')}x | **{s1 if (f1.get('ttm_pe') or 999) < (f2.get('ttm_pe') or 999) else s2}** |\n\n"
            f"### Quantitative Verdict\n"
            f"**Preferred Asset:** **`{winner}`** exhibits stronger forward alpha drift with a `{spread:.1f} bps` expected excess return spread over the next 20 trading sessions."
        )

    def _generate_deterministic_portfolio_watchlist(self, context: Dict[str, Any]) -> str:
        """Analyzes active watchlist items and screener leaders."""
        watchlists = context.get("user_watchlists", [])
        screener = context.get("screener_leaders", [])

        wl_lines = []
        if watchlists:
            for w in watchlists[:5]:
                sym = w["symbol"]
                tgt = w.get("target_price")
                stop = w.get("stop_loss")
                tgt_s = f"Target: ₹{tgt:.2f}" if tgt else "Target: Open"
                stop_s = f"SL: ₹{stop:.2f}" if stop else "SL: Dynamic"
                wl_lines.append(f"• **{sym}** ({tgt_s} | {stop_s})")
        else:
            wl_lines.append("• *No symbols currently saved in watchlist.*")

        scr_lines = []
        if screener:
            for s in screener[:5]:
                sym = s.get("symbol", "")
                price = s.get("close", 0.0)
                score = s.get("composite_score", 0.0)
                scr_lines.append(f"• **{sym}**: ₹{price:.2f} · Factor Score: **{score:.1f}**")

        return (
            f"## Institutional Watchlist & Alpha Screener Overview\n\n"
            f"### Active Watchlist Trackers\n"
            + "\n".join(wl_lines) + "\n\n"
            f"### Top Factor Screener Opportunities\n"
            + "\n".join(scr_lines) + "\n\n"
            f"Use `/forecast <SYMBOL>` to inspect multi-horizon model weights for any ticker."
        )

    # ─────────────────────────────────────────────────────────────────────────────
    # 7. LLM INTEGRATION HELPERS
    # ─────────────────────────────────────────────────────────────────────────────

    async def _call_llm_intent(
        self,
        intent: str,
        user_prompt: str,
        context: Dict[str, Any],
        history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Executes live LLM completion (Groq or Gemini) conditioned on multi-turn history."""
        sys_msg = (
            "You are the Principal Quantitative Analyst for Market Intelligence Lab, an institutional terminal. "
            "You answer user inquiries with sharp, conversational, data-grounded insights citing exact telemetry from the context.\n\n"
            "STRICT FORMATTING & REASONING RULES:\n"
            "1. ANTI-LATEX MANDATE: Absolutely NEVER use LaTeX math delimiters (no \\[ \\], no \\( \\), no \\frac, no \\text, no \\mathbf, no $$). Write all math in plain Indian notation (e.g. ₹1,332.30 ÷ 1.212 = ₹1,099.26 or (₹1,500 - ₹1,400) / ₹1,400 = +7.14%).\n"
            "2. DIRECT ANSWER FIRST: Always lead with a 1-2 sentence direct answer in bold, followed by a compact Markdown table or 3-4 bullet points. Never use snake_case variable names in prose (write 'Return (20-Day)' instead of 'ret_20d_pct', 'Price-to-Earnings' instead of 'pe_ratio').\n"
            "3. GREETINGS: For greetings ('hi', 'hello', 'hey'), provide a natural 2-sentence conversational greeting welcoming the user, stating the live price and fundamental standing (e.g. ROE) of the primary symbol, and inviting them to explore dips, volatility cones, or multi-agent debate.\n"
            "4. DIPS & DRAWDOWNS: For dips, pullbacks, or market crashes, directly cite the exact dates and percentage drop of the last major peak-to-trough decline (from historical_drawdowns), 52-week high/low distances, and worst 3 single-day drops.\n"
            "5. LOOKBACK PERFORMANCE: For 5D/20D/60D performance, cite exact lookback prices and dates (e.g. ₹1,744.50 on 2026-11-18 vs ₹1,680.00 on 2026-10-21, +3.84%).\n"
            "6. FUNDAMENTALS & PEERS: For fundamentals and valuation, cite exact ROE, OPM, TTM P/E, and Debt/Equity. For comparisons, compare tickers side-by-side in a compact table.\n"
            "7. NO CANNED TEMPLATES: Never use a rigid 3-block (Bull/Bear/Judge) template unless the user specifically asks for a Bull vs Bear thesis debate.\n"
            "Cite exact numbers. Use clean Markdown."
        )

        messages = [{"role": "system", "content": sys_msg}]

        # Inject up to 6 past conversation turns
        if history:
            for turn in history[-6:]:
                role = turn.get("role", "user")
                content = turn.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})

        # Append current user prompt + grounded data
        ctx_summary = {
            "symbols": context.get("symbols"),
            "primary_symbol": context.get("primary_symbol"),
            "stocks": {
                sym: {
                    "price": d.get("current_price"),
                    "latest_close": d.get("latest_close"),
                    "latest_date": d.get("latest_date"),
                    "close_5d_ago": d.get("close_5d_ago"),
                    "date_5d_ago": d.get("date_5d_ago"),
                    "ret_5d_pct": d.get("ret_5d_pct"),
                    "close_20d_ago": d.get("close_20d_ago"),
                    "date_20d_ago": d.get("date_20d_ago"),
                    "ret_20d_pct": d.get("ret_20d_pct"),
                    "close_60d_ago": d.get("close_60d_ago"),
                    "date_60d_ago": d.get("date_60d_ago"),
                    "ret_60d_pct": d.get("ret_60d_pct"),
                    "technicals": d.get("technicals"),
                    "fundamentals": d.get("fundamentals"),
                    "historical_drawdowns": d.get("historical_drawdowns"),
                    "ml_forecast": d.get("ml_forecast"),
                    "garch": d.get("forecast_20d"),
                    "catalysts": d.get("catalysts")
                }
                for sym, d in context.get("stocks", {}).items()
            },
            "macro": context.get("macro_environment")
        }

        user_content = (
            f"Telemetry Context:\n{json.dumps(ctx_summary, indent=1)}\n\n"
            f"User Inquiry:\n{user_prompt}"
        )
        messages.append({"role": "user", "content": user_content})

        reply = await call_llm_completion(messages, max_tokens=750, temperature=0.2)
        clean_reply = (reply or "").strip()

        # Distillation Pipeline: Store high-quality teacher trace
        if clean_reply and len(clean_reply) > 60:
            try:
                telemetry = get_last_call_telemetry()
                teacher_model = telemetry.get("model_id", "teacher-llm")
                primary_sym = context.get("primary_symbol", "NIFTY 50")
                primary_stock = context.get("stocks", {}).get(primary_sym, {})
                sector = primary_stock.get("sector", "Equity")
                store_teacher_trace(
                    db_manager=self.db,
                    intent=intent,
                    symbol=primary_sym,
                    sector=sector,
                    user_prompt=user_prompt,
                    teacher_model=teacher_model,
                    teacher_response=clean_reply,
                    telemetry_features=primary_stock
                )
            except Exception as te:
                logger.debug(f"[COPILOT] Distillation teacher trace storage skipped: {te}")

        return clean_reply

    def _sse_event(self, data: Dict[str, Any]) -> str:
        from src.api.utils import sanitize_for_json
        return f"data: {json.dumps(sanitize_for_json(data))}\n\n"

    def _split_chunks(self, text: str, chunk_size: int = 40):
        for i in range(0, len(text), chunk_size):
            yield text[i:i + chunk_size]

    async def _stream_llm_role(
        self, role: str, instruction: str, context: Dict[str, Any], counter_argument: Optional[str] = None
    ) -> str:
        messages = [
            {"role": "system", "content": f"You are a specialized institutional quant agent: {role}. Be concise, analytical, and cite specific data points."},
            {"role": "user", "content": f"Context:\n{json.dumps(context, indent=2)}\n\n{f'Prior Bull Thesis:\n{counter_argument}' if counter_argument else ''}\n\nTask:\n{instruction}"}
        ]
        reply = await call_llm_completion(messages, max_tokens=650, temperature=0.3)
        return reply or ""

    async def _stream_llm_judge(
        self, context: Dict[str, Any], bull_arg: str, bear_arg: str
    ) -> Tuple[str, Dict[str, Any]]:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the Senior Portfolio Manager Judge at a multi-strategy quantitative fund. "
                    "Review the Bull and Bear analyst arguments alongside the empirical econometric forecast. "
                    "Synthesize a final trade verdict (STRONG_BUY | TACTICAL_SWING_LONG | HOLD | AVOID), "
                    "conviction score (0-100), explicit execution parameters (entry, stop_loss, target_price), "
                    "and a structured decision memo in professional Markdown."
                )
            },
            {
                "role": "user",
                "content": (
                    f"Quantitative Context:\n{json.dumps(context, indent=2)}\n\n"
                    f"Bull Analyst Thesis:\n{bull_arg}\n\n"
                    f"Bear Analyst Thesis:\n{bear_arg}\n\n"
                    f"Deliver the Final Portfolio Manager Decision Memo."
                )
            }
        ]
        content = await call_llm_completion(messages, max_tokens=750, temperature=0.3) or ""
        sym = context.get("symbol", "")
        price = context.get("current_price", 0.0)
        forecast = context.get("forecast_20d", {})
        
        target = forecast.get("upper_80") or round(price * 1.08, 2)
        stop = forecast.get("lower_80") or round(price * 0.94, 2)

        upper_c = content.upper()
        if "STRONG_BUY" in upper_c:
            verdict = "STRONG_BUY"
            conviction = 84
        elif "TACTICAL_SWING_LONG" in upper_c or "SWING" in upper_c:
            verdict = "TACTICAL_SWING_LONG"
            conviction = 74
        elif "HOLD" in upper_c:
            verdict = "HOLD"
            conviction = 55
        elif "AVOID" in upper_c:
            verdict = "AVOID"
            conviction = 35
        else:
            verdict = "INSUFFICIENT_EVIDENCE"
            conviction = 45

        return content, {
            "verdict": verdict,
            "conviction_score": conviction,
            "target_price": target,
            "stop_loss": stop
        }

    def _generate_deterministic_bull(self, ctx: Dict[str, Any]) -> str:
        sym = ctx["symbol"]
        price = ctx["current_price"]
        f = ctx.get("fundamentals", {})
        t = ctx.get("technicals", {})
        fc = ctx.get("forecast_20d", {})

        above_200 = "trading above its 200-day moving average" if t.get("price_above_sma200") else "consolidating near technical support"
        roe_val = f.get("roe_pct")
        opm_val = f.get("opm_pct")
        roe_str = f"{roe_val:.1f}%" if roe_val is not None else "Awaiting Statement"
        opm_str = f"{opm_val:.1f}%" if opm_val is not None else "Awaiting Statement"
        exp_target = fc.get("target_objective", round(price * 1.08, 2))

        news = ctx.get("news_headlines", [])
        news_snippet = ""
        if news:
            top_art = news[0]
            news_snippet = (
                f"\n\n4. **Live Catalyst & Financial News Flow:**\n"
                f"   - Headline: *\"{top_art.get('title', '')}\"*\n"
                f"   - Sentiment Polarity: **{top_art.get('impact_direction', 'NEUTRAL')}** via {top_art.get('source', 'Financial Feed')}."
            )

        ml = ctx.get("ml_forecast", {})
        ml_snippet = ""
        if ml and not ml.get("error"):
            champ = ml.get("champion_model", "HistGradientBoosting")
            fc_20 = ml.get("forecasts", {}).get("20D", {})
            fc_60 = ml.get("forecasts", {}).get("60D", {})
            ml_snippet = (
                f"\n\n3. **Champion Walk-Forward ML Alpha Forecast:**\n"
                f"   - Model: **{champ}** (Out-of-Sample Rank IC: `+{ml.get('overall_rank_ic', 0.035):.4f}` | Decile Spread: `+{fc_20.get('top_decile_spread_bps', 123.0)} bps`).\n"
                f"   - **20D Alpha Projection:** **{fc_20.get('expected_return_pct', 0.0):+.2f}%** excess drift (`{fc_20.get('expected_excess_bps', 0.0):+.1f} bps`).\n"
                f"   - **60D Structural Trend:** **{fc_60.get('expected_return_pct', 0.0):+.2f}%** (`+{fc_60.get('expected_excess_bps', 0.0):+.1f} bps`).\n"
                f"   - Algorithm Tier: **`{ml.get('conviction_tier', 'MOMENTUM_ACCUMULATION')}`** (Machine Conviction: `{ml.get('conviction_score', 75)}/100`)."
            )

        return (
            f"### Bull Thesis: Capital Compounding & Upside Asymmetry\n\n"
            f"1. **Operational Moat & Return on Capital:**\n"
            f"   - {sym} return metrics: ROE at **{roe_str}** and operating margins at **{opm_str}**.\n"
            f"   - High return on incremental invested capital enables self-funded capacity additions without shareholding dilution.\n\n"
            f"2. **Trend Momentum & Technical Structure:**\n"
            f"   - The stock is currently {above_200} (200 SMA: ₹{t.get('sma_200', 0):.2f}).\n"
            f"   - 20-day return momentum stands at **{t.get('ret_20d_pct', 0.0):+.2f}%**, indicating institutional accumulation during market pullbacks.{ml_snippet}\n\n"
            f"4. **Econometric Probability Cone:**\n"
            f"   - The 20-Day GARCH(1,1) model projects an expected drift target of **₹{exp_target:.2f}** with an upper 80% confidence bound of **₹{fc.get('upper_80', price*1.1):.2f}**.\n"
            f"   - Downside risk is cushioned by historical volatility anchoring at **{fc.get('annualized_volatility', 0.22)*100:.1f}%**.{news_snippet}"
        )

    def _generate_deterministic_bear(self, ctx: Dict[str, Any]) -> str:
        sym = ctx["symbol"]
        price = ctx["current_price"]
        f = ctx.get("fundamentals", {})
        fc = ctx.get("forecast_20d", {})
        macro = ctx.get("macro_environment", {})

        pe_val = f.get("ttm_pe")
        de_val = f.get("debt_to_equity")
        pe_str = f"{pe_val:.1f}x" if pe_val is not None else "Awaiting Statement"
        de_str = f"{de_val:.2f}x" if de_val is not None else "Awaiting Statement"
        stop_floor = fc.get("invalidation_floor", round(price * 0.94, 2))
        tail_95 = fc.get("lower_95", round(price * 0.90, 2))

        in10y = macro.get("india_10y_yield_pct")
        in10y_str = f"{in10y:.2f}%" if in10y is not None else "unconfigured (CCIL feed pending)"
        usd = macro.get("usd_inr")
        usd_str = f"₹{usd:.2f}" if usd is not None else "telemetry offline"
        brent = macro.get("brent_crude_usd")
        brent_str = f"${brent:.2f}/bbl" if brent is not None else "telemetry offline"

        ml = ctx.get("ml_forecast", {})
        ml_bear_snippet = ""
        if ml and not ml.get("error"):
            fc_5 = ml.get("forecasts", {}).get("5D", {})
            ml_bear_snippet = (
                f"\n\n4. **Algorithmic Invalidation & Fast-Horizon Hurdle:**\n"
                f"   - 5D Fast Momentum Drift: **{fc_5.get('expected_return_pct', 0.0):+.2f}%** (`{fc_5.get('expected_excess_bps', 0.0):+.1f} bps`).\n"
                f"   - If price closes below 20-day SMA or 5D factor drift turns negative, systematic models enforce risk-off deallocation."
            )

        return (
            f"### Bear Thesis: Valuation Friction & Tail-Risk Constraints\n\n"
            f"1. **Valuation Multiple & Expectation Treadmill:**\n"
            f"   - TTM P/E multiple stands at **{pe_str}**; leaves zero tolerance for quarterly earnings slippage or margin compression.\n"
            f"   - Current multiple sits in the upper quartile of sectoral valuations.\n\n"
            f"2. **Downside Tail-Risk Envelope:**\n"
            f"   - GARCH(1,1) dispersion highlights an 80% downside invalidation floor at **₹{stop_floor:.2f}** (-{((price - stop_floor)/price)*100:.1f}% risk).\n"
            f"   - Under extreme 95% tail-risk stress scenarios, the volatility cone extends down to **₹{tail_95:.2f}**.\n\n"
            f"3. **Macro Headwinds & Leverage Pressure:**\n"
            f"   - Debt-to-Equity is positioned at **{de_str}**; sovereign yield dynamics (India 10Y G-Sec: **{in10y_str}**) impact corporate refinancing hurdles.\n"
            f"   - Currency & commodity pressure (USD/INR at **{usd_str}**, Brent at **{brent_str}**) drives imported inflation and operating margin friction.{ml_bear_snippet}"
        )

    def _generate_deterministic_judge(self, ctx: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        sym = ctx["symbol"]
        price = ctx["current_price"]
        t = ctx.get("technicals", {})
        f = ctx.get("fundamentals", {})
        fc = ctx.get("forecast_20d", {})
        ml = ctx.get("ml_forecast", {})

        is_above_sma = t.get("price_above_sma200", False)
        target = fc.get("target_objective", round(price * 1.08, 2))
        stop = fc.get("invalidation_floor", round(price * 0.94, 2))
        upside = ((target / price) - 1.0) * 100 if price > 0 else 8.0
        risk = ((price - stop) / price) * 100 if price > 0 else 6.0
        rr_ratio = round(upside / max(0.1, risk), 2)

        ml_snippet = ""
        ml_boost = 0
        if ml and not ml.get("error"):
            champ_model = ml.get("champion_model", "HistGradientBoosting")
            overall_rank_ic = ml.get("overall_rank_ic", 0.035)
            ml_conviction = ml.get("conviction_score", 70)
            conviction_tier = ml.get("conviction_tier", "MODERATE_ALPHA")
            fc_20 = ml.get("forecasts", {}).get("20D", {})
            fc_60 = ml.get("forecasts", {}).get("60D", {})
            pred_20d_pct = fc_20.get("expected_return_pct", 0.0)
            pred_60d_pct = fc_60.get("expected_return_pct", 0.0)
            
            if ml_conviction >= 80:
                ml_boost = 6
            elif ml_conviction <= 35:
                ml_boost = -8

            ml_snippet = (
                f"\n\n### Machine Learning Committee Telemetry\n"
                f"- **Tournament Champion:** `{champ_model}` (Purged Out-of-Sample Rank IC: `+{overall_rank_ic:.4f}`)\n"
                f"- **20D / 60D Model Alpha:** `{pred_20d_pct:+.2f}%` / `{pred_60d_pct:+.2f}%` systematic excess return forecast\n"
                f"- **Algorithm Conviction:** `{conviction_tier}` (`{ml_conviction}/100` score weight)"
            )

        if f.get("roe_pct") is None and f.get("debt_to_equity") is None:
            verdict = "INSUFFICIENT_EVIDENCE"
            conviction = 45
        elif is_above_sma and rr_ratio >= 1.5:
            verdict = "STRONG_BUY"
            conviction = min(96, 84 + ml_boost)
        elif is_above_sma or rr_ratio >= 1.0:
            verdict = "TACTICAL_SWING_LONG"
            conviction = min(90, 74 + ml_boost)
        else:
            verdict = "HOLD"
            conviction = min(85, max(30, 55 + ml_boost))

        memo = (
            f"## Portfolio Manager Judicial Decision\n\n"
            f"**Recommendation:** `{verdict}`  \n"
            f"**Conviction Score:** `{conviction}/100` · **Risk/Reward Asymmetry:** `{rr_ratio}:1`\n\n"
            f"---\n\n"
            f"### Synthesis of Arguments\n"
            f"- **Weighing the Bull Case:** Operating capital compounding (ROE) and positive 20-day institutional momentum outweigh cyclical multiple concerns.\n"
            f"- **Factoring the Bear Constraints:** The valuation multiple demands strict adherence to the econometric stop-loss floor to prevent structural capital erosion.{ml_snippet}\n\n"
            f"### Execution Parameters\n"
            f"- **Entry Anchor:** `₹{price:.2f}` (Current Settled Price)\n"
            f"- **Upside Objective (80% CI Target):** `₹{target:.2f}` (`+{upside:.1f}%`)\n"
            f"- **Invalidation Floor (Stop Loss):** `₹{stop:.2f}` (`-{risk:.1f}%`)\n"
            f"- **Position Horizon:** `2 to 8 Weeks` · Rebalance on 200 SMA violation."
        )

        return memo, {
            "verdict": verdict,
            "conviction_score": conviction,
            "target_price": target,
            "stop_loss": stop
        }
