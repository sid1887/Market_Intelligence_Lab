"""
Deterministic PWA Icon & Android Notification Badge Generator for Market Intelligence Lab.
Uses Pillow with 4x supersampling (anti-aliased) to render high-DPI assets:
- icon-512x512.png: High-res obsidian & cyan/emerald quant candlestick pulse emblem
- icon-192x192.png: Android PWA launcher icon
- apple-touch-icon.png: Apple iOS home-screen icon (180x180)
- badge-96x96.png: Android monochrome status-bar badge (strictly transparent background + pure white silhouette)
"""

import os
from PIL import Image, ImageDraw, ImageFilter

OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "icons"))
os.makedirs(OUTPUT_DIR, exist_ok=True)


def create_base_app_icon(size: int = 512, scale: int = 4) -> Image.Image:
    """Renders the full-color dark obsidian quant terminal emblem with 4x supersampling."""
    s = size * scale
    img = Image.new("RGBA", (s, s), (4, 6, 9, 255))
    draw = ImageDraw.Draw(img)

    # 1. Subtle radial ambient cyan glow in center
    cx, cy = s // 2, s // 2
    glow_radius = int(s * 0.42)
    glow_img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_img)
    for r in range(glow_radius, 0, -scale * 4):
        alpha = int(35 * (1.0 - (r / glow_radius) ** 1.5))
        glow_draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(6, 182, 212, alpha)
        )
    img = Image.alpha_composite(img, glow_img)
    draw = ImageDraw.Draw(img)

    # 2. Outer rounded border frame
    pad = int(s * 0.08)
    radius = int(s * 0.18)
    draw.rounded_rectangle(
        [pad, pad, s - pad, s - pad],
        radius=radius,
        outline=(6, 182, 212, 100),
        width=int(4 * scale)
    )

    # Secondary inner micro-border
    inner_pad = pad + int(12 * scale)
    draw.rounded_rectangle(
        [inner_pad, inner_pad, s - inner_pad, s - inner_pad],
        radius=radius - int(8 * scale),
        outline=(255, 255, 255, 18),
        width=int(1.5 * scale)
    )

    # 3. Ascending Quant Candlesticks
    # 3 candlesticks: Bar 1 (left), Bar 2 (mid), Bar 3 (right, tallest)
    bar_width = int(36 * scale)
    wick_width = int(6 * scale)

    # Positions
    bars = [
        # (x_center, wick_top, body_top, body_bottom, wick_bottom, color)
        (cx - int(85 * scale), cy + int(20 * scale), cy + int(40 * scale), cy + int(110 * scale), cy + int(130 * scale), (16, 185, 129, 230)), # Green
        (cx - int(5 * scale),  cy - int(40 * scale), cy - int(20 * scale), cy + int(70 * scale),  cy + int(95 * scale),  (6, 182, 212, 240)),  # Cyan
        (cx + int(75 * scale), cy - int(115 * scale), cy - int(95 * scale), cy + int(15 * scale), cy + int(45 * scale),  (16, 185, 129, 255)), # Bright Green
    ]

    for x_c, w_t, b_t, b_b, w_b, col in bars:
        # Wick
        draw.line([(x_c, w_t), (x_c, w_b)], fill=col, width=wick_width)
        # Body
        draw.rounded_rectangle(
            [x_c - bar_width // 2, b_t, x_c + bar_width // 2, b_b],
            radius=int(6 * scale),
            fill=col,
            outline=(255, 255, 255, 120),
            width=int(2 * scale)
        )

    # 4. Superimposed Dynamic Pulse Wave (Ascending institutional momentum line)
    wave_points = [
        (cx - int(135 * scale), cy + int(120 * scale)),
        (cx - int(85 * scale), cy + int(75 * scale)),
        (cx - int(45 * scale), cy + int(95 * scale)),
        (cx - int(5 * scale), cy + int(20 * scale)),
        (cx + int(35 * scale), cy + int(35 * scale)),
        (cx + int(80 * scale), cy - int(55 * scale)),
        (cx + int(135 * scale), cy - int(120 * scale)),
    ]

    # Glow layer for wave
    for width_offset, alpha in [(int(14 * scale), 40), (int(8 * scale), 80), (int(4 * scale), 200)]:
        draw.line(wave_points, fill=(6, 182, 212, alpha), width=width_offset, joint="curve")

    # Pure white central core line
    draw.line(wave_points, fill=(255, 255, 255, 255), width=int(3 * scale), joint="curve")

    # Vertex pulse beacon node at peak
    peak_x, peak_y = wave_points[-1]
    beacon_r = int(14 * scale)
    draw.ellipse([peak_x - beacon_r, peak_y - beacon_r, peak_x + beacon_r, peak_y + beacon_r], fill=(16, 185, 129, 255))
    draw.ellipse([peak_x - beacon_r // 2, peak_y - beacon_r // 2, peak_x + beacon_r // 2, peak_y + beacon_r // 2], fill=(255, 255, 255, 255))

    # Downsample using high-quality Lanczos filter
    final_img = img.resize((size, size), Image.Resampling.LANCZOS)
    return final_img


def create_monochrome_badge(size: int = 96, scale: int = 4) -> Image.Image:
    """
    Renders an Android-compliant monochrome notification status bar badge.
    Rules: Strictly transparent background (alpha=0) and pure white (#FFFFFF) silhouette.
    """
    s = size * scale
    # Strictly transparent RGBA canvas
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = s // 2, s // 2
    bar_width = int(24 * scale)
    wick_width = int(5 * scale)
    white = (255, 255, 255, 255)

    bars = [
        (cx - int(55 * scale), cy + int(10 * scale), cy + int(25 * scale), cy + int(70 * scale), cy + int(85 * scale)),
        (cx - int(0 * scale),  cy - int(30 * scale), cy - int(15 * scale), cy + int(45 * scale),  cy + int(60 * scale)),
        (cx + int(55 * scale), cy - int(80 * scale), cy - int(65 * scale), cy + int(10 * scale), cy + int(25 * scale)),
    ]

    # Draw pure white candlesticks
    for x_c, w_t, b_t, b_b, w_b in bars:
        draw.line([(x_c, w_t), (x_c, w_b)], fill=white, width=wick_width)
        draw.rounded_rectangle(
            [x_c - bar_width // 2, b_t, x_c + bar_width // 2, b_b],
            radius=int(4 * scale),
            fill=white
        )

    # Draw pure white momentum pulse line
    wave_points = [
        (cx - int(90 * scale), cy + int(75 * scale)),
        (cx - int(55 * scale), cy + int(45 * scale)),
        (cx - int(30 * scale), cy + int(60 * scale)),
        (cx - int(0 * scale), cy + int(15 * scale)),
        (cx + int(25 * scale), cy + int(25 * scale)),
        (cx + int(55 * scale), cy - int(35 * scale)),
        (cx + int(90 * scale), cy - int(80 * scale)),
    ]
    draw.line(wave_points, fill=white, width=int(5 * scale), joint="curve")

    # Vertex node
    peak_x, peak_y = wave_points[-1]
    beacon_r = int(9 * scale)
    draw.ellipse([peak_x - beacon_r, peak_y - beacon_r, peak_x + beacon_r, peak_y + beacon_r], fill=white)

    # Downsample using Lanczos
    final_img = img.resize((size, size), Image.Resampling.LANCZOS)
    return final_img


def main():
    print(f"Generating high-DPI PWA icons in {OUTPUT_DIR}...")

    # 1. 512x512 Master Icon
    icon_512 = create_base_app_icon(512, scale=4)
    icon_512_path = os.path.join(OUTPUT_DIR, "icon-512x512.png")
    icon_512.save(icon_512_path, "PNG", optimize=True)
    print(f"✓ Saved {icon_512_path} ({os.path.getsize(icon_512_path)} bytes)")

    # 2. 192x192 Launcher Icon
    icon_192 = create_base_app_icon(192, scale=4)
    icon_192_path = os.path.join(OUTPUT_DIR, "icon-192x192.png")
    icon_192.save(icon_192_path, "PNG", optimize=True)
    print(f"✓ Saved {icon_192_path} ({os.path.getsize(icon_192_path)} bytes)")

    # 3. 180x180 Apple Touch Icon
    icon_180 = create_base_app_icon(180, scale=4)
    icon_180_path = os.path.join(OUTPUT_DIR, "apple-touch-icon.png")
    icon_180.save(icon_180_path, "PNG", optimize=True)
    print(f"✓ Saved {icon_180_path} ({os.path.getsize(icon_180_path)} bytes)")

    # 4. 96x96 Android Monochrome Badge Icon
    badge_96 = create_monochrome_badge(96, scale=4)
    badge_96_path = os.path.join(OUTPUT_DIR, "badge-96x96.png")
    badge_96.save(badge_96_path, "PNG", optimize=True)
    print(f"✓ Saved {badge_96_path} ({os.path.getsize(badge_96_path)} bytes)")

    print("All PWA assets successfully generated.")


if __name__ == "__main__":
    main()
