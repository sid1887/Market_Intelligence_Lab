"""
Market Intelligence Lab: Offline SVG Visualizer.
Generates pure, self-contained SVG graphics for stock movement reports.
Requires zero external network requests, CDNs, or Javascript dependencies.
"""

from typing import Dict, Any, Optional, List


def generate_performance_chart_svg(
    stock_symbol: str,
    stock_return: Optional[float],
    benchmark_name: str,
    benchmark_return: Optional[float],
    sector_name: str,
    sector_return: Optional[float],
    width: int = 560,
    height: int = 180
) -> str:
    """
    Renders an offline SVG bar chart comparing Stock Return, Benchmark Return, and Sector Return.
    """
    s_ret = 0.0 if stock_return is None else float(stock_return)
    items = [(stock_symbol, s_ret)]
    if benchmark_return is not None:
        items.append((benchmark_name, benchmark_return))
    if sector_return is not None:
        items.append((sector_name, sector_return))

    max_abs = max(max(abs(r) for _, r in items), 0.02) * 1.25
    zero_x = width // 2
    bar_height = 24
    gap = 14
    start_y = 35

    svg_lines = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="background:#ffffff; border-radius:6px; font-family:system-ui, sans-serif;">',
        f'  <rect width="{width}" height="{height}" fill="#f8fafc" rx="6" />',
        f'  <text x="20" y="24" font-size="12" font-weight="700" fill="#334155">1-DAY PERFORMANCE DECOMPOSITION (PRI BASIS)</text>',
        f'  <line x1="{zero_x}" y1="30" x2="{zero_x}" y2="{height - 15}" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="3 3" />',
        f'  <text x="{zero_x}" y="{height - 4}" font-size="10" fill="#64748b" text-anchor="middle">0.0% Baseline</text>'
    ]

    for i, (label, ret) in enumerate(items):
        y = start_y + i * (bar_height + gap)
        bar_w = int((abs(ret) / max_abs) * (width // 2 - 80))
        bar_w = max(bar_w, 2)
        
        if ret >= 0:
            bar_x = zero_x
            fill_color = "#16a34a"  # Green
            text_x = bar_x + bar_w + 6
            text_anchor = "start"
        else:
            bar_x = zero_x - bar_w
            fill_color = "#dc2626"  # Red
            text_x = bar_x - 6
            text_anchor = "end"

        # Label on left
        svg_lines.append(f'  <text x="20" y="{y + 16}" font-size="11" font-weight="600" fill="#1e293b">{label}</text>')
        # Bar
        svg_lines.append(f'  <rect x="{bar_x}" y="{y}" width="{bar_w}" height="{bar_height}" fill="{fill_color}" rx="3" />')
        # Value label
        svg_lines.append(f'  <text x="{text_x}" y="{y + 16}" font-size="11" font-weight="700" fill="{fill_color}" text-anchor="{text_anchor}">{ret:+.2%}</text>')

    svg_lines.append('</svg>')
    return "\n".join(svg_lines)


def generate_drift_decomposition_svg(
    gap_open: Optional[float],
    intraday_drift: Optional[float],
    total_adj_return: Optional[float],
    width: int = 560,
    height: int = 150
) -> str:
    """
    Renders an offline SVG chart visualizing Overnight Gap vs Intraday Drift vs Net Return.
    """
    g_val = 0.0 if gap_open is None else float(gap_open)
    d_val = 0.0 if intraday_drift is None else float(intraday_drift)
    r_val = 0.0 if total_adj_return is None else float(total_adj_return)
    items = [
        ("Overnight Gap", g_val, "#0284c7"),       # Blue
        ("Intraday Drift", d_val, "#8b5cf6"), # Purple
        ("Net Return (Adj)", r_val, "#0d9488") # Teal
    ]

    max_abs = max(max(abs(r) for _, r, _ in items), 0.02) * 1.25
    zero_x = width // 2
    bar_height = 20
    gap = 12
    start_y = 35

    svg_lines = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="background:#ffffff; border-radius:6px; font-family:system-ui, sans-serif;">',
        f'  <rect width="{width}" height="{height}" fill="#f8fafc" rx="6" />',
        f'  <text x="20" y="22" font-size="12" font-weight="700" fill="#334155">INTRADAY PRICE DRIFT &amp; GAP DECOMPOSITION</text>',
        f'  <line x1="{zero_x}" y1="30" x2="{zero_x}" y2="{height - 12}" stroke="#94a3b8" stroke-width="1.5" stroke-dasharray="3 3" />'
    ]

    for i, (label, val, color) in enumerate(items):
        y = start_y + i * (bar_height + gap)
        bar_w = int((abs(val) / max_abs) * (width // 2 - 80))
        bar_w = max(bar_w, 2)

        if val >= 0:
            bar_x = zero_x
            text_x = bar_x + bar_w + 6
            text_anchor = "start"
        else:
            bar_x = zero_x - bar_w
            text_x = bar_x - 6
            text_anchor = "end"

        svg_lines.append(f'  <text x="20" y="{y + 15}" font-size="11" font-weight="600" fill="#1e293b">{label}</text>')
        svg_lines.append(f'  <rect x="{bar_x}" y="{y}" width="{bar_w}" height="{bar_height}" fill="{color}" rx="3" />')
        svg_lines.append(f'  <text x="{text_x}" y="{y + 15}" font-size="11" font-weight="700" fill="{color}" text-anchor="{text_anchor}">{val:+.2%}</text>')

    svg_lines.append('</svg>')
    return "\n".join(svg_lines)


def generate_volume_gauge_svg(
    volume_ratio: Optional[float],
    z_score: Optional[float],
    is_spike: bool,
    width: int = 560,
    height: int = 110
) -> str:
    """
    Renders an offline SVG gauge illustrating trading volume activity relative to 20d average.
    """
    vr = volume_ratio if volume_ratio is not None else 1.0
    z_str = f"Log Z={z_score:+.2f}" if z_score is not None else "Z=N/A"
    
    # Scale: 0x to 4.0x
    max_scale = 4.0
    bar_max_w = width - 120
    current_w = int(min(vr / max_scale, 1.0) * bar_max_w)
    
    if vr >= 2.5 or is_spike:
        color = "#ea580c"  # Orange/amber spike
        status_text = f"ANOMALOUS ACTIVITY ({vr:.2f}x 20d SMA, {z_str})"
    elif vr >= 1.5:
        color = "#3b82f6"  # Blue active
        status_text = f"ELEVATED ACTIVITY ({vr:.2f}x 20d SMA, {z_str})"
    else:
        color = "#64748b"  # Muted slate
        status_text = f"NORMAL / MUTED ACTIVITY ({vr:.2f}x 20d SMA, {z_str})"

    svg = f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="background:#ffffff; border-radius:6px; font-family:system-ui, sans-serif;">
  <rect width="{width}" height="{height}" fill="#f8fafc" rx="6" />
  <text x="20" y="24" font-size="12" font-weight="700" fill="#334155">VOLUME &amp; LIQUIDITY ANOMALY INDICATOR</text>
  <text x="{width - 20}" y="24" font-size="11" font-weight="700" fill="{color}" text-anchor="end">{status_text}</text>
  
  <!-- Background Track -->
  <rect x="20" y="45" width="{bar_max_w}" height="20" fill="#e2e8f0" rx="4" />
  
  <!-- Active Bar -->
  <rect x="20" y="45" width="{current_w}" height="20" fill="{color}" rx="4" />
  
  <!-- Benchmark Markers -->
  <line x1="{20 + int(1.0/max_scale * bar_max_w)}" y1="40" x2="{20 + int(1.0/max_scale * bar_max_w)}" y2="70" stroke="#0f172a" stroke-width="2" />
  <text x="{20 + int(1.0/max_scale * bar_max_w)}" y="84" font-size="10" fill="#475569" text-anchor="middle">1.0x (Norm)</text>

  <line x1="{20 + int(2.0/max_scale * bar_max_w)}" y1="40" x2="{20 + int(2.0/max_scale * bar_max_w)}" y2="70" stroke="#0f172a" stroke-width="2" />
  <text x="{20 + int(2.0/max_scale * bar_max_w)}" y="84" font-size="10" fill="#475569" text-anchor="middle">2.0x (High)</text>

  <line x1="{20 + int(3.0/max_scale * bar_max_w)}" y1="40" x2="{20 + int(3.0/max_scale * bar_max_w)}" y2="70" stroke="#0f172a" stroke-width="2" />
  <text x="{20 + int(3.0/max_scale * bar_max_w)}" y="84" font-size="10" fill="#475569" text-anchor="middle">3.0x (Extreme)</text>
</svg>"""
    return svg


def generate_score_breakdown_svg(
    breakdown: Dict[str, Any],
    width: int = 560,
    height: int = 210
) -> str:
    """
    Renders an offline SVG horizontal breakdown of scoring components.
    """
    components = [
        ("Base Tier Score", breakdown.get("base_score", 0.0), "#3b82f6"),
        ("Temporal Timing", breakdown.get("temporal_score", 0.0), "#06b6d4"),
        ("Direction Alignment", breakdown.get("directional_score", 0.0), "#10b981"),
        ("Abnormal Return Bonus", breakdown.get("abnormal_return_score", 0.0), "#8b5cf6"),
        ("Volume Confirmation", breakdown.get("volume_score", 0.0), "#f59e0b"),
        ("Independent Corroboration", breakdown.get("corroboration_score", 0.0), "#ec4899"),
        ("Contradiction Penalty", -abs(breakdown.get("contradiction_penalty", 0.0)), "#ef4444")
    ]

    # Filter non-zero components for clean display
    active_components = [c for c in components if abs(c[1]) > 0.001]
    final_score = breakdown.get("clamped_total", breakdown.get("evidence_strength_score", breakdown.get("final_score", 0.0)))

    start_y = 38
    bar_height = 14
    gap = 8
    scale = (width - 240) / 70.0  # max expected single bonus ~70

    svg_lines = [
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" style="background:#ffffff; border-radius:6px; font-family:system-ui, sans-serif;">',
        f'  <rect width="{width}" height="{height}" fill="#f8fafc" rx="6" />',
        f'  <text x="20" y="24" font-size="12" font-weight="700" fill="#334155">EVIDENCE STRENGTH SCORE DECOMPOSITION</text>',
        f'  <text x="{width - 20}" y="24" font-size="13" font-weight="800" fill="#0f172a" text-anchor="end">Final Score: {final_score:.1f} / 100.0</text>'
    ]

    for i, (name, val, color) in enumerate(active_components[:6]):
        y = start_y + i * (bar_height + gap)
        w_val = int(abs(val) * scale)
        w_val = max(w_val, 2)
        
        svg_lines.append(f'  <text x="20" y="{y + 11}" font-size="11" font-weight="500" fill="#475569">{name}</text>')
        svg_lines.append(f'  <rect x="180" y="{y}" width="{w_val}" height="{bar_height}" fill="{color}" rx="2" />')
        val_str = f"{val:+.1f}" if val != 0 else "0.0"
        svg_lines.append(f'  <text x="{180 + w_val + 6}" y="{y + 11}" font-size="10" font-weight="700" fill="{color}">{val_str}</text>')

    svg_lines.append('</svg>')
    return "\n".join(svg_lines)
