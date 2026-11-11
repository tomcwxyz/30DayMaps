"""Build reproducible, data-derived Day 08 and Day 09 maps.

Inputs:
  - ESA WorldCover 2021 v200 public 10 m Cloud Optimised GeoTIFF (N54W003)
  - ONS 2025 North East English region polygon
  - OpenStreetMap named river ways and disused/abandoned railway alignments
Outputs are static PNG/JSON assets committed with the source; no remote browser GIS.

Day 08 is a deliberately hypothetical allocation of 50% of terrestrial
study-region cells to nature-first land, NOT a feasibility or access model.
Day 09 is a measured land-cover transect, NOT an imagined interpolation.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import time

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import numpy as np
from pyproj import Transformer
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin, rowcol
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import from_bounds
import requests
from scipy.ndimage import distance_transform_edt, gaussian_filter
from shapely.geometry import LineString, shape
from shapely.ops import transform as shapely_transform

from maps.common import NORTH_EAST_CODE, regions

ROOT = Path(__file__).resolve().parents[1]
D8 = ROOT / "web/day08-utopia/data"
D9 = ROOT / "web/day09-urban-rural/data"
RAW = ROOT / "data/raw"
COG_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
           "ESA_WorldCover_10m_2021_v200_N54W003_Map.tif")
OSM_QUERY = """[out:json][timeout:90];
(
 way["waterway"="river"]["name"~"Tyne|Wear|Tees",i](54.30,-2.95,55.42,-1.07);
 way["railway"~"abandoned|disused"](54.30,-2.95,55.42,-1.07);
);
out geom;"""
OVERPASS_SERVERS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
)
CITY = {
    "Newcastle": (54.9783, -1.6178),
    "Sunderland": (54.9069, -1.3838),
    "Durham": (54.7753, -1.5849),
    "Middlesbrough": (54.5742, -1.2350),
    "Berwick": (55.7702, -2.0024),
    "Hexham": (54.9700, -2.1010),
}
START = (54.9783, -1.6178)
END = (54.675, -1.859)
TO_BNG = Transformer.from_crs(4326, 27700, always_xy=True)
TO_WGS = Transformer.from_crs(27700, 4326, always_xy=True)
# Sampled land-cover classes. All categories used are in ESA WorldCover 2021.
CLASS_COLOUR = {
    0: (244, 241, 231), 10: (53, 105, 69), 20: (149, 172, 112),
    30: (197, 203, 151), 40: (220, 205, 161), 50: (169, 139, 132),
    60: (224, 214, 194), 70: (224, 229, 229), 80: (109, 156, 169),
    90: (125, 177, 163), 95: (53, 105, 69), 100: (187, 183, 159),
}
LAND_CLASSES = {10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100}


def grid(bounds, cell_m):
    x0, y0, x1, y1 = map(float, bounds)
    width = int(math.ceil((x1 - x0) / cell_m))
    height = int(math.ceil((y1 - y0) / cell_m))
    return np.zeros((height, width), dtype=np.uint8), from_origin(x0, y1, cell_m, cell_m)


def worldcover_bng(bounds, cell_m):
    """Read a small overview of real 10 m WorldCover and warp nearest to BNG.

    This is a sampled representation, not an area-weighted 10 m census.
    A failure is fatal: there is no fabricated raster fallback.
    """
    output, dst_transform = grid(bounds, cell_m)
    west, south, east, north = transform_bounds("EPSG:27700", "EPSG:4326", *bounds,
                                                 densify_pts=25)
    west, east = max(-2.9999, west - .03), min(-.0001, east + .03)
    south, north = max(54.0001, south - .03), min(56.9999, north + .03)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                      CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                      GDAL_HTTP_MAX_RETRY="3",
                      GDAL_HTTP_RETRY_DELAY="2"):
        with rasterio.open(COG_URL) as src:
            window = from_bounds(west, south, east, north, transform=src.transform)
            w = max(1, int(math.ceil((east - west) * 111320 * .58 / cell_m)))
            h = max(1, int(math.ceil((north - south) * 111320 / cell_m)))
            w = min(2400, w * 2)
            h = min(2400, h * 2)
            raw = src.read(1, window=window, out_shape=(h, w),
                           resampling=Resampling.nearest)
            source_transform = src.window_transform(window) * rasterio.Affine.scale(
                window.width / w, window.height / h)
    reproject(raw, output, src_transform=source_transform, src_crs="EPSG:4326",
              dst_transform=dst_transform, dst_crs="EPSG:27700",
              src_nodata=0, dst_nodata=0, resampling=Resampling.nearest)
    if np.count_nonzero(output) < output.size * .3:
        raise ValueError("WorldCover returned too few classified samples")
    if not set(np.unique(output)).issubset(LAND_CLASSES | {0}):
        raise ValueError("Unrecognised WorldCover classification codes")
    return output, dst_transform


def osm_lines():
    RAW.mkdir(parents=True, exist_ok=True)
    cache = RAW / "day08-rivers-and-railways-osm.json"
    if cache.exists():
        data = json.loads(cache.read_text())
    else:
        errors = []
        for base in OVERPASS_SERVERS:
            try:
                response = requests.post(base, data={"data": OSM_QUERY}, timeout=(15, 115),
                                         headers={"User-Agent": "30DayMaps/2026 educational cartography"})
                response.raise_for_status()
                data = response.json()
                if len(data.get("elements", [])) < 10:
                    raise ValueError("Too few OSM ways returned")
                cache.write_text(json.dumps(data))
                break
            except Exception as exc:
                errors.append(f"{base}: {exc}")
                time.sleep(2)
        else:
            raise RuntimeError("OSM source unavailable: " + "; ".join(errors))
    rivers, rails = [], []
    for element in data["elements"]:
        tags = element.get("tags", {})
        geom = element.get("geometry", [])
        if len(geom) < 2:
            continue
        line = LineString([(p["lon"], p["lat"]) for p in geom])
        line = shapely_transform(TO_BNG.transform, line)
        if tags.get("waterway") == "river" and any(
            name in tags.get("name", "").lower() for name in ("tyne", "wear", "tees")
        ):
            rivers.append(line)
        if tags.get("railway") in {"abandoned", "disused"}:
            rails.append(line)
    if len(rivers) < 3 or len(rails) < 3:
        raise ValueError(f"Insufficient named OSM rivers ({len(rivers)}) or former railway ways ({len(rails)})")
    return rivers, rails


def terrain_rgb(codes):
    result = np.zeros((*codes.shape, 3), dtype=np.uint8)
    for code, colour in CLASS_COLOUR.items():
        result[codes == code] = colour
    return result


def sample_landcover(codes, transform, x, y):
    """Sample a BNG raster with scalar, 1D or multi-dimensional coordinates.

    Rasterio flattens array inputs; preserve the caller's grid dimensions.
    Out-of-raster positions are returned as 0 (NoData).
    """
    shape = np.broadcast_shapes(np.shape(x), np.shape(y))
    row, col = rowcol(transform, x, y)
    row = np.asarray(row).reshape(shape)
    col = np.asarray(col).reshape(shape)
    good = ((row >= 0) & (row < codes.shape[0]) &
            (col >= 0) & (col < codes.shape[1]))
    result = np.zeros(shape, dtype=np.uint8)
    result[good] = codes[row[good], col[good]]
    return result


def draw_day8(codes, transform, region, rivers, rails, chosen, existing, filename, future):
    rgb = terrain_rgb(codes)
    if future:
        rgb[chosen & ~existing] = (117, 172, 104)
        rgb[existing] = (43, 101, 66)
    else:
        rgb[existing] = (56, 112, 78)
    h, w = codes.shape
    x0, y1 = transform * (0, 0)
    x1, y0 = transform * (w, h)
    extent = (x0, x1, y0, y1)
    fig, ax = plt.subplots(figsize=(11, 10), dpi=185, facecolor="#f7f3e9")
    fig.subplots_adjust(left=.015, right=.985, bottom=.018, top=.982)
    ax.set_facecolor("#dbe9e9")
    ax.imshow(rgb, extent=extent, origin="upper", zorder=1, interpolation="nearest")
    region.boundary.plot(ax=ax, color="#46665c", lw=.35, alpha=.58, zorder=3)
    for line in rivers:
        if line.intersects(region.geometry.iloc[0]):
            xs, ys = line.xy
            ax.plot(xs, ys, color="#3d8c9c", lw=.85 if future else .6,
                    alpha=.83, zorder=6)
    if future:
        for line in rails:
            if line.intersects(region.geometry.iloc[0]):
                xs, ys = line.xy
                ax.plot(xs, ys, color="#eadc91", linewidth=.75,
                        linestyle=(0, (3, 3)), alpha=.85, zorder=7)
    for city, (lat, lon) in CITY.items():
        x, y = TO_BNG.transform(lon, lat)
        if x0 <= x <= x1 and y0 <= y <= y1:
            ax.scatter(x, y, s=12, facecolor="#faf5e8", edgecolor="#263a31",
                       linewidth=.65, zorder=9)
            ax.annotate(city, (x, y), xytext=(4, 5), textcoords="offset points",
                        color="#172f29", family="serif", fontsize=8.7,
                        fontweight="bold", zorder=10)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.axis("off")
    filename.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(filename, dpi=185, facecolor="#f7f3e9")
    plt.close(fig)


def make_day8():
    D8.mkdir(parents=True, exist_ok=True)
    boundary = regions(RAW / "ons-regions-2025.geojson")
    region = boundary.loc[boundary.RGN25CD == NORTH_EAST_CODE].copy()
    if len(region) != 1:
        raise ValueError("North East ONS region not found")
    region = region.to_crs(27700)
    geom = region.geometry.iloc[0]
    bbox = tuple(v + o for v, o in zip(geom.bounds, (-3500, -3500, 3500, 3500)))
    cell = 300
    cover, tx = worldcover_bng(bbox, cell)
    mask = rasterize([(geom, 1)], out_shape=cover.shape, transform=tx).astype(bool)
    # Never claim to have sampled unclassified or water cells as terrestrial land.
    land = mask & np.isin(cover, [10, 20, 30, 40, 50, 60, 90, 95, 100])
    if land.sum() < 20000:
        raise ValueError("Unexpectedly little classified terrestrial land")
    eligible = land & (cover != 50)
    existing = eligible & np.isin(cover, [10, 90, 95])  # woodland + wetlands; NOT 'wild'
    rivers, rails = osm_lines()
    river_geom = [(g.buffer(450), 1) for g in rivers if g.intersects(geom)]
    rail_geom = [(g.buffer(160), 1) for g in rails if g.intersects(geom)]
    river_mask = rasterize(river_geom, out_shape=cover.shape, transform=tx).astype(bool)
    rail_mask = rasterize(rail_geom, out_shape=cover.shape, transform=tx).astype(bool)
    h, w = cover.shape
    easting = tx.c + (np.arange(w) + .5) * cell
    westness = np.clip((460000 - easting) / 170000, 0, 1)[None, :]
    # An explicit (and contestable) allocation rule, not habitat suitability.
    # Core westness + adjacency to existing tree/wetland + river/rail corridors.
    distance_km = distance_transform_edt(~existing, sampling=cell) / 1000
    adjacency = np.exp(-distance_km / 3.0)
    score = 3.0 * westness + 1.3 * adjacency + 1.8 * river_mask + 1.0 * rail_mask
    score = score + .1 * (cover == 30)  # grassland slightly favoured over cropland
    target = int(round(.5 * land.sum()))
    chosen = existing.copy()
    needed = max(0, target - int(existing.sum()))
    candidates = np.flatnonzero((eligible & ~existing).ravel())
    if len(candidates) < needed:
        raise ValueError("Cannot allocate half of terrestrial land without developed land")
    scores = score.ravel()[candidates]
    top = candidates[np.argpartition(scores, -needed)[-needed:]] if needed else []
    chosen.ravel()[top] = True
    draw_day8(cover, tx, region, rivers, rails, chosen, existing, D8 / "today.png", False)
    draw_day8(cover, tx, region, rivers, rails, chosen, existing, D8 / "2050.png", True)
    if not (chosen & land).sum() == target:
        raise AssertionError("Modelled allocation is not the intended target")
    square_km = (cell * cell) / 1_000_000
    result = {
        "status": "measured_inputs_modelled_future",
        "source_year": 2021,
        "study_region": "ONS 2025 North East region E12000001",
        "resolution_m": cell,
        "base_landcover": "ESA WorldCover 2021 v200; sampled at 300 m, nearest-neighbour",
        "current_woodland_wetland_km2_approx": round(int(existing.sum()) * square_km, 1),
        "modelled_nature_first_km2_approx": round(int(chosen.sum()) * square_km, 1),
        "modelled_added_km2_approx": round(int((chosen & ~existing).sum()) * square_km, 1),
        "study_land_km2_approx": round(int(land.sum()) * square_km, 1),
        "current_woodland_wetland_pct_of_sampled_land": round(100 * existing.sum() / land.sum(), 1),
        "2050_nature_first_pct_of_sampled_land": round(100 * chosen.sum() / land.sum(), 1),
        "named_river_ways": len(rivers),
        "former_rail_ways": len(rails),
        "method": "50% of sampled classified terrestrial cells allocated using westness, adjacency to existing tree/wetland, and 450m named river/160m former-railway buffers; built-up areas excluded",
        "critical_note": "This is a designed land-allocation scenario, NOT a forecast, restoration suitability model, ecological connectivity analysis, legal access assessment or landownership proposal.",
        "sources": [
            {"name": "ESA WorldCover 2021", "url": COG_URL},
            {"name": "ONS Regions December 2025", "url": "https://www.ons.gov.uk/methodology/geography"},
            {"name": "© OpenStreetMap contributors", "url": "https://www.openstreetmap.org/copyright"},
        ],
    }
    (D8 / "metrics.json").write_text(json.dumps(result, indent=2))
    print("Day 08 model:", result)
    return result


def classify_pct(codes):
    valid = codes[np.isin(codes, list(LAND_CLASSES)) & (codes != 0)]
    if valid.size < 100:
        raise ValueError("Too few satellite land-cover pixels at sample")
    return {
        "built": round(float(np.mean(valid == 50) * 100), 2),
        "trees": round(float(np.mean(valid == 10) * 100), 2),
        "cropland": round(float(np.mean(valid == 40) * 100), 2),
        "open": round(float(np.mean(np.isin(valid, [20, 30])) * 100), 2),
        "other": round(float(np.mean(~np.isin(valid, [10, 20, 30, 40, 50])) * 100), 2),
        "sample_count": int(valid.size),
    }


def make_day9():
    D9.mkdir(parents=True, exist_ok=True)
    a = np.array(TO_BNG.transform(START[1], START[0]), dtype=float)
    b = np.array(TO_BNG.transform(END[1], END[0]), dtype=float)
    vec = b - a
    distance = float(np.linalg.norm(vec))
    forward = vec / distance
    normal = np.array([-forward[1], forward[0]])
    corners = np.stack([a + p * vec + q * normal
                        for p in (-.08, 1.08) for q in (-5200, 5200)])
    bounds = (corners[:, 0].min() - 1000, corners[:, 1].min() - 1000,
              corners[:, 0].max() + 1000, corners[:, 1].max() + 1000)
    cell = 40
    cover, tx = worldcover_bng(bounds, cell)
    h, w = cover.shape

    def sample(x, y):
        return sample_landcover(cover, tx, x, y)

    n = 85
    stations = []
    dxy = np.arange(-500, 501, cell)
    dx, dy = np.meshgrid(dxy, dxy)
    circle = (dx * dx + dy * dy) <= 500 ** 2
    offsets = np.column_stack([dx[circle], dy[circle]])
    for i, fraction in enumerate(np.linspace(0, 1, n)):
        point = a + vec * fraction
        vals = sample(point[0] + offsets[:, 0], point[1] + offsets[:, 1])
        cover_pct = classify_pct(vals)
        lon, lat = TO_WGS.transform(*point)
        stations.append({
            "index": i, "distance_km": round(distance * fraction / 1000, 3),
            "lat": round(lat, 6), "lon": round(lon, 6), **cover_pct
        })
    # Re-orient the sampled classified pixels to a 40 km by 8 km corridor.
    # Map is a straight transect, not a road route. Each pixel has a real source.
    across = np.linspace(-3800, 3800, 191)
    along = np.linspace(0, distance, 1101)
    u, v = np.meshgrid(along, across)
    world_x = a[0] + forward[0] * u + normal[0] * v
    world_y = a[1] + forward[1] * u + normal[1] * v
    sampled_strip = sample(world_x, world_y)
    rgb = terrain_rgb(sampled_strip)
    fig, ax = plt.subplots(figsize=(15, 3.6), dpi=170, facecolor="#f6f2e8")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    ax.imshow(rgb, extent=[0, distance/1000, -3.8, 3.8], origin="lower",
              aspect="auto", interpolation="nearest")
    ax.plot([0, distance/1000], [0, 0], color="#f9f8ed",
            linewidth=1.8, alpha=.95, zorder=3)
    for frac, label in [(0, "Newcastle"), (1, "Hamsterley Forest")]:
        px = frac * distance/1000
        ax.scatter([px], [0], facecolor="#fcfbf6",
                   edgecolor="#193b2f", s=65, zorder=4)
        ax.annotate(label, (px, 0), xytext=(10 if frac == 0 else -10, 14),
                    textcoords="offset points",
                    horizontalalignment="left" if frac == 0 else "right",
                    color="#193b2f", fontsize=12, family="serif", weight="bold",
                    zorder=5, bbox={"fc": "#f8f4e9", "ec": "none", "alpha": .9, "pad": 2})
    for d in np.arange(10, distance/1000, 10):
        ax.text(d, -3.45, f"{int(d)} km", fontsize=8.5, color="#2d473c",
                horizontalalignment="center", family="sans-serif",
                bbox={"fc": "#f7f2e8", "ec": "none", "alpha": .8, "pad": 1})
    ax.axis("off")
    fig.savefig(D9 / "transect.png", dpi=170, facecolor="#f6f2e8")
    plt.close(fig)
    output = {
        "status": "measured",
        "title": "Where does the city end?",
        "source": "ESA WorldCover 2021 v200 (10 m), downsampled to 40 m before sampling",
        "source_url": COG_URL,
        "date_of_source": 2021,
        "distance_km": round(distance/1000, 3),
        "radius_m": 500,
        "sample_resolution_m": cell,
        "samples": stations,
        "method": "85 evenly spaced locations along a straight BNG transect; each proportion counts sampled ESA land-cover cells within a 500m radius. No curve smoothing or invented points.",
        "notes": "A land-cover composition measure, not an official urban/rural boundary or a measure of accessibility. Classes are satellite classifications, subject to source accuracy.",
    }
    (D9 / "profile.json").write_text(json.dumps(output, indent=2))
    assert all(abs(sum(s[k] for k in ("built", "trees", "cropland", "open", "other")) - 100) < .1
               for s in stations)
    print("Day 09 transect:", round(distance / 1000, 2), "km;",
          len(stations), "measured points;", cover.shape)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", choices=("all", "8", "9"), default="all")
    args = parser.parse_args()
    if args.day in ("all", "8"):
        make_day8()
    if args.day in ("all", "9"):
        make_day9()


if __name__ == "__main__":
    main()
