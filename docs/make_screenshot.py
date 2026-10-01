"""Generate docs/screenshot-cli.png — a real `autohunt list` run rendered as a
terminal screenshot. Run: python3 docs/make_screenshot.py"""
from __future__ import annotations

import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent
BG = "#0d1117"
BAR = "#161b22"
FG = "#e6edf3"
DIM = "#8b949e"
GREEN = "#7ee787"
AMBER = "#ffa657"

COMMAND = "autohunt list --profile mustang --min-score 50 --limit 8"


def capture() -> list[str]:
    # Fresh deterministic state, then capture the real CLI output.
    subprocess.run(["python3", "-m", "autohunt", "demo"],
                   capture_output=True, cwd=ROOT, check=True)
    proc = subprocess.run(
        ["python3", "-m", "autohunt"] + COMMAND.split()[1:],
        capture_output=True, text=True, cwd=ROOT, check=True)
    return proc.stdout.splitlines()


def line_color(line: str) -> str:
    if "HOT DEAL" in line:
        return GREEN
    if "Good deal" in line:
        return AMBER
    if line.startswith("Top deals") or line.startswith("("):
        return DIM
    return FG


def main() -> Path:
    lines = capture()
    n = len(lines)

    px_per_line = 30
    pad_top, bar_h, pad_bottom = 26, 52, 30
    img_w, char_px = 1560, 10.6
    img_h = int(pad_top + bar_h + pad_bottom + n * px_per_line + 40)

    fig = plt.figure(figsize=(img_w / 100, img_h / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, img_w)
    ax.set_ylim(0, img_h)
    ax.axis("off")
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    # terminal chrome
    bar = FancyBboxPatch((0, img_h - bar_h), img_w, bar_h,
                         boxstyle="round,pad=0,rounding_size=14",
                         facecolor=BAR, edgecolor="#30363d", lw=1)
    ax.add_patch(bar)
    for i, color in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        ax.add_patch(plt.Circle((34 + i * 28, img_h - bar_h / 2), 8,
                                facecolor=color, edgecolor="none"))
    ax.text(110, img_h - bar_h / 2, f"parth@dev: ~/autohunt  —  {COMMAND}",
            fontsize=14, color=DIM, family="monospace", va="center", ha="left")

    # prompt line + output
    y = img_h - bar_h - pad_top
    ax.text(28, y, f"$ {COMMAND}", fontsize=15, color=FG, weight="bold",
            family="monospace", va="top", ha="left")
    y -= px_per_line * 1.6
    for line in lines:
        ax.text(28, y, line if line else " ", fontsize=14.5, color=line_color(line),
                family="monospace", va="top", ha="left")
        y -= px_per_line

    out = Path(__file__).resolve().parent / "screenshot-cli.png"
    fig.savefig(out, dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return out


if __name__ == "__main__":
    main()
