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

THEMES = {  # ink, paper, muted, accent
    "paper": ("#1E2B2F", "#F4F1E8", "#8C968F", "#B4543A"),
    "night": ("#E9E3D3", "#141E24", "#6E7F86", "#D99A5B"),
    "blue": ("#EEF3F5", "#1F4560", "#93AFC1", "#F2C14E"),
    "ink": ("#111111", "#FFFFFF", "#8A8A8A", "#C0392B"),
    "moss": ("#E8E6D1", "#2F3B2A", "#8E9878", "#D9C27A"),
}


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


def load(slug: str) -> dict:
    d = np.load(DEM_DIR / f"{slug}.npz")
    return {k: (d[k] if d[k].ndim else d[k].item()) for k in d.files}


# ---------------------------------------------------------------- layout

def _page(theme: str, size=(11.69, 16.54)):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ink, paper, muted, accent = THEMES[theme]
    fig = plt.figure(figsize=size, facecolor=paper)
    return fig, (ink, paper, muted, accent)


def _caption(fig, cols, title, lines, credit, top=0.135):
    ink, paper, muted, accent = cols
    fig.text(0.08, top, title, color=ink, fontsize=40, weight="bold", va="top")
    fig.text(0.08, top - 0.042, "   ·   ".join(lines), color=muted, fontsize=13, va="top")
    fig.text(0.08, 0.03, credit, color=muted, fontsize=7.5, va="bottom")


def _dms(lat: float, lon: float) -> str:
    def f(v, pos, neg):
        a = abs(v); d = int(a); m = (a - d) * 60
        return f"{d}°{m:04.1f}′{pos if v >= 0 else neg}"
    return f"{f(lat, 'N', 'S')}  {f(lon, 'E', 'W')}"


def _nice(step: float) -> float:
    for s in (5, 10, 20, 25, 50, 100, 200, 250, 500):
        if step <= s:
            return s
    return 1000


# ---------------------------------------------------------------- styles

def contours(slug: str, theme="paper", out: Path | None = None, lines=70):
    """Pure contour lines, index contour every fifth, summit marked."""
    from scipy.ndimage import gaussian_filter
    p, d = AREAS[slug], load(slug)
    dem, res = d["dem"], d["res"]
    dem = np.where(np.isnan(dem), np.nanmin(dem), dem)
    sm = gaussian_filter(dem, sigma=max(1.0, 18 / res))
    lo, hi = float(sm.min()), float(sm.max())
    step = _nice((hi - lo) / lines)
    levels = np.arange(math.ceil(lo / step) * step, hi, step)
    major = levels[(np.round(levels / step) % 5) == 0]
    minor = np.setdiff1d(levels, major)

    fig, cols = _page(theme)
    ink, paper, muted, accent = cols
    ax = fig.add_axes([0.08, 0.17, 0.84, 0.77])
    ax.set_facecolor(paper)
    h, w = dem.shape
    ext = [-d["half_w"], d["half_w"], -d["half_h"], d["half_h"]]
    ax.contour(sm[::-1], levels=minor, colors=ink, linewidths=0.35, alpha=0.55, extent=ext)
    ax.contour(sm[::-1], levels=major, colors=ink, linewidths=0.9, extent=ext)
    # summit: highest cell near centre
    cy, cx = np.unravel_index(np.argmax(dem), dem.shape)
    sx, sy = ext[0] + (cx + .5) * res, ext[3] - (cy + .5) * res
    ax.plot(sx, sy, marker="^", ms=7, color=accent, mec=paper, mew=0.8)
    ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3]); ax.set_aspect("equal")
    ax.axis("off")
    _caption(fig, cols, p["title"],
             [p["region"], f"{p.get('summit_m') or int(dem.max())} m", _dms(p["lat"], p["lon"]),
              f"contours every {step:g} m"],
             SOURCE + " · north up")
    return _save(fig, out or OUT_DIR / f"{slug}-contours-{theme}.png")


def ridgelines(slug: str, theme="paper", out: Path | None = None, rows=90, exaggerate=1.0):
    """Stacked east–west elevation profiles, each hiding those behind it."""
    from scipy.ndimage import gaussian_filter
    p, d = AREAS[slug], load(slug)
    dem = d["dem"]
    dem = np.where(np.isnan(dem), np.nanmin(dem), dem)
    dem = gaussian_filter(dem, 1.0)
    h, w = dem.shape
    ys = np.linspace(0, h - 1, rows).astype(int)
    lo, hi = float(dem.min()), float(dem.max())
    # vertical scale: the highest point rises ~ 7 row-gaps above its baseline
    gap = 1.0 / rows
    scale = 7 * gap / (hi - lo) * exaggerate
    fig, cols = _page(theme)
    ink, paper, muted, accent = cols
    ax = fig.add_axes([0.08, 0.17, 0.84, 0.77])
    ax.set_facecolor(paper)
    x = np.linspace(0, 1, w)
    for i, r in enumerate(ys):  # north (back) first
        base = 1 - (i + 1) * gap * 0.92
        y = base + (dem[r] - lo) * scale
        ax.fill_between(x, 0, y, color=paper, zorder=i * 2, lw=0)
        ax.plot(x, y, color=ink, lw=0.7, zorder=i * 2 + 1, solid_capstyle="round")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1.0); ax.axis("off")
    _caption(fig, cols, p["title"],
             [p["region"], f"{p.get('summit_m') or int(hi)} m", _dms(p["lat"], p["lon"]),
              f"{rows} profiles, {p['width_km']} km across"],
             SOURCE + " · profiles run west–east, north at the back")
    return _save(fig, out or OUT_DIR / f"{slug}-ridgelines-{theme}.png")


def _skyline_angles(slug: str, cols_n=2400, bands=(1.5, 3, 5, 8, 12, 18, 25, 40)):
    """Elevation angle of the skyline for each column, per distance band (cumulative)."""
    from scipy.ndimage import map_coordinates
    p, d = VIEWS[slug], load(slug)
    dem, res = d["dem"], d["res"]
    dem = np.where(np.isnan(dem), np.nanmin(dem), dem)
    h, w = dem.shape
    eye = dem[h // 2, w // 2] + p["lift_m"]
    az = np.radians(p["azimuth"] + np.linspace(-p["fov"] / 2, p["fov"] / 2, cols_n))
    reach = p["reach_km"] * 1000
    dist = np.concatenate([np.arange(60, 2000, res / 2), np.arange(2000, reach, res)])
    X = np.sin(az)[None, :] * dist[:, None]
    Y = np.cos(az)[None, :] * dist[:, None]
    rr, cc = d["half_h"] / res - Y / res - .5, X / res + d["half_w"] / res - .5
    z = map_coordinates(dem, [rr, cc], order=1, mode="nearest")
    drop = dist[:, None] ** 2 * (1 - 0.13) / (2 * EARTH_R)  # curvature with refraction
    ang = np.degrees(np.arctan2(z - drop - eye, dist[:, None]))
    out = []
    for b in bands:
        m = dist <= b * 1000
        if m.any():
            out.append((b, ang[m].max(axis=0)))
    return p, out, eye


def skyline(slug: str, theme="paper", out: Path | None = None):
    """Layered silhouettes from a real viewpoint: far ridges pale, near ridges dark."""
    from matplotlib.colors import to_rgb
    p, layers, eye = _skyline_angles(slug)
    fig, cols = _page(theme, size=(16.54, 11.69))
    ink, paper, muted, accent = cols
    ax = fig.add_axes([0.06, 0.24, 0.88, 0.68])
    ax.set_facecolor(paper)
    n = len(layers)
    x = np.linspace(-p["fov"] / 2, p["fov"] / 2, len(layers[0][1]))
    allang = np.concatenate([a for _, a in layers])
    top, bottom = np.max(allang), np.percentile(layers[0][1], 2)
    pad = (top - bottom)
    ink_c, paper_c = np.array(to_rgb(ink)), np.array(to_rgb(paper))
    for i, (b, a) in enumerate(reversed(layers)):  # farthest first
        t = (i + 1) / n
        c = paper_c + (ink_c - paper_c) * (0.12 + 0.88 * t ** 1.6)
        ax.fill_between(x, bottom - pad, a, color=c, lw=0)
    ax.set_xlim(x[0], x[-1]); ax.set_ylim(bottom - pad * 0.05, top + pad * 0.9)
    ax.axis("off")
    fig.text(0.06, 0.17, p["title"], color=ink, fontsize=40, weight="bold", va="top")
    fig.text(0.06, 0.115, f"{p['subtitle']}   ·   {_dms(p['lat'], p['lon'])}   ·   eye {eye:.0f} m",
             color=muted, fontsize=13, va="top")
    fig.text(0.06, 0.04, SOURCE + f" · {p['fov']}° field of view · earth curvature and refraction applied",
             color=muted, fontsize=7.5)
    return _save(fig, out or OUT_DIR / f"{slug}-skyline-{theme}.png")


def _save(fig, path: Path, dpi=110) -> Path:
    import matplotlib.pyplot as plt
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    print("wrote", path)
    return path


STYLES = {"contours": contours, "ridgelines": ridgelines, "skyline": skyline}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("slugs", nargs="*"); f.add_argument("--all", action="store_true")
    r = sub.add_parser("render"); r.add_argument("slugs", nargs="*"); r.add_argument("--all", action="store_true")
    r.add_argument("--style", choices=list(STYLES)); r.add_argument("--theme", default="paper", choices=list(THEMES))
    a = ap.parse_args()
    every = list(AREAS) + list(VIEWS)
    if a.cmd == "fetch":
        for s in (every if a.all else a.slugs):
            fetch(s)
        return
    slugs = [s for s in every if (DEM_DIR / f"{s}.npz").exists()] if a.all else a.slugs
    for s in slugs:
        styles = [a.style] if a.style else (["skyline"] if s in VIEWS else ["contours", "ridgelines"])
        for st in styles:
            STYLES[st](s, a.theme)


if __name__ == "__main__":
    main()
