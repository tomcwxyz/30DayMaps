import sys, time, importlib.util
spec=importlib.util.spec_from_file_location('h','web/peaks/test/harness.py'); h=importlib.util.module_from_spec(spec); sys.argv=['x']; spec.loader.exec_module(h)
from playwright.sync_api import sync_playwright
base="https://peaks.tomcw.xyz/"
def settle(page, label, t):
    for i in range(40):
        page.wait_for_timeout(500)
        st=page.evaluate("[document.getElementById('status').textContent, document.getElementById('sheet').classList.contains('busy'), state.place && state.place.name, state.style, window.PeaksTimings && JSON.stringify(window.PeaksTimings)]")
        if not st[1] and st[0]=="": break
    print(f"{label:40s} {time.time()-t:5.1f}s {st}")
with sync_playwright() as pw:
    b=pw.chromium.launch(); page=b.new_page(viewport={"width":1400,"height":1000})
    page.on("pageerror", lambda e: print("pageerror:", e))
    page.on("console", lambda m: print("console:", m.type, m.text[:300]))
    page.on("requestfailed", lambda r: print("failed:", r.url[:120], r.failure))
    page.goto(base+"?place=helvellyn"); h.wait_drawn(page)
    for style, place in [("skyline","blencathra"),("panorama","cuillin"),("contours","ben-nevis"),("ridgelines","scafell"),("poster","yr-wyddfa")]:
        page.click(f"#styles button[data-style={style}]"); t=time.time(); settle(page, f"style {style}", t)
        t=time.time(); page.click(f'#presets button[data-slug="{place}"]'); settle(page, f"  -> {place}", t)
    # rapid clicks
    t=time.time()
    for s in ["helvellyn","blencathra","cuillin"]: page.click(f'#presets button[data-slug="{s}"]'); page.wait_for_timeout(150)
    settle(page, "rapid clicks", t)
    # round then place
    page.click('#rounds button[data-slug="tea-round"]'); t=time.time(); settle(page,"tea round",t)
    t=time.time(); page.click('#presets button[data-slug="helvellyn"]'); settle(page,"  -> helvellyn",t)
    b.close()
