// Peaks print maker: turns terrain into a sheet description in millimetres (y down).
// The sheet is a flat list of drawing items that lib/render.js paints to canvas or SVG,
// so the preview, the PNG and the SVG are the same drawing.
(function (root) {
  "use strict";
  const T = root.PeaksTerrain;
  const EARTH_R = 6371008.8, REFRACT = 0.87;
  const SANS = "Jost", MONO = "IBM Plex Mono";

  // ---- colours -------------------------------------------------------------------
  // page, panel (the map's ground), line, text, muted, accent; sky = gradient top/bottom and
  // the farthest/nearest skyline layers.
  const THEMES = {
    paper:   { label: "Paper", page: "#F6F3EC", panel: "#F6F3EC", line: "#1F2321", text: "#1F2321", muted: "#7D817C", accent: "#B5482F",
               sky: ["#E7E4DA", "#F6F3EC", "#D6D3CA", "#1F2321"] },
    white:   { label: "White", page: "#FFFFFF", panel: "#FFFFFF", line: "#141414", text: "#141414", muted: "#8A8A8A", accent: "#C0392B",
               sky: ["#EDEDED", "#FFFFFF", "#D9D9D9", "#141414"] },
    navy:    { label: "Navy", page: "#F6F3EC", panel: "#17263A", line: "#E6EDF1", text: "#17263A", muted: "#7D8790", accent: "#F0B45A",
               sky: ["#B9C2DA", "#F2D3BF", "#B5B0CB", "#1D2440"] },
    oxblood: { label: "Oxblood", page: "#7C2A30", panel: "#7C2A30", line: "#F3D9D4", text: "#FBEDE8", muted: "#D9A9A6", accent: "#FFFFFF", frame: true,
               sky: ["#6A2228", "#8E3A40", "#B0676B", "#3A1013"] },
    night:   { label: "Night", page: "#121A1E", panel: "#121A1E", line: "#DCD5C4", text: "#E9E3D3", muted: "#76858B", accent: "#E0A55E",
               sky: ["#0E151A", "#24333A", "#3E5058", "#0A0F12"] },
    moss:    { label: "Moss", page: "#EEEBDD", panel: "#2E3A2C", line: "#E7E2C6", text: "#2E3A2C", muted: "#7F8A72", accent: "#E2C46B",
               sky: ["#DCE8E3", "#EFEBDF", "#C3D4CB", "#1E4C3D"] },
    bands:   { label: "Bands", page: "#F4EEDC", panel: "#F4EEDC", line: "#2B2A28", text: "#2B2A28", muted: "#837D70", accent: "#2B2A28",
               fills: ["#D8D2BE", "#9FB7B1", "#E7B24C", "#C76E6B", "#E9E2CC", "#8FA3C2", "#B9C3A1", "#F0C9A6"],
               sky: ["#F4EEDC", "#F4EEDC", "#8FA3C2", "#2B2A28"] },
  };

  const hex = c => [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16));
  const mix = (a, b, t) => { const A = hex(a), B = hex(b); return "#" + A.map((v, i) => Math.round(v + (B[i] - v) * t).toString(16).padStart(2, "0")).join(""); };

  // ---- small helpers ---------------------------------------------------------------
  function nice(step) {
    for (const s of [5, 10, 15, 20, 25, 50, 100, 200, 250, 500]) if (step <= s) return s;
    return 1000;
  }
  const ll = (lat, lon) => `${Math.abs(lat).toFixed(4)}° ${lat >= 0 ? "N" : "S"}   ·   ${Math.abs(lon).toFixed(4)}° ${lon >= 0 ? "E" : "W"}`;
  const fmtKm = m => m >= 10000 ? `${(m / 1000).toFixed(0)} km` : `${(m / 1000).toFixed(1)} km`;

  // ---- layout --------------------------------------------------------------------
  // Everything scales with u: 1 on A3 (short side 297 mm).
  function layout(pw, ph, kind, words) {
    const u = Math.min(pw, ph) / 297;
    if (kind === "panorama") {
      const m = 0.06 * ph;
      const cap = (words.title ? 15 : 0) + (words.subtitle ? 6 : 0) + (words.details ? 5 : 0) + 12;
      const map = { x: m, y: m, w: pw - 2 * m, h: ph - 2 * m - cap * u - 8 * u };
      return { u, map, align: "left", capX: m, capY: map.y + map.h + 13 * u, credit: [pw / 2, ph - m * 0.45], compass: true };
    }
    const land = pw > ph;
    const left = kind === "skyline";
    const mx = (left ? 0.06 : land ? 0.07 : 0.09) * pw, mt = (land ? 0.07 : 0.065) * ph;
    const capH = ((words.title ? 26 : 8) + (words.subtitle ? 6 : 0) + (words.details ? 5 : 0) + 14) * u;
    const map = { x: mx, y: mt, w: pw - 2 * mx, h: ph - mt - capH - 0.035 * ph };
    return { u, map, align: left ? "left" : "center", capX: left ? mx : pw / 2, capY: map.y + map.h + 14 * u, credit: [pw / 2, ph - 0.022 * ph] };
  }

  function caption(L, items, th, words) {
    const u = L.u;
    let y = L.capY;
    if (words.title) {
      items.push({ t: "text", x: L.capX, y, s: words.title.toUpperCase(), size: 12 * u, family: SANS, weight: 700, fill: th.text, align: L.align, base: "top", spacing: 0.2 });
      y += 15.5 * u;
    }
    if (words.subtitle) {
      items.push({ t: "text", x: L.capX, y, s: words.subtitle, size: 3.4 * u, family: MONO, weight: 400, fill: th.text, align: L.align, base: "top" });
      y += 5.6 * u;
    }
    if (words.details) items.push({ t: "text", x: L.capX, y, s: words.details.toUpperCase(), size: 2.75 * u, family: MONO, weight: 400, fill: th.muted, align: L.align, base: "top", spacing: 0.04 });
  }

  function credit(L, items, th, text) {
    items.push({ t: "text", x: L.credit[0], y: L.credit[1], s: text, size: Math.max(1.6, 1.95 * L.u), family: MONO, weight: 400, fill: th.muted, align: "center", base: "bottom" });
  }

  // ---- contours --------------------------------------------------------------------
  // Contour geometry for a frame (metres around the grid centre). Cached by the caller.
  function contourGeometry(g, frame, { lines = 90, smooth = 14, filled = false } = {}) {
    const pad = 4, res = g.res;
    const c0 = Math.max(0, Math.floor((frame.x0 + g.halfW) / res) - pad), c1 = Math.min(g.w, Math.ceil((frame.x1 + g.halfW) / res) + pad);
    const r0 = Math.max(0, Math.floor((g.halfH - frame.y1) / res) - pad), r1 = Math.min(g.h, Math.ceil((g.halfH - frame.y0) / res) + pad);
    const sw = c1 - c0, sh = r1 - r0;
    const blurred = T.blur(g.z, g.w, g.h, Math.max(1.2, smooth / res));
    const z = new Float64Array(sw * sh);
    let lo = Infinity, hi = -Infinity, sea = 0;
    for (let r = 0; r < sh; r++) for (let c = 0; c < sw; c++) {
      const v = blurred[(r0 + r) * g.w + c0 + c];
      z[r * sw + c] = v;
      if (r >= pad && r < sh - pad && c >= pad && c < sw - pad) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
      if (g.z[(r0 + r) * g.w + c0 + c] <= 0.5) sea++;
    }
    const step = nice((hi - lo) / lines);
    const levels = [];
    for (let v = Math.max(step, Math.ceil(lo / step) * step); v < hi; v += step) levels.push(v);
    const gx0 = -g.halfW + c0 * res, gy0 = g.halfH - r0 * res;
    const toM = geom => geom.coordinates.map(poly => poly.map(ring => {
      const out = new Float64Array(ring.length * 2);
      for (let i = 0; i < ring.length; i++) { out[2 * i] = gx0 + ring[i][0] * res; out[2 * i + 1] = gy0 - ring[i][1] * res; }
      return out;
    }));
    const gen = root.d3.contours().size([sw, sh]);
    const all = levels.length ? gen.thresholds(levels)(z) : [];
    const out = { step, lo, hi, levels: all.map(gm => ({ level: gm.value, major: Math.abs(gm.value / (step * 5) - Math.round(gm.value / (step * 5))) < 1e-6, polys: toM(gm) })) };
    if (sea / (sw * sh) > 0.002) out.coast = toM(gen.thresholds([0.5])(z)[0]);
    return out;
  }

  // A frame-to-millimetre mapping for a map box.
  function mapping(frame, box) {
    const s = box.w / (frame.x1 - frame.x0);
    return { s, x: x => box.x + (x - frame.x0) * s, y: y => box.y + (frame.y1 - y) * s };
  }

  function ringsToMM(polys, M, flatten = true) {
    const out = [];
    for (const poly of polys) for (const ring of poly) {
      const r = new Float32Array(ring.length);
      for (let i = 0; i < ring.length; i += 2) { r[i] = M.x(ring[i]); r[i + 1] = M.y(ring[i + 1]); }
      out.push(r);
    }
    return out;
  }

  // Height labels along index contours: on straight-ish stretches, spread out, kept upright.
  function contourLabels(geo, M, box, u, avoid) {
    const out = [], gap = 55 * u, edge = 9 * u, near = 24 * u;
    const taken = avoid.slice();
    for (const lv of geo.levels) {
      if (!lv.major) continue;
      for (const poly of lv.polys) for (const ring of poly) {
        let run = gap * 0.5, px = null, py = null;
        for (let i = 0; i < ring.length; i += 2) {
          const x = M.x(ring[i]), y = M.y(ring[i + 1]);
          if (px !== null) run += Math.hypot(x - px, y - py);
          px = x; py = y;
          if (run < gap) continue;
          if (x < box.x + edge || x > box.x + box.w - edge || y < box.y + edge || y > box.y + box.h - edge) continue;
          // direction over about ±4 mm of line either side
          let a = i, b = i, la = 0, lb = 0;
          while (a > 0 && la < 4 * u) { la += Math.hypot(M.x(ring[a]) - M.x(ring[a - 2]), M.y(ring[a + 1]) - M.y(ring[a - 1])); a -= 2; }
          while (b < ring.length - 2 && lb < 4 * u) { lb += Math.hypot(M.x(ring[b + 2]) - M.x(ring[b]), M.y(ring[b + 3]) - M.y(ring[b + 1])); b += 2; }
          const ax = M.x(ring[a]), ay = M.y(ring[a + 1]), bx = M.x(ring[b]), by = M.y(ring[b + 1]);
          const span = Math.hypot(bx - ax, by - ay);
          if (span < 6.6 * u) continue;   // too curly here
          if (taken.some(([tx, ty, tr]) => Math.hypot(tx - x, ty - y) < (tr || near))) continue;
          let rot = Math.atan2(by - ay, bx - ax);
          if (rot > Math.PI / 2) rot -= Math.PI; else if (rot < -Math.PI / 2) rot += Math.PI;
          out.push({ x, y, rot, level: lv.level });
          taken.push([x, y]); run = 0;
        }
      }
    }
    return out;
  }

  // Pick summits to name: highest first, spread apart, inside the frame.
  function pickSummits(names, g, frame, n, sep) {
    const mx = (frame.x1 - frame.x0) * 0.05, my = (frame.y1 - frame.y0) * 0.05;
    const cand = [];
    for (const p of names || []) {
      if (p.kind === "ridge") continue;
      const [x, y] = T.toXY(g.lat, g.lon, p.lat, p.lon);
      if (x < frame.x0 + mx || x > frame.x1 - mx || y < frame.y0 + my || y > frame.y1 - my) continue;
      const h = p.ele || T.localMax(g, x, y, 80);
      cand.push({ name: p.name, x, y, h });
    }
    cand.sort((a, b) => b.h - a.h);
    const keep = [], d = sep * (frame.x1 - frame.x0);
    for (const p of cand) {
      if (keep.every(q => Math.hypot(p.x - q.x, p.y - q.y) > d)) keep.push(p);
      if (keep.length >= n) break;
    }
    return keep;
  }

  function summitMarks(items, peaks, M, box, th, u) {
    const out = [];
    for (const p of peaks) {
      const x = M.x(p.x), y = M.y(p.y), right = x > box.x + box.w * 0.72;
      const s = 1.3 * u;
      items.push({ t: "poly", pts: [x, y - s, x + s, y + s * 0.75, x - s, y + s * 0.75], fill: th.accent, stroke: th.panel, w: 0.25 * u });
      const tx = right ? x - 2.2 * u : x + 2.2 * u;
      const halo = { color: th.panel, width: 0.9 * u };
      items.push({ t: "text", x: tx, y: y - 1.6 * u, s: p.name, size: 2.5 * u, family: SANS, weight: 500, fill: th.line, align: right ? "right" : "left", base: "bottom", halo });
      items.push({ t: "text", x: tx, y: y - 1.4 * u, s: `${Math.round(p.h)} m`, size: 2.1 * u, family: MONO, weight: 400, fill: th.line, align: right ? "right" : "left", base: "top", halo });
      out.push([x, y, 22 * u]);
    }
    return out;
  }

  // Named ridges (Sharp Edge, Striding Edge…) in spaced capitals at their middle, as OS maps do.
  function ridgeLabels(items, names, g, frame, M, box, th, u, avoid) {
    const out = [], size = 2.2 * u, edge = 12 * u;
    for (const p of names || []) {
      if (p.kind !== "ridge" || out.length >= 5) continue;
      const [gx, gy] = T.toXY(g.lat, g.lon, p.lat, p.lon);
      const x = M.x(gx), y = M.y(gy);
      if (x < box.x + edge || x > box.x + box.w - edge || y < box.y + edge || y > box.y + box.h - edge) continue;
      const half = p.name.length * size * 0.42;
      if (avoid.concat(out).some(([ax, ay, r]) => Math.abs(ax - x) < half + (r || 6 * u) * 0.5 && Math.abs(ay - y) < (r || 6 * u) * 0.5 + size)) continue;
      items.push({ t: "text", x, y, s: p.name.toUpperCase(), size, family: SANS, weight: 500, fill: th.line, align: "center", base: "middle",
                   spacing: 0.22, halo: { color: th.panel, width: 0.9 * u } });
      out.push([x, y, half * 2]);
    }
    return out;
  }

  function drawContours(items, { g, geo, frame, box, th, u, labels, names, filled, route }) {
    const M = mapping(frame, box);
    items.push({ t: "rect", x: box.x, y: box.y, w: box.w, h: box.h, fill: th.panel });
    items.push({ t: "clip", x: box.x, y: box.y, w: box.w, h: box.h });
    const widthKm = (frame.x1 - frame.x0) / 1000;
    const lw = (widthKm < 16 ? 0.15 : 0.115) * Math.max(0.75, u);
    if (filled && th.fills) {
      items.push({ t: "rect", x: box.x, y: box.y, w: box.w, h: box.h, fill: th.fills[0] });
      geo.levels.forEach((lv, i) => items.push({ t: "path", rings: ringsToMM(lv.polys, M), fill: th.fills[(i + 1) % th.fills.length], rule: "evenodd" }));
    }
    const minor = [], major = [];
    for (const lv of geo.levels) (lv.major ? major : minor).push(...ringsToMM(lv.polys, M));
    items.push({ t: "path", rings: minor, stroke: th.line, w: lw, alpha: 0.78 });
    if (geo.coast) items.push({ t: "path", rings: ringsToMM(geo.coast, M), stroke: th.line, w: lw * 1.7 });
    items.push({ t: "path", rings: major, stroke: th.line, w: lw * 2.3 });
    let avoid = [];
    if (route) avoid = drawRoute(items, route, M, th, u);
    if (labels) {
      const peaks = pickSummits(names, g, frame, Math.round(6 * Math.sqrt(box.w * box.h) / 260), 0.14);
      avoid = avoid.concat(summitMarks(items, peaks, M, box, th, u));
      if (frame.x1 - frame.x0 <= 12000) avoid = avoid.concat(ridgeLabels(items, names, g, frame, M, box, th, u, avoid));
      for (const l of contourLabels(geo, M, box, u, avoid))
        items.push({ t: "text", x: l.x, y: l.y, s: `${Math.round(l.level)}`, size: 1.95 * u, family: MONO, weight: 400, fill: th.line,
                     align: "center", base: "middle", rot: l.rot, halo: { color: filled && th.fills ? th.page : th.panel, width: 0.9 * u } });
    }
    items.push({ t: "unclip" });
    if (th.frame) items.push({ t: "rect", x: box.x, y: box.y, w: box.w, h: box.h, stroke: th.line, w: 0.3 * u });
    return M;
  }

  // ---- ridgelines -------------------------------------------------------------------
  function drawRidgelines(items, { g, frame, box, th, u, rows, route }) {
    const wide = frame.x1 - frame.x0 > 16000;
    rows = rows || (wide ? 80 : 64);
    const lift = wide ? 7 : 15;
    const blurred = T.blur(g.z, g.w, g.h, 1.6);
    const cols = Math.min(1600, Math.round(box.w * 3));
    const prof = [];
    let lo = Infinity, hi = -Infinity;
    for (let i = 0; i < rows; i++) {
      const y = frame.y1 - (frame.y1 - frame.y0) * i / (rows - 1);
      const row = new Float32Array(cols);
      for (let c = 0; c < cols; c++) {
        const v = T.sample(g, frame.x0 + (frame.x1 - frame.x0) * c / (cols - 1), y, blurred);
        row[c] = v; lo = Math.min(lo, v); hi = Math.max(hi, v);
      }
      prof.push(row);
    }
    const gap = box.h / (rows + lift);
    items.push({ t: "rect", x: box.x, y: box.y, w: box.w, h: box.h, fill: th.panel });
    items.push({ t: "clip", x: box.x, y: box.y - 2, w: box.w, h: box.h + 2 });
    prof.forEach((row, i) => {
      const base = box.y + lift * gap + i * gap;
      const pts = new Float32Array(cols * 2 + 4);
      for (let c = 0; c < cols; c++) { pts[2 * c] = box.x + box.w * c / (cols - 1); pts[2 * c + 1] = base - (row[c] - lo) / (hi - lo || 1) * lift * gap; }
      pts[2 * cols] = box.x + box.w; pts[2 * cols + 1] = box.y + box.h + 5;
      pts[2 * cols + 2] = box.x; pts[2 * cols + 3] = box.y + box.h + 5;
      items.push({ t: "path", rings: [pts], fill: th.panel });
      items.push({ t: "path", rings: [pts.subarray(0, cols * 2)], stroke: th.line, w: 0.3 * u, open: true });
    });
    items.push({ t: "unclip" });
    if (th.frame) items.push({ t: "rect", x: box.x, y: box.y, w: box.w, h: box.h, stroke: th.line, w: 0.3 * u });
    return rows;
  }

  // ---- skyline ------------------------------------------------------------------------
  // Elevation angle of the horizon per column, by distance band. g is centred on the viewpoint.
  function skyline(g, v, names, cols = 2000) {
    const res = g.res, reach = Math.min(v.reach, g.halfW, g.halfH), near = v.near != null ? v.near : 400;
    const eye = T.sample(g, 0, 0) + (v.lift || 2);
    const dist = [];
    for (let d = near; d < 3000; d += res / 2) dist.push(d);
    for (let d = Math.max(near, 3000); d < reach; d += res * 0.8) dist.push(d);
    const nb = 7, edges = [];
    const e0 = Math.max(near, 600) * 2.2;
    for (let i = 0; i < nb; i++) edges.push(e0 * (reach / e0) ** (i / (nb - 1)));
    const layers = edges.map(() => new Float32Array(cols));
    // The last stretch of open sea seen in each band, as [lo, hi] angles: islands and far
    // shores beyond it stand on that sea rather than reaching down to the nearer land.
    const seaLo = edges.map(() => new Float32Array(cols).fill(-90)), seaHi = edges.map(() => new Float32Array(cols).fill(-90));
    const offs = new Float32Array(cols);
    let anySea = false;
    for (let c = 0; c < cols; c++) {
      const off = -v.fov / 2 + v.fov * c / (cols - 1);
      offs[c] = off;
      const az = (v.az + off) * Math.PI / 180, sx = Math.sin(az), sy = Math.cos(az);
      let m = -90, b = 0;
      for (const d of dist) {
        while (b < nb && d > edges[b]) layers[b++][c] = m;
        if (b >= nb) break;
        const z = T.sample(g, sx * d, sy * d);
        const a = Math.atan2(Math.max(z, 0) - d * d * REFRACT / (2 * EARTH_R) - eye, d) * 180 / Math.PI;
        if (z <= 0.5) {
          anySea = true;
          if (a > m) { if (seaHi[b][c] < m - 0.1) seaLo[b][c] = m; seaHi[b][c] = a; m = a; }
          continue;
        }
        if (a > m) m = a;
      }
      while (b < nb) layers[b++][c] = m;
    }
    const sea = anySea ? Math.atan2(-reach * reach * REFRACT / (2 * EARTH_R) - eye, reach) * 180 / Math.PI : null;
    // named summits that stand on the horizon
    const seen = [];
    for (const n of names || []) {
      if (n.kind === "ridge") continue;
      const [x, y] = T.toXY(g.lat, g.lon, n.lat, n.lon);
      const dd = Math.hypot(x, y);
      if (dd < near + 300 || dd > reach) continue;
      const off = ((Math.atan2(x, y) * 180 / Math.PI - v.az + 540) % 360) - 180;
      if (Math.abs(off) > v.fov / 2 * 0.97) continue;
      const h = Math.max(n.ele || 0, T.localMax(g, x, y, 90));
      const a = Math.atan2(h - dd * dd * REFRACT / (2 * EARTH_R) - eye, dd) * 180 / Math.PI;
      let occ = -90;
      for (const d of dist) {
        if (d > dd - 250) break;
        const z = T.sample(g, x / dd * d, y / dd * d);
        occ = Math.max(occ, Math.atan2(z - d * d * REFRACT / (2 * EARTH_R) - eye, d) * 180 / Math.PI);
      }
      if (a >= occ - 0.03) seen.push({ name: n.name, off, ang: a, h, dist: dd });
    }
    return { offs, layers, seaLo, seaHi, eye, sea, summits: seen, v };
  }

  function drawSkyline(items, { sd, box, th, u, labels, labelRoom, crop, colours, sky = true, compass = false, exag = 0 }) {
    const [skyTop, skyBottom, far, near] = colours || th.sky;
    let x0 = 0, x1 = sd.offs.length - 1;
    if (crop) { while (Math.abs(sd.offs[x0]) > crop) x0++; while (Math.abs(sd.offs[x1]) > crop) x1--; }
    if (exag) {
      // Choose how much of the view to show so heights come out about `exag` times true,
      // centred on the highest point (a narrow strip of a wide view flattens mountains).
      x0 = 0; x1 = sd.offs.length - 1;
      const far = sd.layers[sd.layers.length - 1];
      let hiC = 0, vmax = -90;
      for (let c = 0; c <= x1; c++) if (far[c] > vmax) { vmax = far[c]; hiC = c; }
      const sorted = Array.from(far).sort((p, q) => p - q), v5 = sorted[Math.floor(sorted.length * 0.05)];
      const vspan = (vmax - v5) * 1.45 || 1;
      const n = Math.round(exag * vspan * box.w / box.h / (sd.offs[1] - sd.offs[0]));
      if (n < x1) { x0 = Math.max(0, Math.min(x1 - n, hiC - (n >> 1))); x1 = x0 + n; }
    }
    const L = sd.layers.map(a => a.subarray(x0, x1 + 1)), offs = sd.offs.subarray(x0, x1 + 1);
    let top = -90;
    for (const a of L) for (const v of a) top = Math.max(top, v);
    const nearest = Array.from(L[0]).filter(v => v > -89).sort((a, b) => a - b);
    let bottom = nearest.length ? nearest[Math.floor(nearest.length * 0.03)] : top - 1;
    if (crop === "outline" || sd.v.floor === "skyline") {
      const f = Array.from(L[L.length - 1]).sort((a, b) => a - b), b5 = f[Math.floor(f.length * 0.05)];
      bottom = b5 - (top - b5) * 0.35;
    }
    if (sd.sea != null) bottom = Math.min(bottom, sd.sea - (top - sd.sea) * 0.08);
    const room = labelRoom != null ? labelRoom : (labels ? 0.3 : 0.1);
    const span = top - bottom || 1;
    const yLo = bottom - span * 0.02, yHi = top + span * room;
    const X = o => box.x + (o - offs[0]) / (offs[offs.length - 1] - offs[0]) * box.w;
    const Y = a => box.y + box.h - (a - yLo) / (yHi - yLo) * box.h;
    if (sky) items.push({ t: "grad", x: box.x, y: box.y, w: box.w, h: box.h, top: skyTop, bottom: skyBottom });
    items.push({ t: "clip", x: box.x, y: box.y, w: box.w, h: box.h });
    const seaFill = mix(skyBottom, far, 0.55);   // sea: paler than any land
    if (sd.sea != null) items.push({ t: "rect", x: box.x, y: Y(sd.sea), w: box.w, h: box.y + box.h - Y(sd.sea), fill: seaFill });
    const n = L.length, cols = offs.length;
    for (let i = n - 1; i >= 0; i--) {
      const t = (n - 1 - i) / Math.max(1, n - 1);
      const fill = th.fills && !colours ? (i === 0 ? near : th.fills[(n - 1 - i) % th.fills.length]) : mix(far, near, t ** 1.35);
      const pts = new Float32Array(cols * 2 + 4);
      for (let c = 0; c < cols; c++) { pts[2 * c] = X(offs[c]); pts[2 * c + 1] = Math.min(box.y + box.h + 5, Y(Math.max(L[i][c], yLo - span))); }
      pts[2 * cols] = box.x + box.w; pts[2 * cols + 1] = box.y + box.h + 5; pts[2 * cols + 2] = box.x; pts[2 * cols + 3] = box.y + box.h + 5;
      items.push({ t: "path", rings: [pts], fill });
      // open sea in this band, in front of anything further away
      const hi = sd.seaHi && sd.seaHi[i].subarray(x0, x1 + 1), lo = sd.seaLo && sd.seaLo[i].subarray(x0, x1 + 1);
      if (hi) {
        let c = 0;
        while (c < cols) {
          if (hi[c] <= lo[c] || hi[c] <= -89) { c++; continue; }
          let e = c;
          while (e + 1 < cols && hi[e + 1] > lo[e + 1] && hi[e + 1] > -89) e++;
          const ring = [];
          for (let k = c; k <= e; k++) ring.push(X(offs[k]), Math.min(box.y + box.h + 5, Y(Math.max(hi[k], yLo - span))));
          for (let k = e; k >= c; k--) ring.push(X(offs[k]), Math.min(box.y + box.h + 5, Y(Math.max(lo[k], yLo - span))));
          if (e === c) { ring.splice(2, 0, X(offs[c]) + 0.01, ring[1]); ring.push(X(offs[c]) + 0.01, ring[ring.length - 1]); }
          items.push({ t: "path", rings: [Float32Array.from(ring)], fill: seaFill });
          c = e + 1;
        }
      }
    }
    items.push({ t: "unclip" });
    if (labels && sd.summits.length) {
      const lo = offs[0], hi = offs[offs.length - 1], sep = (hi - lo) / Math.max(8, box.w / (22 * u));
      const keep = [];
      for (const p of sd.summits.filter(p => p.off >= lo && p.off <= hi).sort((a, b) => b.h - a.h)) {
        if (keep.every(q => Math.abs(p.off - q.off) > sep)) keep.push(p);
        if (keep.length >= Math.round(box.w / (24 * u))) break;
      }
      keep.sort((a, b) => a.off - b.off);
      const ty = Y(top + span * room * 0.25);
      keep.forEach((p, k) => {
        const yy = ty - (k % 2 ? span * room * 0.38 / (yHi - yLo) * box.h : 0);
        const x = X(p.off);
        items.push({ t: "line", pts: [x, Y(p.ang) - 1.2 * u, x, yy + 1.2 * u], stroke: th.muted, w: 0.15 * u });
        items.push({ t: "text", x, y: yy - 2.6 * u, s: p.name, size: 2.35 * u, family: SANS, weight: 500, fill: th.text, align: "center", base: "bottom" });
        items.push({ t: "text", x, y: yy - 2.4 * u, s: `${Math.round(p.h)} m`, size: 1.95 * u, family: MONO, weight: 400, fill: th.muted, align: "center", base: "top" });
      });
    }
    if (compass) {
      const lo = offs[0], hi = offs[offs.length - 1], names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
      for (let b = Math.ceil((sd.v.az + lo) / 5) * 5; b <= sd.v.az + hi; b += 5) {
        const deg = ((b % 360) + 360) % 360, card = deg % 45 === 0;
        if (!card && deg % 10) continue;
        const x = X(b - sd.v.az);
        items.push({ t: "line", pts: [x, box.y + box.h + 1 * u, x, box.y + box.h + (card ? 3.2 : 2) * u], stroke: th.muted, w: 0.15 * u });
        if (card) items.push({ t: "text", x, y: box.y + box.h + 4 * u, s: names[deg / 45], size: 2.3 * u, family: MONO, weight: 500, fill: th.text, align: "center", base: "top" });
      }
    }
  }

  // ---- routes ----------------------------------------------------------------------------
  // route = { pts: [[x, y, dist, ele]], ... } in metres around the grid centre.
  function drawRoute(items, route, M, th, u) {
    const pts = new Float32Array(route.pts.length * 2);
    route.pts.forEach((p, i) => { pts[2 * i] = M.x(p[0]); pts[2 * i + 1] = M.y(p[1]); });
    items.push({ t: "path", rings: [pts], stroke: th.panel, w: 1.9 * u, open: true, alpha: 0.85 });
    items.push({ t: "path", rings: [pts], stroke: th.accent, w: 0.85 * u, open: true });
    const n = pts.length;
    items.push({ t: "circle", x: pts[0], y: pts[1], r: 1.5 * u, fill: th.panel, stroke: th.accent, w: 0.6 * u });
    items.push({ t: "circle", x: pts[n - 2], y: pts[n - 1], r: 1.5 * u, fill: th.accent, stroke: th.panel, w: 0.4 * u });
    const avoid = [];
    for (let i = 0; i < n; i += 8) avoid.push([pts[i], pts[i + 1], 6 * u]);
    return avoid;
  }

  function drawProfile(items, { route, box, th, u, labels }) {
    const P = route.profile, D = route.length;
    let lo = Infinity, hi = -Infinity;
    for (const [, e] of P) { lo = Math.min(lo, e); hi = Math.max(hi, e); }
    const base = Math.max(0, lo - (hi - lo) * 0.35), top = hi + (hi - lo) * 0.15 + 1;
    const X = d => box.x + d / D * box.w, Y = e => box.y + box.h - (e - base) / (top - base) * box.h;
    const pts = new Float32Array(P.length * 2 + 4);
    P.forEach(([d, e], i) => { pts[2 * i] = X(d); pts[2 * i + 1] = Y(e); });
    pts[2 * P.length] = box.x + box.w; pts[2 * P.length + 1] = box.y + box.h; pts[2 * P.length + 2] = box.x; pts[2 * P.length + 3] = box.y + box.h;
    const ink = th.panel !== th.page ? th.panel : th.line;
    items.push({ t: "path", rings: [pts], fill: mix(th.page, ink, 0.22) });
    items.push({ t: "path", rings: [pts.subarray(0, P.length * 2)], stroke: ink, w: 0.45 * u, open: true });
    items.push({ t: "line", pts: [box.x, box.y + box.h, box.x + box.w, box.y + box.h], stroke: ink, w: 0.3 * u });
    if (labels) {
      const stepKm = [1, 2, 5, 10, 20, 50].find(s => D / 1000 / s <= 12) || 100;
      for (let k = 0; k * stepKm * 1000 <= D; k++) {
        const x = X(k * stepKm * 1000);
        items.push({ t: "line", pts: [x, box.y + box.h, x, box.y + box.h + 1.4 * u], stroke: th.muted, w: 0.15 * u });
        items.push({ t: "text", x, y: box.y + box.h + 2 * u, s: `${k * stepKm}`, size: 1.95 * u, family: MONO, weight: 400, fill: th.muted, align: "center", base: "top" });
      }
      const iHi = P.reduce((b, p, i) => p[1] > P[b][1] ? i : b, 0);
      items.push({ t: "text", x: X(P[iHi][0]), y: Y(P[iHi][1]) - 1.5 * u, s: `${Math.round(P[iHi][1])} m`, size: 2 * u, family: MONO, weight: 500, fill: th.text, align: "center", base: "bottom" });
    }
  }

  root.PeaksDraw = { THEMES, layout, caption, credit, contourGeometry, drawContours, drawRidgelines, skyline, drawSkyline, drawProfile, nice, ll, fmtKm, mix };
})(typeof window !== "undefined" ? window : globalThis);
