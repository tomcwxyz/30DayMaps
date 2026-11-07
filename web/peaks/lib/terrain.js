// Terrain for the Peaks print maker: Terrarium elevation tiles -> a local metre grid.
// Same pipeline as maps/peaks.py (fetch, repair, flatten sea), done in the browser.
// The grid is centred on (lat, lon); x runs east and y north, in metres.
(function (root) {
  "use strict";
  const R = 6371008.8, TILE = 256, EQUATOR = 40075016.686;
  const DEG = Math.PI / 180;
  const TERRARIUM = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
  const OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"];
  const CREDIT = "Elevation: Mapzen/Tilezen Terrain Tiles (AWS Open Data) incl. SRTM, EU-DEM, UK LiDAR";

  // Local plane around (lat0, lon0). Accurate to well under a metre over the 60 km we draw.
  function toXY(lat0, lon0, lat, lon) {
    return [(lon - lon0) * DEG * R * Math.cos(lat * DEG), (lat - lat0) * DEG * R];
  }
  function toLL(lat0, lon0, x, y) {
    const lat = lat0 + y / R / DEG;
    return [lat, lon0 + x / (R * Math.cos(lat * DEG)) / DEG];
  }

  // ---- tiles ------------------------------------------------------------------
  const tileCache = new Map();   // "z/x/y" -> Promise<Float32Array(256*256)>
  let tileUrl = TERRARIUM;

  async function decodePNG(blob) {
    const bmp = await createImageBitmap(blob, { colorSpaceConversion: "none", premultiplyAlpha: "none" });
    const c = typeof OffscreenCanvas !== "undefined" ? new OffscreenCanvas(TILE, TILE)
      : Object.assign(document.createElement("canvas"), { width: TILE, height: TILE });
    const ctx = c.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(bmp, 0, 0);
    const px = ctx.getImageData(0, 0, TILE, TILE).data;
    const out = new Float32Array(TILE * TILE);
    for (let i = 0, j = 0; i < out.length; i++, j += 4) out[i] = px[j] * 256 + px[j + 1] + px[j + 2] / 256 - 32768;
    return out;
  }

  function getTile(z, x, y) {
    const key = `${z}/${x}/${y}`;
    if (!tileCache.has(key)) {
      const p = (async () => {
        for (let attempt = 0; ; attempt++) {
          try {
            const r = await fetch(tileUrl.replace("{z}", z).replace("{x}", x).replace("{y}", y));
            if (!r.ok) throw new Error(`tile ${key}: HTTP ${r.status}`);
            return await decodePNG(await r.blob());
          } catch (e) {
            if (attempt >= 2) throw e;
            await new Promise(res => setTimeout(res, 600 * (attempt + 1)));
          }
        }
      })();
      p.catch(() => tileCache.delete(key));
      tileCache.set(key, p);
    }
    return tileCache.get(key);
  }

  function mercPx(lat, lon, z) {
    const n = TILE * 2 ** z, s = Math.sin(lat * DEG);
    return [(lon + 180) / 360 * n, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * n];
  }

  function chooseZoom(lat, res) {
    for (let z = 5; z <= 14; z++) if (EQUATOR * Math.cos(lat * DEG) / (TILE * 2 ** z) <= res * 1.15) return z;
    return 14;
  }

  // Elevation grid of w x h cells of `res` metres, covering [-halfW, halfW] x [-halfH, halfH].
  // Row 0 is the north edge. Returns { z: Float32Array, w, h, res, halfW, halfH, lat, lon }.
  async function grid({ lat, lon, halfW, halfH, res, onProgress }) {
    const w = Math.ceil(2 * halfW / res), h = Math.ceil(2 * halfH / res);
    halfW = w * res / 2; halfH = h * res / 2;
    let z = chooseZoom(lat, res), x0, x1, y0, y1;
    const corners = [[-halfW, -halfH], [halfW, -halfH], [-halfW, halfH], [halfW, halfH], [0, halfH], [0, -halfH]]
      .map(([x, y]) => toLL(lat, lon, x, y));
    for (; ; z--) {
      const px = corners.map(([la, lo]) => mercPx(la, lo, z));
      x0 = Math.floor(Math.min(...px.map(p => p[0])) / TILE); x1 = Math.floor(Math.max(...px.map(p => p[0])) / TILE);
      y0 = Math.floor(Math.min(...px.map(p => p[1])) / TILE); y1 = Math.floor(Math.max(...px.map(p => p[1])) / TILE);
      if ((x1 - x0 + 1) * (y1 - y0 + 1) <= 240 || z <= 5) break;
    }
    const tw = x1 - x0 + 1, th = y1 - y0 + 1, MW = tw * TILE, MH = th * TILE;
    const mosaic = new Float32Array(MW * MH);
    const jobs = [];
    for (let ty = y0; ty <= y1; ty++) for (let tx = x0; tx <= x1; tx++) jobs.push([tx, ty]);
    let done = 0;
    const worker = async () => {
      while (jobs.length) {
        const [tx, ty] = jobs.shift();
        const t = await getTile(z, tx, ty);
        const ox = (tx - x0) * TILE, oy = (ty - y0) * TILE;
        for (let r = 0; r < TILE; r++) mosaic.set(t.subarray(r * TILE, (r + 1) * TILE), (oy + r) * MW + ox);
        done++; onProgress && onProgress(done, tw * th);
      }
    };
    await Promise.all(Array.from({ length: 8 }, worker));

    const out = new Float32Array(w * h);
    const n = TILE * 2 ** z;
    for (let r = 0; r < h; r++) {
      const y = halfH - (r + 0.5) * res;
      const la = lat + y / R / DEG, s = Math.sin(la * DEG);
      const my = (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * n - y0 * TILE - 0.5;
      const lonPerM = 1 / (R * Math.cos(la * DEG)) / DEG;
      const iy = Math.max(0, Math.min(MH - 2, Math.floor(my))), fy = Math.max(0, Math.min(1, my - iy));
      for (let c = 0; c < w; c++) {
        const x = -halfW + (c + 0.5) * res;
        const mx = (lon + x * lonPerM + 180) / 360 * n - x0 * TILE - 0.5;
        const ix = Math.max(0, Math.min(MW - 2, Math.floor(mx))), fx = Math.max(0, Math.min(1, mx - ix));
        const i = iy * MW + ix;
        out[r * w + c] = (mosaic[i] * (1 - fx) + mosaic[i + 1] * fx) * (1 - fy) + (mosaic[i + MW] * (1 - fx) + mosaic[i + MW + 1] * fx) * fy;
      }
    }
    clean(out, w, h);
    return { z: out, w, h, res, halfW, halfH, lat, lon, zoom: z };
  }

  // ---- repair -------------------------------------------------------------------
  function median(a) { const s = Float32Array.from(a).sort(); return s[s.length >> 1]; }

  // Terrarium faults: voids (huge negative values), whole rows/columns of garbage along tile
  // seams, and isolated spikes. Mark them bad, then fill from good neighbours. Sea goes to 0 m.
  function clean(z, w, h) {
    const bad = new Uint8Array(w * h);
    for (let i = 0; i < z.length; i++) if (!Number.isFinite(z[i]) || z[i] < -440) { bad[i] = 1; z[i] = 0; }
    const stride = Math.max(1, Math.floor(Math.min(w, h) / 400));
    const rowStep = new Float32Array(h - 1), colStep = new Float32Array(w - 1);
    for (let r = 0; r < h - 1; r++) { const a = []; for (let c = 0; c < w; c += stride) a.push(Math.abs(z[r * w + c] - z[(r + 1) * w + c])); rowStep[r] = median(a); }
    for (let c = 0; c < w - 1; c++) { const a = []; for (let r = 0; r < h; r += stride) a.push(Math.abs(z[r * w + c] - z[r * w + c + 1])); colStep[c] = median(a); }
    const rLim = Math.max(8, 8 * median(rowStep)), cLim = Math.max(8, 8 * median(colStep));
    for (let r = 0; r < h - 1; r++) if (rowStep[r] > rLim) for (let rr = Math.max(0, r - 2); rr < Math.min(h, r + 4); rr++) bad.fill(1, rr * w, rr * w + w);
    for (let c = 0; c < w - 1; c++) if (colStep[c] > cLim) for (let r = 0; r < h; r++) for (let cc = Math.max(0, c - 2); cc < Math.min(w, c + 4); cc++) bad[r * w + cc] = 1;
    for (let r = 1; r < h - 1; r++) for (let c = 1; c < w - 1; c++) {
      const i = r * w + c;
      const m = (z[i - w - 1] + z[i - w] + z[i - w + 1] + z[i - 1] + z[i + 1] + z[i + w - 1] + z[i + w] + z[i + w + 1]) / 8;
      if (Math.abs(z[i] - m) > 220) bad[i] = 1;
    }
    // Needles a few cells wide: far above everything two cells away.
    for (let r = 2; r < h - 2; r++) for (let c = 2; c < w - 2; c++) {
      const i = r * w + c;
      let m = -Infinity;
      for (let k = -2; k <= 2; k++) {
        m = Math.max(m, z[i - 2 * w + k], z[i + 2 * w + k]);
        if (k > -2 && k < 2) m = Math.max(m, z[i + k * w - 2], z[i + k * w + 2]);
      }
      if (z[i] - m > 150) for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) bad[i + dr * w + dc] = 1;
    }
    flatBlocks(z, w, h, bad);
    // Fill from the edge of each bad patch inwards.
    let left = bad.reduce((a, b) => a + b, 0);
    for (let pass = 0; left && pass < 400; pass++) {
      const next = [];
      for (let i = 0; i < z.length; i++) {
        if (!bad[i]) continue;
        const r = (i / w) | 0, c = i - r * w;
        let s = 0, k = 0;
        if (r > 0 && !bad[i - w]) { s += z[i - w]; k++; }
        if (r < h - 1 && !bad[i + w]) { s += z[i + w]; k++; }
        if (c > 0 && !bad[i - 1]) { s += z[i - 1]; k++; }
        if (c < w - 1 && !bad[i + 1]) { s += z[i + 1]; k++; }
        if (k) next.push(i, s / k);
      }
      if (!next.length) break;
      for (let j = 0; j < next.length; j += 2) { z[next[j]] = next[j + 1]; bad[next[j]] = 0; }
      left -= next.length / 2;
    }
    for (let i = 0; i < z.length; i++) if (z[i] < 0) z[i] = 0;
  }

  // Terrarium sometimes has blocks of a single height standing out of the sea (or out of
  // lower ground) with cliff edges, from a coarse source tile. Lakes and tarns are flat too,
  // but sit below their surroundings, so only patches that stand well above nearly all of
  // their edge are marked bad (with a two-cell margin for the blurred rim).
  function flatBlocks(z, w, h, bad) {
    const seen = new Uint8Array(w * h), stack = [], comp = [];
    const isFlat = i => {
      const v = z[i];
      return v > 3 && Math.abs(v - z[i - 1]) < 0.5 && Math.abs(v - z[i + 1]) < 0.5 && Math.abs(v - z[i - w]) < 0.5 && Math.abs(v - z[i + w]) < 0.5;
    };
    for (let r = 3; r < h - 3; r++) for (let c = 3; c < w - 3; c++) {
      const start = r * w + c;
      if (seen[start] || !isFlat(start)) continue;
      comp.length = 0; stack.push(start); seen[start] = 1;
      while (stack.length) {
        const i = stack.pop(); comp.push(i);
        const rr = (i / w) | 0, cc = i - rr * w;
        for (const j of [i - 1, i + 1, i - w, i + w]) {
          const jr = (j / w) | 0, jc = j - jr * w;
          if (jr < 3 || jr >= h - 3 || jc < 3 || jc >= w - 3 || seen[j] || Math.abs(jr - rr) + Math.abs(jc - cc) !== 1) continue;
          if (isFlat(j)) { seen[j] = 1; stack.push(j); }
        }
      }
      if (comp.length < 12) continue;
      const inComp = new Set(comp);
      let edges = 0, above = 0;
      for (const i of comp) for (const d of [-1, 1, -w, w]) {
        if (inComp.has(i + d)) continue;
        edges++;
        if (z[i] - z[i + 3 * d] > 30) above++;
      }
      if (edges && above / edges >= 0.8)
        for (const i of comp) for (let dr = -2; dr <= 2; dr++) for (let dc = -2; dc <= 2; dc++) {
          const j = i + dr * w + dc;
          if (j >= 0 && j < z.length && z[j] > 3) bad[j] = 1;
        }
    }
  }

  // Separable Gaussian blur, sigma in cells. Returns a new array.
  function blur(z, w, h, sigma) {
    if (sigma < 0.3) return Float32Array.from(z);
    const rad = Math.ceil(sigma * 3), k = new Float32Array(2 * rad + 1);
    let sum = 0;
    for (let i = -rad; i <= rad; i++) sum += (k[i + rad] = Math.exp(-i * i / (2 * sigma * sigma)));
    for (let i = 0; i < k.length; i++) k[i] /= sum;
    const tmp = new Float32Array(z.length), out = new Float32Array(z.length);
    for (let r = 0; r < h; r++) {
      const o = r * w;
      for (let c = 0; c < w; c++) {
        let s = 0;
        for (let j = -rad; j <= rad; j++) s += z[o + Math.min(w - 1, Math.max(0, c + j))] * k[j + rad];
        tmp[o + c] = s;
      }
    }
    for (let c = 0; c < w; c++) for (let r = 0; r < h; r++) {
      let s = 0;
      for (let j = -rad; j <= rad; j++) s += tmp[Math.min(h - 1, Math.max(0, r + j)) * w + c] * k[j + rad];
      out[r * w + c] = s;
    }
    return out;
  }

  // Bilinear sample at local metres.
  function sample(g, x, y, z = g.z) {
    const cx = (x + g.halfW) / g.res - 0.5, cy = (g.halfH - y) / g.res - 0.5;
    const ix = Math.max(0, Math.min(g.w - 2, Math.floor(cx))), iy = Math.max(0, Math.min(g.h - 2, Math.floor(cy)));
    const fx = Math.max(0, Math.min(1, cx - ix)), fy = Math.max(0, Math.min(1, cy - iy));
    const i = iy * g.w + ix;
    return (z[i] * (1 - fx) + z[i + 1] * fx) * (1 - fy) + (z[i + g.w] * (1 - fx) + z[i + g.w + 1] * fx) * fy;
  }

  // Highest value within `rad` metres of (x, y): a summit's height even if the point is a little off.
  function localMax(g, x, y, rad) {
    const n = Math.max(1, Math.round(rad / g.res));
    const cx = Math.round((x + g.halfW) / g.res - 0.5), cy = Math.round((g.halfH - y) / g.res - 0.5);
    let m = -Infinity;
    for (let r = cy - n; r <= cy + n; r++) for (let c = cx - n; c <= cx + n; c++)
      if (r >= 0 && r < g.h && c >= 0 && c < g.w) m = Math.max(m, g.z[r * g.w + c]);
    return m;
  }

  // ---- named summits --------------------------------------------------------------
  const latin = t => !!t && [...t].every(ch => ch.codePointAt(0) < 0x250 || "’‘·".includes(ch));
  const nameCache = new Map();
  async function summits(lat, lon, halfW, halfH) {
    const ll = [[-halfW, -halfH], [halfW, halfH], [-halfW, halfH], [halfW, -halfH]].map(([x, y]) => toLL(lat, lon, x, y));
    const s = Math.min(...ll.map(p => p[0])), n = Math.max(...ll.map(p => p[0]));
    const w = Math.min(...ll.map(p => p[1])), e = Math.max(...ll.map(p => p[1]));
    const key = [s, w, n, e].map(v => v.toFixed(3)).join(",");
    if (nameCache.has(key)) return nameCache.get(key);
    const q = `[out:json][timeout:40];(node["natural"~"^(peak|hill|volcano)$"]["name"](${key});way["natural"~"^(arete|ridge)$"]["name"](${key}););out center;`;
    let els = null;
    for (const url of OVERPASS) {
      try {
        const r = await fetch(url, { method: "POST", body: new URLSearchParams({ data: q }) });
        if (r.ok) { els = (await r.json()).elements; break; }
      } catch (e) { /* try the next server */ }
    }
    if (!els) {
      if (root.PeaksTerrain.strict) throw new Error("summit names unavailable (Overpass)");
      return [];
    }
    const out = els.map(e => {
      const name = latin(e.tags.name) ? e.tags.name : e.tags["name:en"];
      if (!name || !latin(name)) return null;
      if (e.type === "way") return e.center ? { name, lat: e.center.lat, lon: e.center.lon, kind: "ridge" } : null;
      const ele = parseFloat(String(e.tags.ele || "").replace(/[^\d.\-]/g, ""));
      return { name, lat: e.lat, lon: e.lon, ele: Number.isFinite(ele) ? ele : null };
    }).filter(Boolean);
    nameCache.set(key, out);
    return out;
  }

  root.PeaksTerrain = {
    grid, blur, sample, localMax, summits, toXY, toLL, CREDIT, R, _clean: clean,
    setTileUrl(u) { tileUrl = u; tileCache.clear(); },
  };
})(typeof window !== "undefined" ? window : globalThis);
