"""Temporary: render the Tea Round on the GitHub runner exactly like a print order, and save crops."""
import sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, ".")
from maps.peaks_render import _serve, _download
from playwright.sync_api import sync_playwright

out = Path("diag/out"); out.mkdir(parents=True, exist_ok=True)
with _serve() as base, sync_playwright() as pw:
    b = pw.chromium.launch(args=["--js-flags=--max-old-space-size=8192"])
    print("chromium", b.version)
    p = b.new_page(accept_downloads=True, viewport={"width": 1200, "height": 900})
    p.set_default_timeout(15 * 60 * 1000)
    p.goto(base + "?render=1"); p.evaluate("PeaksApp.ready")
    p.evaluate("""async () => { await loadRound('tea-round');
      state.theme = 'slate'; document.getElementById('labels').checked = true; await refresh(); }""")
    png = _download(p, out / "full.png", "png", 300 / 25.4)
    # canvas text test: tiny font under a big transform vs real pixel size
    p.evaluate("""async () => { await document.fonts.load('500 20px Jost');
      const c = document.createElement('canvas'); c.width = 900; c.height = 160; c.id = 'tt'; document.body.prepend(c);
      const x = c.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0,0,900,160); x.fillStyle = '#000';
      x.save(); x.setTransform(11.81,0,0,11.81,0,0); x.font = '500 2.25px "Jost"'; x.fillText('Whiteless Pike  Crag Hill  Sail', 1, 4); x.restore();
      x.font = '500 26.6px "Jost"'; x.fillText('Whiteless Pike  Crag Hill  Sail', 12, 120); }""")
    p.locator("#tt").screenshot(path=str(out / "canvas-test.png"))
    b.close()
im = Image.open(png); w, h = im.size
im.crop((0, int(h * 0.78), w, int(h * 0.88))).save(out / "list.png")
im.crop((0, 0, w // 2, int(h * 0.35))).resize((w // 4, int(h * 0.35) // 2)).save(out / "map.png")
(out / "full.png").unlink()
