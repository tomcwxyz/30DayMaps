"""Day 03 extra — Footprints only: Newcastle and Gateshead as buildings, nothing else.

OS OpenMap – Local building polygons for the NZ 100 km tile. OpenMap – Local
generalises: terraces often appear as one long block rather than separate houses,
which suits the Tyneside flat streets but hides individual plots.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
import matplotlib.pyplot as plt
from pyproj import Transformer
from shapely.geometry import box

from maps.common import download
from maps.polygon_frame import INK, PAPER, GREEN, MUTED, KICKER, page, map_axes, frame_to, footer, save

OML_NZ = ("https://api.os.uk/downloads/v1/products/OpenMapLocal/downloads?"
          "area=NZ&format=ESRI%C2%AE+Shapefile&redirect")
OUT = Path("challenges/03-polygons/outputs/footprints")
CITY_CENTRE = (54.9738, -1.6132)  # Grey's Monument
CITY_W, CITY_H = 9_000, 11_000    # metres, the page's own proportions
DETAIL_SIDE = 1_400
DETAILS = [  # (label, lat, lon, note)
    ("Byker", 54.9742, -1.5789, "Ralph Erskine's Byker Wall wraps the estate"),
    ("Heaton", 54.9842, -1.5808, "Tyneside flats in parallel rows"),
    ("Bensham", 54.9532, -1.6172, "Gateshead's terraced streets on the slope above the Tyne"),
]
ATTRIBUTION = "Contains OS data © Crown copyright and database right 2026 · OS OpenMap – Local, OGL v3.0"

_to_bng = Transformer.from_crs(4326, 27700, always_xy=True)


def to_bng(lat: float, lon: float) -> tuple[float, float]:
    return _to_bng.transform(lon, lat)


def window(lat: float, lon: float, width: float, height: float | None = None):
    x, y = to_bng(lat, lon)
    height = height or width
    return (x - width / 2, y - height / 2, x + width / 2, y + height / 2)


def building_layer(archive: Path) -> str:
    with ZipFile(archive) as z:
        names = [n for n in z.namelist() if n.endswith("_Building.shp")
                 and "Important" not in n]
    if len(names) != 1:
        raise ValueError(f"Expected one *_Building.shp in {archive}; found {names}")
    return f"zip://{Path(archive).resolve()}!{names[0]}"


def read_buildings(archive: Path, bounds) -> gpd.GeoDataFrame:
    data = gpd.read_file(building_layer(archive), bbox=bounds)
    if data.crs is None:
        raise ValueError("Building layer has no CRS")
    data = data.to_crs(27700)
    return data.loc[data.geometry.notna() & data.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]


def clip(buildings: gpd.GeoDataFrame, bounds) -> gpd.GeoDataFrame:
    frame = box(*bounds)
    kept = buildings.loc[buildings.intersects(frame)].copy()
    kept["geometry"] = kept.geometry.intersection(frame)
    return kept.loc[~kept.geometry.is_empty]


def draw_city(buildings, bounds, filename):
    fig = page()
    ax = map_axes(fig, (0.06, 0.08, 0.88, 0.80))
    clip(buildings, bounds).plot(ax=ax, color=INK, lw=0, rasterized=True)
    frame_to(ax, bounds, pad=0)
    fig.text(0.06, 0.955, KICKER, color=GREEN, fontsize=10, weight="bold")
    fig.text(0.06, 0.918, "Footprints only", color=INK, fontsize=20, weight="bold")
    fig.text(0.06, 0.890, "Newcastle and Gateshead, every building and nothing else. The Tyne is the gap.",
             color=INK, fontsize=10)
    footer(fig, [ATTRIBUTION, "Building outlines are generalised; terraces can appear as single blocks."],
           x=0.06, top=0.055)
    return save(fig, filename, dpi=300)


def draw_details(buildings, filename):
    fig = plt.figure(figsize=(12, 5.6), facecolor=PAPER)
    fig.text(0.04, 0.93, KICKER, color=GREEN, fontsize=10, weight="bold")
    fig.text(0.04, 0.85, "Three ways to house Tyneside", color=INK, fontsize=20, weight="bold")
    for i, (label, lat, lon, note) in enumerate(DETAILS):
        bounds = window(lat, lon, DETAIL_SIDE)
        ax = map_axes(fig, (0.04 + i * 0.32, 0.14, 0.29, 0.62))
        clip(buildings, bounds).plot(ax=ax, color=INK, lw=0)
        frame_to(ax, bounds, pad=0)
        ax.set_aspect("equal", adjustable="box")
        fig.text(0.04 + i * 0.32, 0.10, label, color=INK, fontsize=12, weight="bold")
        fig.text(0.04 + i * 0.32, 0.065, note, color=INK, fontsize=8.5)
    fig.text(0.04, 0.02, f"Each square is {DETAIL_SIDE / 1000:.1f} km across · {ATTRIBUTION}",
             color=MUTED, fontsize=7.5)
    return save(fig, filename, dpi=250)


def run(archive: Path, out: Path = OUT) -> dict:
    city = window(*CITY_CENTRE, CITY_W, CITY_H)
    detail_bounds = [window(lat, lon, DETAIL_SIDE) for _, lat, lon, _ in DETAILS]
    minx = min(b[0] for b in [city, *detail_bounds]); miny = min(b[1] for b in [city, *detail_bounds])
    maxx = max(b[2] for b in [city, *detail_bounds]); maxy = max(b[3] for b in [city, *detail_bounds])
    buildings = read_buildings(archive, (minx, miny, maxx, maxy))
    if buildings.empty:
        raise ValueError("No buildings in the Newcastle window; is this the NZ tile?")
    out = Path(out)
    draw_city(buildings, city, out / "newcastle-gateshead-footprints.png")
    draw_details(buildings, out / "byker-heaton-bensham.png")
    in_city = clip(buildings, city)
    stats = {"buildings_in_city_window": int(len(in_city)),
             "built_share_of_city_window": float(in_city.area.sum() / box(*city).area)}
    (out / "summary.json").write_text(json.dumps(stats, indent=2))
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("data/raw/opmplc_essh_nz.zip"))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    download(OML_NZ, args.archive, force=args.force)
    print(json.dumps(run(args.archive, args.out), indent=2))


if __name__ == "__main__":
    main()
