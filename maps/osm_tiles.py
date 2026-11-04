"""OpenStreetMap buildings from OpenFreeMap's vector tiles.

The public Overpass servers turn away or time out on city-sized building queries,
so prints use the ready-made OpenMapTiles vector tiles that OpenFreeMap serves from
a CDN: free, no API key, commercial use allowed. Zoom 14 tiles carry every building
at full detail (about 0.3 m precision at UK latitudes). The web print maker reads the
same tiles, so a preview and its print match.

Credit required on anything made from them: "OpenFreeMap © OpenMapTiles Data from
OpenStreetMap" (see CREDIT). OpenFreeMap asks bulk downloaders for at most four
parallel requests and an identifying User-Agent; a print needs well under its
3,000-tile limit.
"""
from __future__ import annotations

import concurrent.futures as cf
import math
import time
from pathlib import Path

import geopandas as gpd
import requests
import shapely
from shapely import affinity
from shapely.geometry import box, shape

TILEJSON = "https://tiles.openfreemap.org/planet"
ZOOM = 14
LAYER = "building"
PARALLEL = 4
USER_AGENT = "30DayMaps-footprints/0.2 (+https://github.com/tomcwxyz/30DayMaps)"
CREDIT = "Data from OpenStreetMap (openstreetmap.org/copyright) · © OpenMapTiles · OpenFreeMap"
EARTH = 2 * math.pi * 6378137  # Web Mercator world width in metres
MAX_TILES = 600
# Each tile repeats a margin of its neighbours. Clip to the tile, plus a sliver of
# overlap so neighbouring pieces of a building print without a hairline seam.
OVERLAP = 1


def tile_range(west: float, south: float, east: float, north: float, zoom: int = ZOOM):
    """Inclusive x and y tile ranges covering a lon/lat box."""
    n = 2 ** zoom

    def xy(lon, lat):
        x = (lon + 180) / 360 * n
        y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
        return min(n - 1, max(0, int(x))), min(n - 1, max(0, int(y)))

    x0, y0 = xy(west, north)
    x1, y1 = xy(east, south)
    return range(x0, x1 + 1), range(y0, y1 + 1)


def tile_template(session=requests) -> str:
    r = session.get(TILEJSON, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    tiles = r.json().get("tiles") or []
    if not tiles:
        raise RuntimeError("OpenFreeMap TileJSON lists no tiles")
    return tiles[0]


def decode_buildings(data: bytes, x: int, y: int, zoom: int = ZOOM) -> list:
    """Building polygons from one tile, clipped to it, in Web Mercator metres (EPSG:3857)."""
    import mapbox_vector_tile
    layer = mapbox_vector_tile.decode(data, default_options={"y_coord_down": True}).get(LAYER)
    if not layer:
        return []
    extent = layer.get("extent", 4096)
    frame = box(-OVERLAP, -OVERLAP, extent + OVERLAP, extent + OVERLAP)
    scale = EARTH / (extent * 2 ** zoom)
    out = []
    for feature in layer["features"]:
        geom = feature.get("geometry") or {}
        if geom.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        g = shape(geom)
        if not g.is_valid:
            g = shapely.make_valid(g)
        g = g.intersection(frame)
        if g.is_empty:
            continue
        # tile units (y down) -> world tile units -> Web Mercator metres (y up)
        g = affinity.affine_transform(g, [scale, 0, 0, -scale,
                                          x * extent * scale - EARTH / 2,
                                          EARTH / 2 - y * extent * scale])
        out.extend(p for p in shapely.get_parts(g) if p.geom_type == "Polygon" and not p.is_empty)
    return out


def fetch_tile(url: str, session=requests, attempts: int = 3) -> bytes:
    for attempt in range(attempts):
        try:
            r = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=(15, 90))
            if r.status_code == 404:
                return b""  # open sea beyond the data
            if r.status_code < 500:
                r.raise_for_status()
                return r.content
        except (requests.ConnectionError, requests.Timeout):
            if attempt == attempts - 1:
                raise
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Map tile unavailable after {attempts} tries")


def buildings(bounds_lonlat, crs, cache=Path("data/raw"), session=requests) -> gpd.GeoDataFrame:
    """Every building in a lon/lat box (west, south, east, north), projected to `crs`."""
    west, south, east, north = bounds_lonlat
    xs, ys = tile_range(west, south, east, north)
    tiles = [(x, y) for x in xs for y in ys]
    if len(tiles) > MAX_TILES:
        raise ValueError(f"That area needs {len(tiles)} map tiles; choose a smaller width")
    template = tile_template(session)
    version = template.rstrip("/").split("/")[-4] if template.count("/") >= 4 else "tiles"
    folder = Path(cache) / "openfreemap" / version / str(ZOOM)

    def load(t):
        x, y = t
        path = folder / f"{x}-{y}.pbf"
        if path.exists():
            return t, path.read_bytes()
        data = fetch_tile(template.format(z=ZOOM, x=x, y=y), session)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return t, data

    polys = []
    with cf.ThreadPoolExecutor(PARALLEL) as pool:
        for (x, y), data in pool.map(load, tiles):
            if data:
                polys.extend(decode_buildings(data, x, y))
    if not polys:
        raise ValueError("No OpenStreetMap buildings in this window")
    return gpd.GeoDataFrame(geometry=polys, crs=3857).to_crs(crs)
