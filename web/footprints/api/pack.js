"use strict";
// /api/pack: a shared cache of places people have drawn, so the next person to pick
// somewhere nearby gets its buildings in one small file instead of dozens of tiles.
//
//   GET  /api/pack?lat=&lon=&w=   -> 200 {url, lat, lon, w, h} if cached, 404 if not
//   POST /api/pack {lat, lon, w}  -> builds the pack from OpenFreeMap tiles on the
//                                    server, stores it in Vercel Blob, returns {url, ...}
//
// Places are snapped to a grid (about 200 m) and widths rounded up to whole kilometres,
// with a margin so any centre in the cell fits. The server builds packs itself rather
// than accepting them from browsers, so nobody can plant fake maps in the cache.
// Switched off (501) until a Blob store is connected to the project. Newer stores connect
// with BLOB_STORE_ID and Vercel's own login (OIDC); older ones with BLOB_READ_WRITE_TOKEN.
// The Blob library handles both.

const zlib = require("zlib");
const D = require("../lib/footprints-data.js");

const SNAP = 0.002;            // degrees
const MARGIN = 600;            // metres added to width and height, covering any centre in the cell
const ASPECT = 1.35;           // height / width: the tallest map (A-series portrait) is 1.3
const MAX_KM = 20;
const MAX_BYTES = 15 * 1024 * 1024;
const USER_AGENT = "30DayMaps-footprints/0.2 (+https://github.com/tomcwxyz/30DayMaps)";

function send(res, code, obj, cache) {
  res.statusCode = code;
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Cache-Control", cache || "no-store");
  res.end(JSON.stringify(obj));
}

// The cache cell for a request, or an error message.
function cell(q) {
  const lat = Number(q.lat), lon = Number(q.lon), km = Number(q.w);
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 80 || Math.abs(lon) > 180) return { error: "Bad position" };
  if (!Number.isFinite(km) || km <= 0 || km > MAX_KM) return { error: `Width must be up to ${MAX_KM} km` };
  const snap = v => Math.round(Math.round(v / SNAP) * SNAP * 1e4) / 1e4;
  const wk = Math.max(1, Math.ceil(km));
  const c = { lat: snap(lat), lon: snap(lon), wk };
  c.w = wk * 1000 + MARGIN;
  c.h = Math.round(wk * 1000 * ASPECT) + MARGIN;
  c.pathname = `packs/v1/${c.lat.toFixed(4)}_${c.lon.toFixed(4)}_${wk}km.fpk.gz`;
  return c;
}

async function readBody(req) {
  if (req.body && typeof req.body === "object" && !Buffer.isBuffer(req.body)) return req.body;
  let text = typeof req.body === "string" ? req.body : Buffer.isBuffer(req.body) ? req.body.toString("utf8") : null;
  if (text == null) {
    text = await new Promise((resolve, reject) => {
      let data = ""; req.on("data", c => { data += c; }); req.on("end", () => resolve(data)); req.on("error", reject);
    });
  }
  return JSON.parse(text || "{}");
}

const blobApi = () => module.exports._blob || require("@vercel/blob");

async function lookup(c) {
  try {
    const found = await blobApi().head(c.pathname);
    return { url: found.url, lat: c.lat, lon: c.lon, w: c.w, h: c.h };
  } catch (e) {
    if (e && (e.name === "BlobNotFoundError" || /not.?found/i.test(e.message || ""))) return null;
    throw e;
  }
}

module.exports = async (req, res) => {
  const connected = process.env.BLOB_READ_WRITE_TOKEN || process.env.BLOB_STORE_ID || module.exports._blob;
  if (!connected) return send(res, 501, { error: "Place cache isn't set up" });
  let c;
  try {
    const q = req.method === "POST" ? await readBody(req) : Object.fromEntries(new URL(req.url, "http://x").searchParams);
    c = cell(q);
  } catch { return send(res, 400, { error: "Bad request" }); }
  if (c.error) return send(res, 400, { error: c.error });

  try {
    const found = await lookup(c);
    if (req.method === "GET") {
      return found ? send(res, 200, found, "public, max-age=300") : send(res, 404, { cached: false });
    }
    if (req.method !== "POST") { res.setHeader("Allow", "GET, POST"); return send(res, 405, { error: "Use GET or POST" }); }
    if (found) return send(res, 200, found);

    const built = await D.buildFromTiles(c.lat, c.lon, c.w, c.h, { headers: { "User-Agent": USER_AGENT } });
    const pack = zlib.gzipSync(D.encodePack(built.rings, {
      name: `${c.lat}, ${c.lon}`, lat: c.lat, lon: c.lon, w: c.w, h: c.h,
      buildings: built.buildings, tiles: built.tiles, built: new Date().toISOString(),
    }), { level: 9 });
    if (pack.length > MAX_BYTES) return send(res, 413, { error: "Too big to cache" });
    const stored = await blobApi().put(c.pathname, pack, {
      access: "public", addRandomSuffix: false, allowOverwrite: true,
      contentType: "application/octet-stream", cacheControlMaxAge: 30 * 24 * 3600,
    });
    return send(res, 200, { url: stored.url, lat: c.lat, lon: c.lon, w: c.w, h: c.h, built: true });
  } catch (e) {
    console.error("pack failed:", e && e.name, e && e.message);
    return send(res, 502, { error: "Couldn't cache this place" });
  }
};
module.exports.cell = cell;
