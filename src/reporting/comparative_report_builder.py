import os
import datetime
from typing import Dict, Any, List, Optional
from src.quant.breadth import MarketBreadthEngine
from src.quant.relative_strength import RelativeStrengthEngine
from src.quant.volume import (
    calculate_volume_ratio,
    calculate_volume_zscores,
    adjust_volume_for_corporate_actions
)
from src.storage.database import DatabaseManager

class ComparativeReportBuilder:
    """
    Builds comprehensive markdown comparative research reports:
    - Market breadth dashboard with explicit coverage metrics
    - Relative strength leaderboard (Mode 1 PRI and Mode 2 TRI)
    - Dual volume anomaly detection (VR vs Z-Score)
    - Full source attribution and mathematical formulas in KaTeX
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
        # 1. Compute Breadth
        breadth = self.breadth_engine.compute_daily_breadth(as_of_date, index_name)

        # 2. Get constituents
        constituents = self.db.get_index_constituents(index_name, as_of_date)["constituents"]

        # 3. Compute Relative Strength Leaderboard
        leaderboard = self.rs_engine.generate_universe_leaderboard(
            as_of_date=as_of_date,
            symbols=constituents,
            benchmark_name=index_name,
            mode=benchmark_mode,
            ranking_horizon="1M"
        )

        # 4. Volume Anomaly Scan across universe
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
                    anomalies.append({
                        "symbol": sym,
                        "close": float(hist[-1]["close"]),
                        "today_volume": int(hist[-1]["volume"]),
                        "volume_ratio_20d": round(vr, 2) if vr else None,
                        "volume_zscore_50d": round(z_raw, 2) if z_raw else None,
                        "volume_log_zscore_50d": round(z_log, 2) if z_log else None,
                        "spike_type": "Both VR & Z-Score" if (is_vr_spike and is_z_spike) else ("Volume Ratio Outlier" if is_vr_spike else "Statistical Z-Score Tail")
                    })

        # 5. Fetch Index Benchmark Bar for Header
        idx_bars = self.db.get_index_history(index_name, benchmark_mode, as_of_date, as_of_date)
        idx_close = idx_bars[0]["close"] if idx_bars else None

        # Build Markdown Document
        report_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = []

        lines.append(f"# Market Intelligence Lab — Comparative Analytics Report")
        lines.append(f"**As of Trading Session:** `{as_of_date}` | **Generated At:** `{report_time}`  ")
        lines.append(f"**Benchmark:** `{index_name}` (`{benchmark_mode}` Mode) | **Index Close:** `{idx_close:,.2f}`  " if idx_close else f"**Benchmark:** `{index_name}`  ")
        lines.append(f"**Research Universe:** Nifty 50 Constituents | **System Status:** Local-First / Research Only  ")
        lines.append("\n---\n")

        # Section 1: Executive Breadth Summary
        lines.append("## 1. Market Breadth & Participation Dashboard\n")
        lines.append("| Metric | Value | Reference / Notes |")
        lines.append("| :--- | :---: | :--- |")
        lines.append(f"| **Expected Constituents** | `{breadth['expected_constituents_count']}` | Point-in-time constituent universe |")
        lines.append(f"| **Valid Observations** | `{breadth['valid_observations_count']}` | Clean settled exchange observations |")
        lines.append(f"| **Data Coverage** | **`{breadth['coverage_pct']:.1f}%`** | Missing: `{breadth['missing_observations_count']}` stocks |")
        lines.append(f"| **Survivorship-Bias Status** | `{'VERIFIED FREE' if breadth['is_survivorship_bias_free'] else 'PROXY UNADJUSTED'}` | Basis: `{breadth['membership_basis']}` |")
        lines.append(f"| **Advancing Stocks** | `{breadth['advances']}` | Close > Previous Close |")
        lines.append(f"| **Declining Stocks** | `{breadth['declines']}` | Close < Previous Close |")
        lines.append(f"| **Unchanged Stocks** | `{breadth['unchanged']}` | Close == Previous Close |")
        ad_ratio_str = f"{breadth['ad_ratio']:.2f}" if breadth.get("ad_ratio") else "N/A"
        lines.append(f"| **Advance / Decline Ratio** | `{ad_ratio_str}` | Advancing / Declining count |")
        lines.append(f"| **Volume Breadth Ratio** | `{breadth['volume_breadth_ratio']:.2f}x` | Advance Volume / Decline Volume |")
        lines.append(f"| **Total Advance Volume** | `{breadth['advance_volume']:,}` shares | Cumulative turnover across advancers |")
        lines.append(f"| **Total Decline Volume** | `{breadth['decline_volume']:,}` shares | Cumulative turnover across decliners |")

        lines.append("\n### Moving Average Participation (% Above Trend)\n")
        lines.append("| Indicator | Eligible Stocks | Stocks Above | % Above | Regime / Status |")
        lines.append("| :--- | :---: | :---: | :---: | :--- |")

        sma20 = breadth["sma20"]
        p20_str = f"{sma20['pct_above']:.1f}%" if sma20['pct_above'] is not None else "Warm-up"
        lines.append(f"| **20-Day SMA** | `{sma20['eligible_count']}` | `{sma20['above_count']}` | **`{p20_str}`** | Short-term momentum |")

        sma50 = breadth["sma50"]
        p50_str = f"{sma50['pct_above']:.1f}%" if sma50['pct_above'] is not None else "Warm-up"
        lines.append(f"| **50-Day SMA** | `{sma50['eligible_count']}` | `{sma50['above_count']}` | **`{p50_str}`** | Intermediate trend |")

        sma200 = breadth["sma200"]
        p200_str = f"{sma200['pct_above']:.1f}%" if sma200['pct_above'] is not None else "Warm-up (<200d)"
        lines.append(f"| **200-Day SMA** | `{sma200['eligible_count']}` | `{sma200['above_count']}` | **`{p200_str}`** | Structural long-term regime |")

        if breadth.get("membership_warning"):
            lines.append(f"\n> [!WARNING]\n> {breadth['membership_warning']}\n")

        lines.append("\n---\n")

        # Section 2: Relative Strength Leaderboard
        lines.append("## 2. Relative Strength Leaderboard vs. Nifty 50\n")
        lines.append(f"**Ranking Criterion:** Trailing 1-Month (21-Day) Excess Return over `{index_name} {benchmark_mode}`  ")
        lines.append(f"**Comparison Mode:** `MODE 1 (PRICE RETURN)` | Total Stocks Evaluated: `{leaderboard['total_ranked']}`\n")

        lines.append("### Top 10 Outperformers\n")
        lines.append("| Rank | Symbol | Latest Close | 1M Stock Return | 1M Nifty Return | 1M Excess Return | 60-Day Beta |")
        lines.append("| :---: | :--- | :---: | :---: | :---: | :---: | :---: |")
        for i, item in enumerate(leaderboard["top_outperformers"], 1):
            lines.append(
                f"| {i} | **`{item['symbol']}`** | ₹{item['latest_close']:,.2f} | "
                f"`{item['stock_return_pct']:+.2f}%` | `{item['benchmark_return_pct']:+.2f}%` | "
                f"**`{item['excess_return_pct']:+.2f}%`** | `{item['beta_60d']}` |"
            )

        lines.append("\n### Top 10 Underperformers\n")
        lines.append("| Rank | Symbol | Latest Close | 1M Stock Return | 1M Nifty Return | 1M Excess Return | 60-Day Beta |")
        lines.append("| :---: | :--- | :---: | :---: | :---: | :---: | :---: |")
        for i, item in enumerate(leaderboard["top_underperformers"], 1):
            lines.append(
                f"| {i} | **`{item['symbol']}`** | ₹{item['latest_close']:,.2f} | "
                f"`{item['stock_return_pct']:+.2f}%` | `{item['benchmark_return_pct']:+.2f}%` | "
                f"**`{item['excess_return_pct']:+.2f}%`** | `{item['beta_60d']}` |"
            )

        lines.append("\n---\n")

        # Section 3: Volume Anomaly Scanner
        lines.append("## 3. Volume Anomaly Detection (Dual Metric Scan)\n")
        lines.append("Screening criteria: **Volume Ratio** $\\text{VR}_{20} \\ge 2.5\\times$ OR **Volume Z-Score** $Z_{V, 50} \\ge 2.5\\sigma$.  ")
        lines.append("All historical volumes are share-count adjusted to prevent stock split or bonus issue distortions.\n")

        if anomalies:
            lines.append("| Symbol | Close Price | Session Volume | Volume Ratio (20d) | Volume Z-Score (50d) | Log Z-Score | Anomaly Classification |")
            lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :--- |")
            for a in anomalies:
                lines.append(
                    f"| **`{a['symbol']}`** | ₹{a['close']:,.2f} | `{a['today_volume']:,}` | "
                    f"**`{a['volume_ratio_20d']}x`** | **`{a['volume_zscore_50d']}σ`** | `{a['volume_log_zscore_50d']}σ` | `{a['spike_type']}` |"
                )
        else:
            lines.append("> [!NOTE]\n> No stocks in the evaluated universe crossed the $\\text{VR}_{20} \\ge 2.5\\times$ or $Z_{V, 50} \\ge 2.5\\sigma$ threshold on this session.\n")

        lines.append("\n---\n")

        # Section 4: Quantitative Methodology & KaTeX Formulations
        lines.append("## 4. Quantitative Methodology & Mathematical Formulations\n")
        lines.append("### 1. Volume Ratio vs. Volume Z-Score")
        lines.append("$$\\text{VR}_{t, 20} = \\frac{V_t}{\\frac{1}{20}\\sum_{i=1}^{20} V_{t-i}}, \\qquad Z_{V, t, 50} = \\frac{V_t - \\mu_{V, 50}}{\\sigma_{V, 50}}, \\qquad Z_{\\ln V, t, 50} = \\frac{\\ln(V_t) - \\mu_{\\ln V}}{\\sigma_{\\ln V}}$$")
        lines.append("Where historical volume series are scaled by corporate action multipliers: $V_{\\text{adj}, t} = V_t / \\prod_{\\tau > t} k_\\tau$.\n")

        lines.append("### 2. Rolling Beta Formulation")
        lines.append("$$\\beta_{60d} = \\frac{\\text{Cov}(R_{\\text{stock}}, R_{\\text{benchmark}})}{\\text{Var}(R_{\\text{benchmark}})} = \\frac{\\sum_{i=1}^{60} (R_{s, i} - \\bar{R}_s)(R_{b, i} - \\bar{R}_b)}{\\sum_{i=1}^{60} (R_{b, i} - \\bar{R}_b)^2}$$")
        lines.append("Evaluated strictly on aligned trading session pairs with identical economic return modes.\n")

        lines.append("### 3. Advance / Decline Volume Breadth")
        lines.append("$$\\text{Volume Breadth Ratio} = \\frac{\\sum_{i \\in \\text{Advancing}} V_{i, t}}{\\sum_{j \\in \\text{Declining}} V_{j, t}}$$")

        lines.append("\n---\n*Report generated by Market Intelligence Lab Quantitative Analytics Core (Milestone 2.2).*")

        report_content = "\n".join(lines)
        report_path = os.path.join(self.output_dir, "market_breadth_and_relative_strength.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        return report_path
