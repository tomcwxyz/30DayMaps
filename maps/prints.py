"""Footprints print maker: any place, buildings and nothing else, sized for print and web.

Great Britain uses OS OpenMap – Local (downloaded per 100 km tile); anywhere else,
or when asked, uses OpenStreetMap buildings from the Overpass API.

    python -m maps.prints --list
    python -m maps.prints --place york --paper A3
    python -m maps.prints --lat 54.97 --lon -1.61 --name "Ouseburn" --width-km 2 \\
        --title "The Ouseburn" --subtitle "Every building in the valley" --theme night
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import requests
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import LineString, Polygon, box

from maps.common import download
from maps.footprints import building_layer, clip

PLACES = json.loads((Path(__file__).with_name("print_places.json")).read_text())
OML_TILE = ("https://api.os.uk/downloads/v1/products/OpenMapLocal/downloads?"
            "area={tile}&format=ESRI%C2%AE+Shapefile&redirect")
OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]
OUT = Path("prints")
MM_PER_INCH = 25.4

PAPERS = {  # portrait width x height, mm
    "A4": (210, 297), "A3": (297, 420), "A2": (420, 594), "A1": (594, 841),
    "50x70": (500, 700), "square": (300, 300),
}
THEMES = {  # buildings, background, secondary text
    "paper": ("#1E353B", "#F7F6F0", "#8A9B9B"),
    "night": ("#EDE6D6", "#17252B", "#7F9399"),
    "blue": ("#F1F5F7", "#1F4A66", "#9DB5C4"),
    "ink": ("#111111", "#FFFFFF", "#888888"),
}
CREDITS = {
    "os": "Contains OS data © Crown copyright and database right {year} · OS OpenMap – Local, OGL v3.0",
    "osm": "Buildings © OpenStreetMap contributors, ODbL · openstreetmap.org/copyright",
}


@dataclass
class Spec:
    name: str
    lat: float
    lon: float
    title: str
    subtitle: str = "Every building and nothing else."
    kicker: str = ""
    note: str = ""
    paper: str = "A3"
    landscape: bool = False
    width_km: float = 9.0
    theme: str = "paper"
    ink: str | None = None
    background: str | None = None
    source: str = "auto"
    dpi: int = 300
    formats: list[str] = field(default_factory=lambda: ["print", "web", "pdf"])
    year: int = 2026

    @property
    def slug(self) -> str:
        return slugify(self.name)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "place"


# --- Geometry and layout -----------------------------------------------------

def paper_mm(paper: str, landscape: bool = False) -> tuple[float, float]:
    if paper not in PAPERS:
        raise ValueError(f"Unknown paper {paper!r}; choose from {', '.join(PAPERS)}")
    w, h = PAPERS[paper]
    return (h, w) if landscape else (w, h)


def layout(paper_w: float, paper_h: float, has_kicker: bool) -> dict:
    """Page fractions for the map box and the text, so text scales with the paper."""
    margin = 0.055 * min(paper_w, paper_h)
    title_pt = min(paper_w, paper_h) * 0.13           # A3 portrait ≈ 39 pt
    head = (title_pt * 1.0 + title_pt * 0.42 * 2.2 + (title_pt * 0.32 * 1.6 if has_kicker else 0)) \
        * MM_PER_INCH / 72 + margin * 0.6
    foot = margin * 0.9
    map_box = (margin / paper_w, (margin + foot * 0.6) / paper_h,
               1 - 2 * margin / paper_w, 1 - (2 * margin + head + foot * 0.6) / paper_h)
    return {"margin": margin, "title_pt": title_pt, "map": map_box}


def ground_window(centre_xy, width_m: float, map_box, paper_w: float, paper_h: float):
    """Ground extent with exactly the map box's shape, so buildings aren't stretched."""
    box_w = map_box[2] * paper_w
    box_h = map_box[3] * paper_h
    height_m = width_m * box_h / box_w
    x, y = centre_xy
    return (x - width_m / 2, y - height_m / 2, x + width_m / 2, y + height_m / 2)


# --- Data sources ------------------------------------------------------------

def in_great_britain(lat: float, lon: float) -> bool:
    """Rough GB test for picking OS data; Ireland and Northern Ireland use OSM."""
    if not (49.8 <= lat <= 60.9 and -8.7 <= lon <= 1.8):
        return False
    return not (lon < -5.4 and 51.3 <= lat <= 55.45)


def pick_source(spec: Spec) -> str:
    if spec.source in ("os", "osm"):
        if spec.source == "os" and not in_great_britain(spec.lat, spec.lon):
            raise ValueError("OS OpenMap – Local only covers Great Britain; use --source osm")
        return spec.source
    return "os" if in_great_britain(spec.lat, spec.lon) else "osm"


def grid_tile(easting: float, northing: float) -> str:
    """Two-letter OS 100 km grid square (e.g. NZ for Newcastle, TQ for London)."""
    e, n = int(easting // 100_000), int(northing // 100_000)
    if not (0 <= e <= 6 and 0 <= n <= 12):
        raise ValueError("Outside the British National Grid")
    l1 = (19 - n) - (19 - n) % 5 + (e + 10) // 5
    l2 = (19 - n) * 5 % 25 + e % 5
    l1 += l1 > 7
    l2 += l2 > 7
    return chr(65 + l1) + chr(65 + l2)


def tiles_for(bounds) -> list[str]:
    minx, miny, maxx, maxy = bounds
    tiles = {grid_tile(x, y) for x in (minx, maxx) for y in (miny, maxy)}
    return sorted(tiles)


def os_buildings(bounds, cache=Path("data/raw")) -> gpd.GeoDataFrame:
    frames = []
    for tile in tiles_for(bounds):
        archive = cache / f"opmplc_essh_{tile.lower()}.zip"
        try:
            download(OML_TILE.format(tile=tile), archive)
        except requests.HTTPError as err:
            if err.response is not None and err.response.status_code == 404:
                continue  # all-sea squares have no tile
            raise
        data = gpd.read_file(building_layer(archive), bbox=bounds)
        frames.append(data.to_crs(27700))
    if not frames:
        raise ValueError("No OS tiles found for this window")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=27700)


def overpass_query(south, west, north, east) -> str:
    b = f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}"
    return (f'[out:json][timeout:240];(way["building"]({b});'
            f'relation["building"]["type"="multipolygon"]({b}););out geom;')


def osm_polygons(payload: dict) -> list[Polygon]:
    """Turn Overpass 'out geom' JSON into polygons in lon/lat."""
    polys = []
    for el in payload.get("elements", []):
        if el.get("type") == "way":
            pts = [(p["lon"], p["lat"]) for p in el.get("geometry", [])]
            if len(pts) >= 4 and pts[0] == pts[-1]:
                polys.append(Polygon(pts))
        elif el.get("type") == "relation":
            rings = {"outer": [], "inner": []}
            for m in el.get("members", []):
                if m.get("type") == "way" and m.get("geometry") and m.get("role") in rings:
                    rings[m["role"]].append(LineString([(p["lon"], p["lat"]) for p in m["geometry"]]))
            outer = shapely.union_all(list(shapely.polygonize(rings["outer"]).geoms)) if rings["outer"] else None
            if outer is None or outer.is_empty:
                continue
            if rings["inner"]:
                outer = outer.difference(shapely.union_all(list(shapely.polygonize(rings["inner"]).geoms)))
            polys.extend(g for g in shapely.get_parts(outer) if g.geom_type == "Polygon")
    return [shapely.make_valid(p) if not p.is_valid else p for p in polys]


def osm_buildings(bounds_lonlat, crs, cache=Path("data/raw")) -> gpd.GeoDataFrame:
    west, south, east, north = bounds_lonlat
    query = overpass_query(south, west, north, east)
    key = hashlib.sha1(query.encode()).hexdigest()[:12]
    cached = cache / f"overpass-{key}.json"
    if cached.exists():
        payload = json.loads(cached.read_text())
    else:
        last = None
        for url in OVERPASS:
            try:
                r = requests.post(url, data={"data": query}, timeout=(20, 300),
                                  headers={"User-Agent": "30DayMaps-prints/0.1"})
                r.raise_for_status()
                payload = r.json()
                break
            except (requests.RequestException, ValueError) as err:
                last = err
        else:
            raise RuntimeError(f"Overpass unavailable: {last}")
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(payload))
    polys = osm_polygons(payload)
    if not polys:
        raise ValueError("No OpenStreetMap buildings in this window")
    return gpd.GeoDataFrame(geometry=polys, crs=4326).to_crs(crs)


# --- Rendering ---------------------------------------------------------------

def colours(spec: Spec):
    ink, bg, muted = THEMES[spec.theme]
    return spec.ink or ink, spec.background or bg, muted


def draw(spec: Spec, buildings: gpd.GeoDataFrame, bounds, source: str, filename: Path,
         *, dpi: int, vector: bool = False) -> Path:
    pw, ph = paper_mm(spec.paper, spec.landscape)
    lay = layout(pw, ph, bool(spec.kicker))
    ink, bg, muted = colours(spec)
    fig = plt.figure(figsize=(pw / MM_PER_INCH, ph / MM_PER_INCH), facecolor=bg)
    ax = fig.add_axes(lay["map"])
    ax.set_facecolor(bg)
    ax.axis("off")
    clip(buildings, bounds).plot(ax=ax, color=ink, lw=0, rasterized=not vector)
    ax.set_xlim(bounds[0], bounds[2]); ax.set_ylim(bounds[1], bounds[3])
    ax.set_aspect("equal", adjustable="box")

    left = lay["margin"] / pw
    top = 1 - lay["margin"] / ph
    pt = lay["title_pt"]
    to_frac = lambda points: points * MM_PER_INCH / 72 / ph
    y = top
    if spec.kicker:
        fig.text(left, y, spec.kicker.upper(), color=muted, fontsize=pt * 0.32, weight="bold", va="top")
        y -= to_frac(pt * 0.32 * 1.6)
    fig.text(left, y, spec.title, color=ink, fontsize=pt, weight="bold", va="top")
    y -= to_frac(pt * 1.25)
    if spec.subtitle:
        chars = int((1 - 2 * left) * pw / (pt * 0.42 * 0.19))  # rough characters per line
        fig.text(left, y, textwrap.fill(spec.subtitle, max(20, chars)), color=ink,
                 fontsize=pt * 0.42, va="top", linespacing=1.3)
    credit = CREDITS[source].format(year=spec.year)
    if spec.note:
        credit = f"{spec.note} · {credit}"
    fig.text(left, lay["margin"] * 0.55 / ph, credit, color=muted, fontsize=max(5.5, pt * 0.17), va="bottom")
    filename = Path(filename)
    filename.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(filename, dpi=dpi, facecolor=bg)
    plt.close(fig)
    return filename


def make(spec: Spec, out: Path = OUT) -> dict:
    pw, ph = paper_mm(spec.paper, spec.landscape)
    lay = layout(pw, ph, bool(spec.kicker))
    source = pick_source(spec)
    if source == "os":
        crs = CRS.from_epsg(27700)
    else:
        crs = gpd.GeoSeries.from_xy([spec.lon], [spec.lat], crs=4326).estimate_utm_crs()
    centre = Transformer.from_crs(4326, crs, always_xy=True).transform(spec.lon, spec.lat)
    bounds = ground_window(centre, spec.width_km * 1000, lay["map"], pw, ph)
    if source == "os":
        buildings = os_buildings(bounds)
    else:
        lonlat = Transformer.from_crs(crs, 4326, always_xy=True).transform_bounds(*bounds)
        buildings = osm_buildings(lonlat, crs)
    buildings = buildings.loc[buildings.geometry.notna()]
    folder = Path(out) / spec.slug
    stem = f"{spec.slug}-{spec.paper.lower()}{'-landscape' if spec.landscape else ''}"
    files = []
    if "print" in spec.formats:
        files.append(draw(spec, buildings, bounds, source, folder / f"{stem}-{spec.dpi}dpi.png", dpi=spec.dpi))
    if "pdf" in spec.formats:
        files.append(draw(spec, buildings, bounds, source, folder / f"{stem}.pdf", dpi=spec.dpi, vector=True))
    if "web" in spec.formats:
        web_dpi = max(72, int(2000 / (max(pw, ph) / MM_PER_INCH)))  # long edge ≈ 2000 px
        files.append(draw(spec, buildings, bounds, source, folder / f"{stem}-web.png", dpi=web_dpi))
    summary = {"place": spec.name, "source": source, "paper": spec.paper,
               "landscape": spec.landscape, "ground_km": [round((bounds[2] - bounds[0]) / 1000, 2),
                                                          round((bounds[3] - bounds[1]) / 1000, 2)],
               "buildings": int(len(clip(buildings, bounds))), "files": [str(f) for f in files]}
    (folder / f"{stem}.json").write_text(json.dumps(summary, indent=2))
    return summary


def spec_from_args(args) -> Spec:
    preset = {}
    if args.place:
        key = slugify(args.place)
        if key not in PLACES:
            raise SystemExit(f"Unknown place {args.place!r}. Use --list, or give --lat and --lon.")
        preset = PLACES[key]
    lat = args.lat if args.lat is not None else preset.get("lat")
    lon = args.lon if args.lon is not None else preset.get("lon")
    if lat is None or lon is None:
        raise SystemExit("Give --place, or both --lat and --lon")
    name = args.name or preset.get("name") or f"{lat:.4f}, {lon:.4f}"
    return Spec(
        name=name, lat=float(lat), lon=float(lon),
        title=args.title or name,
        subtitle=args.subtitle if args.subtitle is not None else preset.get("subtitle", Spec.subtitle),
        kicker=args.kicker or "", note=args.note or "",
        paper=args.paper, landscape=args.landscape,
        width_km=args.width_km or preset.get("width_km", 9.0),
        theme=args.theme, ink=args.ink, background=args.background, source=args.source,
        dpi=args.dpi, formats=[f.strip() for f in args.formats.split(",") if f.strip()],
    )


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", action="store_true", help="list preset places")
    p.add_argument("--place", help="preset name, e.g. york")
    p.add_argument("--lat", type=float); p.add_argument("--lon", type=float)
    p.add_argument("--name", help="place name for files and default title")
    p.add_argument("--title"); p.add_argument("--subtitle"); p.add_argument("--kicker")
    p.add_argument("--note", help="extra text before the data credit")
    p.add_argument("--paper", default="A3", choices=list(PAPERS))
    p.add_argument("--landscape", action="store_true")
    p.add_argument("--width-km", type=float, help="ground width shown (default 9, or the preset's)")
    p.add_argument("--theme", default="paper", choices=list(THEMES))
    p.add_argument("--ink", help="building colour, e.g. '#222222'")
    p.add_argument("--background", help="background colour")
    p.add_argument("--source", default="auto", choices=["auto", "os", "osm"])
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--formats", default="print,web,pdf", help="any of print,web,pdf")
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args(argv)
    if args.list:
        for key, v in PLACES.items():
            print(f"{key:15} {v['name']}")
        return
    print(json.dumps(make(spec_from_args(args), args.out), indent=2))


if __name__ == "__main__":
    main()
