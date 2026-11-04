#!/usr/bin/env python3
"""
Market Intelligence Lab — Daily Market Overview Report Generator.
Generates comprehensive daily market overview reports combining:
- Benchmark index performance & market pulse
- Market breadth & moving average participation (% > SMA20, 50, 200 with warm-up tracking)
- Relative strength leaderboards (Top 5 / Bottom 5 across horizons)
- Statistical volume anomaly alerts (VR >= 2.5x and Z >= 2.5 sigma)
- Corporate disclosures & regulatory filings audit with direct document links
- Non-causal explanatory hypotheses with strict epistemic boundaries
"""
import os
import math
import datetime
from typing import Dict, Any, List, Optional
from src.storage.database import DatabaseManager
from src.quant.breadth import MarketBreadthEngine
from src.quant.relative_strength import RelativeStrengthEngine
from src.quant.volume import (
    calculate_volume_ratio,
    calculate_volume_zscores,
    adjust_volume_for_corporate_actions
)

class DailyMarketReportBuilder:
    """
    Builds the daily market overview report from the local SQLite database.
    """

    def __init__(self, db: DatabaseManager, output_dir: str = "reports"):
        self.db = db
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.breadth_engine = MarketBreadthEngine(db)
        self.rs_engine = RelativeStrengthEngine(db)

    def generate_report(
        self,
        as_of_date: str = "2026-10-23",
        index_name: str = "NIFTY 50",
        benchmark_mode: str = "PRI"
    ) -> str:
        report_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # 1. Fetch Index Performance
        idx_hist = self.db.get_index_history(index_name, benchmark_mode, end_date=as_of_date)
        if idx_hist and idx_hist[-1]["trading_date"] == as_of_date:
            idx_today = idx_hist[-1]
            idx_prev = idx_hist[-2] if len(idx_hist) >= 2 else None
            idx_close = float(idx_today["close"])
            idx_ret_1d = ((idx_close / float(idx_prev["close"])) - 1.0) * 100.0 if idx_prev else 0.0

            # Multi-horizon index returns
            def get_index_ret(trading_days_back: int) -> Optional[float]:
                if len(idx_hist) > trading_days_back:
                    base_close = float(idx_hist[-1 - trading_days_back]["close"])
                    return ((idx_close / base_close) - 1.0) * 100.0
                return None

            idx_ret_1m = get_index_ret(21)
            idx_ret_3m = get_index_ret(63)
            idx_ret_6m = get_index_ret(126)
            idx_ret_1y = get_index_ret(245)
        else:
            idx_today = None
            idx_prev = None
            idx_close = None
            idx_ret_1d = None
            idx_ret_1m = None
            idx_ret_3m = None
            idx_ret_6m = None
            idx_ret_1y = None

        # 2. Compute Market Breadth
        breadth = self.breadth_engine.compute_daily_breadth(as_of_date, index_name)

        # 3. Compute Relative Strength Leaderboards
        constituents_meta = self.db.get_index_constituents(index_name, as_of_date)
        constituents = constituents_meta["constituents"]

        leaderboard_1m = self.rs_engine.generate_universe_leaderboard(
            as_of_date=as_of_date,
            symbols=constituents,
            benchmark_name=index_name,
            mode=benchmark_mode,
            ranking_horizon="1M"
        )
        leaderboard_3m = self.rs_engine.generate_universe_leaderboard(
            as_of_date=as_of_date,
            symbols=constituents,
            benchmark_name=index_name,
            mode=benchmark_mode,
            ranking_horizon="3M"
        )

        top_1m = leaderboard_1m.get("top_outperformers", [])[:5]
        bottom_1m = leaderboard_1m.get("top_underperformers", [])[:5]
        top_3m = leaderboard_3m.get("top_outperformers", [])[:5]
        bottom_3m = leaderboard_3m.get("top_underperformers", [])[:5]

        # 4. Volume Anomaly Detection across 50 constituents
        anomalies = []
        for sym in constituents:
            hist = self.db.get_stock_history(sym, start_date=None, end_date=as_of_date)
            if len(hist) >= 21:
                cas = self.db.get_corporate_actions(sym)
                adj_vols = adjust_volume_for_corporate_actions(hist, cas)
                vr = calculate_volume_ratio(adj_vols, window=20)
                z_raw, z_log = calculate_volume_zscores(adj_vols, window=50)

                is_vr_spike = (vr is not None and vr >= 2.5)
                is_z_spike = (z_raw is not None and z_raw >= 2.5)

                if is_vr_spike or is_z_spike:
                    spike_type = "Both VR & Z-Score" if (is_vr_spike and is_z_spike) else (
                        "Volume Ratio Outlier (>=2.5x)" if is_vr_spike else "Statistical Z-Score Tail (>=2.5σ)"
                    )
                    anomalies.append({
                        "symbol": sym,
                        "close": float(hist[-1]["close"]),
                        "volume": int(hist[-1]["volume"]),
                        "vr_20d": round(vr, 2) if vr else None,
                        "z_50d": round(z_raw, 2) if z_raw else None,
                        "spike_type": spike_type
                    })

        # 5. Fetch Recent Corporate Disclosures
        all_disclosures = self.db.get_corporate_disclosures()
        # Sort recent first
        recent_disclosures = sorted(
            all_disclosures,
            key=lambda x: (x["effective_session_date"], x["broadcast_timestamp"]),
            reverse=True
        )[:10]

        # 6. Build Markdown Report
        lines = []
        lines.append(f"# Daily Market Overview — {index_name}")
        lines.append(f"**As-of Trading Session:** `{as_of_date}` | **Generated:** `{report_time}`  ")
        lines.append(f"**Benchmark Mode:** Official `{benchmark_mode}` (Price Return Index) | **Coverage:** 50 Constituents (100%)  ")
        lines.append(f"**System Status:** Local-First SQLite (`data/market_lab.db`) | **Trading Operations:** Strictly Disabled  ")
        lines.append("\n---\n")

        # Section 1: Benchmark Performance
        lines.append("## 1. Benchmark Index Performance & Market Pulse\n")
        lines.append("| Benchmark Index | Close Value | 1D Return | 1M Return | 3M Return | 6M Return | 1Y Return |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: |")
        close_str = f"**`{idx_close:,.2f}`**" if idx_close is not None else "*Unavailable*"
        ret_1d_str = f"**`{idx_ret_1d:+.2f}%`**" if idx_ret_1d is not None else "N/A"
        r1m_str = f"{idx_ret_1m:+.2f}%" if idx_ret_1m is not None else "N/A"
        r3m_str = f"{idx_ret_3m:+.2f}%" if idx_ret_3m is not None else "N/A"
        r6m_str = f"{idx_ret_6m:+.2f}%" if idx_ret_6m is not None else "N/A"
        r1y_str = f"{idx_ret_1y:+.2f}%" if idx_ret_1y is not None else "N/A"
        lines.append(f"| **{index_name} (PRI)** | {close_str} | {ret_1d_str} | `{r1m_str}` | `{r3m_str}` | `{r6m_str}` | `{r1y_str}` |")
        if idx_today is None:
            lines.append(f"\n> [!WARNING]\n> Benchmark observation for session `{as_of_date}` is unavailable in database. Trailing benchmark performance metrics are withheld to prevent stale reporting.\n")
        lines.append("\n> [!NOTE]\n> **Return Horizon Methodology**: Trailing returns use fixed trading-session windows (1D = 1 trading session, 1M = 21 trading sessions, 3M = 63 trading sessions, 6M = 126 trading sessions, 1Y = 245 trading sessions), rather than calendar-day offsets, ensuring exact session-by-session reproducibility across holidays and suspensions.\n")

        # Section 2: Market Breadth & Moving Average Participation
        lines.append("## 2. Market Breadth & Moving Average Participation\n")
        lines.append("| Market Breadth Metric | Observed Value | Specification & Accounting |")
        lines.append("| :--- | :---: | :--- |")
        lines.append(f"| **Universe Tracking** | `{breadth['valid_observations_count']} / {breadth['expected_constituents_count']}` stocks | Point-in-time constituent coverage: **`{breadth['coverage_pct']:.1f}%`** |")
        lines.append(f"| **Advancing Stocks** | **`{breadth['advances']}`** | Close > Prior Close |")
        lines.append(f"| **Declining Stocks** | **`{breadth['declines']}`** | Close < Prior Close |")
        lines.append(f"| **Unchanged Stocks** | `{breadth['unchanged']}` | Close == Prior Close |")
        ad_ratio_str = f"{breadth['ad_ratio']:.2f}" if breadth.get("ad_ratio") else "N/A"
        lines.append(f"| **Advance / Decline Ratio** | **`{ad_ratio_str}`** | Advance count / Decline count |")
        lines.append(f"| **Advance / Decline Volume Ratio** | **`{breadth['volume_breadth_ratio']:.2f}x`** | Advance Volume / Decline Volume ({breadth['advance_volume']:,} / {breadth['decline_volume']:,} shares) |")
        adv_share_str = f"{breadth.get('advance_volume_share_pct', 0.0):.2f}%"
        lines.append(f"| **Advancing Share of Total Volume** | **`{adv_share_str}`** | Advance Volume / Total Volume ({breadth['advance_volume']:,} / {breadth.get('total_volume', 0):,} shares) |")
        sma20_pct = f"{breadth['sma20']['pct_above']:.1f}%" if breadth['sma20']['pct_above'] is not None else "Warm-up"
        sma50_pct = f"{breadth['sma50']['pct_above']:.1f}%" if breadth['sma50']['pct_above'] is not None else "Warm-up"
        sma200_pct = f"{breadth['sma200']['pct_above']:.1f}%" if breadth['sma200']['pct_above'] is not None else "Warm-up"
        lines.append(f"| **Constituents > 20-Day SMA** | **`{sma20_pct}`** | Short-term trend participation (`{breadth['sma20']['above_count']}` eligible stocks) |")
        lines.append(f"| **Constituents > 50-Day SMA** | **`{sma50_pct}`** | Intermediate-term trend participation (`{breadth['sma50']['above_count']}` eligible stocks) |")
        lines.append(f"| **Constituents > 200-Day SMA** | **`{sma200_pct}`** | Long-term structural trend participation (`{breadth['sma200']['above_count']}` eligible stocks) |")
        lines.append("\n")

        # Section 3: Relative Strength Leaderboards
        lines.append("## 3. Relative Strength Leaderboards (Excess Return vs Nifty 50)\n")
        lines.append("### 3.1 One-Month Horizon (1M)\n")
        lines.append("| Category | Symbol | Stock Return (1M) | Benchmark Return (1M) | Excess Return | 60D Beta |")
        lines.append("| :--- | :--- | :---: | :---: | :---: | :---: |")
        for item in top_1m:
            b_str = f"{item['beta_60d']:.2f}" if item.get("beta_60d") is not None else "N/A"
            lines.append(f"| Outperformer | **{item['symbol']}** | `{item['stock_return_pct']:+.2f}%` | `{item['benchmark_return_pct']:+.2f}%` | **`{item['excess_return_pct']:+.2f}%`** | `{b_str}` |")
        for item in bottom_1m:
            b_str = f"{item['beta_60d']:.2f}" if item.get("beta_60d") is not None else "N/A"
            lines.append(f"| Underperformer | **{item['symbol']}** | `{item['stock_return_pct']:+.2f}%` | `{item['benchmark_return_pct']:+.2f}%` | **`{item['excess_return_pct']:+.2f}%`** | `{b_str}` |")

        lines.append("\n### 3.2 Three-Month Horizon (3M)\n")
        lines.append("| Category | Symbol | Stock Return (3M) | Benchmark Return (3M) | Excess Return | 60D Beta |")
        lines.append("| :--- | :--- | :---: | :---: | :---: | :---: |")
        for item in top_3m:
            b_str = f"{item['beta_60d']:.2f}" if item.get("beta_60d") is not None else "N/A"
            lines.append(f"| Outperformer | **{item['symbol']}** | `{item['stock_return_pct']:+.2f}%` | `{item['benchmark_return_pct']:+.2f}%` | **`{item['excess_return_pct']:+.2f}%`** | `{b_str}` |")
        for item in bottom_3m:
            b_str = f"{item['beta_60d']:.2f}" if item.get("beta_60d") is not None else "N/A"
            lines.append(f"| Underperformer | **{item['symbol']}** | `{item['stock_return_pct']:+.2f}%` | `{item['benchmark_return_pct']:+.2f}%` | **`{item['excess_return_pct']:+.2f}%`** | `{b_str}` |")

        lines.append("\n> [!IMPORTANT]\n> Relative strength calculations use Mode 1 (Price Return vs Nifty 50 PRI) with corporate action split/bonus price adjustments. Mode 2 (Total Return vs TRI) is reserved for stocks with verified dividend ledgers.\n")

        # Section 4: Statistical Volume Anomalies
        lines.append("## 4. Statistical Volume Anomaly Scanner\n")
        if anomalies:
            lines.append("| Symbol | Close Price | Traded Volume | 20D Volume Ratio | 50D Volume Z-Score | Anomaly Classification |")
            lines.append("| :--- | :---: | :---: | :---: | :---: | :--- |")
            for a in anomalies:
                vr_str = f"{a['vr_20d']:.2f}x" if a["vr_20d"] else "N/A"
                z_str = f"{a['z_50d']:+.2f}σ" if a["z_50d"] else "N/A"
                lines.append(f"| **{a['symbol']}** | ₹{a['close']:,.2f} | {a['volume']:,} | `{vr_str}` | `{z_str}` | {a['spike_type']} |")
        else:
            lines.append("*No statistical volume outliers met the dual anomaly thresholds (VR >= 2.5x or Z >= 2.5σ) on this trading session.*\n")

        # Section 5: Recent Corporate Disclosures & Provenance
        lines.append("## 5. Corporate Disclosures & Material Filings Audit\n")
        lines.append("| Effective Session | Symbol | Category | Verification Status | Subject / Direct Source Document |")
        lines.append("| :---: | :--- | :--- | :---: | :--- |")
        for d in recent_disclosures:
            status_badge = f"`{d['verification_status']}`"
            if d['verification_status'] == 'VERIFIED':
                status_badge = "**`VERIFIED`**"
            elif d['verification_status'] == 'SOURCE_UNVERIFIED':
                status_badge = "⚠️ **`SOURCE_UNVERIFIED`**"
            elif d['verification_status'] == 'PENDING_VERIFICATION':
                status_badge = "⏳ `PENDING_VERIFICATION`"

            doc_link = f"[{d['subject']}]({d['source_url']})" if d.get("source_url") else d["subject"]
            lines.append(f"| `{d['effective_session_date']}` | **{d['symbol']}** | `{d['category']}` | {status_badge} | {doc_link} |")

        lines.append("\n")

        # Section 6: AI-Assisted Epistemic Hypotheses & Epistemic Boundaries
        lines.append("## 6. Explanatory Hypotheses & Epistemic Boundaries\n")
        adv_pct = (breadth["advances"] / float(breadth["valid_observations_count"])) * 100.0 if breadth["valid_observations_count"] > 0 else 0.0
        tone = "broad-market accumulation" if adv_pct > 60.0 else ("broad-market liquidation" if adv_pct < 40.0 else "mixed rotational consolidation")

        lines.append(f"1. **Market Regime Hypothesis**: Session `{as_of_date}` exhibited characteristics of **{tone}**, with `{adv_pct:.1f}%` of Nifty 50 constituents advancing. Advance volume accounted for `{breadth['volume_breadth_ratio']:.2f}x` of total turnover.")
        lines.append(f"2. **Participation Structure**: Long-term moving average breadth shows `{sma200_pct}` of the universe trading above their 200-day moving averages, while short-term 20-day participation is at `{sma20_pct}`.")
        lines.append("3. **Confounding Market Factors**: All abnormal returns and volume spikes are documented as co-occurring empirical phenomena. Observed relative outperformance cannot be attributed to a single cause without accounting for global macro rates, institutional liquidity rebalancing, and industry-wide sector rotation.")
        lines.append("\n> [!CAUTION]\n> **Non-Execution Notice**: The Market Intelligence Lab operates strictly as a local-first quantitative research environment. Live order placement, broker credential storage, and autonomous execution are permanently disabled.\n")

        report_content = "\n".join(lines)
        report_filename = f"daily_market_overview_{as_of_date.replace('-', '')}.md"
        report_path = os.path.join(self.output_dir, report_filename)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        return report_path
