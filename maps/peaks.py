"""Peaks: contour, ridgeline and skyline prints of real mountains.

Elevation comes from Mapzen/Tilezen Terrarium tiles (AWS Open Data), reprojected to
metres on a local azimuthal grid centred on the place. Nothing is synthesised: every
line is drawn from the elevation model, only lightly smoothed for contours.

    python -m maps.peaks fetch helvellyn cuillin-from-elgol   # download DEMs to peaks/dem
    python -m maps.peaks fetch --all
    python -m maps.peaks render helvellyn --style contours --theme paper
    python -m maps.peaks render --all                          # every style for every DEM

Styles: contours, ridgelines (area places) and skyline (view places).
Requires the 'sight' extra: pip install -e ".[sight]"
"""
from __future__ import annotations

import argparse
import json
import math
from io import BytesIO
from pathlib import Path

import numpy as np

PLACES = json.loads(Path(__file__).with_name("peak_places.json").read_text())
AREAS = {p["slug"]: p for p in PLACES["areas"]}
VIEWS = {p["slug"]: p for p in PLACES["views"]}
DEM_DIR = Path("peaks/dem")
OUT_DIR = Path("peaks/out")
TERRARIUM = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
SOURCE = "Elevation: Mapzen/Tilezen Terrain Tiles (AWS Open Data) incl. SRTM, EU-DEM, UK LiDAR"
TILE = 256
WEB_MERC_HALF = 20_037_508.342789244
EARTH_R = 6_371_008.8

# ---------------------------------------------------------------- elevation data

def _aeqd(lat: float, lon: float) -> str:
    return f"+proj=aeqd +lat_0={lat} +lon_0={lon} +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"


def _choose_zoom(lat: float, res_m: float) -> int:
    for z in range(8, 15):
        if 2 * WEB_MERC_HALF / (TILE * 2 ** z) * math.cos(math.radians(lat)) <= res_m * 1.15:
            return z
    return 14


def _decode(png: bytes) -> np.ndarray:
    from PIL import Image
    rgb = np.asarray(Image.open(BytesIO(png)).convert("RGB"), dtype=np.float32)
    return rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768


def fetch_dem(slug: str, lat: float, lon: float, half_w: float, half_h: float, res: float) -> Path:
    """Download Terrarium tiles covering the box and resample to a local metre grid."""
    import requests
    from pyproj import Transformer
    from rasterio.enums import Resampling
    from rasterio.transform import Affine, from_origin
    from rasterio.warp import reproject

    crs = _aeqd(lat, lon)
    to_ll = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    to_merc = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    edge = [(x, y) for x in np.linspace(-half_w, half_w, 9) for y in (-half_h, half_h)] + \
           [(x, y) for y in np.linspace(-half_h, half_h, 9) for x in (-half_w, half_w)]
    mx, my = to_merc.transform(*to_ll.transform([p[0] for p in edge], [p[1] for p in edge]))
    z = _choose_zoom(lat, res)
    while True:
        span = 2 * WEB_MERC_HALF / 2 ** z
        x0, x1 = int((min(mx) + WEB_MERC_HALF) // span), int((max(mx) + WEB_MERC_HALF) // span)
        y0, y1 = int((WEB_MERC_HALF - max(my)) // span), int((WEB_MERC_HALF - min(my)) // span)
        if (x1 - x0 + 1) * (y1 - y0 + 1) <= 400:
            break
        z -= 1
    mosaic = np.zeros(((y1 - y0 + 1) * TILE, (x1 - x0 + 1) * TILE), np.float32)
    s = requests.Session()
    s.headers["User-Agent"] = "30DayMaps-peaks/0.1 (+https://github.com/tomcwxyz/30DayMaps)"
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            r = s.get(TERRARIUM.format(z=z, x=tx, y=ty), timeout=40)
            r.raise_for_status()
            mosaic[(ty - y0) * TILE:(ty - y0 + 1) * TILE, (tx - x0) * TILE:(tx - x0 + 1) * TILE] = _decode(r.content)
    px = span / TILE
    src_t = Affine(px, 0, -WEB_MERC_HALF + x0 * span, 0, -px, WEB_MERC_HALF - y0 * span)
    w, h = math.ceil(2 * half_w / res), math.ceil(2 * half_h / res)
    dem = np.full((h, w), np.nan, np.float32)
    reproject(mosaic, dem, src_transform=src_t, src_crs="EPSG:3857",
              dst_transform=from_origin(-half_w, half_h, res, res), dst_crs=crs,
              resampling=Resampling.cubic, dst_nodata=np.nan)
    # Terrarium has occasional void pixels decoded as huge negative depths; treat them as gaps
    # and fill each from its nearest valid neighbour.
    bad = ~np.isfinite(dem) | (dem < -450)
    if bad.any() and (~bad).any():
        from scipy.ndimage import distance_transform_edt
        idx = distance_transform_edt(bad, return_distances=False, return_indices=True)
        dem = dem[tuple(idx)]
    DEM_DIR.mkdir(parents=True, exist_ok=True)
    out = DEM_DIR / f"{slug}.npz"
    np.savez_compressed(out, dem=np.round(dem * 2) / 2, res=res, lat=lat, lon=lon, zoom=z,
                        half_w=half_w, half_h=half_h)
    print(f"{slug}: zoom {z}, {(x1-x0+1)*(y1-y0+1)} tiles, grid {w}x{h} @ {res:.0f} m, "
          f"{np.nanmin(dem):.0f}–{np.nanmax(dem):.0f} m -> {out}")
    return out


def fetch(slug: str) -> Path:
    if slug in AREAS:
        p = AREAS[slug]
        half = p["width_km"] * 500
        res = max(4.0, p["width_km"] * 1000 / 1500)
        return fetch_dem(slug, p["lat"], p["lon"], half, half * 1.3, res)
    p = VIEWS[slug]
    reach = p["reach_km"] * 1000
    return fetch_dem(slug, p["lat"], p["lon"], reach, reach, max(15.0, reach / 1600))


OVERPASS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")


def fetch_names(slug: str) -> Path:
    """Named summits (OpenStreetMap natural=peak/hill) and ridges (natural=arete/ridge, at their
    middle) inside the DEM, in local metres. Ridges carry kind "ridge"."""
    import time
    import requests
    from pyproj import Transformer
    d = load(slug)
    crs = _aeqd(d["lat"], d["lon"])
    to_ll = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    xs, ys = to_ll.transform([-d["half_w"], d["half_w"], -d["half_w"], d["half_w"]],
                             [-d["half_h"], -d["half_h"], d["half_h"], d["half_h"]])
    bbox = f"{min(ys)},{min(xs)},{max(ys)},{max(xs)}"
    q = (f'[out:json][timeout:60];(node["natural"~"^(peak|hill|volcano)$"]["name"]({bbox});'
         f'way["natural"~"^(arete|ridge)$"]["name"]({bbox}););out center;')
    for attempt in range(6):
        url = OVERPASS[attempt % 2]
        try:
            r = requests.post(url, data={"data": q}, timeout=90,
                              headers={"User-Agent": "30DayMaps-peaks/0.1 (+https://github.com/tomcwxyz/30DayMaps)"})
            r.raise_for_status()
            els = r.json()["elements"]
            break
        except Exception as e:  # rate limits are common; wait and try the other server
            print(f"{slug}: overpass {url} failed ({e}); retrying")
            time.sleep(15 * (attempt + 1))
    else:
        raise RuntimeError("Overpass unavailable")
    to_xy = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    out = []
    for e in els:
        kind = "ridge" if e["type"] == "way" else "peak"
        if kind == "ridge":
            e = dict(e, lat=e["center"]["lat"], lon=e["center"]["lon"])
        x, y = to_xy.transform(e["lon"], e["lat"])
        ele = e["tags"].get("ele", "").replace("m", "").strip()
        try:
            ele = float(ele)
        except ValueError:
            ele = None
        out.append({"name": e["tags"]["name"], "name_en": e["tags"].get("name:en"), "lat": e["lat"], "lon": e["lon"],
                    "x": round(x, 1), "y": round(y, 1), "ele": ele, "osm": e["id"], "kind": kind})
    path = DEM_DIR / f"{slug}.names.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=0))
    print(f"{slug}: {sum(n['kind'] == 'peak' for n in out)} named summits, {sum(n['kind'] == 'ridge' for n in out)} ridges -> {path}")
    time.sleep(3)
    return path


def _latin(t: str | None) -> bool:
    return bool(t) and all(ord(c) < 0x250 or c in "’‘·" for c in t)


def names(slug: str, kind: str = "peak") -> list[dict]:
    """Named summits (or ridges, kind="ridge"), keeping a Latin-script name (English if the local
    one isn't) so labels print."""
    p = DEM_DIR / f"{slug}.names.json"
    out = []
    for n in (json.loads(p.read_text()) if p.exists() else []):
        if n.get("kind", "peak") != kind:
            continue
        name = n["name"] if _latin(n["name"]) else n.get("name_en")
        if _latin(name):
            out.append(dict(n, name=name, name_en=None))
    return out


def clean(dem: np.ndarray) -> np.ndarray:
    """Repair Terrarium faults: garbage strips along tile seams, isolated spikes and voids.
    Sea floor (bathymetry) is flattened to 0 m so coasts draw as one clean line."""
    from scipy.ndimage import distance_transform_edt, median_filter
    z = dem.astype(np.float32).copy()
    bad = ~np.isfinite(z) | (z < -440)
    zf = np.where(bad, np.nanmedian(z), z)
    for axis in (0, 1):  # whole rows/columns whose step to the next is wildly out of character
        step = np.median(np.abs(np.diff(zf, axis=axis)), axis=1 - axis)
        line = np.where(step > max(8.0, 8 * np.median(step)))[0]
        for i in line:
            sl = slice(max(0, i - 2), i + 4)
            if axis == 0:
                bad[sl, :] = True
            else:
                bad[:, sl] = True
    m = median_filter(zf, 7)
    bad |= np.abs(zf - m) > 220  # spikes far beyond any real cliff at these resolutions
    if bad.any():
        idx = distance_transform_edt(bad, return_distances=False, return_indices=True)
        z = zf[tuple(idx)]
        z = np.where(bad, median_filter(z, 9), z)
    return np.maximum(z, 0)


def load(slug: str) -> dict:
    d = np.load(DEM_DIR / f"{slug}.npz")
    out = {k: (d[k] if d[k].ndim else d[k].item()) for k in d.files}
    out["dem"] = clean(out["dem"])
    return out


# ---------------------------------------------------------------- look

FONT_DIR = Path(__file__).with_name("fonts")
SANS = ["Jost", "DejaVu Sans"]
MONO = ["IBM Plex Mono", "DejaVu Sans Mono"]

# page, panel (the map's ground), line, text, muted, accent
THEMES = {
    "paper":   dict(page="#F6F3EC", panel="#F6F3EC", line="#1F2321", text="#1F2321", muted="#7D817C", accent="#B5482F"),
    "white":   dict(page="#FFFFFF", panel="#FFFFFF", line="#141414", text="#141414", muted="#8A8A8A", accent="#C0392B"),
    "navy":    dict(page="#F6F3EC", panel="#17263A", line="#E6EDF1", text="#17263A", muted="#7D8790", accent="#F0B45A"),
    "oxblood": dict(page="#7C2A30", panel="#7C2A30", line="#F3D9D4", text="#FBEDE8", muted="#D9A9A6", accent="#FFFFFF", frame="#F3D9D4"),
    "night":   dict(page="#121A1E", panel="#121A1E", line="#DCD5C4", text="#E9E3D3", muted="#76858B", accent="#E0A55E"),
    "moss":    dict(page="#EEEBDD", panel="#2E3A2C", line="#E7E2C6", text="#2E3A2C", muted="#7F8A72", accent="#E2C46B"),
    "bands":   dict(page="#F4EEDC", panel="#F4EEDC", line="#2B2A28", text="#2B2A28", muted="#837D70", accent="#2B2A28",
                    fills=["#D8D2BE", "#9FB7B1", "#E7B24C", "#C76E6B", "#E9E2CC", "#8FA3C2", "#B9C3A1", "#F0C9A6"]),
}
# skyline palettes: sky top, sky bottom, far layer, near layer
SKIES = {
    "green": ("#DCE8E3", "#EFEBDF", "#C3D4CB", "#1E4C3D"),
    "mist":  ("#F1EEE6", "#F6F3EC", "#D9D6CD", "#1F2321"),
    "dusk":  ("#B9C2DA", "#F2D3BF", "#B5B0CB", "#1D2440"),
    "night": ("#0E151A", "#24333A", "#3E5058", "#0A0F12"),
}


def _fonts():
    from matplotlib import font_manager as fm
    for f in FONT_DIR.glob("*.ttf"):
        fm.fontManager.addfont(str(f))


def _spaced(text: str) -> str:
    return "   ".join(" ".join(w) for w in text.upper().split())


def _nice(step: float) -> float:
    for s in (5, 10, 15, 20, 25, 50, 100, 200, 250, 500):
        if step <= s:
            return s
    return 1000


def _ll(lat: float, lon: float) -> str:
    return f"{abs(lat):.4f}° {'N' if lat >= 0 else 'S'}   ·   {abs(lon):.4f}° {'E' if lon >= 0 else 'W'}"


def _figure(th, w_mm=297, h_mm=420):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _fonts()
    return plt.figure(figsize=(w_mm / 25.4, h_mm / 25.4), facecolor=th["page"])


def _caption(fig, th, title, line1, line2, y, x=0.5, ha="center", size=34):
    fig.text(x, y, _spaced(title), color=th["text"], fontsize=size, family=SANS, weight="bold", ha=ha, va="top")
    H = fig.get_size_inches()[1] * 72
    y1 = y - size * 1.45 / H
    fig.text(x, y1, line1, color=th["text"], fontsize=9.5, family=MONO, ha=ha, va="top")
    fig.text(x, y1 - 17 / H, line2.upper(), color=th["muted"], fontsize=8, family=MONO, ha=ha, va="top")


def _credit(fig, th, text, y=0.022):
    fig.text(0.5, y, text, color=th["muted"], fontsize=5.6, family=MONO, ha="center", va="bottom")


def _map_axes(fig, box, aspect):
    """Largest axes of the given width/height ratio centred in box (figure fractions)."""
    W, H = fig.get_size_inches()
    x0, y0, w, h = box
    if (w * W) / (h * H) > aspect:
        nw = h * H * aspect / W
        x0, w = x0 + (w - nw) / 2, nw
    else:
        nh = w * W / aspect / H
        y0, h = y0 + (h - nh) / 2, nh
    return fig.add_axes([x0, y0, w, h]), (x0, y0, w, h)


def _crop(d, aspect=None, zoom=1.0, dx=0.0, dy=0.0):
    """Frame inside the DEM: zoom in, shift the centre by dx/dy metres, keep inside the data."""
    hw, hh = d["half_w"] / zoom, d["half_h"] / zoom
    if aspect:
        if hw / hh > aspect:
            hw = hh * aspect
        else:
            hh = hw / aspect
    dx = float(np.clip(dx, -d["half_w"] + hw, d["half_w"] - hw))
    dy = float(np.clip(dy, -d["half_h"] + hh, d["half_h"] - hh))
    return dx - hw, dx + hw, dy - hh, dy + hh


def _frame(slug):
    f = AREAS[slug].get("frame", {})
    return dict(zoom=f.get("zoom", 1.0), dx=f.get("dx_km", 0) * 1000, dy=f.get("dy_km", 0) * 1000)


def _grid_slice(d, crop):
    res, x0, x1, y0, y1 = d["res"], *crop
    c0, c1 = int((x0 + d["half_w"]) / res), int(math.ceil((x1 + d["half_w"]) / res))
    r0, r1 = int((d["half_h"] - y1) / res), int(math.ceil((d["half_h"] - y0) / res))
    return slice(r0, r1), slice(c0, c1)


def _pick_summits(slug, d, crop, n=6, min_sep=0.14):
    from scipy.ndimage import maximum_filter
    x0, x1, y0, y1 = crop
    res, dem = d["res"], d["dem"]
    peak = maximum_filter(dem, size=max(3, int(80 / res)))
    out = []
    for p in names(slug):
        mx, my = (x1 - x0) * .04, (y1 - y0) * .04
        if not (x0 + mx < p["x"] < x1 - mx and y0 + my < p["y"] < y1 - my):
            continue
        r, c = int((d["half_h"] - p["y"]) / res), int((p["x"] + d["half_w"]) / res)
        h = p["ele"] or float(peak[r, c])
        out.append(dict(p, h=h))
    out.sort(key=lambda p: -p["h"])
    keep, sep = [], min_sep * (x1 - x0)
    for p in out:
        if all(math.hypot(p["x"] - q["x"], p["y"] - q["y"]) > sep for q in keep):
            keep.append(p)
        if len(keep) == n:
            break
    return keep


def _label(ax, x, y, name, h, th, size=7.2, dy=7, ha="left"):
    import matplotlib.patheffects as pe
    halo = [pe.withStroke(linewidth=2.6, foreground=th["panel"])]
    ax.plot(x, y, marker="^", ms=4.2, color=th["accent"], mec=th["panel"], mew=0.6, zorder=50)
    t = ax.annotate(f"{name}\n{h:.0f} m", (x, y), xytext=(5 if ha == "left" else -5, dy), textcoords="offset points",
                    fontsize=size, family=SANS, color=th["line"], ha=ha, va="bottom", zorder=51, linespacing=1.05)
    t.set_path_effects(halo)


# ---------------------------------------------------------------- drawing pieces

def draw_contours(ax, slug, th, crop, target=None, labels=True, summits=6, filled=False, weight=1.0):
    from scipy.ndimage import gaussian_filter
    d = load(slug)
    res = d["res"]
    rs, cs = _grid_slice(d, crop)
    sm = gaussian_filter(d["dem"], sigma=max(1.2, AREAS[slug].get("smooth_m", 14) / res))[rs, cs]
    width_km = (crop[1] - crop[0]) / 1000
    lo, hi = float(sm.min()), float(sm.max())
    step = _nice((hi - lo) / (target or (90 if width_km < 16 else 60)))
    levels = np.arange(max(step, math.ceil(lo / step) * step), hi, step)
    major = levels[np.isclose(np.mod(levels, step * 5), 0)]
    minor = np.setdiff1d(levels, major)
    ext = [crop[0], crop[1], crop[2], crop[3]]
    raw = d["dem"][rs, cs]
    sea = raw <= 0.5
    coast = None
    if sea.mean() > 0.002:  # coasts: no contours at sea, one softened coastline instead
        from scipy.ndimage import binary_dilation
        soft = gaussian_filter(sea.astype(float), sigma=max(3, 30 / res))
        coast = soft[::-1]
        sm = np.ma.masked_where(binary_dilation(sea, iterations=3) | (soft > 0.35), sm)
    z = sm[::-1]
    ax.set_facecolor(th["panel"])
    if filled and "fills" in th:
        f = th["fills"]
        lv = np.concatenate([[lo - 1], levels, [hi + 1]])
        ax.contourf(z, levels=lv, colors=[f[i % len(f)] for i in range(len(lv) - 1)], extent=ext, origin="lower")
    lw = (0.42 if width_km < 16 else 0.32) * weight
    ax.contour(z, levels=minor, colors=th["line"], linewidths=lw, alpha=0.78, extent=ext, origin="lower")
    if coast is not None:
        ax.contour(coast, levels=[0.5], colors=th["line"], linewidths=lw * 1.6, extent=ext, origin="lower")
    cmaj = ax.contour(z, levels=major, colors=th["line"], linewidths=lw * 2.3, extent=ext, origin="lower")
    if labels and len(major):
        txt = ax.clabel(cmaj, fmt=lambda v: f"{v:.0f}", fontsize=5.6, inline=True, inline_spacing=3)
        for t in txt:
            t.set_family(MONO)
    if summits:
        for p in _pick_summits(slug, d, crop, n=summits):
            _label(ax, p["x"], p["y"], p.get("name_en") or p["name"], p["h"], th,
                   ha="right" if p["x"] > crop[0] + (crop[1] - crop[0]) * 0.72 else "left")
    ax.set_xlim(crop[0], crop[1]); ax.set_ylim(crop[2], crop[3]); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible("frame" in th); sp.set_color(th.get("frame", th["line"])); sp.set_linewidth(0.8)
    return step


def draw_ridgelines(ax, slug, th, crop, rows=64, lift=15.0):
    from scipy.ndimage import gaussian_filter
    d = load(slug)
    rs, cs = _grid_slice(d, crop)
    z = gaussian_filter(d["dem"], 1.6)[rs, cs]
    h, w = z.shape
    lo, hi = float(z.min()), float(z.max())
    gap = 1.0 / (rows + lift)
    x = np.linspace(0, 1, w)
    ax.set_facecolor(th["panel"])
    for i, r in enumerate(np.linspace(0, h - 1, rows).astype(int)):
        base = 1 - lift * gap - i * gap
        y = base + (z[r] - lo) / (hi - lo) * lift * gap
        ax.fill_between(x, -1, y, color=th["panel"], zorder=2 * i, lw=0)
        ax.plot(x, y, color=th["line"], lw=0.85, zorder=2 * i + 1, solid_capstyle="round", solid_joinstyle="round")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1.0)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)


def skyline_data(slug, cols_n=2600, near_km=None, bands=7):
    """Per-column elevation angles of the horizon, cumulative by distance band, plus visible named summits."""
    from scipy.ndimage import map_coordinates, maximum_filter
    p, d = VIEWS[slug], load(slug)
    dem, res = d["dem"], d["res"]
    h, w = dem.shape
    eye = float(dem[h // 2, w // 2]) + p["lift_m"]
    offs = np.linspace(-p["fov"] / 2, p["fov"] / 2, cols_n)
    az = np.radians(p["azimuth"] + offs)
    reach = p["reach_km"] * 1000
    near = (near_km if near_km is not None else p.get("near_km", 1.2 if p.get("panorama") else 0.4)) * 1000
    dist = np.concatenate([np.arange(near, 3000, res / 2), np.arange(max(near, 3000), reach, res * 0.8)])
    X, Y = np.sin(az)[None] * dist[:, None], np.cos(az)[None] * dist[:, None]
    rr, cc = d["half_h"] / res - Y / res - .5, X / res + d["half_w"] / res - .5
    z = map_coordinates(dem, [rr, cc], order=1, mode="nearest")
    drop = dist[:, None] ** 2 * 0.87 / (2 * EARTH_R)
    ang = np.degrees(np.arctan2(z - drop - eye, dist[:, None]))
    sea_h = float(np.degrees(np.arctan2(-reach ** 2 * 0.87 / (2 * EARTH_R) - eye, reach)))
    ang = np.where(z <= 0.5, -90.0, ang)
    edges = np.geomspace(max(near, 600) * 2.2, reach, bands)
    layers = [(e / 1000, ang[dist <= e].max(axis=0)) for e in edges]
    # named summits that stand on the horizon (not hidden behind nearer ground)
    peak = maximum_filter(dem, size=max(3, int(90 / res)))
    seen = []
    for n in names(slug):
        dx, dy = n["x"], n["y"]
        dd = math.hypot(dx, dy)
        if dd < near + 300 or dd > reach:
            continue
        off = (math.degrees(math.atan2(dx, dy)) - p["azimuth"] + 540) % 360 - 180
        if abs(off) > p["fov"] / 2 * 0.97:
            continue
        r, c = int((d["half_h"] - dy) / res), int((dx + d["half_w"]) / res)
        hz = max(n["ele"] or 0, float(peak[r, c]))
        a = math.degrees(math.atan2(hz - dd * dd * 0.87 / (2 * EARTH_R) - eye, dd))
        j = int(np.argmin(np.abs(offs - off)))
        js = slice(max(0, j - 3), j + 4)
        occ = ang[dist < dd - 250, js].max() if (dist < dd - 250).any() else -90
        if a >= occ - 0.03:
            seen.append(dict(name=n.get("name_en") or n["name"], off=off, ang=a, dist=dd / 1000, h=hz))
    return dict(view=p, x=offs, layers=layers, eye=eye, summits=seen, sea=sea_h if (z <= 0.5).any() else None)


def draw_skyline(ax, sd, colours, labels=10, label_room=0.3, line=None, text=None, halo=None, floor=3):
    """Layered silhouettes, farthest palest. colours = (far, near) hex."""
    from matplotlib.colors import to_rgb
    far, near = np.array(to_rgb(colours[0])), np.array(to_rgb(colours[1]))
    x, layers = sd["x"], sd["layers"]
    top = max(a.max() for _, a in layers)
    land = [a[a > -89] for _, a in layers if (a > -89).any()]
    if floor == "skyline":  # crop to the outline itself: base of the far horizon, a little below
        far_line = layers[-1][1]
        b = np.percentile(far_line, 5)
        bottom = b - (top - b) * 0.35
    else:
        bottom = np.percentile(land[0], floor) if len(land) else top - 1
    if sd.get("sea") is not None:
        bottom = min(bottom, sd["sea"] - (top - sd["sea"]) * 0.08)
    span = top - bottom
    n = len(layers)
    if sd.get("sea") is not None:
        ax.fill_between(x, bottom - span, sd["sea"], color=far + (near - far) * 0.45, lw=0, zorder=-1)
    for i, (km, a) in enumerate(reversed(layers)):
        t = i / max(1, n - 1)
        c = far + (near - far) * t ** 1.35
        ax.fill_between(x, bottom - span, a, color=c, lw=0, zorder=i)
    ax.set_xlim(x[0], x[-1]); ax.set_ylim(bottom - span * 0.02, top + span * label_room)
    ax.axis("off")
    if labels and sd["summits"]:
        s = sorted(sd["summits"], key=lambda p: -p["h"])
        keep, sep = [], (x[-1] - x[0]) / 13
        for p in s:
            if all(abs(p["off"] - q["off"]) > sep for q in keep):
                keep.append(p)
            if len(keep) == labels:
                break
        keep.sort(key=lambda p: p["off"])
        ytxt = top + span * label_room * 0.22
        for k, p in enumerate(keep):
            yy = ytxt + (span * label_room * 0.38 if k % 2 else 0)
            ax.plot([p["off"], p["off"]], [p["ang"] + span * 0.012, yy - span * 0.012], color=line, lw=0.5, zorder=60)
            ax.text(p["off"], yy, f"{p['name']}\n{p['h']:.0f} m", ha="center", va="bottom", fontsize=6.8,
                    family=SANS, color=text, linespacing=1.05, zorder=61)


def _sky(ax, top, bottom):
    from matplotlib.colors import LinearSegmentedColormap
    cm = LinearSegmentedColormap.from_list("sky", [bottom, top])
    ax.imshow(np.linspace(0, 1, 256)[:, None], aspect="auto", cmap=cm, origin="lower",
              extent=[*ax.get_xlim(), *ax.get_ylim()], zorder=-10)


# ---------------------------------------------------------------- prints

def contours(slug, theme="paper", out=None, filled=None):
    th = THEMES[theme]
    p, d = AREAS[slug], load(slug)
    fig = _figure(th)
    crop = _crop(d, aspect=0.80 / 0.70 * 297 / 420, **_frame(slug))
    ax, box = _map_axes(fig, (0.09, 0.215, 0.82, 0.72), (crop[1] - crop[0]) / (crop[3] - crop[2]))
    step = draw_contours(ax, slug, th, crop, filled=theme == "bands" if filled is None else filled)
    _caption(fig, th, p["title"], _ll(p["lat"], p["lon"]),
             f"{p['summit_m']} m   ·   {p['region']}   ·   contours every {step:g} m", y=0.165)
    _credit(fig, th, SOURCE + "  ·  summits © OpenStreetMap contributors")
    return _save(fig, out or OUT_DIR / f"{slug}-contours-{theme}.png")


def ridgelines(slug, theme="paper", out=None, rows=None, lift=None):
    th = THEMES[theme]
    p, d = AREAS[slug], load(slug)
    fig = _figure(th)
    crop = _crop(d, aspect=1.0, **_frame(slug))
    wide = (crop[1] - crop[0]) > 16000
    rows = rows or (80 if wide else 64)
    lift = lift or (7 if wide else 15)
    ax = fig.add_axes([0.09, 0.25, 0.82, 0.67])
    draw_ridgelines(ax, slug, th, crop, rows=rows, lift=lift)
    _caption(fig, th, p["title"], _ll(p["lat"], p["lon"]),
             f"{p['summit_m']} m   ·   {p['region']}   ·   {rows} west–east profiles, north at the back", y=0.165)
    _credit(fig, th, SOURCE)
    return _save(fig, out or OUT_DIR / f"{slug}-ridgelines-{theme}.png")


def skyline(slug, theme="green", out=None):
    sky_top, sky_bottom, far, near = SKIES[theme]
    dark = theme == "night"
    th = dict(page=sky_bottom if not dark else "#0E151A", text="#E9E3D3" if dark else near,
              muted="#76858B" if dark else "#7D817C", panel=sky_bottom)
    p = VIEWS[slug]
    sd = skyline_data(slug)
    fig = _figure(th, 420, 297)
    ax = fig.add_axes([0.06, 0.25, 0.88, 0.68])
    draw_skyline(ax, sd, (far, near), line=th["muted"], text=th["text"])
    _sky(ax, sky_top, sky_bottom)
    _caption(fig, th, p["title"], f"{p['subtitle']}   ·   {_ll(p['lat'], p['lon'])}",
             f"eye {sd['eye']:.0f} m   ·   {p['fov']}° wide   ·   reaching {p['reach_km']} km", y=0.185, x=0.06, ha="left")
    _credit(fig, th, SOURCE + "  ·  summits © OpenStreetMap contributors  ·  earth curvature and refraction applied")
    return _save(fig, out or OUT_DIR / f"{slug}-skyline-{theme}.png")


POSTERS = {  # contour place -> (skyline that shows it, half-width of the strip in degrees or None for all)
    "cuillin": ("cuillin-from-elgol", None), "matterhorn": ("matterhorn-from-riffelsee", 10),
    "ben-nevis": ("ben-nevis-from-corpach", 24), "helvellyn": ("helvellyn-from-place-fell", 26),
    "cheviot": ("cheviot-from-simonside", None), "lake-district": ("lakes-from-orrest-head", None),
    "blencathra": ("blencathra-from-castlerigg", None),
}


def poster(slug, theme="paper", out=None):
    """Contour map above, the same mountain's skyline below, sharing one palette."""
    from matplotlib.colors import to_rgb
    th = THEMES[theme]
    p, d = AREAS[slug], load(slug)
    view, half = POSTERS[slug]
    fig = _figure(th)
    crop = _crop(d, aspect=1.0, **_frame(slug))
    ax, box = _map_axes(fig, (0.09, 0.40, 0.82, 0.54), 1.0)
    step = draw_contours(ax, slug, th, crop, filled=theme == "bands", summits=5)
    ax2 = fig.add_axes([box[0], 0.232, box[2], 0.15])
    sd = skyline_data(view, cols_n=1800)
    if half:
        keep = np.abs(sd["x"]) <= half
        sd = dict(sd, x=sd["x"][keep], layers=[(k, a[keep]) for k, a in sd["layers"]])
    page = np.array(to_rgb(th["page"]))
    ink = np.array(to_rgb(th["panel"] if th["panel"] != th["page"] else th["line"]))
    draw_skyline(ax2, sd, (page + (ink - page) * 0.2, ink), labels=0, label_room=0.08, floor=VIEWS[view].get("poster_floor", 3))
    _caption(fig, th, p["title"], _ll(p["lat"], p["lon"]),
             f"{p['summit_m']} m   ·   contours every {step:g} m   ·   skyline {VIEWS[view]['subtitle']}", y=0.185)
    _credit(fig, th, SOURCE + "  ·  summits © OpenStreetMap contributors")
    return _save(fig, out or OUT_DIR / f"{slug}-poster-{theme}.png")


def _save(fig, path: Path, dpi=110) -> Path:
    import matplotlib.pyplot as plt
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    print("wrote", path)
    return path


STYLES = {"contours": contours, "ridgelines": ridgelines, "skyline": skyline, "poster": poster}


WEB_PLACES = Path("web/peaks/places.json")


def web_places(path: Path = WEB_PLACES) -> Path:
    """The ready-made mountains for the web print maker, with their named summits bundled
    (so the common places need no Overpass call)."""
    def summits(slug, limit=160):
        ns = sorted(names(slug), key=lambda n: -(n["ele"] or 0))[:limit]
        out = [{"name": n["name"], "lat": round(n["lat"], 5), "lon": round(n["lon"], 5), "ele": n["ele"]} for n in ns]
        return out + [{"name": n["name"], "lat": round(n["lat"], 5), "lon": round(n["lon"], 5), "kind": "ridge"}
                      for n in names(slug, "ridge")]
    areas = []
    for a in PLACES["areas"]:
        view, crop = POSTERS.get(a["slug"], (None, None))
        # Hand-named ridges replace any OpenStreetMap ridge within 400 m of them.
        extra = [{**r, "kind": "ridge"} for r in a.get("ridges", [])]
        near = lambda n: any(abs(n["lat"] - r["lat"]) * 111320 < 400 and
                             abs(n["lon"] - r["lon"]) * 111320 * math.cos(math.radians(r["lat"])) < 400 for r in extra)
        named = [n for n in summits(a["slug"]) if not (n.get("kind") == "ridge" and near(n))]
        areas.append({**{k: v for k, v in a.items() if k != "ridges"}, "names": named + extra,
                      "poster_view": view, "poster_crop": crop})
    views = [{**v, "names": summits(v["slug"])} for v in PLACES["views"]]
    path.write_text(json.dumps({"areas": areas, "views": views}, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {path} ({path.stat().st_size // 1024} KB, {len(areas)} areas, {len(views)} views)")
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("slugs", nargs="*"); f.add_argument("--all", action="store_true")
    f.add_argument("--force", action="store_true", help="refetch files that already exist")
    r = sub.add_parser("render"); r.add_argument("slugs", nargs="*"); r.add_argument("--all", action="store_true")
    r.add_argument("--style", choices=list(STYLES)); r.add_argument("--theme")
    sub.add_parser("web", help="write web/peaks/places.json for the print maker")
    a = ap.parse_args()
    if a.cmd == "web":
        web_places()
        return
    every = list(AREAS) + list(VIEWS)
    if a.cmd == "fetch":
        for s in (every if a.all else a.slugs):
            if not (DEM_DIR / f"{s}.npz").exists() or a.force:
                fetch(s)
            if not (DEM_DIR / f"{s}.names.json").exists() or a.force:
                fetch_names(s)
        return
    slugs = [s for s in every if (DEM_DIR / f"{s}.npz").exists()] if a.all else a.slugs
    for s in slugs:
        styles = [a.style] if a.style else (["skyline"] if s in VIEWS else ["contours", "ridgelines"])
        for st in styles:
            STYLES[st](s, a.theme or ("green" if st == "skyline" else "paper"))


if __name__ == "__main__":
    main()
