// node --test web/footprints/test/*.test.js
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");
const D = require("../lib/footprints-data.js");

const FIX = path.join(__dirname, "../../../tests/fixtures");
const tile = new Uint8Array(fs.readFileSync(path.join(FIX, "building-tile.pbf")));
const expected = JSON.parse(fs.readFileSync(path.join(FIX, "building-tile.json"))).rings;
const area = r => { let a = 0; for (let i = 0, j = r.length - 1; i < r.length; j = i++) a += (r[j][0] - r[i][0]) * (r[j][1] + r[i][1]); return a / 2; };
const norm = r => { const p = r.map(q => q.join(",")); if (p[0] === p[p.length - 1]) p.pop(); return p.sort().join(" "); };

test("reads a tile's buildings exactly as the reference Python library does", () => {
  const got = D.decodeBuildingRings(tile);
  assert.strictEqual(got.extent, 4096);
  assert.deepStrictEqual(got.rings.map(norm).sort(), expected.map(norm).sort());
  assert.ok(got.rings.some(r => area(r) < 0) && got.rings.some(r => area(r) > 0));  // holes wound the other way
});

test("packs round-trip to 0.1 m, trimmed to their box, keeping winding", () => {
  const rings = [[[-100.04, -100], [100, -100], [100, 100], [-100, 100]],
                 [[-40, -40], [-40, 40], [40, 40], [40, -40]],
                 [[900, 0], [1300, 0], [1300, 50], [900, 50]],
                 [[5000, 5000], [5100, 5000], [5100, 5100]]];          // outside the box: dropped
  const bytes = D.encodePack(rings, { name: "T", lat: 1, lon: 2, w: 2000, h: 1000 });
  const { header, rings: back } = D.decodePack(bytes);
  assert.strictEqual(header.rings, 3);
  assert.strictEqual(back.length, 3);
  assert.ok(Math.abs(back[0][0][0] - -100) <= 0.1);
  assert.ok(Math.sign(area(back[0])) !== Math.sign(area(back[1])));
  assert.strictEqual(Math.max(...back[2].map(p => p[0])), 1000);
  assert.ok(header.credit.includes("OpenStreetMap"));
});

test("gzip packs are recognised", () => {
  const gz = zlib.gzipSync(D.encodePack([], { name: "E", lat: 0, lon: 0, w: 10, h: 10 }));
  assert.ok(D.isGzip(gz));
  assert.deepStrictEqual(D.decodePack(zlib.gunzipSync(gz)).rings, []);
});

test("builds a place from tiles: fetches each tile once, places buildings in metres", async () => {
  const fetched = [];
  const fake = async url => {
    fetched.push(url);
    if (!url.includes("{")) {
      if (url.endsWith("/planet")) return { ok: true, status: 200, json: async () => ({ tiles: ["https://t/20261101_1/{z}/{x}/{y}.pbf"] }) };
    }
    return { ok: true, status: 200, arrayBuffer: async () => tile.buffer.slice(tile.byteOffset, tile.byteOffset + tile.byteLength) };
  };
  const progress = [];
  const out = await D.buildFromTiles(54.97, -1.61, 3000, 3000, { fetch: fake, onProgress: (d, t) => progress.push([d, t]) });
  const tileUrls = fetched.filter(u => u.endsWith(".pbf"));
  assert.strictEqual(new Set(tileUrls).size, tileUrls.length);
  assert.strictEqual(progress[progress.length - 1][0], tileUrls.length);
  assert.strictEqual(out.tiles, "20261101_1");
  assert.strictEqual(out.buildings, 3 * tileUrls.length);   // outer rings starting inside each tile; holes and the edge-straddler (counted by its own tile) are not
  const xs = out.rings.flat().map(p => p[0]);
  assert.ok(Math.min(...xs) > -3000 && Math.max(...xs) < 3000);  // all near the centre, in metres
});

test("offsets between nearby centres are in metres", () => {
  const [x, y] = D.offsetMetres(54.97, -1.61, 54.971, -1.61);
  assert.ok(Math.abs(x) < 1e-6 && Math.abs(y - 111.4) < 1);
});
