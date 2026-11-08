// Social clips and stills for Peaks, drawn by the print maker itself (injected by make.py).
// Every frame is a real design: the same display list the shop prints, shown in stages.
(function () {
  "use strict";
  const RN = PeaksRender;
  const FONT = "Jost", MONO = "IBM Plex Mono";
  const ease = t => t < 0 ? 0 : t > 1 ? 1 : t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  const clamp = (t, a, b) => Math.max(0, Math.min(1, (t - a) / (b - a)));

  // A design, frozen: items plus what animating needs.
  function capture() {
    const c = state.composed;
    let lo = Infinity, hi = -Infinity;
    for (const it of c.items) if (it.heights) for (const h of it.heights) { lo = Math.min(lo, h); hi = Math.max(hi, h); }
    const layers = Math.max(0, ...c.items.filter(i => i.layer != null).map(i => i.layer + 1));
    return { items: c.items, pw: c.pw, ph: c.ph, lo, hi, layers, theme: D.THEMES[state.theme], title: $("title").value };
  }

  // The design at animation state s: { level (0..1 of the height range), sky (0..1), route (0..1), text (0..1) }
  function staged(d, s) {
    const out = [];
    const cut = d.lo + (d.hi - d.lo) * (s.level ?? 1);
    let inClip = 0;
    for (const it of d.items) {
      if (it.heights && (s.level ?? 1) < 1) {
        const rings = [];
        for (let i = 0; i < it.rings.length; i++) if (it.heights[i] <= cut) rings.push(it.rings[i]);
        out.push({ ...it, rings });
        continue;
      }
      if (it.layer != null && (s.sky ?? 1) < 1) {
        const k = d.layers > 1 ? it.layer / (d.layers - 1) : 0;          // far layers first
        const p = ease(clamp(s.sky ?? 1, k * 0.55, k * 0.55 + 0.45));
        const dy = (1 - p) * 60;
        const rings = it.rings.map(r => { const q = Float32Array.from(r); for (let j = 1; j < q.length; j += 2) q[j] += dy; return q; });
        out.push({ ...it, rings, alpha: p });
        continue;
      }
      if (it.route && (s.route ?? 1) < 1) {
        const r = it.rings[0], n = Math.max(2, Math.floor(r.length / 2 * (s.route ?? 1)));
        out.push({ ...it, rings: [r.subarray(0, n * 2)] });
        continue;
      }
      if (it.profile && (s.route ?? 1) < 1) {
        if (it.open) { const r = it.rings[0], n = Math.max(2, Math.floor(r.length / 2 * (s.route ?? 1))); out.push({ ...it, rings: [r.subarray(0, n * 2)] }); }
        else out.push({ ...it, alpha: (s.route ?? 1) ** 2 });
        continue;
      }
      if ((it.t === "text" || it.t === "poly" || it.t === "circle") && (s.text ?? 1) < 1) {
        if ((s.text ?? 1) <= 0) continue;
        out.push({ ...it, alpha: s.text, fill: it.fill });
        continue;
      }
      out.push(it);
    }
    return out;
  }

  const sheetCache = new Map();
  function sheet(d, s, pxW) {
    const c = document.createElement("canvas");
    RN.toCanvas(c, s ? staged(d, s) : d.items, d.pw, d.ph, pxW / d.pw);
    return c;
  }

  function shadowed(ctx, img, x, y, w, h, blur = 40) {
    ctx.save();
    ctx.shadowColor = "rgba(20,24,22,.28)"; ctx.shadowBlur = blur; ctx.shadowOffsetY = blur * 0.4;
    ctx.fillStyle = "#fff"; ctx.fillRect(x, y, w, h);
    ctx.restore();
    ctx.drawImage(img, x, y, w, h);
  }

  function text(ctx, s, x, y, { size = 40, weight = 500, family = FONT, color = "#1F2321", align = "center", spacing = 0, alpha = 1, base = "alphabetic" } = {}) {
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.font = `${weight} ${size}px "${family}"`;
    ctx.fillStyle = color; ctx.textAlign = align; ctx.textBaseline = base;
    if ("letterSpacing" in ctx) ctx.letterSpacing = `${spacing}px`;
    ctx.fillText(s, x, y);
    ctx.restore();
  }

  function wall(d, W, H, opts) {
    const c = document.createElement("canvas"); c.width = W; c.height = H;
    const img = sheet(d, null, Math.round(W * d.pw / (opts.span || 2400) * 1.6));
    drawWall(c, img, d.pw, d.ph, opts);
    return c;
  }

  const BG = "#EEEDE7", INK = "#1F2321", MUTED = "#6B706C", ACCENT = "#2F5D50";

  function endCard(ctx, W, H, a, lines) {
    ctx.save(); ctx.globalAlpha = a; ctx.fillStyle = BG; ctx.fillRect(0, 0, W, H); ctx.restore();
    const cy = H * 0.44, k = W / 1080;
    text(ctx, "PEAKS", W / 2, cy - 150 * k, { size: 92 * k, weight: 700, spacing: 22 * k, alpha: a });
    text(ctx, lines[0], W / 2, cy - 30 * k, { size: 46 * k, weight: 500, alpha: a });
    if (lines[1]) text(ctx, lines[1], W / 2, cy + 36 * k, { size: 46 * k, weight: 500, alpha: a });
    text(ctx, "peaks.tomcw.xyz", W / 2, cy + 160 * k, { size: 52 * k, weight: 600, color: ACCENT, alpha: a });
    text(ctx, "Prints from £22 · free UK delivery", W / 2, cy + 232 * k, { size: 32 * k, weight: 400, family: MONO, color: MUTED, alpha: a });
  }

  // ---- clips --------------------------------------------------------------------------------
  // Each returns { W, H, seconds, frame(t) -> canvas }.
  function drawIn(d, { W = 1080, H = 1920, kicker = "", headline = [], wallOpts = {} } = {}) {
    const k = W / 1080;
    const pxW = Math.min(W * 0.86, (H * 0.68) * d.pw / d.ph);
    const pxH = pxW * d.ph / d.pw, x = (W - pxW) / 2, y = H * (H > W ? 0.17 : 0.1);
    const wallC = wall(d, W, H, { span: H > W ? 950 : 1150, focus: H > W ? 0.4 : 0.36, cx: 0.5, ...wallOpts });
    const final = sheet(d, null, pxW * 1.25);
    const T = { draw: 4.2, sky: 1.6, text: 0.8, hold: 1.0, wall: 2.6, end: 2.4 };
    const seconds = T.draw + T.sky + T.text + T.hold + T.wall + T.end;
    const frame = t => {
      const c = document.createElement("canvas"); c.width = W; c.height = H;
      const ctx = c.getContext("2d");
      ctx.fillStyle = BG; ctx.fillRect(0, 0, W, H);
      const t1 = T.draw, t2 = t1 + T.sky, t3 = t2 + T.text, t4 = t3 + T.hold, t5 = t4 + T.wall;
      if (t < t4 + 0.6) {
        const s = { level: ease(clamp(t, 0.2, t1)), sky: clamp(t, t1 - 0.3, t2), route: 1, text: clamp(t, t2, t3) };
        const img = t >= t3 ? final : sheet(d, s, pxW * 1.25);
        shadowed(ctx, img, x, y, pxW, pxH, 50 * k);
        if (kicker) text(ctx, kicker, W / 2, y - 48 * k, { size: 30 * k, family: MONO, weight: 500, color: MUTED, spacing: 3 * k, alpha: clamp(t, 0.1, 0.8) });
        headline.forEach((h, i) => text(ctx, h, W / 2, y + pxH + (96 + 58 * i) * k, { size: 46 * k, weight: 500, alpha: clamp(t, t2 - 0.2, t3 + 0.2) }));
      }
      if (t > t4) {   // to the wall, pushing in slowly
        const a = ease(clamp(t, t4, t4 + 0.6)), z = 1.06 - 0.06 * clamp(t, t4, t5 + T.end);
        ctx.save(); ctx.globalAlpha = a;
        ctx.translate(W / 2, H / 2); ctx.scale(z, z); ctx.translate(-W / 2, -H / 2);
        ctx.drawImage(wallC, 0, 0); ctx.restore();
        text(ctx, `${d.sizeLabel || "A3"} · to scale`, W / 2, H * 0.06 + 20 * k, { size: 28 * k, family: MONO, color: MUTED, alpha: a * (1 - clamp(t, t5 - 0.3, t5)) });
      }
      if (t > t5) endCard(ctx, W, H, ease(clamp(t, t5, t5 + 0.5)), ["Your mountain, drawn", "from real elevation data"]);
      return c;
    };
    return { W, H, seconds, frame };
  }

  function routeClip(d, { W = 1080, H = 1920, kicker = "", stats = [] } = {}) {
    const k = W / 1080;
    const pxW = Math.min(W * 0.86, (H * 0.68) * d.pw / d.ph);
    const pxH = pxW * d.ph / d.pw, x = (W - pxW) / 2, y = H * (H > W ? 0.15 : 0.08);
    const base = sheet(d, { level: 1, sky: 1, route: 0.001, text: 0 }, pxW * 1.25);
    const final = sheet(d, null, pxW * 1.25);
    const T = { fade: 0.8, trace: 5.0, text: 0.8, hold: 1.4, end: 2.4 };
    const seconds = T.fade + T.trace + T.text + T.hold + T.end;
    const frame = t => {
      const c = document.createElement("canvas"); c.width = W; c.height = H;
      const ctx = c.getContext("2d");
      ctx.fillStyle = BG; ctx.fillRect(0, 0, W, H);
      const t1 = T.fade, t2 = t1 + T.trace, t3 = t2 + T.text, t4 = t3 + T.hold;
      const r = ease(clamp(t, t1, t2));
      let img;
      if (t < t1) img = base;
      else if (t < t2) img = sheet(d, { level: 1, sky: 1, route: r, text: 0 }, pxW * 1.25);
      else if (t < t3) img = sheet(d, { level: 1, sky: 1, route: 1, text: clamp(t, t2, t3) }, pxW * 1.25);
      else img = final;
      ctx.save(); ctx.globalAlpha = clamp(t, 0, t1); shadowed(ctx, img, x, y, pxW, pxH, 50 * k); ctx.restore();
      if (kicker) text(ctx, kicker, W / 2, y - 44 * k, { size: 30 * k, family: MONO, weight: 500, color: MUTED, spacing: 3 * k, alpha: clamp(t, 0.1, 0.8) });
      // a running count while the line draws
      stats.forEach((st, i) => {
        const v = st.n != null ? `${Math.round(st.n * (t < t2 ? r : 1)).toLocaleString("en-GB")}${st.unit}` : st.s;
        text(ctx, v, W / 2 + (i - (stats.length - 1) / 2) * 300 * k, y + pxH + 100 * k, { size: 58 * k, weight: 600, alpha: clamp(t, t1, t1 + 0.4) });
        text(ctx, st.label, W / 2 + (i - (stats.length - 1) / 2) * 300 * k, y + pxH + 146 * k, { size: 26 * k, family: MONO, color: MUTED, alpha: clamp(t, t1, t1 + 0.4) });
      });
      if (t > t4) endCard(ctx, W, H, ease(clamp(t, t4, t4 + 0.5)), ["Your route, or a famous one,", "drawn from real elevation data"]);
      return c;
    };
    return { W, H, seconds, frame };
  }

  // Several finished designs in turn: [{ d, label }]
  function styles(list, { W = 1080, H = 1920, kicker = "" } = {}) {
    const k = W / 1080, per = 1.5, fade = 0.25;
    const imgs = list.map(({ d, label }) => {
      const pxW = Math.min(W * 0.86, (H * 0.66) * d.pw / d.ph), pxH = pxW * d.ph / d.pw;
      return { img: sheet(d, null, pxW * 1.25), pxW, pxH, label };
    });
    const seconds = per * list.length + 2.4;
    const frame = t => {
      const c = document.createElement("canvas"); c.width = W; c.height = H;
      const ctx = c.getContext("2d");
      ctx.fillStyle = BG; ctx.fillRect(0, 0, W, H);
      const i = Math.min(list.length - 1, Math.floor(t / per)), f = t - i * per;
      const draw = (j, a) => {
        const { img, pxW, pxH, label } = imgs[j];
        const x = (W - pxW) / 2, y = H * 0.47 - pxH / 2;
        ctx.save(); ctx.globalAlpha = a; shadowed(ctx, img, x, y, pxW, pxH, 50 * k); ctx.restore();
        text(ctx, label, W / 2, y + pxH + 90 * k, { size: 44 * k, weight: 500, alpha: a });
      };
      if (t < per * list.length) {
        if (f < fade && i > 0) { draw(i - 1, 1); draw(i, ease(f / fade)); } else draw(i, 1);
        if (kicker) text(ctx, kicker, W / 2, H * 0.08, { size: 30 * k, family: MONO, weight: 500, color: MUTED, spacing: 3 * k });
      } else {
        draw(list.length - 1, 1);
        endCard(ctx, W, H, ease(clamp(t, per * list.length, per * list.length + 0.5)), ["Five styles, any mountain,", "or your own route"]);
      }
      return c;
    };
    return { W, H, seconds, frame };
  }

  // ---- stills ---------------------------------------------------------------------------------
  function still(fn, W, H) {
    const c = document.createElement("canvas"); c.width = W; c.height = H;
    const ctx = c.getContext("2d"); ctx.fillStyle = BG; ctx.fillRect(0, 0, W, H);
    fn(ctx, W, H);
    return c;
  }
  function onWall(d, W, H, opts = {}) { return wall(d, W, H, opts); }

  // Prints side by side on one wall, each at true size: [{ d }]
  function gallery(list, W, H, { span = 2600, focus = 0.4, gap = 160 } = {}) {
    return still((ctx) => {
      const c = document.createElement("canvas"); c.width = W; c.height = H;
      const mm = W / span, tall = Math.max(...list.map(x => x.d.ph));
      const floorY = H * focus + (tall / 2 + 20 + 220 + 750) * mm, sbTop = floorY - 750 * mm;
      drawWall(c, null, 1, 1, { span, floor: floorY / H, noPrint: true, vaseAt: 1.18 });
      ctx.drawImage(c, 0, 0);
      const total = list.reduce((s, x) => s + x.d.pw, 0) + gap * (list.length - 1);
      let xm = (span - total) / 2;
      for (const { d } of list) {
        const w = d.pw * mm, h = d.ph * mm, f = 20 * mm, xx = xm * mm, yy = H * focus - h / 2;   // middles in a line
        ctx.save(); ctx.shadowColor = "rgba(30,25,20,.35)"; ctx.shadowBlur = 40 * mm; ctx.shadowOffsetY = 18 * mm;
        ctx.fillStyle = "#1E1E1C"; ctx.fillRect(xx - f, yy - f, w + 2 * f, h + 2 * f); ctx.restore();
        ctx.drawImage(sheet(d, null, w * 1.4), xx, yy, w, h);
        xm += d.pw + gap;
      }
    }, W, H);
  }

  window.Studio = { capture, staged, sheet, drawIn, routeClip, styles, still, onWall, gallery, text, endCard, BG, INK, MUTED, ACCENT };
})();
