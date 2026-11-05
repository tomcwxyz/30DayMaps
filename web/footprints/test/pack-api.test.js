"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");
const D = require("../lib/footprints-data.js");
const api = require("../api/pack.js");

const tile = new Uint8Array(fs.readFileSync(path.join(__dirname, "../../../tests/fixtures/building-tile.pbf")));
function res() {
  const r = { statusCode: 0, headers: {} };
  r.setHeader = (k, v) => { r.headers[k] = v; };
  r.end = t => { r.body = JSON.parse(t); };
  return r;
}
function fakeBlob() {
  const store = new Map();
  return {
    store,
    head: async p => { if (!store.has(p)) { const e = new Error("not found"); e.name = "BlobNotFoundError"; throw e; } return { url: `https://blob.test/${p}` }; },
    put: async (p, body, opts) => { store.set(p, { body, opts }); return { url: `https://blob.test/${p}` }; },
  };
}
global.fetch = async url => url.endsWith("/planet")
  ? { ok: true, status: 200, json: async () => ({ tiles: ["https://t/v1/{z}/{x}/{y}.pbf"] }) }
  : { ok: true, status: 200, arrayBuffer: async () => tile.buffer.slice(tile.byteOffset, tile.byteOffset + tile.byteLength) };

test("nearby requests share one cache cell that covers them", () => {
  const a = api.cell({ lat: 54.97391, lon: -1.61321, w: 8.5 });
  const b = api.cell({ lat: 54.9741, lon: -1.6135, w: 9 });
  assert.strictEqual(a.pathname, b.pathname);
  assert.strictEqual(a.pathname, "packs/v1/54.9740_-1.6140_9km.fpk.gz");
  // a centre at the far corner of the cell still fits a 9 km wide window of the tallest shape (1.3×)
  const [dx, dy] = D.offsetMetres(a.lat, a.lon, a.lat + 0.001, a.lon + 0.001);
  assert.ok(Math.abs(dx) + 4500 <= a.w / 2 && Math.abs(dy) + 9000 * 1.3 / 2 <= a.h / 2);
  assert.ok(api.cell({ lat: 54, lon: 1, w: 25 }).error);
  assert.ok(api.cell({ lat: "x", lon: 1, w: 2 }).error);
});

test("GET says whether a place is cached; POST builds, stores and then reuses it", async () => {
  const blob = fakeBlob(); api._blob = blob;
  let r = res();
  await api({ method: "GET", url: "/api/pack?lat=54.97&lon=-1.61&w=2" }, r);
  assert.strictEqual(r.statusCode, 404);

  r = res();
  await api({ method: "POST", body: { lat: 54.97, lon: -1.61, w: 2 } }, r);
  assert.strictEqual(r.statusCode, 200);
  assert.strictEqual(r.body.built, true);
  const [pathname, saved] = [...blob.store.entries()][0];
  assert.strictEqual(saved.opts.access, "public");
  const { header, rings } = D.decodePack(zlib.gunzipSync(saved.body));
  assert.ok(rings.length > 0 && header.w === 2600 && header.h === 3300 && header.tiles === "v1");

  r = res();
  await api({ method: "GET", url: "/api/pack?lat=54.9701&lon=-1.6099&w=1.5" }, r);
  assert.strictEqual(r.statusCode, 200);
  assert.strictEqual(r.body.url, `https://blob.test/${pathname}`);

  r = res();
  await api({ method: "POST", body: { lat: 54.97, lon: -1.61, w: 2 } }, r);
  assert.strictEqual(r.body.built, undefined);   // already cached: not rebuilt
  assert.strictEqual(blob.store.size, 1);
});

test("switched off until a Blob store is connected", async () => {
  delete api._blob; delete process.env.BLOB_READ_WRITE_TOKEN; delete process.env.BLOB_STORE_ID;
  const r = res();
  await api({ method: "GET", url: "/api/pack?lat=1&lon=1&w=1" }, r);
  assert.strictEqual(r.statusCode, 501);
});

test("a store connected by store ID (Vercel's own login) counts as set up", async () => {
  delete api._blob; delete process.env.BLOB_READ_WRITE_TOKEN;
  process.env.BLOB_STORE_ID = "store_test";
  const r = res();
  await api({ method: "GET", url: "/api/pack?lat=1&lon=1&w=50" }, r);   // reaches validation, not the 501
  assert.strictEqual(r.statusCode, 400);
  delete process.env.BLOB_STORE_ID;
});
