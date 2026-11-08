"""Social stills and clips for Peaks, drawn by the print maker itself.

    python peaks/social/make.py OUTDIR [stills] [clips]

Opens web/peaks in headless Chromium (ready-made places use their baked data, so this works
offline), designs a few prints through the page's own controls, then has peaks/social/studio.js
compose stills (JPEG) and clips (H.264 MP4, frames piped straight to ffmpeg).
"""
from __future__ import annotations

import base64
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("harness", ROOT / "web/peaks/test/harness.py")
H = importlib.util.module_from_spec(spec); sys.argv, argv = ["x"], sys.argv; spec.loader.exec_module(H); sys.argv = argv
STUDIO = (Path(__file__).parent / "studio.js").read_text()

# name: (how to get there, style, theme, paper, orient, size label)
DESIGNS = {
    "blencathra": ({"place": "blencathra"}, "poster", "paper", "A3", "portrait", "A3"),
    "bgr": ({"round": "bob-graham-round"}, "poster", "navy", "A3", "portrait", "A3"),
    "tea": ({"round": "tea-round"}, "poster", "moss", "A3", "portrait", "A3"),
    "helv-poster": ({"place": "helvellyn"}, "poster", "paper", "A3", "portrait", "A3"),
    "helv-contours": ({"place": "helvellyn"}, "contours", "night", "A3", "portrait", "A3"),
    "helv-ridges": ({"place": "helvellyn"}, "ridgelines", "oxblood", "A3", "portrait", "A3"),
    "striding": ({"place": "helvellyn", "seen": "view:striding-edge-from-red-tarn"}, "skyline", "moss", "A3", "landscape", "A3"),
    "cuillin-pano": ({"place": "cuillin"}, "panorama", "navy", "pano90", "landscape", "90 × 30 cm"),
    "sharp": ({"place": "blencathra", "seen": "view:sharp-edge-from-bannerdale"}, "skyline", "paper", "A3", "landscape", "A3"),
}


CLIPS = [
    ("Studio.drawIn(DS.blencathra, { W: 1080, H: 1920, kicker: 'BLENCATHRA · LAKE DISTRICT', headline: ['Every contour from real data,', 'Sharp Edge from 2 m LiDAR'] })",
     "reel-blencathra-draw.mp4"),
    ("Studio.drawIn(DS.blencathra, { W: 1080, H: 1080, kicker: 'BLENCATHRA · LAKE DISTRICT' })",
     "square-blencathra-draw.mp4"),
    ("Studio.routeClip(DS.bgr, { W: 1080, H: 1920, kicker: 'THE BOB GRAHAM ROUND', stats: [{ n: 42, unit: '', label: 'summits' }, { n: 109, unit: ' km', label: 'distance' }, { s: '24 h', label: 'to do it in' }] })",
     "reel-bob-graham-route.mp4"),
    ("Studio.routeClip(DS.bgr, { W: 1080, H: 1080, kicker: 'THE BOB GRAHAM ROUND', stats: [] })",
     "square-bob-graham-route.mp4"),
    ("Studio.styles([{ d: DS['helv-poster'], label: 'Poster' }, { d: DS['helv-contours'], label: 'Contours' }, { d: DS['helv-ridges'], label: 'Ridgelines' }, { d: DS.striding, label: 'Skyline' }, { d: DS['cuillin-pano'], label: 'Panorama' }], { W: 1080, H: 1920, kicker: 'PICK A STYLE' })",
     "reel-five-styles.mp4"),
]


def design(page, name):
    how, style, theme, paper, orient, size = DESIGNS[name]
    page.goto(BASE + f"?place={how.get('place', 'helvellyn')}")
    H.wait_drawn(page)
    if how.get("round"):
        page.click(f'#rounds button[data-slug="{how["round"]}"]'); page.wait_for_timeout(300); H.wait_drawn(page)
    page.click(f"#styles button[data-style={style}]"); page.wait_for_timeout(300); H.wait_drawn(page)
    if how.get("seen"):
        page.select_option("#seenFrom", how["seen"]); page.wait_for_timeout(300); H.wait_drawn(page)
    page.click(f'#themes button[data-theme="{theme}"]'); page.wait_for_timeout(300); H.wait_drawn(page)
    if style != "panorama":
        page.select_option("#orient", orient); page.wait_for_timeout(300); H.wait_drawn(page)
    page.select_option("#paper", paper); page.wait_for_timeout(300); H.wait_drawn(page)
    page.evaluate("document.fonts.ready")
    page.add_script_tag(content=STUDIO)
    page.evaluate(f"window.DS = window.DS || {{}}; DS[{name!r}] = Object.assign(Studio.capture(), {{ sizeLabel: {size!r} }})")


def jpeg(page, expr, path, q=0.92):
    data = page.evaluate(f"(() => {{ const c = {expr}; return c.toDataURL('image/jpeg', {q}); }})()")
    Path(path).write_bytes(base64.b64decode(data.split(",", 1)[1]))
    print("still", path, flush=True)


def clip(page, setup, path, fps=30):
    """setup: JS expression making a clip; frames go straight into ffmpeg."""
    page.evaluate(f"window.CLIP = {setup}")
    W, Hh, secs = page.evaluate("[CLIP.W, CLIP.H, CLIP.seconds]")
    n = int(round(secs * fps))
    tmp = str(path) + ".part.mp4"
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                           "-r", str(fps), tmp], stdin=subprocess.PIPE)
    for i in range(n):
        data = page.evaluate(f"CLIP.frame({i / fps}).toDataURL('image/jpeg', 0.92)")
        ff.stdin.write(base64.b64decode(data.split(",", 1)[1]))
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit(f"ffmpeg failed for {path}")
    os.replace(tmp, path)
    print("clip", path, f"{W}x{Hh}", f"{secs:.1f}s", flush=True)


def main():
    global BASE
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    what = set(sys.argv[2:]) or {"stills", "clips"}
    from playwright.sync_api import sync_playwright
    BASE = H.serve()
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--js-flags=--max-old-space-size=8192"])
        page = b.new_page(viewport={"width": 1400, "height": 1000})
        page.on("pageerror", lambda e: print("pageerror:", e, flush=True))
        # designs live in window.DS across navigations? No: each goto resets, so capture, then compose in one page
        snaps = {}
        for name in DESIGNS:
            design(page, name)
            snaps[name] = page.evaluate(f"""(() => {{ const d = DS[{name!r}];
              return {{ pw: d.pw, ph: d.ph, lo: d.lo, hi: d.hi, layers: d.layers, title: d.title, sizeLabel: d.sizeLabel, theme: state.theme,
                        items: d.items.map(it => {{ const o = {{ ...it }}; if (o.rings) o.rings = o.rings.map(r => Array.from(r)); if (o.pts) o.pts = Array.from(o.pts); return o; }}) }}; }})()""")
            print("designed", name, flush=True)
        # one page holding every design
        page.goto(BASE + "?place=helvellyn"); H.wait_drawn(page)
        page.evaluate("document.fonts.ready")
        page.add_script_tag(content=STUDIO)
        for name, d in snaps.items():
            page.evaluate("""([name, d]) => { window.DS = window.DS || {};
              d.items.forEach(it => { if (it.rings) it.rings = it.rings.map(r => Float32Array.from(r)); if (it.pts) it.pts = Float32Array.from(it.pts); });
              DS[name] = d; }""", [name, d])
        if "stills" in what:
            jpeg(page, "Studio.onWall(DS.blencathra, 1080, 1080, { span: 1050, focus: 0.4 })", out / "square-blencathra-on-wall.jpg")
            jpeg(page, "Studio.onWall(DS.bgr, 1080, 1350, { span: 1000, focus: 0.38 })", out / "portrait-bob-graham-on-wall.jpg")
            jpeg(page, "Studio.gallery([{ d: DS.blencathra }, { d: DS['helv-contours'] }, { d: DS.tea }], 1080, 1350, { span: 1800, focus: 0.4, gap: 110 })",
                 out / "portrait-gallery-wall.jpg")
            jpeg(page, "Studio.onWall(DS['cuillin-pano'], 1200, 675, { span: 1700, focus: 0.42 })", out / "landscape-cuillin-panorama-on-wall.jpg")
            jpeg(page, "Studio.gallery([{ d: DS.striding }, { d: DS.sharp }], 1200, 675, { span: 1900, focus: 0.42, gap: 140 })", out / "landscape-edges-on-wall.jpg")
            for i, (n, label) in enumerate([("helv-poster", "Poster"), ("helv-contours", "Contours"), ("helv-ridges", "Ridgelines"), ("striding", "Skyline"), ("cuillin-pano", "Panorama")]):
                jpeg(page, f"""Studio.still((ctx, W, H) => {{ const d = DS[{n!r}], k = W / 1080;
                    const pxW = Math.min(W * 0.84, H * 0.72 * d.pw / d.ph), pxH = pxW * d.ph / d.pw;
                    const img = Studio.sheet(d, null, pxW * 1.3), x = (W - pxW) / 2, y = H * 0.44 - pxH / 2;
                    ctx.save(); ctx.shadowColor = 'rgba(20,24,22,.28)'; ctx.shadowBlur = 40; ctx.shadowOffsetY = 16; ctx.fillStyle = '#fff'; ctx.fillRect(x, y, pxW, pxH); ctx.restore();
                    ctx.drawImage(img, x, y, pxW, pxH);
                    Studio.text(ctx, {label!r}, W / 2, H * 0.92, {{ size: 44 * k, weight: 500 }});
                    Studio.text(ctx, '{i + 1} / 5', W / 2, H * 0.06 + 10, {{ size: 24 * k, family: 'IBM Plex Mono', color: Studio.MUTED }});
                  }}, 1080, 1350)""", out / f"carousel-{i + 1}-{label.lower()}.jpg")
            jpeg(page, """Studio.still((ctx, W, H) => { const d = DS.tea, k = W / 1080;
                    const pxW = W * 0.78, pxH = pxW * d.ph / d.pw, img = Studio.sheet(d, null, pxW * 1.3), x = (W - pxW) / 2, y = H * 0.13;
                    ctx.save(); ctx.shadowColor = 'rgba(20,24,22,.3)'; ctx.shadowBlur = 50; ctx.shadowOffsetY = 20; ctx.fillStyle = '#fff'; ctx.fillRect(x, y, pxW, pxH); ctx.restore();
                    ctx.drawImage(img, x, y, pxW, pxH);
                    Studio.text(ctx, 'The Tea Round', W / 2, y + pxH + 100 * k, { size: 46 * k, weight: 500 });
                    Studio.text(ctx, '48 km of Lakeland fells, from Keswick', W / 2, y + pxH + 156 * k, { size: 30 * k, family: 'IBM Plex Mono', color: Studio.MUTED });
                    Studio.text(ctx, 'peaks.tomcw.xyz', W / 2, H * 0.93, { size: 52 * k, weight: 600, color: Studio.ACCENT });
                  }, 1080, 1920)""", out / "story-striding-edge.jpg")
        if "clips" in what:
            for setup, name in CLIPS:
                clip(page, setup, out / name)
        if "frames" in what:   # a few full-size frames per clip, at the busy moments, to check before rendering
            for setup, name in CLIPS:
                page.evaluate(f"window.CLIP = {setup}")
                secs = page.evaluate("CLIP.seconds")
                for f in (0.3, 0.55, 0.75, 0.9):
                    jpeg(page, f"CLIP.frame({secs * f})", out / f"frame-{name[:-4]}-{int(f * 100)}.jpg")
        b.close()


if __name__ == "__main__":
    main()
