"""Day 03 extra — Right to roam in the North East, and the gaps between.

Natural England's CRoW Access Land layer: open country, registered common land and
Section 16 dedicated land. It excludes public rights of way, the England Coast Path
margin, and permissive access, so "outside access land" does not mean "no access".
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from PIL import Image, ImageDraw
from scipy import ndimage

from maps.arcgis import cached_query
from maps.common import regions, NORTH_EAST_CODE
from maps.polygon_frame import (INK, PAPER, GREEN, MUTED, page, map_axes, frame_to,
                                header, footer, save)

CROW = ("https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/"
        "CRoW_Act_2000_Access_Layer/FeatureServer/0")
OUT = Path("challenges/03-polygons/outputs/access-land")
CELL_M = 100
BORDER_M = 15_000
DISTANCE_BANDS_KM = [1, 2, 5, 10]
DISTANCE_COLOURS = ["#EFEDE4", "#E6DCC5", "#D9C49D", "#C9A26A", "#A9773F"]
OPEN_COLOUR = "#2F6B54"
DEDICATED_COLOUR = "#7FAE8E"


def classify(data: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Dedicated-only land (mostly forestry) versus open country or common land."""
    for col in ("OC", "RCL", "S16"):
        if col not in data:
            raise ValueError(f"CRoW schema changed: {col} missing")
    yes = lambda c: data[c].astype(str).str.strip().str.lower().eq("yes")
    data = data.copy()
    data["kind"] = np.where(yes("S16") & ~yes("OC") & ~yes("RCL"), "dedicated", "open")
    return data


def access_islands(access: gpd.GeoDataFrame, area) -> gpd.GeoDataFrame:
    """Touching polygons merged into separate islands of access land, clipped to the area."""
    merged = shapely.union_all(access.geometry.values, grid_size=0.5).intersection(area)
    islands = gpd.GeoDataFrame(geometry=list(shapely.get_parts(merged)), crs=27700)
    islands = islands.loc[islands.geom_type == "Polygon"].copy()
    islands["area_ha"] = islands.area / 10_000
    return islands.sort_values("area_ha", ascending=False).reset_index(drop=True)


def rasterise(geoms, bounds, cell: float) -> np.ndarray:
    """Boolean mask of polygon coverage on a regular grid (row 0 = north)."""
    minx, miny, maxx, maxy = bounds
    w, h = int(np.ceil((maxx - minx) / cell)), int(np.ceil((maxy - miny) / cell))
    img = Image.new("1", (w, h), 0)
    draw = ImageDraw.Draw(img)
    to_px = lambda xy: [((x - minx) / cell, (maxy - y) / cell) for x, y in xy]
    for geom in geoms:
        for poly in shapely.get_parts(geom):
            if poly.geom_type != "Polygon" or poly.is_empty:
                continue
            draw.polygon(to_px(poly.exterior.coords), fill=1)
            for hole in poly.interiors:
                draw.polygon(to_px(hole.coords), fill=0)
    return np.array(img, dtype=bool)


def distance_to_access_km(access_mask: np.ndarray, cell: float) -> np.ndarray:
    """Straight-line distance from each cell to the nearest access-land cell."""
    if not access_mask.any():
        raise ValueError("No access land in the mask")
    return ndimage.distance_transform_edt(~access_mask) * cell / 1000


def summarise(islands, area, distance_km, inside_mask) -> dict:
    d = distance_km[inside_mask]
    total = islands.area_ha.sum()
    return {
        "access_land_ha": float(total),
        "share_of_region": float(total * 10_000 / area.area),
        "islands": int(len(islands)),
        "largest_island_ha": float(islands.area_ha.iloc[0]),
        "largest_island_share": float(islands.area_ha.iloc[0] / total),
        "islands_under_10ha": int((islands.area_ha < 10).sum()),
        "share_of_region_over_5km_from_access_land": float((d > 5).mean()),
        "max_distance_km": float(d.max()),
    }


def draw(access, area, distance_km, bounds, stats, filename):
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch
    fig = page()
    ax = map_axes(fig, (0.06, 0.13, 0.88, 0.71))
    inside = rasterise([area], bounds, CELL_M)
    shown = np.ma.masked_where(~inside, distance_km)
    cmap = ListedColormap(DISTANCE_COLOURS)
    norm = BoundaryNorm([0] + DISTANCE_BANDS_KM + [1e6], cmap.N)
    minx, miny, maxx, maxy = bounds
    ax.imshow(shown, cmap=cmap, norm=norm, interpolation="nearest", zorder=0,
              extent=(minx, minx + shown.shape[1] * CELL_M, maxy - shown.shape[0] * CELL_M, maxy))
    access.loc[access.kind == "dedicated"].plot(ax=ax, color=DEDICATED_COLOUR, lw=0, zorder=2)
    access.loc[access.kind == "open"].plot(ax=ax, color=OPEN_COLOUR, lw=0, zorder=3)
    gpd.GeoSeries([area], crs=27700).boundary.plot(ax=ax, color=INK, lw=0.6, zorder=4)
    frame_to(ax, area.bounds, pad=0.02)
    handles = [Patch(color=OPEN_COLOUR, label="Open country or common land"),
               Patch(color=DEDICATED_COLOUR, label="Dedicated access land only (mostly forestry)")]
    labels = ["under 1 km", "1–2 km", "2–5 km", "5–10 km", "over 10 km"]
    handles += [Patch(color=c, label=f"{l} to the nearest access land") for c, l in zip(DISTANCE_COLOURS, labels)]
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=7.5,
              labelcolor=INK, handlelength=1.2, borderaxespad=0)
    header(fig, f"Right to roam covers {stats['share_of_region']:.0%} of the North East",
           f"{stats['islands']:,} separate patches of CRoW access land; the largest holds "
           f"{stats['largest_island_share']:.0%} of it. {stats['share_of_region_over_5km_from_access_land']:.0%} "
           "of the region is over 5 km from any.")
    footer(fig, [
        "Distances are straight-line to the nearest access land, not a walk. Footpaths, bridleways and coast path spreading room aren't in this layer.",
        "© Natural England copyright. Contains Ordnance Survey data © Crown copyright and database right 2026. OGL v3.0.",
        "ONS Regions December 2025 (North East, including Tees Valley) · CRoW Act 2000 Access Layer via Natural England's ArcGIS service.",
    ])
    return save(fig, filename)


def run(out: Path = OUT, *, force: bool = False) -> dict:
    boundaries = regions(Path("data/raw/ons-regions-2025.geojson"), force=force)
    area = boundaries.loc[boundaries.RGN25CD == NORTH_EAST_CODE].geometry.iloc[0]
    # Pad the search so access land just over the border (Cumbria, the Dales,
    # Scotland has none in this layer) counts when measuring distances.
    minx, miny, maxx, maxy = area.bounds
    bounds = (minx - BORDER_M, miny - BORDER_M, maxx + BORDER_M, maxy + BORDER_M)
    raw = cached_query(Path("data/raw/crow-north-east.gpkg"), CROW, bbox=bounds, force=force)
    id_col = next((c for c in raw.columns if c.lower() == "objectid"), None)
    if id_col:
        raw = raw.drop_duplicates(id_col)
    nearby = classify(raw)
    access = nearby.loc[nearby.intersects(area)].copy()
    access["geometry"] = access.geometry.intersection(area)
    islands = access_islands(access, area)
    distance = distance_to_access_km(rasterise(nearby.geometry, bounds, CELL_M), CELL_M)
    inside = rasterise([area], bounds, CELL_M)
    stats = summarise(islands, area, distance, inside)
    out = Path(out)
    draw(access, area, distance, bounds, stats, out / "north-east-access-land.png")
    (out / "summary.json").write_text(json.dumps(stats, indent=2))
    islands.assign(rank=range(1, len(islands) + 1)).drop(columns="geometry").head(50) \
        .to_csv(out / "largest-access-islands.csv", index=False)
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(run(args.out, force=args.force), indent=2))


if __name__ == "__main__":
    main()
