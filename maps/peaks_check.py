"""Check that each ready-made mountain is where peak_places.json says it is.

For every area with fetched data (peaks/dem), compares the place's centre and summit height
with OpenStreetMap's named summits and the elevation grid, and flags anything that looks off:
a centre far from the named top it was meant to sit on, or a summit_m the terrain disagrees with.

    python -m maps.peaks_check            # prints a table; also writes it to the Actions summary
"""
import json
import math
import os
from pathlib import Path

import numpy as np

from maps.peaks import AREAS, DEM_DIR, VIEWS


def km(la1, lo1, la2, lo2):
    return math.hypot((la2 - la1) * 111.32, (lo2 - lo1) * 111.32 * math.cos(math.radians(la1)))


def check_area(slug, a):
    names_f, dem_f = DEM_DIR / f"{slug}.names.json", DEM_DIR / f"{slug}.npz"
    if not names_f.exists() or not dem_f.exists():
        return None
    peaks = [n for n in json.loads(names_f.read_text()) if n.get("kind", "peak") == "peak"]
    d = np.load(dem_f)
    dem_max = float(np.nanmax(d["dem"]))
    # The named summit closest in height to summit_m, within half the frame: the top this place is about.
    half = a["width_km"] / 2
    near = [p for p in peaks if km(a["lat"], a["lon"], p["lat"], p["lon"]) <= half]
    top = min(near, key=lambda p: abs((p["ele"] or -1e4) - a["summit_m"])) if near else None
    row = {"slug": slug, "summit_m": a["summit_m"], "dem_max": round(dem_max)}
    if top:
        row.update(top=top["name"], top_ele=top["ele"], top_lat=round(top["lat"], 5), top_lon=round(top["lon"], 5),
                   off_km=round(km(a["lat"], a["lon"], top["lat"], top["lon"]), 2))
    flags = []
    if not top or top["ele"] is None or abs(top["ele"] - a["summit_m"]) > 25:
        flags.append("no named summit near summit_m")
    if abs(dem_max - a["summit_m"]) > 60:
        flags.append(f"terrain top {dem_max:.0f} m")
    row["flags"] = "; ".join(flags)
    return row


def check_view(slug, v):
    dem_f = DEM_DIR / f"{slug}.npz"
    if not dem_f.exists():
        return None
    d = np.load(dem_f)
    z = d["dem"]
    h, w = z.shape
    ground = float(z[h // 2, w // 2])
    return {"slug": slug, "ground_m": round(ground), "flags": "viewpoint in water or below sea" if ground <= 0 else ""}


def main():
    rows = [r for r in (check_area(s, a) for s, a in AREAS.items()) if r]
    vrows = [r for r in (check_view(s, v) for s, v in VIEWS.items()) if r]
    lines = ["| place | summit_m | terrain top | named summit | its height | centre off by | flags |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['slug']} | {r['summit_m']} | {r['dem_max']} | {r.get('top', '')} ({r.get('top_lat', '')}, {r.get('top_lon', '')}) | "
                     f"{r.get('top_ele', '')} | {r.get('off_km', '')} km | {r['flags']} |")
    lines += ["", "| view | ground at viewpoint | flags |", "|---|---|---|"]
    lines += [f"| {r['slug']} | {r['ground_m']} m | {r['flags']} |" for r in vrows]
    text = "\n".join(lines)
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("## Ready-made places against OpenStreetMap\n\n" + text + "\n")
    Path("peaks/check.json").write_text(json.dumps({"areas": rows, "views": vrows}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
