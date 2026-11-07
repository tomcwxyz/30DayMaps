"""Fetch Environment Agency LiDAR (Composite DTM 2 m, England, OGL) for a box in British
National Grid metres, for close views of ridges the 30 m worldwide data cannot show.

    python -m maps.peaks_lidar caps OUT.xml
    python -m maps.peaks_lidar fetch E0 N0 E1 N1 OUT.npz
    python -m maps.peaks_lidar pack LIDAR.npz LAT LON HALF_W HALF_H RES OUT.png

pack resamples onto the print maker's own local grid (north up, metres from LAT, LON, the same
flat-earth sums as lib/terrain.js) and writes a Terrarium-encoded PNG the page reads like a tile.

The npz holds dem (rows north to south, metres, nan where no data), res, e0, n1 (top-left corner).
"""
from __future__ import annotations

import io
import re
import sys
import time

import numpy as np
import requests

BASE = "https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-2m/wcs"
UA = {"User-Agent": "30daymaps-peaks/1.0"}


def caps() -> str:
    r = requests.get(BASE, params={"service": "WCS", "request": "GetCapabilities", "version": "2.0.1"}, headers=UA, timeout=120)
    r.raise_for_status()
    return r.text


def coverage_id(xml: str) -> str:
    ids = re.findall(r"<(?:wcs:)?CoverageId>([^<]+)</", xml)
    if not ids:
        raise SystemExit("no CoverageId in capabilities")
    return ids[0]


def chunk(cov: str, e0, n0, e1, n1):
    import rasterio
    params = [("service", "WCS"), ("request", "GetCoverage"), ("version", "2.0.1"), ("coverageId", cov),
              ("format", "image/tiff"), ("subset", f"E({e0},{e1})"), ("subset", f"N({n0},{n1})")]
    for attempt in range(4):
        r = requests.get(BASE, params=params, headers=UA, timeout=300)
        if r.ok and r.content[:2] in (b"II", b"MM"):
            break
        print("retry", r.status_code, r.text[:300], file=sys.stderr)
        time.sleep(5 * (attempt + 1))
    else:
        raise SystemExit(f"GetCoverage failed for {e0},{n0}")
    with rasterio.open(io.BytesIO(r.content)) as src:
        a = src.read(1).astype(np.float32)
        nod = src.nodata
        t = src.transform
    if nod is not None:
        a[a == nod] = np.nan
    a[a < -100] = np.nan
    return a, t


def fetch(e0, n0, e1, n1, out, step=2000):
    cov = coverage_id(caps())
    print("coverage", cov)
    res = 2.0
    W, H = int((e1 - e0) / res), int((n1 - n0) / res)
    dem = np.full((H, W), np.nan, np.float32)
    for ce in range(int(e0), int(e1), step):
        for cn in range(int(n0), int(n1), step):
            a, t = chunk(cov, ce, cn, min(ce + step, e1), min(cn + step, n1))
            c0 = int(round((t.c - e0) / res)); r0 = int(round((n1 - t.f) / res))
            h, w = a.shape
            rr0, cc0 = max(0, r0), max(0, c0)
            rr1, cc1 = min(H, r0 + h), min(W, c0 + w)
            dem[rr0:rr1, cc0:cc1] = a[rr0 - r0:rr1 - r0, cc0 - c0:cc1 - c0]
            print("chunk", ce, cn, a.shape, t.a, np.nanmin(a), np.nanmax(a), flush=True)
    np.savez_compressed(out, dem=dem, res=res, e0=e0, n1=n1)
    print("saved", out, dem.shape, np.nanmax(dem), "nan", int(np.isnan(dem).sum()))


R = 6371008.8


def pack(src, lat, lon, half_w, half_h, res, out):
    from PIL import Image
    from pyproj import Transformer
    from scipy.ndimage import map_coordinates
    d = np.load(src)
    dem, r0, e0, n1 = d["dem"], float(d["res"]), float(d["e0"]), float(d["n1"])
    w, h = int(round(2 * half_w / res)), int(round(2 * half_h / res))
    x = -half_w + (np.arange(w) + 0.5) * res
    y = half_h - (np.arange(h) + 0.5) * res
    X, Y = np.meshgrid(x, y)
    la = lat + np.degrees(Y / R)
    lo = lon + np.degrees(X / (R * np.cos(np.radians(la))))
    E, N = Transformer.from_crs(4326, 27700, always_xy=True).transform(lo, la)
    z = map_coordinates(np.nan_to_num(dem, nan=-1), [(n1 - N) / r0 - 0.5, (E - e0) / r0 - 0.5], order=1, mode="nearest")
    if (z < 0).any():
        raise SystemExit(f"{int((z < 0).sum())} cells outside the LiDAR box")
    v = (np.round((z + 32768) * 8) * 32).astype(np.uint32)   # eighth-metre steps: plenty, and they compress
    rgb = np.stack([(v >> 16) & 255, (v >> 8) & 255, v & 255], -1).astype(np.uint8)
    Image.fromarray(rgb, "RGB").save(out, optimize=True)
    print("packed", out, (w, h), round(float(z.min()), 1), round(float(z.max()), 1))


if __name__ == "__main__":
    if sys.argv[1] == "caps":
        open(sys.argv[2], "w").write(caps())
    elif sys.argv[1] == "pack":
        a = sys.argv[2:]
        pack(a[0], *map(float, a[1:6]), a[6])
    else:
        e0, n0, e1, n1 = map(float, sys.argv[2:6])
        fetch(e0, n0, e1, n1, sys.argv[6])
