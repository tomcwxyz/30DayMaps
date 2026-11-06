"""Drive the Peaks print maker in Chromium with offline stand-ins for the network.

Terrarium tiles are rebuilt from the elevation files in peaks/dem (fetched by the Peaks
workflow), and Overpass and Nominatim answers come from the bundled summit names. So the page
can be tested anywhere, including where AWS is unreachable.

    python web/peaks/test/harness.py shots OUTDIR          # screenshots of every style
"""
from __future__ import annotations

import glob
import io
import json
import math
import sys
import threading
from functools import lru_cache
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
WEB = ROOT / "web" / "peaks"
DEMS = []
for f in sorted(glob.glob(str(ROOT / "peaks" / "dem" / "*.npz"))):
    d = np.load(f)
    dd = dict(slug=Path(f).stem, dem=d["dem"].astype(np.float32), res=float(d["res"]), lat=float(d["lat"]), lon=float(d["lon"]),
              hw=float(d["half_w"]), hh=float(d["half_h"]))
    k = math.cos(math.radians(dd["lat"]))
    dd["box"] = (dd["lat"] - dd["hh"] / 111000, dd["lat"] + dd["hh"] / 111000, dd["lon"] - dd["hw"] / 111000 / k, dd["lon"] + dd["hw"] / 111000 / k)
    DEMS.append(dd)
DEMS.sort(key=lambda d: d["res"])   # finest first
NAMES = []
for f in glob.glob(str(ROOT / "peaks" / "dem" / "*.names.json")):
    NAMES += json.loads(Path(f).read_text())


@lru_cache(maxsize=4096)
def tile_png(z: int, x: int, y: int) -> bytes:
    n = 2 ** z
    px = (np.arange(256) + 0.5) / 256
    lon = (x + px) / n * 360 - 180
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (y + px) / n))))
    LON, LAT = np.meshgrid(lon, lat)
    h = np.zeros_like(LON, dtype=np.float32)
    filled = np.zeros_like(LON, dtype=bool)
    from pyproj import Transformer
    from scipy.ndimage import map_coordinates
    for d in DEMS:
        s_, n_, w_, e_ = d["box"]
        if lat.min() > n_ or lat.max() < s_ or lon.min() > e_ or lon.max() < w_:
            continue
        t = Transformer.from_crs("EPSG:4326", f"+proj=aeqd +lat_0={d['lat']} +lon_0={d['lon']} +datum=WGS84 +units=m", always_xy=True)
        X, Y = t.transform(LON, LAT)
        inside = (np.abs(X) < d["hw"] - d["res"]) & (np.abs(Y) < d["hh"] - d["res"]) & ~filled
        if not inside.any():
            continue
        rr = (d["hh"] - Y[inside]) / d["res"] - 0.5
        cc = (X[inside] + d["hw"]) / d["res"] - 0.5
        h[inside] = map_coordinates(np.nan_to_num(d["dem"], nan=0.0), [rr, cc], order=1, mode="nearest")
        filled |= inside
    v = np.clip(h, -32000, 30000) + 32768
    rgb = np.stack([np.floor(v / 256), np.floor(v % 256), np.floor((v % 1) * 256)], -1).astype(np.uint8)
    b = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(b, "PNG")
    return b.getvalue()


def overpass(body: str) -> dict:
    import re
    from urllib.parse import parse_qs
    q = parse_qs(body).get("data", [""])[0]
    s, w, n, e = map(float, re.search(r"\(([-\d.]+),([-\d.]+),([-\d.]+),([-\d.]+)\)", q).groups())
    seen, out = set(), []
    for p in NAMES:
        if s <= p["lat"] <= n and w <= p["lon"] <= e and p["osm"] not in seen:
            seen.add(p["osm"])
            tags = {"name": p["name"], "natural": "peak"}
            if p.get("ele") is not None:
                tags["ele"] = str(p["ele"])
            out.append({"type": "node", "id": p["osm"], "lat": p["lat"], "lon": p["lon"], "tags": tags})
    return {"elements": out}


class Quiet(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(WEB), **k)

    def log_message(self, *a):
        pass


def serve() -> str:
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_port}/"


def attach(page):
    """Route the page's network calls to the stand-ins."""
    import re

    def tiles(route):
        z, x, y = map(int, re.search(r"/(\d+)/(\d+)/(\d+)\.png", route.request.url).groups())
        route.fulfill(status=200, body=tile_png(z, x, y), headers={"Content-Type": "image/png", "Access-Control-Allow-Origin": "*"})

    def ovp(route):
        route.fulfill(status=200, body=json.dumps(overpass(route.request.post_data or "")), headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"})

    def nom(route):
        res = [{"lat": "54.4542", "lon": "-3.2116", "name": "Scafell Pike", "display_name": "Scafell Pike, Cumberland, England", "type": "peak", "category": "natural",
                "boundingbox": ["54.4492", "54.4592", "-3.2166", "-3.2066"]}]
        route.fulfill(status=200, body=json.dumps(res), headers={"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"})

    page.route(re.compile(r".*elevation-tiles-prod/terrarium/.*"), tiles)
    page.route(re.compile(r".*/api/interpreter.*"), ovp)
    page.route(re.compile(r".*nominatim\.openstreetmap\.org.*"), nom)


def wait_drawn(page, timeout=600000):
    page.wait_for_function("() => !document.getElementById('png').disabled && !document.getElementById('sheet').classList.contains('busy') && document.getElementById('status').textContent === ''", timeout=timeout)


def errors_of(page):
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.on("console", lambda m: m.type == "error" and errs.append(m.text))
    return errs


if __name__ == "__main__" and sys.argv[1:2] == ["shots"]:
    from playwright.sync_api import sync_playwright
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "peaks-shots")
    out.mkdir(parents=True, exist_ok=True)
    base = serve()
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1400, "height": 1000})
        errs = errors_of(page)
        attach(page)
        page.goto(base + "?place=helvellyn")
        wait_drawn(page)
        for style in ["poster", "contours", "ridgelines", "skyline", "panorama"]:
            page.click(f"#styles button[data-style={style}]")
            page.wait_for_timeout(300)
            wait_drawn(page)
            page.locator("#sheet").screenshot(path=str(out / f"helvellyn-{style}.png"))
            print(style, "ok", page.locator("#status").text_content())
        print("errors:", errs)
        b.close()


def suite(out: Path, offline: bool = True):
    """Every style and a spread of colours, a search, a GPX route, and both downloads.
    offline=False uses the real tile, Overpass and Nominatim services (as in CI)."""
    from playwright.sync_api import sync_playwright
    out.mkdir(parents=True, exist_ok=True)
    base = serve()
    shots = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        page = b.new_page(viewport={"width": 1400, "height": 1000}, accept_downloads=True)
        errs = errors_of(page)
        if offline:
            attach(page)

        def snap(name):
            page.wait_for_timeout(250); wait_drawn(page)
            page.locator("#sheet").screenshot(path=str(out / f"{name}.png")); shots.append(name)

        def style(s): page.click(f"#styles button[data-style={s}]")
        def theme(t): page.click(f"#themes button[data-theme={t}]")

        page.goto(base + "?place=cuillin")
        wait_drawn(page)
        for s, t in [("poster", "paper"), ("contours", "oxblood"), ("ridgelines", "navy"), ("skyline", "moss"), ("panorama", "night")]:
            theme(t); style(s); snap(f"cuillin-{s}-{t}")
        page.click("#presets button[data-slug=matterhorn]"); style("poster"); theme("navy"); snap("matterhorn-poster-navy")
        theme("bands"); style("contours"); snap("matterhorn-contours-bands")
        # search
        page.fill("#q", "Scafell Pike"); page.click("#find")
        page.click("#results button"); theme("paper"); style("poster"); snap("search-scafell-poster")
        # route
        page.set_input_files("#gpxFile", str(WEB / "test" / "helvellyn-round.gpx"))
        theme("paper"); style("poster"); snap("route-poster-paper")
        theme("moss"); style("contours"); snap("route-contours-moss")
        style("panorama"); theme("paper"); snap("route-panorama")
        # downloads
        style("poster")
        page.wait_for_timeout(300); wait_drawn(page)
        page.select_option("#dpi", "150")
        with page.expect_download(timeout=180000) as d:
            page.click("#png")
        png = out / d.value.suggested_filename; d.value.save_as(png)
        with page.expect_download(timeout=180000) as d:
            page.click("#svg")
        svg = out / d.value.suggested_filename; d.value.save_as(svg)
        print("downloads:", png.name, png.stat().st_size // 1024, "KB;", svg.name, svg.stat().st_size // 1024, "KB")
        print("errors:", errs)
        b.close()
    return shots


if __name__ == "__main__" and sys.argv[1:2] in (["suite"], ["live"]):
    o = Path(sys.argv[2])
    names = suite(o, offline=sys.argv[1] == "suite")
    if sys.argv[1] == "live":   # small JPEGs to commit
        for n in names:
            im = Image.open(o / f"{n}.png").convert("RGB")
            im.thumbnail((1400, 1400))
            im.save(o / f"{n}.jpg", quality=84)
            (o / f"{n}.png").unlink()
        for f in o.glob("*.svg"):
            f.unlink()
        for f in o.glob("*-A3.png"):
            f.unlink()
