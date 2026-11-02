"""Publication-quality Matplotlib renderer; no tiles or external API keys."""
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

SLATE = "#182B34"
PAPER = "#F7F5EF"
GREEN = "#376B5E"
GOLD = "#C49339"
RED = "#B85B4B"
MUTED = "#8A9B9B"


def draw_trig_map(points: gpd.GeoDataFrame, boundary, title: str, filename: Path, *, mode: str, highlighted=None):
    """Draw one map from the England data or its North East subset."""
    fig, ax = plt.subplots(figsize=(9, 11), facecolor=PAPER)
    ax.set_facecolor(PAPER)
    gpd.GeoSeries([boundary], crs="EPSG:27700").boundary.plot(ax=ax, color=SLATE, lw=0.65, zorder=1)
    active = points.loc[~points.destroyed_in_archive & ~points.archive_status_unknown]
    lost = points.loc[points.destroyed_in_archive]
    uncertain = points.loc[points.archive_status_unknown]
    if mode == "elevation":
        ax.scatter(active.easting, active.northing, c=active.height_m, cmap="YlGn", vmin=0, vmax=900,
                   s=9, linewidths=0, alpha=0.83, zorder=3, rasterized=True)
        ax.scatter(lost.easting, lost.northing, s=10, edgecolors=RED, facecolors="none", lw=0.5, zorder=4)
        legend_note = "Archive height (metres) · red rings: recorded destroyed"
    elif mode == "visited":
        ax.scatter(active.easting, active.northing, s=7, color=MUTED, alpha=0.6, linewidths=0, zorder=3)
        visited = points.loc[points.visited]
        ax.scatter(visited.easting, visited.northing, s=35, color=GOLD, edgecolors=SLATE,
                   linewidths=0.4, zorder=5, marker="*", label="Recorded as visited")
        ax.scatter(lost.easting, lost.northing, s=8, edgecolors=RED, facecolors="none", lw=0.5)
        legend_note = f"{int(points.visited.sum())} recorded visits · grey: no visit recorded"
    elif mode == "lost":
        ax.scatter(active.easting, active.northing, s=4, color=MUTED, alpha=0.25, linewidths=0, zorder=2)
        ax.scatter(lost.easting, lost.northing, s=20, color=RED, alpha=0.84, linewidths=0, zorder=4)
        legend_note = f"{len(lost):,} pillars recorded destroyed in the OS archive"
    elif mode == "highlights":
        ax.scatter(active.easting, active.northing, s=5, color=MUTED, alpha=0.38, linewidths=0, zorder=2)
        if highlighted is not None:
            ax.scatter(highlighted.easting, highlighted.northing, color=GOLD, marker="o", s=47,
                       edgecolors=SLATE, linewidths=0.55, zorder=5)
            for i, (_, p) in enumerate(highlighted.iterrows(), 1):
                ax.annotate(str(i), (p.easting, p.northing), xytext=(5, 4), textcoords="offset points",
                            color=SLATE, fontsize=7, fontweight="bold", zorder=6)
        legend_note = "Gold: top ten · rank names and values in companion CSV"
    else:
        raise ValueError(f"Unknown rendering mode: {mode}")

    if len(uncertain):
        ax.scatter(uncertain.easting, uncertain.northing, s=16, marker="x", color=GOLD, lw=0.7, zorder=6)
    minx, miny, maxx, maxy = boundary.bounds
    dx, dy = maxx - minx, maxy - miny
    ax.set_xlim(minx - dx * 0.08, maxx + dx * 0.08)
    ax.set_ylim(miny - dy * 0.055, maxy + dy * 0.055)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    fig.text(0.10, 0.945, "30 DAY MAP CHALLENGE  /  DAY 01: POINTS", color=GREEN,
             fontfamily="DejaVu Sans", fontsize=10, weight="bold")
    fig.text(0.10, 0.910, title, color=SLATE, fontsize=21, weight="bold")
    fig.text(0.10, 0.076, legend_note, fontsize=9, color=SLATE)
    fig.text(0.10, 0.049, "Contains OS data © Crown copyright and database right · ONS boundaries · OGL v3.0", fontsize=7.5, color=MUTED)
    fig.text(0.10, 0.034, "Historic OS archive · condition is not independently verified · location is approximate", fontsize=7.5, color=MUTED)
    filename.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(filename, dpi=200, facecolor=PAPER, bbox_inches="tight", pad_inches=0.12)
    plt.close(fig)