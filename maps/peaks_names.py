"""Summit and ridge names for the regions Peaks' ready-made places and rounds sit in.

The page asks Overpass for names whenever it draws; a print job insists on them, so a slow
Overpass stopped orders. This bakes the names once into web/peaks/names.json, which the page
reads first for any frame inside one of these regions.

    python -m maps.peaks_names        # needs network; run by the Peaks names workflow
"""
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "web" / "peaks" / "names.json"
SERVERS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
           "https://overpass.private.coffee/api/interpreter"]
# [south, west, north, east], generous enough for every ready-made view's reach
REGIONS = {
    "lake-district": [54.00, -3.85, 55.00, -2.40],
    "cheviot": [54.90, -2.90, 55.90, -1.30],
    "lochaber": [56.20, -5.90, 57.30, -3.20],
    "skye": [56.75, -7.10, 57.80, -5.40],
    "eryri": [52.30, -4.80, 53.45, -3.30],
    "mont-blanc-matterhorn": [45.30, 6.40, 46.30, 8.20],
    "arrochar-lomond": [55.95, -5.10, 56.30, -4.40],
    "arran": [55.20, -6.00, 56.05, -4.55],
    "cairngorms": [56.75, -4.10, 57.40, -2.90],
    "torridon-fisherfield": [57.30, -5.90, 58.00, -4.80],
    "assynt": [57.90, -5.50, 58.30, -4.90],
    "brecon-beacons": [51.55, -3.95, 52.20, -2.90],
    "bernese-oberland": [46.35, 7.60, 46.80, 8.30],
    "ecrins": [44.75, 6.10, 45.10, 6.60],
    "bernina": [46.25, 9.70, 46.55, 10.15],
    "dolomites": [46.30, 11.55, 46.75, 12.45],
    "glockner": [46.95, 12.50, 47.25, 12.90],
    "wetterstein": [46.85, 10.15, 47.98, 11.80],
    "khumbu": [27.50, 86.30, 28.50, 87.50],
}


def latin(t):
    return bool(t) and all(ord(ch) < 0x250 or ch in "’‘·" for ch in t)


def query(box):
    bb = ",".join(f"{v:.3f}" for v in box)
    q = (f'[out:json][timeout:180];(node["natural"~"^(peak|hill|volcano)$"]["name"]({bb});'
         f'way["natural"~"^(arete|ridge)$"]["name"]({bb}););out center;')
    last = None
    for attempt in range(3):
        for url in SERVERS:
            try:
                req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(),
                                             headers={"User-Agent": "peaks-names/1 (peaks.tomcw.xyz)"})
                with urllib.request.urlopen(req, timeout=240) as r:
                    return json.load(r)["elements"]
            except Exception as e:  # try the next server
                last = e
        time.sleep(20 * (attempt + 1))
    raise RuntimeError(f"Overpass failed for {bb}: {last}")


def clean(els):
    """Same choices as summits() in lib/terrain.js: [name, lat, lon, ele or null, ridge 0/1]."""
    out = []
    for e in els:
        tags = e.get("tags", {})
        name = tags.get("name") if latin(tags.get("name")) else tags.get("name:en")
        if not name or not latin(name):
            continue
        if e["type"] == "way":
            c = e.get("center")
            if c:
                out.append([name, round(c["lat"], 5), round(c["lon"], 5), None, 1])
            continue
        try:
            ele = float("".join(ch for ch in str(tags.get("ele", "")) if ch.isdigit() or ch in ".-") or "x")
        except ValueError:
            ele = None
        out.append([name, round(e["lat"], 5), round(e["lon"], 5), ele, 0])
    return out


def main():
    items, seen = [], set()
    for slug, box in REGIONS.items():
        got = clean(query(box))
        for it in got:
            k = (it[0], it[1], it[2])
            if k not in seen:
                seen.add(k); items.append(it)
        print(f"{slug}: {len(got)} names")
        time.sleep(5)
    OUT.write_text(json.dumps({"v": 1, "regions": list(REGIONS.values()), "items": items},
                              ensure_ascii=False, separators=(",", ":")))
    print(f"{len(items)} names → {OUT}")


if __name__ == "__main__":
    main()
