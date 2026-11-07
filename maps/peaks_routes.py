"""Build ready-made routes for Peaks: snap named summits to OpenStreetMap, then route
each leg along real paths with BRouter (hiking-mountain profile), and write a GPX.

    python -m maps.peaks_routes maps/peak_routes.json web/peaks/routes [SLUG ...]

SPEC: {slug: {"name": ..., "points": [[name, lat, lon, kind], ...]}} where kind is "peak"
(snap to the OSM summit of that name within 1.5 km) or "via" (use as given).
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import requests

UA = {"User-Agent": "30daymaps-peaks/1.0 (route builder)"}
OVERPASS = "https://overpass-api.de/api/interpreter"
BROUTER = "https://brouter.de/brouter"


def dist(a, b):
    R = 6371008.8
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def peaks_near(points):
    lats = [p[1] for p in points]; lons = [p[2] for p in points]
    bbox = f"{min(lats) - 0.03},{min(lons) - 0.04},{max(lats) + 0.03},{max(lons) + 0.04}"
    q = f'[out:json][timeout:120];(node["natural"~"peak|hill"]["name"]({bbox}););out;'
    for attempt in range(4):
        r = requests.post(OVERPASS, data={"data": q}, headers=UA, timeout=180)
        if r.ok:
            return [(e["tags"]["name"], e["lat"], e["lon"], e["tags"].get("ele")) for e in r.json()["elements"]]
        time.sleep(10 * (attempt + 1))
    raise SystemExit(f"Overpass failed: {r.status_code}")


def norm(s):
    return "".join(ch for ch in s.lower().replace("’", "'") if ch.isalnum())


def snap(points, osm):
    out = []
    for name, lat, lon, kind in points:
        if kind != "peak":
            out.append((name, lat, lon, kind, None)); continue
        best = None
        for n, a, b, ele in osm:
            if norm(n) == norm(name) or norm(name) in norm(n) or norm(n) in norm(name):
                d = dist((lat, lon), (a, b))
                if d < 1500 and (best is None or d < best[0]):
                    best = (d, a, b, ele, n)
        if best:
            print(f"  {name:22s} -> {best[4]} {best[0]:.0f} m away", flush=True)
            out.append((name, best[1], best[2], kind, best[3]))
        else:
            print(f"  {name:22s} -> not in OSM, using the hint", flush=True)
            out.append((name, lat, lon, kind, None))
    return out


def leg(a, b, profile="hiking-mountain"):
    params = {"lonlats": f"{a[2]},{a[1]}|{b[2]},{b[1]}", "profile": profile, "alternativeidx": 0, "format": "geojson"}
    for attempt in range(5):
        r = requests.get(BROUTER, params=params, headers=UA, timeout=120)
        if r.ok and r.text.startswith("{"):
            coords = r.json()["features"][0]["geometry"]["coordinates"]
            return [(c[1], c[0], c[2] if len(c) > 2 else None) for c in coords]
        print("   retry", r.status_code, r.text[:200], flush=True)
        time.sleep(5 * (attempt + 1))
    raise SystemExit(f"BRouter failed {a[0]} -> {b[0]}")


def gpx(name, track, wpts):
    pts = "\n".join(f'<trkpt lat="{la:.6f}" lon="{lo:.6f}">' + (f"<ele>{e:.1f}</ele>" if e is not None else "") + "</trkpt>" for la, lo, e in track)
    w = "\n".join(f'<wpt lat="{p[1]:.6f}" lon="{p[2]:.6f}"><name>{p[0]}</name></wpt>' for p in wpts if p[3] == "peak")
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="30daymaps peaks_routes" xmlns="http://www.topografix.com/GPX/1/1">\n'
            f"<metadata><name>{name}</name><desc>Summits from OpenStreetMap; legs routed on OpenStreetMap paths by BRouter.</desc></metadata>\n"
            f"{w}\n<trk><name>{name}</name><trkseg>\n{pts}\n</trkseg></trk>\n</gpx>\n")


def build(slug, spec, out: Path):
    print(slug, flush=True)
    pts = spec["points"]
    osm = peaks_near(pts)
    snapped = snap(pts, osm)
    track = []
    km = 0
    for a, b in zip(snapped, snapped[1:]):
        seg = leg(a, b)
        if track and seg and track[-1][:2] == seg[0][:2]:
            seg = seg[1:]
        track += seg
        d = sum(dist(p[:2], q[:2]) for p, q in zip(seg, seg[1:])) / 1000
        km += d
        print(f"   {a[0]} -> {b[0]}: {d:.1f} km", flush=True)
        time.sleep(1)
    up = sum(max(0, (q[2] or 0) - (p[2] or 0)) for p, q in zip(track, track[1:]) if p[2] is not None and q[2] is not None)
    (out / f"{slug}.gpx").write_text(gpx(spec["name"], track, snapped))
    summary = {"name": spec["name"], "km": round(km, 1), "ascent_m": round(up), "points": len(track),
               "summits": [{"name": p[0], "lat": p[1], "lon": p[2], "ele": p[4]} for p in snapped if p[3] == "peak"]}
    (out / f"{slug}.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    print(f"  {slug}: {km:.1f} km, {up:.0f} m up, {len(track)} points", flush=True)


if __name__ == "__main__":
    spec = json.loads(Path(sys.argv[1]).read_text())
    out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    only = sys.argv[3:] or [s for s in spec if not (out / f"{s}.gpx").exists() or spec[s].get("rebuild")]
    for slug, s in spec.items():
        if not only or slug in only:
            build(slug, s, out)
