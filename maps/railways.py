"""Day 02 — Lines: rail corridors mapped by OpenStreetMap in England.

Download Geofabrik's England extract, use osmium-tool to retain railway ways and
referenced geometry nodes, then render a national map and North East detail.
Nothing here claims to be a complete record of historic railways or services.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd
from shapely.geometry import shape

from maps.common import NORTH_EAST_CODE, download, regions

ENGLAND_PBF = "https://download.geofabrik.de/europe/united-kingdom/england-latest.osm.pbf"
FORMER = ("disused", "abandoned", "razed", "dismantled", "demolished")
CURRENT = ("rail", "light_rail", "narrow_gauge")
STATUS = (*FORMER, *CURRENT)
STYLES = {
    "disused": ("#B75E43", 0.95),
    "abandoned": ("#C68C3E", 0.85),
    "razed": ("#527E82", 0.75),
    "dismantled": ("#527E82", 0.75),
    "demolished": ("#527E82", 0.75),
}
PAPER, SLATE, MUTED = "#F7F5EF", "#20323A", "#A7ADAF"


def source_signature(source_pbf: Path) -> dict:
    """Identify the PBF for cache invalidation without hashing a multi-GB file."""
    stat = Path(source_pbf).stat()
    return {
        "path": str(Path(source_pbf).resolve()),
        "bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
    }


def osmium_extract(source_pbf: Path, destination: Path, *, force: bool = False) -> Path:
    """Keep railway ways and referenced nodes; reject stale cache from another PBF."""
    destination = Path(destination)
    source_pbf = Path(source_pbf)
    signature = source_signature(source_pbf)
    metadata = destination.with_suffix(destination.suffix + ".source.json")
    if destination.exists() and metadata.exists() and not force:
        try:
            if json.loads(metadata.read_text(encoding="utf-8")) == signature:
                print("Using cached railway extract for this exact PBF", flush=True)
                return destination
        except (OSError, ValueError):
            pass
    destination.parent.mkdir(parents=True, exist_ok=True)
    filtered = destination.with_suffix(".railways.osm.pbf")
    selection = "w/railway=" + ",".join(STATUS)
    begin = time.monotonic()
    try:
        print(f"Filtering railway ways from {source_pbf.name} ({signature['bytes'] / 1e6:.1f} MB)", flush=True)
        subprocess.run(["osmium", "tags-filter", "--overwrite", "-o", str(filtered),
                        str(source_pbf), selection], check=True)
        print(f"Railway-only PBF ready after {time.monotonic()-begin:.1f}s; exporting geometries", flush=True)
        # Without -u the GeoJSON ID is absent; source OSM way IDs must survive.
        subprocess.run(["osmium", "export", "--overwrite", "--add-unique-id=type_id",
                        "--geometry-types=linestring", "-f", "geojsonseq",
                        "-o", str(destination), str(filtered)], check=True)
        metadata.write_text(json.dumps(signature), encoding="utf-8")
        print(f"GeoJSON sequence: {destination.stat().st_size / 1e6:.1f} MB in {time.monotonic()-begin:.1f}s", flush=True)
    finally:
        filtered.unlink(missing_ok=True)
    return destination

def read_railway_lines(source: Path) -> gpd.GeoDataFrame:
    """Parse OSM-derived GeoJSON Text Sequences (RFC 8142) into projected lines."""
    rows = []
    with Path(source).open("r", encoding="utf-8") as data:
        for raw in data:
            content = raw.lstrip("\x1e \t\r\n")
            if not content:
                continue
            obj = json.loads(content)
            properties = obj.get("properties") or {}
            status = properties.get("railway")
            if status not in STATUS or obj.get("geometry") is None:
                continue
            geom = shape(obj["geometry"])
            if geom.is_empty or geom.geom_type not in ("LineString", "MultiLineString"):
                continue
            rows.append({
                "osm_id": str(obj.get("id", "")),
                "status": status,
                "name": str(properties.get("name", "")),
                "usage": str(properties.get("usage", "")),
                "service": str(properties.get("service", "")),
                "geometry": geom,
            })
    if not rows:
        raise ValueError("No usable railway ways: check the OSM export and railway tags")
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326").to_crs(27700)


def clip_lines(lines: gpd.GeoDataFrame, polygon) -> gpd.GeoDataFrame:
    """Clip to landward boundaries; lengths always measured in British National Grid."""
    subset = gpd.clip(lines, polygon, keep_geom_type=True)
    subset = subset.loc[subset.geometry.length.gt(0)].copy()
    subset["length_km"] = subset.geometry.length / 1000.0
    return subset


def length_summary(lines: gpd.GeoDataFrame) -> pd.DataFrame:
    """Sum mapped feature geometries; NOT unduplicated former route kilometres."""
    grouped = lines.groupby("status", sort=False).agg(
        segments=("status", "size"), mapped_feature_km=("length_km", "sum")
    ).reset_index()
    return grouped.sort_values("status").reset_index(drop=True)


def railway_title(kind: str) -> str:
    if kind == "england":
        return "The Railways We Lost"
    if kind == "north-east":
        return "The Ghost Network of the North East"
    raise ValueError(f"Unknown map kind: {kind}")


def draw_railways(lines: gpd.GeoDataFrame, outline, output: Path, *, kind: str) -> None:
    """Reproducible, static editorial cartography for Day 02."""
    fig = plt.figure(figsize=(10, 12), facecolor=PAPER)
    ax = fig.add_axes([0.08, 0.18, 0.84, 0.68], facecolor=PAPER)
    gpd.GeoSeries([outline], crs=27700).boundary.plot(ax=ax, color=SLATE, lw=0.65, zorder=1)
    existing = lines.loc[lines.status.isin(CURRENT)]
    if not existing.empty:
        existing.plot(ax=ax, color="#A5B3B2", linewidth=0.34 if kind == "england" else 0.57,
                      alpha=0.52, zorder=2)
    for status in FORMER:
        subset = lines.loc[lines.status.eq(status)]
        if not subset.empty:
            colour, width = STYLES[status]
            subset.plot(ax=ax, color=colour, linewidth=width * (0.70 if kind == "england" else 1.1),
                        alpha=0.88, zorder=3, rasterized=True)
    minx, miny, maxx, maxy = outline.bounds
    dx, dy = maxx - minx, maxy - miny
    ax.set_xlim(minx - dx * 0.035, maxx + dx * 0.035)
    ax.set_ylim(miny - dy * 0.035, maxy + dy * 0.035)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")
    fig.text(0.08, 0.953, "30 DAY MAP CHALLENGE   /   DAY 02: LINES", fontsize=10,
             color="#376B5E", fontweight="bold")
    fig.text(0.08, 0.914, railway_title(kind), fontsize=24, fontweight="bold", color=SLATE)
    fig.text(0.08, 0.886, "ENGLAND" if kind == "england" else "NORTH EAST ENGLAND", fontsize=11, color=SLATE)
    handles = [
        Line2D([0], [0], color="#B75E43", lw=2, label="Disused · rails generally remain"),
        Line2D([0], [0], color="#C68C3E", lw=2, label="Abandoned · alignment visible"),
        Line2D([0], [0], color="#527E82", lw=2, label="Removed · razed / dismantled"),
        Line2D([0], [0], color="#A5B3B2", lw=2, label="Other mapped railway track"),
    ]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(0.075, 0.105),
               frameon=False, fontsize=9, labelspacing=0.65)
    fig.text(.08, .075, "Mapped OSM railway features, not a complete history of closed passenger routes.",
             fontsize=8, color=SLATE)
    fig.text(.08, .055, "© OpenStreetMap contributors (ODbL) · ONS region boundaries (OGL v3.0)",
             fontsize=7.5, color=MUTED)
    fig.text(.08, .039, "Some lines are private, industrial or freight. Status and historical coverage are uneven.",
             fontsize=7.5, color=MUTED)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220, facecolor=PAPER, bbox_inches="tight", pad_inches=.15)
    plt.close(fig)


def make_maps(input_geojsonseq: Path, output: Path, *, boundaries_path: Path | None = None,
              area: str = "both") -> None:
    if area not in {"both", "north-east"}:
        raise ValueError("area must be 'both' or 'north-east'")
    print("Reading extracted railway geometries", flush=True)
    network = read_railway_lines(input_geojsonseq)
    print(f"Loaded {len(network):,} railway segments", flush=True)
    borders = gpd.read_file(boundaries_path).to_crs(27700) if boundaries_path else regions(Path("data/raw/regions-2025.geojson"))
    if "RGN25CD" not in borders.columns or NORTH_EAST_CODE not in set(borders.RGN25CD):
        raise ValueError("English regional boundary data is missing or unexpected")
    ne_poly = borders.loc[borders.RGN25CD.eq(NORTH_EAST_CODE)].geometry.union_all()
    ne = clip_lines(network, ne_poly)
    if not len(ne):
        raise ValueError("No North East railways after clipping; check source coverage")
    regions_to_render = [("north-east", ne, ne_poly)]
    if area == "both":
        england_poly = borders.geometry.union_all()
        england = clip_lines(network, england_poly)
        if not len(england):
            raise ValueError("No England railway data after clipping")
        regions_to_render.insert(0, ("england", england, england_poly))
    output.mkdir(parents=True, exist_ok=True)
    for tag, data, polygon in regions_to_render:
        print(f"Rendering {tag} ({len(data):,} segments)", flush=True)
        draw_railways(data, polygon, output / f"{tag}-railways.png", kind=tag)
        length_summary(data).to_csv(output / f"{tag}-railway-summary.csv", index=False)
        data.to_file(output / f"{tag}-railways.gpkg", layer="railways", driver="GPKG", index=False)
        print(f"Completed {tag} map and GeoPackage", flush=True)

def main() -> None:
    parser = argparse.ArgumentParser(description="Day 02: disused and lost railways")
    parser.add_argument("--input", type=Path, help="Pre-extracted osmium GeoJSON sequence for offline/testing")
    parser.add_argument("--pbf", type=Path, help="An existing England OSM PBF rather than downloading")
    parser.add_argument("--output", type=Path, default=Path("challenges/02-lines/outputs"))
    parser.add_argument("--force", action="store_true", help="Re-download and re-extract OSM data")
    parser.add_argument("--area", choices=("both", "north-east"), default="both", help="Render both maps or the North East alone")
    args = parser.parse_args()
    if args.input:
        seq = args.input
    else:
        pbf = args.pbf or download(ENGLAND_PBF, Path("data/raw/england-latest.osm.pbf"), force=args.force)
        seq = osmium_extract(pbf, Path("data/processed/england-railways.geojsonseq"), force=args.force)
    make_maps(seq, args.output, area=args.area)


if __name__ == "__main__":
    main()