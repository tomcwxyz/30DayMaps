"""Day 03 extra — Which sea gets your rain?

Environment Agency WFD river water body catchments (Cycle 3), grouped by where
their rivers meet the sea: the North Sea, or the Irish Sea via the Solway Firth,
Morecambe Bay and the Lancashire coast. The line between the two is the main
watershed of northern England. Catchments are English only: the Tweed and Esk
basins carry on into Scotland, beyond this dataset.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import shapely
from shapely.geometry import box

from maps.arcgis import cached_query
from maps.common import regions, NORTH_EAST_CODE
from maps.polygon_frame import INK, PAPER, MUTED, page, map_axes, frame_to, header, footer, save

CATCHMENTS = ("https://services3.arcgis.com/Bb8lfThdhugyc4G3/ArcGIS/rest/services/"
              "England_WFD_River_Water_Body_Catchments_Cycle_3/FeatureServer/0")
WINDOW = (290000, 445000, 480000, 670000)  # northern England, BNG metres
OUT = Path("challenges/03-polygons/outputs/watersheds")

# River basin districts drain to one sea, except Solway Tweed, which straddles the divide.
RBD_SEA = {"Northumbria": "North Sea", "Humber": "North Sea", "North West": "Irish Sea"}
SOLWAY_TWEED = {"Tweed": "North Sea", "Till": "North Sea",
                "Eden and Esk": "Irish Sea", "Waver and Wampool": "Irish Sea"}
SEA_COLOURS = {"North Sea": "#4F7A8C", "Irish Sea": "#A7C2A0"}


def sea_for(rbd: str, management_catchment: str) -> str:
    """Explicit lookup; unknown names fail loudly rather than being guessed."""
    if rbd == "Solway Tweed":
        if management_catchment not in SOLWAY_TWEED:
            raise ValueError(f"Unclassified Solway Tweed catchment: {management_catchment!r}")
        return SOLWAY_TWEED[management_catchment]
    if rbd not in RBD_SEA:
        raise ValueError(f"Unclassified river basin district: {rbd!r}")
    return RBD_SEA[rbd]


def classify(catchments: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    for col in ("RBD_NAME", "MNCAT_NAME", "WB_ID"):
        if col not in catchments:
            raise ValueError(f"Catchment schema changed: {col} missing")
    data = catchments.drop_duplicates("WB_ID").copy()
    data["sea"] = [sea_for(r, m) for r, m in zip(data.RBD_NAME, data.MNCAT_NAME)]
    return data


def dissolve_by(data: gpd.GeoDataFrame, column: str, window) -> gpd.GeoDataFrame:
    clip = box(*window)
    groups = []
    for value, part in data.groupby(column):
        geom = shapely.union_all(shapely.make_valid(part.geometry.values), grid_size=1).intersection(clip)
        groups.append({column: value, "geometry": geom})
    out = gpd.GeoDataFrame(groups, crs=27700)
    out["area_km2"] = out.area / 1e6
    return out


def watershed_line(seas: gpd.GeoDataFrame):
    """The shared edge of the two drainage areas: where rain chooses a coast."""
    north = seas.loc[seas.sea == "North Sea"].geometry.iloc[0]
    irish = seas.loc[seas.sea == "Irish Sea"].geometry.iloc[0]
    # Dissolved from one tessellation, so the edges coincide; snap away float noise.
    shared = shapely.snap(north.boundary, irish.boundary, 2).intersection(irish.boundary)
    lines = [g for g in shapely.get_parts(shared) if g.geom_type == "LineString"]
    if not lines:
        raise ValueError("The two drainage areas share no edge")
    return shapely.line_merge(shapely.union_all(lines))


def draw(seas, catchments, watershed, north_east, filename):
    from matplotlib.patches import Patch
    fig = page()
    ax = map_axes(fig, (0.05, 0.11, 0.90, 0.75))
    for _, row in seas.iterrows():
        gpd.GeoSeries([row.geometry], crs=27700).plot(ax=ax, color=SEA_COLOURS[row.sea], lw=0, zorder=1)
    catchments.boundary.plot(ax=ax, color=PAPER, lw=0.6, zorder=2)
    gpd.GeoSeries([north_east], crs=27700).boundary.plot(ax=ax, color=INK, lw=0.5, linestyle="--", zorder=3)
    gpd.GeoSeries([watershed], crs=27700).plot(ax=ax, color=INK, lw=2.2, zorder=4)
    for _, row in catchments.iterrows():
        if row.area_km2 < 600:
            continue
        p = row.geometry.representative_point()
        ax.annotate(row.MNCAT_NAME, (p.x, p.y), ha="center", va="center", fontsize=6.5,
                    color=INK, zorder=5)
    frame_to(ax, WINDOW, pad=0.01)
    ax.legend(handles=[
        Patch(color=SEA_COLOURS["North Sea"], label="Drains to the North Sea"),
        Patch(color=SEA_COLOURS["Irish Sea"], label="Drains to the Irish Sea (Solway, Morecambe Bay, Ribble)"),
        Patch(facecolor="none", edgecolor=INK, ls="--", label="North East region"),
    ], loc="upper left", frameon=False, fontsize=8, labelcolor=INK)
    share = seas.set_index("sea").area_km2
    header(fig, "Which sea gets your rain?",
           f"Northern England's river catchments by where they reach the sea. The black line is the watershed. "
           f"In this window, {share['North Sea'] / share.sum():.0%} of the land drains east.")
    footer(fig, [
        "Thin lines: management catchments. Catchments stop at the Scottish border; the Tweed and Esk carry on north.",
        "© Environment Agency copyright and/or database right. WFD River Water Body Catchments Cycle 3, via The Rivers Trust's ArcGIS service. OGL v3.0.",
        "ONS Regions December 2025 · watershed derived from shared catchment edges, so it is only as precise as the catchment boundaries.",
    ], top=0.075)
    return save(fig, filename)


def run(out: Path = OUT, *, force: bool = False) -> dict:
    raw = cached_query(Path("data/raw/wfd-catchments-north.gpkg"), CATCHMENTS, bbox=WINDOW, force=force)
    data = classify(raw)
    seas = dissolve_by(data, "sea", WINDOW)
    if set(seas.sea) != set(SEA_COLOURS):
        raise ValueError(f"Expected both seas in the window; got {sorted(seas.sea)}")
    catchments = dissolve_by(data, "MNCAT_NAME", WINDOW).merge(
        data[["MNCAT_NAME", "sea"]].drop_duplicates(), on="MNCAT_NAME")
    line = watershed_line(seas)
    boundaries = regions(Path("data/raw/ons-regions-2025.geojson"), force=force)
    north_east = boundaries.loc[boundaries.RGN25CD == NORTH_EAST_CODE].geometry.iloc[0]
    out = Path(out)
    draw(seas, catchments, line, north_east, out / "which-sea.png")
    stats = {
        "water_bodies": int(len(data)),
        "area_km2_by_sea": {k: round(v, 1) for k, v in seas.set_index("sea").area_km2.items()},
        "watershed_km": round(line.length / 1000, 1),
        "management_catchments": catchments[["MNCAT_NAME", "sea"]].sort_values("MNCAT_NAME").values.tolist(),
    }
    (out / "summary.json").write_text(json.dumps(stats, indent=2))
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(run(args.out, force=args.force), indent=2))


if __name__ == "__main__":
    main()
