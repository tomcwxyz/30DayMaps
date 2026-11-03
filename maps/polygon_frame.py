"""Shared page furniture for the Day 03 polygon extras, matching earlier days."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

INK = "#1E353B"
PAPER = "#F7F6F0"
GREEN = "#306852"
MUTED = "#8A9B9B"
GOLD = "#C18E46"
RED = "#B85B4B"
KICKER = "30 DAY MAP CHALLENGE  /  DAY 03: POLYGONS"


def page(figsize=(9, 11)):
    fig = plt.figure(figsize=figsize, facecolor=PAPER)
    return fig


def map_axes(fig, rect=(0.06, 0.13, 0.88, 0.70)):
    ax = fig.add_axes(rect)
    ax.set_facecolor(PAPER)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    return ax


def frame_to(ax, bounds, pad=0.04):
    minx, miny, maxx, maxy = bounds
    dx, dy = maxx - minx, maxy - miny
    ax.set_xlim(minx - dx * pad, maxx + dx * pad)
    ax.set_ylim(miny - dy * pad, maxy + dy * pad)


def header(fig, title: str, subtitle: str | None = None, x: float = 0.08):
    fig.text(x, 0.955, KICKER, color=GREEN, fontsize=10, weight="bold")
    fig.text(x, 0.918, title, color=INK, fontsize=20, weight="bold")
    if subtitle:
        fig.text(x, 0.888, subtitle, color=INK, fontsize=10)


def footer(fig, lines: list[str], x: float = 0.08, top: float = 0.085):
    """First line is the key/note in ink; the rest are muted credits and caveats."""
    for i, line in enumerate(lines):
        fig.text(x, top - i * 0.016, line, fontsize=9 if i == 0 else 7.5,
                 color=INK if i == 0 else MUTED)


def save(fig, filename: Path, dpi: int = 200):
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(filename, dpi=dpi, facecolor=PAPER, bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)
    return filename
