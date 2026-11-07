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
