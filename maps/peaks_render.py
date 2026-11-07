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


def render(recipe: str, out: Path, kinds=("print", "web"), min_long_px: int | None = None,
           route: str | None = None, setup=None) -> dict[str, Path]:
    """Returns {"print": PNG, "web": preview PNG, "pdf": vector PDF} for the kinds asked.

    The PNG is 300 dpi at the sheet's size, or finer if min_long_px asks for more pixels.
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
                files["print"] = _download(page, out / f"peaks-{dpi}dpi.png", "png", dpi / MM_PER_INCH)
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
    p.add_argument("--kinds", default="print,web,pdf")
    a = p.parse_args(argv)
    files = render(Path(a.recipe).read_text(), Path(a.out), tuple(a.kinds.split(",")), route=a.route)
    for k, f in files.items():
        print(k, f)


if __name__ == "__main__":
    main()
