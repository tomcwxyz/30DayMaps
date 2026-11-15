"""Draw a Peaks shop order again, with the same page code the customer used.

The print maker (web/peaks) draws in the browser, so the print job opens it in headless
Chromium with ?render=1, applies the order's recipe (and route, if any), waits for the
drawing, and takes the files the page makes: a PNG at print resolution, a small preview,
and a vector PDF printed from the page's own SVG.

    python -m maps.peaks_render RECIPE.json OUTDIR [--route ENCODED] [--kinds print,web,pdf]

Needs Playwright with Chromium (python -m playwright install --with-deps chromium).
Fetches elevation tiles and, for searched places, summit names from Overpass; in render
mode the page fails rather than drawing a print without its names.
"""
from __future__ import annotations

import argparse
import json
import math
import threading
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web" / "peaks"
MM_PER_INCH = 25.4
PREVIEW_LONG_PX = 1600
TIMEOUT_MS = 15 * 60 * 1000


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@contextmanager
def _serve():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=str(WEB)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}/"
    finally:
        srv.shutdown()


def _download(page, path: Path, kind: str, ppm: float | None = None) -> Path:
    with page.expect_download(timeout=TIMEOUT_MS) as d:
        page.evaluate("([k, p, n]) => PeaksApp.file(k, p, n)", [kind, ppm, path.name])
    d.value.save_as(path)
    return path


class TextCheckFailed(RuntimeError):
    """The browser doesn't draw text true at print resolution, so the print would be wrong."""


def check_text(page, ppm: float) -> None:
    """Draws test phrases as the print will and stops if letters or spaces come out wrong.
    On 9 November 2026 a print went out with thin letters and spaces missing; this catches that."""
    r = page.evaluate("p => PeaksApp.textCheck(p)", ppm)
    if not r["ok"]:
        bad = "; ".join(f"{x['font']}: width {x['ratio']}, gaps {x['gaps']} for {x['spaces']} spaces"
                        for x in r["results"] if not x["ok"])
        raise TextCheckFailed(f"text doesn't draw true at print resolution ({bad})")


CROP_PAD_MM = 3


def check_crops(png: Path, boxes: list[dict], size_mm: tuple[float, float], out: Path) -> list[Path]:
    """Full-resolution crops of the finished print for the owner to read before approving:
    the title block, the list of summits (if any) and a patch of map labels."""
    from PIL import Image
    im = Image.open(png)
    k = im.width / size_mm[0]
    pw, ph = size_mm

    def union(bs):
        return (min(b["x"] for b in bs), min(b["y"] for b in bs),
                max(b["x"] + b["w"] for b in bs), max(b["y"] + b["h"] for b in bs))

    regions = []
    plain = [b for b in boxes if not b["halo"]]
    if plain:
        title = max(plain, key=lambda b: b["size"])
        below = [b for b in plain if title["y"] - 1 <= b["y"] <= title["y"] + title["h"] * 3.2]
        regions.append(("title", union(below)))
        head = next((b for b in plain if b["s"].upper().endswith(", IN ORDER")), None)
        if head:
            rows = [b for b in plain if head["y"] <= b["y"] < title["y"] - 1]
            regions.append(("list", union(rows)))
    labels = [b for b in boxes if b["halo"]]
    if labels:
        mid = min(labels, key=lambda b: (b["x"] + b["w"] / 2 - pw / 2) ** 2 + (b["y"] - ph * 0.3) ** 2)
        cx, cy = mid["x"] + mid["w"] / 2, mid["y"] + mid["h"] / 2
        regions.append(("labels", (cx - 40, cy - 25, cx + 40, cy + 25)))
    files = []
    for name, (x0, y0, x1, y1) in regions:
        x0, y0 = max(0, x0 - CROP_PAD_MM), max(0, y0 - CROP_PAD_MM)
        x1, y1 = min(pw, x1 + CROP_PAD_MM), min(ph, y1 + CROP_PAD_MM)
        f = out / f"check-{name}.png"
        im.crop((round(x0 * k), round(y0 * k), round(x1 * k), round(y1 * k))).save(f)
        files.append(f)
    return files


def render(recipe: str, out: Path, kinds=("print", "web"), min_long_px: int | None = None,
           route: str | None = None, setup=None) -> dict[str, Path]:
    """Returns {"print": PNG, "web": preview PNG, "pdf": vector PDF, "check": [crop PNGs]} for the kinds asked.

    The PNG is 300 dpi at the sheet's size, or finer if min_long_px asks for more pixels; the
    text is checked at that resolution first. "check" crops the print PNG (so needs "print").
    setup(page) lets tests route the page's network calls to stand-ins.
    """
    from playwright.sync_api import sync_playwright
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, Path] = {}
    with _serve() as base, sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--js-flags=--max-old-space-size=8192"])
        try:
            page = browser.new_page(accept_downloads=True, viewport={"width": 1200, "height": 900})
            page.set_default_timeout(TIMEOUT_MS)
            if setup:
                setup(page)
            page.goto(base + "?render=1")
            page.evaluate("PeaksApp.ready")
            page.evaluate("([r, route]) => PeaksApp.apply(r, route)", [json.loads(recipe), route])
            pw_mm, ph_mm = page.evaluate("PeaksApp.size()")
            long_mm = max(pw_mm, ph_mm)
            if "print" in kinds:
                dpi = 300
                if min_long_px:
                    dpi = max(dpi, math.ceil(min_long_px / (long_mm / MM_PER_INCH)))
                check_text(page, dpi / MM_PER_INCH)
                files["print"] = _download(page, out / f"peaks-{dpi}dpi.png", "png", dpi / MM_PER_INCH)
                if "check" in kinds:
                    files["check"] = check_crops(files["print"], page.evaluate("PeaksApp.textBoxes()"),
                                                 (pw_mm, ph_mm), out)
            if "web" in kinds:
                files["web"] = _download(page, out / "peaks-web.png", "png", PREVIEW_LONG_PX / long_mm)
            if "pdf" in kinds:
                svg = _download(page, out / "peaks.svg", "svg")
                doc = browser.new_page()
                doc.set_default_timeout(TIMEOUT_MS)
                doc.set_content(f"<!doctype html><html><head><style>@page{{size:{pw_mm}mm {ph_mm}mm;margin:0}}"
                                f"html,body{{margin:0;padding:0}}svg{{display:block;width:{pw_mm}mm;height:{ph_mm}mm}}</style>"
                                f"</head><body>{svg.read_text(encoding='utf-8').split('?>', 1)[-1]}</body></html>")
                doc.evaluate("document.fonts.ready.then(() => true)")
                doc.pdf(path=str(out / "peaks.pdf"), width=f"{pw_mm}mm", height=f"{ph_mm}mm",
                        print_background=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
                files["pdf"] = out / "peaks.pdf"
        finally:
            browser.close()
    return {k: files[k] for k in kinds}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("recipe", help="recipe JSON file")
    p.add_argument("out", help="folder for the files")
    p.add_argument("--route", help="encoded route (from the order's route_* metadata)")
    p.add_argument("--kinds", default="print,web,pdf,check")
    a = p.parse_args(argv)
    files = render(Path(a.recipe).read_text(), Path(a.out), tuple(a.kinds.split(",")), route=a.route)
    for k, f in files.items():
        print(k, f)


if __name__ == "__main__":
    main()
