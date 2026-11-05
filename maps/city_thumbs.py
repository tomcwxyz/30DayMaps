"""Draw gallery thumbnails for the prepared footprint cities.

    python -m maps.city_thumbs            every city in web/footprints/cities/index.json
    python -m maps.city_thumbs paris      just these

Reads each city's pack (see maps/footprint_packs.py) and writes <slug>.jpg beside it:
buildings only, in the page's default paper colours, at the shape of a portrait sheet.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MPath

from maps import footprint_packs

DIR = Path(__file__).resolve().parent.parent / "web" / "footprints" / "cities"
INK, PAPER = "#1E353B", "#F7F6F0"
SIZE_PX = (300, 390)  # width, height: the gallery shows 10:13 cards


def compound_path(rings) -> MPath:
    verts, codes = [], []
    for r in rings:
        if len(r) < 3:
            continue
        verts.extend(r)
        verts.append(r[0])
        codes.extend([MPath.MOVETO] + [MPath.LINETO] * (len(r) - 1) + [MPath.CLOSEPOLY])
    return MPath(np.asarray(verts, dtype=float), codes)


def thumbnail(pack_file: Path, out: Path) -> Path:
    header, rings = footprint_packs.read(pack_file)
    w = header["w"]
    h = w * SIZE_PX[1] / SIZE_PX[0]
    dpi = 100
    fig = plt.figure(figsize=(SIZE_PX[0] / dpi, SIZE_PX[1] / dpi), dpi=dpi, facecolor=PAPER)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_facecolor(PAPER)
    ax.axis("off")
    ax.add_patch(PathPatch(compound_path(rings), facecolor=INK, edgecolor="none", lw=0))
    ax.set_xlim(-w / 2, w / 2)
    ax.set_ylim(-h / 2, h / 2)
    fig.savefig(out, dpi=dpi, facecolor=PAPER, pil_kwargs={"quality": 82, "optimize": True})
    plt.close(fig)
    return out


def main(argv=None):
    only = set(argv if argv is not None else sys.argv[1:])
    index = json.loads((DIR / "index.json").read_text())
    for c in index["cities"]:
        if only and c["slug"] not in only:
            continue
        out = thumbnail(DIR / f"{c['slug']}.fpk.gz", DIR / f"{c['slug']}.jpg")
        print(f"{c['slug']}: {out.stat().st_size // 1024} KB thumbnail")


if __name__ == "__main__":
    main()
