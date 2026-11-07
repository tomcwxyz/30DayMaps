"""Fetch Environment Agency LiDAR (Composite DTM 2 m, England, OGL) for a box in British
National Grid metres, for close views of ridges the 30 m worldwide data cannot show.

    python -m maps.peaks_lidar caps OUT.xml
    python -m maps.peaks_lidar fetch E0 N0 E1 N1 OUT.npz [--chunk 2000]

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


if __name__ == "__main__":
    if sys.argv[1] == "caps":
        open(sys.argv[2], "w").write(caps())
    else:
        e0, n0, e1, n1 = map(float, sys.argv[2:6])
        fetch(e0, n0, e1, n1, sys.argv[6])
