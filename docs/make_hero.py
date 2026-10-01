"""Generate docs/hero.png — the AutoHunt banner (1200x630). Run: python3 docs/make_hero.py"""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, FancyBboxPatch, Wedge

W, H = 1200, 630
AMBER = "#f59e0b"
INK = "#0b1026"


def main() -> Path:
    fig = plt.figure(figsize=(12, 6.3), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")

    # --- background gradient -------------------------------------------------
    top = np.array([0x0B, 0x10, 0x26]) / 255.0
    bottom = np.array([0x1B, 0x25, 0x4D]) / 255.0
    ramp = np.linspace(0, 1, 256)[:, None, None]
    bg = top * (1 - ramp) + bottom * ramp
    bg = np.repeat(bg, W, axis=1)
    ax.imshow(bg, extent=[0, W, 0, H], aspect="auto", origin="upper", zorder=0)

    # --- faint dotted grid ----------------------------------------------------
    xs, ys = np.meshgrid(np.arange(40, W, 56), np.arange(40, H, 56))
    ax.scatter(xs.ravel(), ys.ravel(), s=6, color="white", alpha=0.05, zorder=1)

    # --- speed lines -----------------------------------------------------------
    rng = np.random.default_rng(7)
    for _ in range(26):
        y = rng.uniform(60, H - 40)
        x = rng.uniform(W * 0.45, W - 60)
        length = rng.uniform(60, 220)
        ax.plot([x, x + length], [y, y + length * 0.08],
                color="white", alpha=rng.uniform(0.03, 0.10), lw=2, zorder=1)

    # --- wordmark ---------------------------------------------------------------
    # Measure "Auto" so "Hunt" starts exactly where it ends (two-tone wordmark).
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    auto_text = ax.text(72, 430, "Auto", fontsize=96, weight=800, color="white",
                        family="sans-serif", va="center", ha="left", zorder=3)
    auto_bbox = auto_text.get_window_extent(renderer=renderer)
    hunt_x = ax.transData.inverted().transform((auto_bbox.x1, 0))[0] + 10
    ax.text(hunt_x, 430, "Hunt", fontsize=96, weight=800, color=AMBER,
            family="sans-serif", va="center", ha="left", zorder=3)
    ax.text(76, 348, "Never miss a great car deal.",
            fontsize=29, color="#cbd5e1", family="sans-serif", va="center", zorder=3)

    # --- feature pills ------------------------------------------------------------
    pills = ["Deal scoring", "Smart alerts", "HTML reports"]
    x = 76
    for pill in pills:
        box = FancyBboxPatch((x, 252), 168, 44, boxstyle="round,pad=6,rounding_size=20",
                             facecolor="#ffffff14", edgecolor="#ffffff2e", lw=1, zorder=3)
        ax.add_patch(box)
        ax.text(x + 84, 274, pill, fontsize=16, color="white", ha="center", va="center",
                family="sans-serif", zorder=4)
        x += 188

    ax.text(76, 150, "P Y T H O N   •   S Q L I T E   •   C L I",
            fontsize=15, color="#64748b", family="monospace", va="center", zorder=3)

    # --- deal-score gauge ----------------------------------------------------------
    cx, cy, r = 952, 292, 160
    ax.add_patch(Wedge((cx, cy), r, 135, 405, width=30, facecolor="#1e293b",
                       edgecolor="none", zorder=2))
    ax.add_patch(Wedge((cx, cy), r, 135, 135 + 270 * 0.80, width=30, facecolor=AMBER,
                       edgecolor="none", zorder=3))
    for pct in range(0, 101, 10):  # ticks
        ang = math.radians(135 + 270 * pct / 100)
        x1, y1 = cx + (r - 44) * math.cos(ang), cy + (r - 44) * math.sin(ang)
        x2, y2 = cx + (r - 56) * math.cos(ang), cy + (r - 56) * math.sin(ang)
        ax.plot([x1, x2], [y1, y2], color="#94a3b8", alpha=0.7, lw=2, zorder=4)
    needle_ang = math.radians(135 + 270 * 0.80)
    ax.plot([cx + 64 * math.cos(needle_ang), cx + (r - 58) * math.cos(needle_ang)],
            [cy + 64 * math.sin(needle_ang), cy + (r - 58) * math.sin(needle_ang)],
            color="white", lw=5, solid_capstyle="round", zorder=5)
    ax.add_patch(Circle((cx, cy), 15, facecolor="white", edgecolor="none", zorder=6))
    ax.text(cx, cy + 2, "80", fontsize=56, weight=800, color="white",
            ha="center", va="center", family="sans-serif", zorder=7)
    ax.text(cx, cy - 42, "DEAL SCORE", fontsize=14, color="#94a3b8",
            ha="center", va="center", family="sans-serif", zorder=7)
    ax.text(cx, cy - r - 34, "2017 Mustang Convertible · $11,500", fontsize=16,
            color="#e2e8f0", ha="center", va="center", family="sans-serif", zorder=7)
    ax.text(cx, cy - r - 60, "Cambridge ON · 52,000 km · clean history", fontsize=13,
            color="#64748b", ha="center", va="center", family="sans-serif", zorder=7)

    out = Path(__file__).resolve().parent / "hero.png"
    fig.savefig(out, dpi=100)
    plt.close(fig)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return out


if __name__ == "__main__":
    main()
