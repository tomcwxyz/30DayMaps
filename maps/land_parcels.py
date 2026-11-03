"""Day 03 extra — How much of a county sits in a handful of big parcels?

HM Land Registry's INSPIRE Index Polygons show the extent of registered freehold
titles. They do not name owners, one owner can hold many polygons, and one title
can have several. Unregistered land is simply absent. So this maps *parcel size
concentration*, which is suggestive of, but not the same as, ownership concentration.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
import shapely

from maps.arcgis import cached_query
from maps.polygon_frame import (INK, PAPER, GREEN, GOLD, MUTED, page, map_axes,
                                frame_to, header, footer, save)

INSPIRE_URL = "https://use-land-property-data.service.gov.uk/datasets/inspire/download/{name}.zip"
COUNTIES = ("https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
            "Counties_and_Unitary_Authorities_December_2025_Boundaries_UK_BGC/FeatureServer/0")
# slug: (display name, INSPIRE file name, ONS code, a box inside the area for the boundary query)
AREAS = {
    "northumberland": ("Northumberland", "Northumberland", "E06000057", (380000, 560000, 420000, 620000)),
    "county-durham": ("County Durham", "County_Durham", "E06000047", (400000, 520000, 425000, 545000)),
}
OUT = Path("challenges/03-polygons/outputs/land-parcels")

BANDS = [  # share of parcels, largest first
    ("Largest 1% of parcels", 0.01, "#1F4E3D"),
    ("Next 9%", 0.10, "#6E9C7F"),
    ("Remaining 90%", 1.00, "#D9DFCF"),
]
ATTRIBUTION = [
    "This information is subject to Crown copyright and database rights {year} and is reproduced with the permission of HM Land Registry.",
    "The polygons (including the associated geometry, namely x, y co-ordinates) are subject to Crown copyright and database rights {year} Ordnance Survey AC0000851063.",
]


def download_inspire(name: str, destination: Path, *, force: bool = False) -> Path:
    """The service bounces cookieless clients in a redirect loop, so keep a session."""
    destination = Path(destination)
    if destination.exists() and not force:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".part")
    with requests.Session() as session:
        session.headers["User-Agent"] = "30DayMaps/0.1 (open-data research)"
        with session.get(INSPIRE_URL.format(name=name), stream=True, timeout=(20, 300)) as r:
            r.raise_for_status()
            with temp.open("wb") as out:
                for chunk in r.iter_content(1 << 20):
                    out.write(chunk)
    with ZipFile(temp) as archive:
        if not any(n.lower().endswith(".gml") for n in archive.namelist()):
            raise ValueError("INSPIRE download has no GML; the service may have changed")
    temp.replace(destination)
    return destination


def gml_timestamp(archive: Path) -> str | None:
    """The WFS dump's own timeStamp, which can be much older than the download date."""
    with ZipFile(archive) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".gml"))
        with z.open(name) as f:
            head = f.read(4000).decode("utf-8", errors="ignore")
    found = re.search(r'timeStamp="([^"]+)"', head)
    return found.group(1) if found else None


def read_parcels(archive: Path) -> gpd.GeoDataFrame:
    archive = Path(archive)
    with ZipFile(archive) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".gml"))
    data = gpd.read_file(f"zip://{archive}!{name}")
    if data.crs is None:
        data = data.set_crs(27700)  # srsName in the dump is EPSG:27700
    data = data.to_crs(27700)
    data = data.loc[data.geometry.notna()].copy()
    data["geometry"] = shapely.make_valid(data.geometry.values)
    data = data.loc[data.geometry.geom_type.isin(["Polygon", "MultiPolygon", "GeometryCollection"])]
    data["geometry"] = data.geometry.apply(_polygonal)
    data = data.loc[~data.geometry.is_empty].reset_index(drop=True)
    data["area_ha"] = data.geometry.area / 10_000
    return data.loc[data.area_ha > 0].reset_index(drop=True)


def _polygonal(geom):
    if geom.geom_type == "GeometryCollection":
        parts = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")]
        return shapely.union_all(parts) if parts else shapely.Polygon()
    return geom


def county_boundary(cache: Path, code: str, bbox, *, force: bool = False):
    counties = cached_query(cache, COUNTIES, bbox=bbox, paginate=False, force=force)
    match = counties.loc[counties.apply(lambda r: code in set(map(str, r.values)), axis=1)]
    if len(match) != 1:
        raise ValueError(f"Expected one boundary for {code}; got {len(match)}")
    return match.geometry.iloc[0]


def concentration(areas_ha) -> dict:
    """Size concentration of parcels, largest first. Pure arithmetic, testable."""
    a = np.sort(np.asarray(areas_ha, dtype=float))[::-1]
    if len(a) == 0 or (a <= 0).any():
        raise ValueError("Need positive parcel areas")
    total = a.sum()
    cum = np.cumsum(a) / total
    n = len(a)
    top = lambda share: float(a[:max(1, int(np.ceil(n * share)))].sum() / total)
    return {
        "parcels": int(n),
        "registered_area_ha": float(total),
        "top_1pct_share": top(0.01),
        "top_10pct_share": top(0.10),
        "parcels_for_half": int(np.searchsorted(cum, 0.5) + 1),
        "largest_ha": float(a[0]),
        "median_ha": float(np.median(a)),
    }


def band_parcels(parcels: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    ranked = parcels.sort_values("area_ha", ascending=False).reset_index(drop=True)
    rank_share = (np.arange(len(ranked)) + 1) / len(ranked)
    labels = np.full(len(ranked), BANDS[-1][0], dtype=object)
    for label, upper, _ in reversed(BANDS):
        labels[rank_share <= upper] = label
    ranked["band"] = labels
    return ranked


def draw(parcels: gpd.GeoDataFrame, boundary, stats: dict, coverage: float,
         stamp: str | None, filename: Path, name: str = "Northumberland"):
    year = (stamp or "")[:4] or "2026"
    fig = page()
    minx, miny, maxx, maxy = boundary.bounds
    wide = (maxx - minx) > (maxy - miny)  # landscape counties get the full width
    if wide:
        ax = map_axes(fig, (0.04, 0.33, 0.92, 0.50))
        panel_x, keyy, stats_y, inset_rect = 0.08, 0.27, 0.27, (0.70, 0.135, 0.25, 0.14)
    else:
        ax = map_axes(fig, (0.03, 0.12, 0.62, 0.72))
        panel_x, keyy, stats_y, inset_rect = 0.68, 0.78, 0.68, (0.72, 0.36, 0.23, 0.18)
    gpd.GeoSeries([boundary], crs=27700).plot(ax=ax, color="#ECEAE1", lw=0, zorder=0)
    for label, _, colour in reversed(BANDS):
        part = parcels.loc[parcels.band == label]
        part.plot(ax=ax, color=colour, lw=0.08, edgecolor=PAPER, zorder=2, rasterized=True)
    gpd.GeoSeries([boundary], crs=27700).boundary.plot(ax=ax, color=INK, lw=0.6, zorder=3)
    frame_to(ax, boundary.bounds, pad=0.02)

    # Lorenz-style curve: how quickly area accumulates when parcels are ranked by size.
    a = np.sort(parcels.area_ha.values)[::-1]
    inset = fig.add_axes(inset_rect, facecolor=PAPER)
    x = np.arange(1, len(a) + 1) / len(a) * 100
    inset.plot(x, np.cumsum(a) / a.sum() * 100, color=GREEN, lw=1.6)
    inset.plot([0, 100], [0, 100], color=MUTED, lw=0.6, ls=(0, (3, 3)))
    inset.axvline(1, color=GOLD, lw=0.8)
    inset.set_xlim(0, 10); inset.set_ylim(0, 100)  # the action is in the first 10%
    for side in ("top", "right"):
        inset.spines[side].set_visible(False)
    inset.tick_params(labelsize=7, colors=INK, length=2)
    inset.set_xlabel("Largest parcels first (% of all parcels)", fontsize=7.5, color=INK)
    inset.set_ylabel("% of registered area", fontsize=7.5, color=INK)

    for label, _, colour in BANDS:
        fig.patches.append(matplotlib_rect(fig, panel_x, keyy, colour))
        fig.text(panel_x + 0.025, keyy + 0.002, label, fontsize=8.5, color=INK)
        keyy -= 0.026
    sx = panel_x + (0.28 if wide else 0)
    sy = stats_y if wide else 0.68
    fig.text(sx, sy, f"Largest 1% hold {stats['top_1pct_share']:.0%} of the area", fontsize=8.5, color=INK, weight="bold")
    fig.text(sx, sy - 0.025, f"Largest 10% hold {stats['top_10pct_share']:.0%}", fontsize=8.5, color=INK)
    fig.text(sx, sy - 0.05, f"Median parcel {stats['median_ha']:.2f} ha · largest {stats['largest_ha']:,.0f} ha", fontsize=8.5, color=INK)

    n_half = stats['parcels_for_half']
    header(fig, f"{n_half:,} parcel{'s cover' if n_half != 1 else ' covers'} half of {name}'s",
           None)
    fig.text(0.08, 0.888, "registered land", color=INK, fontsize=20, weight="bold")
    fig.text(0.08, 0.862, f"{stats['parcels']:,} HM Land Registry index polygons · they cover {coverage:.0%} of the county; "
             "blank land is unregistered or not in the index", fontsize=9, color=INK)
    footer(fig, [
        "Index polygons show registered freehold extents. They do not name owners: one owner may hold many parcels.",
        ATTRIBUTION[0].format(year=year),
        ATTRIBUTION[1].format(year=year),
        f"INSPIRE file timestamp {stamp or 'unknown'} · ONS county boundary December 2025 · OGL v3.0",
    ], top=0.09)
    return save(fig, filename)


def matplotlib_rect(fig, x, y, colour):
    from matplotlib.patches import Rectangle
    return Rectangle((x, y), 0.018, 0.012, transform=fig.transFigure, color=colour, figure=fig)


def run(archive: Path, boundary_cache: Path, out: Path = OUT, *, area: str = "northumberland",
        force: bool = False) -> dict:
    name, _, code, bbox = AREAS[area]
    stamp = gml_timestamp(archive)
    boundary = county_boundary(boundary_cache, code, bbox, force=force)
    parcels = read_parcels(archive)
    parcels = parcels.loc[parcels.intersects(boundary)].reset_index(drop=True)
    stats = concentration(parcels.area_ha)
    covered = shapely.union_all(parcels.geometry.values, grid_size=0.1).intersection(boundary)
    coverage = covered.area / boundary.area
    banded = band_parcels(parcels)
    out = Path(out)
    draw(banded, boundary, stats, coverage, stamp, out / f"{area}-parcels.png", name)
    top = banded.head(100).copy()
    id_col = next((c for c in top.columns if "inspire" in c.lower() and "id" in c.lower()), None)
    cent = top.geometry.representative_point()
    pd.DataFrame({
        "rank": range(1, len(top) + 1),
        "inspire_id": top[id_col] if id_col else None,
        "area_ha": top.area_ha.round(2),
        "easting": cent.x.round(), "northing": cent.y.round(),
    }).to_csv(out / f"{area}-largest-100-parcels.csv", index=False)
    summary = dict(stats, county_coverage=coverage, inspire_timestamp=stamp,
                   county_code=code, area=name)
    (out / f"{area}-summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--area", choices=sorted(AREAS), default="northumberland")
    parser.add_argument("--archive", type=Path, help="local INSPIRE zip (default: data/raw/inspire-<area>.zip)")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    archive = args.archive or Path(f"data/raw/inspire-{args.area}.zip")
    if args.download or not archive.exists():
        download_inspire(AREAS[args.area][1], archive, force=args.force)
    summary = run(archive, Path(f"data/raw/ctyua-{args.area}.gpkg"), args.out,
                  area=args.area, force=args.force)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
