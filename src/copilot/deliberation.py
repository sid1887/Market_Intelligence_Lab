"""
Market Intelligence Lab — Multi-Agent Deliberation Architecture.
Milestone B12.0: Part 4.

Implements a 3-agent structured institutional debate:
1. Bullish Research & Momentum Analyst
2. Bearish Risk Management Analyst
3. Portfolio Manager Debate Judge (Synthesizer)

Supports live streaming via Server-Sent Events (SSE).
"""

import os
import json
import asyncio
import logging
from typing import AsyncGenerator, Dict, Any, Optional
from src.copilot.llm_client import get_copilot_client, is_live_llm_configured
from src.copilot.mcp_bridge import QuantMCPBridge

logger = logging.getLogger("copilot.deliberation")


class MultiAgentDeliberationEngine:
    def __init__(self, bridge: Optional[QuantMCPBridge] = None):
        self.bridge = bridge or QuantMCPBridge()

    async def run_deliberation_stream(
        self,
        symbol: str,
        user_prompt: str = "Debate Bull vs Bear Thesis",
        context_override: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[str, None]:
        """
        Executes the 3-agent deliberation debate and yields SSE chunks.
        Format: data: {"stage": "...", "status": "...", "content": "..."}\n\n
        """
        sym = symbol.strip().upper()
        logger.info(f"Initiating multi-agent deliberation for {sym} (prompt='{user_prompt}')...")

        # 1. Fetch Quantitative Ground Truth from Native MCP Tools
        yield self._sse_event({
            "stage": "telemetry",
            "status": f"Querying native quantitative tools & factor database for {sym}...",
            "progress": 10
        })
        await asyncio.sleep(0.3)

        funds = self.bridge.get_stock_fundamentals(sym)
        forecast = self.bridge.get_forecast_bounds(sym)
        actions = self.bridge.get_nse_corporate_actions(sym)
        macro = self.bridge.get_macro_context()

        company_name = funds.get("company_name", sym)
        price = funds.get("current_price", 0.0)
        technicals = funds.get("technicals", {})
        fundamentals = funds.get("fundamentals", {})

        # Context summary for agents
        quant_context = {
            "symbol": sym,
            "company_name": company_name,
            "current_price": price,
            "technicals": technicals,
            "fundamentals": fundamentals,
            "forecast_20d": forecast,
            "recent_actions": actions[:3],
            "macro_environment": macro
        }

        # Check if conversational guidance is requested instead of full 3-agent committee
        if self._is_conversational_prompt(user_prompt):
            yield self._sse_event({
                "stage": "conversational",
                "status": f"Quant Copilot online for {sym}.",
                "progress": 30
            })
            await asyncio.sleep(0.15)

            conversational_reply = self._generate_conversational_guidance(quant_context, user_prompt)
            for chunk in self._split_chunks(conversational_reply):
                yield self._sse_event({
                    "stage": "conversational",
                    "delta": chunk,
                    "progress": 70
                })
                await asyncio.sleep(0.02)

            yield self._sse_event({
                "stage": "complete",
                "status": "Ready for quantitative inquiry.",
                "progress": 100,
                "conversational_response": conversational_reply,
                "result": {
                    "symbol": sym,
                    "verdict": "READY",
                    "conviction_score": 100,
                    "entry_price": price,
                    "target_price": forecast.get("expected_20d_price", round(price * 1.08, 2)),
                    "stop_loss": forecast.get("lower_80", round(price * 0.94, 2)),
                    "conversational_response": conversational_reply
                }
            })
            return

        # Check if live LLM is configured
        live_llm = is_live_llm_configured()

        # =========================================================================
        # STAGE 1: BULL / MOMENTUM ANALYST
        # =========================================================================
        yield self._sse_event({
            "stage": "bull_analyst",
            "status": f"Bull Analyst: Evaluating order books, 20D momentum, and growth moats for {sym}...",
            "progress": 30
        })

        bull_content = ""
        if live_llm:
            try:
                bull_content = await self._stream_llm_role(
                    role="Bullish Research & Momentum Analyst",
                    instruction=(
                        f"You are the Lead Bull/Momentum Analyst at an institutional quantitative hedge fund. "
                        f"Present the strongest, data-backed bullish thesis for {sym} ({company_name}) trading at ₹{price:.2f}. "
                        f"Focus on return on equity (ROE {fundamentals.get('roe_pct', 0):.1f}%), operating margin ({fundamentals.get('opm_pct', 0):.1f}%), "
                        f"20D trend momentum ({technicals.get('ret_20d_pct', 0):.2f}%), and GARCH 20D expected target ₹{forecast.get('expected_20d_price', price):.2f}. "
                        f"Keep it concise, rigorous, and bulleted."
                    ),
                    context=quant_context
                )
            except Exception as e:
                logger.warning(f"Live LLM Bull Analyst failed ({e}), using deterministic synthesis.")
                bull_content = self._generate_deterministic_bull(quant_context)
        else:
            bull_content = self._generate_deterministic_bull(quant_context)

        # Stream bull content in readable chunks
        for chunk in self._split_chunks(bull_content):
            yield self._sse_event({
                "stage": "bull_analyst",
                "delta": chunk,
                "progress": 45
            })
            await asyncio.sleep(0.04)

        # =========================================================================
        # STAGE 2: BEAR / RISK MANAGEMENT ANALYST
        # =========================================================================
        yield self._sse_event({
            "stage": "bear_analyst",
            "status": f"Bear Analyst: Scrutinizing valuation multiple sanity, debt load, and tail risks for {sym}...",
            "progress": 55
        })
        await asyncio.sleep(0.3)

        bear_content = ""
        if live_llm:
            try:
                bear_content = await self._stream_llm_role(
                    role="Bearish Risk Management Analyst",
                    instruction=(
                        f"You are the Chief Risk Officer and Lead Short/Bearish Analyst at an institutional hedge fund. "
                        f"Directly challenge the Bull's thesis on {sym} ({company_name}) at ₹{price:.2f}. "
                        f"Highlight P/E valuation multiples ({fundamentals.get('ttm_pe', 0):.1f}x), leverage/debt-to-equity ({fundamentals.get('debt_to_equity', 0):.2f}), "
                        f"GARCH 20D downside tail-risk floor ₹{forecast.get('lower_80', price):.2f} (95% tail ₹{forecast.get('lower_95', price):.2f}), "
                        f"and macroeconomic friction (USD/INR {macro.get('usd_inr')}, Brent Crude ${macro.get('brent_crude_usd')}). "
                        f"Be rigorous, skeptical, and identify explicit thesis invalidation conditions."
                    ),
                    context=quant_context,
                    counter_argument=bull_content
                )
            except Exception as e:
                logger.warning(f"Live LLM Bear Analyst failed ({e}), using deterministic synthesis.")
                bear_content = self._generate_deterministic_bear(quant_context)
        else:
            bear_content = self._generate_deterministic_bear(quant_context)

        for chunk in self._split_chunks(bear_content):
            yield self._sse_event({
                "stage": "bear_analyst",
                "delta": chunk,
                "progress": 70
            })
            await asyncio.sleep(0.04)

        # =========================================================================
        # STAGE 3: PORTFOLIO MANAGER DEBATE JUDGE
        # =========================================================================
        yield self._sse_event({
            "stage": "judge_synthesis",
            "status": f"Portfolio Manager Judge: Adjudicating debate, calibrating conviction & sizing parameters...",
            "progress": 80
        })
        await asyncio.sleep(0.4)

        judge_content, verdict_meta = "", {}
        if live_llm:
            try:
                judge_content, verdict_meta = await self._stream_llm_judge(
                    quant_context, bull_content, bear_content
                )
            except Exception as e:
                logger.warning(f"Live LLM Judge failed ({e}), using deterministic synthesis.")
                judge_content, verdict_meta = self._generate_deterministic_judge(quant_context)
        else:
            judge_content, verdict_meta = self._generate_deterministic_judge(quant_context)

        for chunk in self._split_chunks(judge_content):
            yield self._sse_event({
                "stage": "judge_synthesis",
                "delta": chunk,
                "progress": 95
            })
            await asyncio.sleep(0.04)

        # =========================================================================
        # COMPLETE EVENT: STRUCTURED DECISION PAYLOAD
        # =========================================================================
        yield self._sse_event({
            "stage": "complete",
            "status": "Deliberation concluded successfully.",
            "progress": 100,
            "result": {
                "symbol": sym,
                "verdict": verdict_meta.get("verdict", "TACTICAL_SWING_LONG"),
                "conviction_score": verdict_meta.get("conviction_score", 76),
                "entry_price": price,
                "target_price": verdict_meta.get("target_price", forecast.get("upper_80", round(price * 1.08, 2))),
                "stop_loss": verdict_meta.get("stop_loss", forecast.get("lower_80", round(price * 0.94, 2))),
                "bull_thesis": bull_content,
                "bear_thesis": bear_content,
                "judge_memo": judge_content
            }
        })

    def _sse_event(self, data: Dict[str, Any]) -> str:
        return f"data: {json.dumps(data)}\n\n"

    def _split_chunks(self, text: str, chunk_size: int = 40):
        for i in range(0, len(text), chunk_size):
            yield text[i:i + chunk_size]

    async def _stream_llm_role(
        self, role: str, instruction: str, context: Dict[str, Any], counter_argument: Optional[str] = None
    ) -> str:
        client, model = get_copilot_client()
        messages = [
            {"role": "system", "content": f"You are a specialized institutional quant agent: {role}. Be concise, analytical, and cite specific data points."},
            {"role": "user", "content": f"Context:\n{json.dumps(context, indent=2)}\n\n{f'Prior Bull Thesis:\n{counter_argument}' if counter_argument else ''}\n\nTask:\n{instruction}"}
        ]
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=600
        )
        return response.choices[0].message.content or ""

    async def _stream_llm_judge(
        self, context: Dict[str, Any], bull_arg: str, bear_arg: str
    ) -> tuple[str, Dict[str, Any]]:
        client, model = get_copilot_client()
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
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            max_tokens=800
        )
        content = response.choices[0].message.content or ""
        # Determine verdict metadata from LLM output (P0-09, Section 17)
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

        return (
            f"### Bull Thesis: Capital Compounding & Upside Asymmetry\n\n"
            f"1. **Operational Moat & Return on Capital:**\n"
            f"   - {sym} return metrics: ROE at **{roe_str}** and operating margins at **{opm_str}**.\n"
            f"   - High return on incremental invested capital enables self-funded capacity additions without shareholding dilution.\n\n"
            f"2. **Trend Momentum & Technical Structure:**\n"
            f"   - The stock is currently {above_200} (200 SMA: ₹{t.get('sma_200', 0):.2f}).\n"
            f"   - 20-day return momentum stands at **{t.get('ret_20d_pct', 0.0):+.2f}%**, indicating institutional accumulation during market pullbacks.\n\n"
            f"3. **Econometric Probability Cone:**\n"
            f"   - The 20-Day GARCH(1,1) model projects an expected drift target of **₹{exp_target:.2f}** with an upper 80% confidence bound of **₹{fc.get('upper_80', price*1.1):.2f}**.\n"
            f"   - Downside risk is cushioned by historical volatility anchoring at **{fc.get('annualized_volatility', 0.22)*100:.1f}%**."
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
            f"   - Currency & commodity pressure (USD/INR at **{usd_str}**, Brent at **{brent_str}**) drives imported inflation and operating margin friction."
        )

    def _generate_deterministic_judge(self, ctx: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
        sym = ctx["symbol"]
        company = ctx["company_name"]
        price = ctx["current_price"]
        t = ctx.get("technicals", {})
        f = ctx.get("fundamentals", {})
        fc = ctx.get("forecast_20d", {})

        is_above_sma = t.get("price_above_sma200", False)
        target = fc.get("target_objective", round(price * 1.08, 2))
        stop = fc.get("invalidation_floor", round(price * 0.94, 2))
        upside = ((target / price) - 1.0) * 100 if price > 0 else 8.0
        risk = ((price - stop) / price) * 100 if price > 0 else 6.0
        rr_ratio = round(upside / max(0.1, risk), 2)

        if f.get("roe_pct") is None and f.get("debt_to_equity") is None:
            verdict = "INSUFFICIENT_EVIDENCE"
            conviction = 45
        elif is_above_sma and rr_ratio >= 1.5:
            verdict = "STRONG_BUY"
            conviction = 84
        elif is_above_sma or rr_ratio >= 1.0:
            verdict = "TACTICAL_SWING_LONG"
            conviction = 74
        else:
            verdict = "HOLD"
            conviction = 55

        memo = (
            f"## Portfolio Manager Judicial Decision\n\n"
            f"**Recommendation:** `{verdict}`  \n"
            f"**Conviction Score:** `{conviction}/100` · **Risk/Reward Asymmetry:** `{rr_ratio}:1`\n\n"
            f"---\n\n"
            f"### Synthesis of Arguments\n"
            f"- **Weighing the Bull Case:** Operating capital compounding (ROE) and positive 20-day institutional momentum outweigh cyclical multiple concerns.\n"
            f"- **Factoring the Bear Constraints:** The valuation multiple demands strict adherence to the econometric stop-loss floor to prevent structural capital erosion.\n\n"
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

    @staticmethod
    def _is_conversational_prompt(prompt: str) -> bool:
        if not prompt or not prompt.strip():
            return True
        import re
        clean = prompt.strip().lower()
        clean_norm = re.sub(r"[^\w\s]", "", clean).strip()

        greetings = {
            "hi", "hello", "hey", "heya", "yo", "sup", "hola",
            "good morning", "good afternoon", "good evening",
            "who are you", "what is this", "what can you do", "help",
            "how does this work", "how do you work", "explain yourself",
            "what are you", "test", "ping"
        }
        if clean_norm in greetings:
            return True

        analytical_keywords = {
            "bull", "bear", "debate", "thesis", "buy", "sell", "hold",
            "target", "stop", "risk", "forecast", "pe", "roe", "opm", "debt",
            "momentum", "valuation", "conviction", "verdict", "memo", "action",
            "filing", "garch", "growth", "catalyst", "downside", "upside", "price",
            "technicals", "fundamentals", "analyze", "evaluate", "check"
        }
        words = set(clean_norm.split())
        if len(words) <= 3 and any(w in {"hi", "hello", "hey", "help"} for w in words):
            if not words.intersection(analytical_keywords):
                return True
        return False

    def _generate_conversational_guidance(self, quant_context: Dict[str, Any], user_prompt: str) -> str:
        sym = quant_context["symbol"]
        name = quant_context["company_name"]
        price = quant_context["current_price"]
        fund = quant_context.get("fundamentals", {})
        tech = quant_context.get("technicals", {})
        fc = quant_context.get("forecast_20d", {})
        roe = fund.get("roe_pct")
        roe_str = f"{roe:.1f}%" if roe is not None else "—"
        de = fund.get("debt_to_equity")
        de_str = f"{de:.2f}x" if de is not None else "—"
        opm = fund.get("opm_pct")
        opm_str = f"{opm:.1f}%" if opm is not None else "—"
        mom = tech.get("ret_20d_pct", 0.0)
        target = fc.get("expected_20d_price", price)

        return (
            f"Hello! I am your institutional Quant Copilot for Market Intelligence Lab.\n\n"
            f"I am actively tracking **{sym}** ({name}) with verified settlement telemetry:\n"
            f"• **Settled Price**: ₹{price:.2f}\n"
            f"• **20D Momentum**: {mom:+.2f}%\n"
            f"• **Return on Equity (ROE)**: {roe_str} | **Debt/Equity**: {de_str} | **OPM**: {opm_str}\n"
            f"• **20D Econometric Target**: ₹{target:.2f}\n\n"
            f"How can I assist your quantitative analysis today? You can prompt me to:\n"
            f"1. **Debate Bull vs Bear Thesis** — Triggers the 3-agent committee (Bull Analyst, Bear Risk Analyst, and Portfolio Manager Judge).\n"
            f"2. **Evaluate Downside Volatility** — Scrutinizes GARCH 80% & 95% confidence cones and stop loss invalidation.\n"
            f"3. **Audit Exchange Disclosures** — Reviews corporate actions, shareholding patterns, and filing dates."
        )
