"use strict";
// Terrain repairs: data faults go, real landscape stays.
const test = require("node:test");
const assert = require("node:assert");
require("../lib/terrain.js");
const T = globalThis.PeaksTerrain;

function grid(w, h, f) { const z = new Float32Array(w * h); for (let r = 0; r < h; r++) for (let c = 0; c < w; c++) z[r * w + c] = f(r, c); return z; }

test("a flat block standing in the sea is removed", () => {
  const w = 60, h = 60;
  const z = grid(w, h, (r, c) => (r >= 20 && r < 32 && c >= 20 && c < 34) ? 120 : 0);
  T._clean(z, w, h);
  assert.ok(Math.max(...z) < 5, `block left at ${Math.max(...z)} m`);
});

test("a tarn in a corrie is kept", () => {
  const w = 60, h = 60;
  const z = grid(w, h, (r, c) => { const d = Math.hypot(r - 30, c - 30); return d < 8 ? 600 : 600 + (d - 8) * 25; });
  const before = Float32Array.from(z);
  T._clean(z, w, h);
  assert.strictEqual(z[30 * w + 30], 600);
  assert.deepStrictEqual(Array.from(z), Array.from(before));
});

test("a high flat plateau that slopes gently away is kept", () => {
  const w = 60, h = 60;
  const z = grid(w, h, (r, c) => { const d = Math.hypot(r - 30, c - 30); return d < 8 ? 400 : Math.max(0, 400 - (d - 8) * 3); });
  const before = Float32Array.from(z);
  T._clean(z, w, h);
  assert.deepStrictEqual(Array.from(z), Array.from(before));
});

test("a two-cell needle is removed, a real summit is not", () => {
  const w = 40, h = 40;
  const z = grid(w, h, (r, c) => 300 + 200 * Math.exp(-((r - 10) ** 2 + (c - 10) ** 2) / 30));
  z[25 * w + 25] = z[25 * w + 26] = 900;
  const summit = z[10 * w + 10];
  T._clean(z, w, h);
  assert.ok(z[25 * w + 25] < 350, `needle left at ${z[25 * w + 25]}`);
  assert.strictEqual(z[10 * w + 10], summit);
});

test("a finer patch is sampled wherever it covers the grid", () => {
  const g = { z: new Float32Array(100 * 100).fill(100), w: 100, h: 100, res: 20, halfW: 1000, halfH: 1000, lat: 54.6, lon: -3 };
  const f = { z: new Float32Array(50 * 50).fill(300), w: 50, h: 50, res: 4, halfW: 100, halfH: 100, lat: 54.6, lon: -3 };
  const fg = T.withFine(Object.assign({}, g), f);
  assert.strictEqual(T.sample(fg, 0, 0), 300);
  assert.strictEqual(T.sample(fg, 500, 500), 100);
  assert.strictEqual(T.sample(g, 0, 0), 100, "the plain grid is untouched");
  assert.strictEqual(T.localMax(fg, 0, 0, 20), 300);
});

test("a baked grid decodes to the heights it was made from (to its half-metre step)", async () => {
  const fs = require("fs"), path = require("path");
  const bytes = fs.readFileSync(path.join(__dirname, "baked-fixture.bin"));
  const real = global.fetch;
  global.fetch = async () => new Response(bytes);
  try {
    const g = await T.baked("x.bin", { w: 9, h: 7, q: 0.5 }, { lat: 54, lon: -3, res: 10 });
    const want = (x, y) => Math.round((100 + 30 * Math.sin(x / 2) + 12 * y + 0.3 * x * y) / 0.5) * 0.5;
    assert.strictEqual(g.z[0], 0);
    for (const [x, y] of [[1, 0], [8, 6], [4, 3], [0, 6]]) assert.ok(Math.abs(g.z[y * 9 + x] - want(x, y)) < 1e-6, `${x},${y}: ${g.z[y * 9 + x]} vs ${want(x, y)}`);
    assert.strictEqual(g.halfW, 45);
  } finally { global.fetch = real; }
});

test("contours match d3-contour's rings on a hilly field", () => {
  const fs = require("fs"), path = require("path");
  (0, eval)(fs.readFileSync(path.join(__dirname, "../lib/vendor/d3-array.min.js"), "utf8"));
  (0, eval)(fs.readFileSync(path.join(__dirname, "../lib/vendor/d3-contour.min.js"), "utf8"));
  require("../lib/draw.js");
  const w = 160, h = 120, res = 20, z = new Float32Array(w * h);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++)
    z[y * w + x] = 300 + 250 * Math.sin(x / 13) * Math.cos(y / 11) + 120 * Math.sin((x + 2 * y) / 7) + 2 * x;
  const g = { z, w, h, res, halfW: w * res / 2, halfH: h * res / 2, lat: 54, lon: -3 };
  const fr = { x0: -1400, x1: 1400, y0: -1000, y1: 1000 };
  const geo = PeaksDraw.contourGeometry(g, fr, { lines: 40, smooth: 1 });
  // the same blurred, cropped field through d3
  const pad = 4, c0 = Math.floor((fr.x0 + g.halfW) / res) - pad, c1 = Math.ceil((fr.x1 + g.halfW) / res) + pad;
  const r0 = Math.floor((g.halfH - fr.y1) / res) - pad, r1 = Math.ceil((g.halfH - fr.y0) / res) + pad;
  const sw = c1 - c0, sh = r1 - r0, bl = T.blur(z, w, h, 1.2), zz = new Float64Array(sw * sh);
  for (let r = 0; r < sh; r++) for (let c = 0; c < sw; c++) zz[r * sw + c] = bl[(r0 + r) * w + c0 + c];
  const ref = globalThis.d3.contours().size([sw, sh]).thresholds(geo.levels.map(l => l.level))(zz);
  const mine = geo.levels.map(l => l.polys.length), theirs = ref.map(gm => gm.coordinates.reduce((n, p) => n + p.length, 0));
  assert.deepStrictEqual(mine, theirs);
  const length = rings => rings.reduce((s, r) => { for (let i = 2; i < r.length; i += 2) s += Math.hypot(r[i] - r[i - 2], r[i + 1] - r[i - 1]); return s; }, 0);
  const a = length(geo.levels.flatMap(l => l.polys.flat())) / res;
  const b = ref.reduce((s, gm) => s + gm.coordinates.flat().reduce((t, ring) => { for (let i = 1; i < ring.length; i++) t += Math.hypot(ring[i][0] - ring[i - 1][0], ring[i][1] - ring[i - 1][1]); return t; }, 0), 0);
  assert.ok(Math.abs(a - b) / b < 0.01, `lengths ${a.toFixed(1)} vs ${b.toFixed(1)}`);
});
