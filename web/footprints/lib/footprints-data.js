/* Footprints building data, shared by the web page (window.FootprintsData), the
 * cache function (api/pack.js) and the prepared-cities builder (lib/build-cities.js).
 *
 * Buildings come from OpenFreeMap's OpenMapTiles vector tiles at zoom 14. They are
 * turned into rings in metres from a centre point, north up: Web Mercator scaled by
 * cos(latitude) at the centre, which is true to scale at city size. Rings keep the
 * tiles' winding (outer rings one way, courtyards the other), so draw them with the
 * "nonzero" fill rule.
 *
 * A "pack" is one place's buildings saved as a single compact file, so a prepared or
 * cached place draws without fetching dozens of tiles:
 *   gzip( "FPK1" | u32 header length | header JSON | varint ring data )
 * Ring data: ring count, then per ring its point count and zigzag deltas of x and y in
 * units of header.unit metres, with one running cursor across all rings.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.FootprintsData = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const TILEJSON = "https://tiles.openfreemap.org/planet";
  const TILE_Z = 14, PARALLEL = 4, OVERLAP = 1, MAX_TILES = 600;
  const EARTH = 2 * Math.PI * 6378137, R = 6378137;
  const UNIT = 0.2;  // metres per pack unit
  const CREDIT = "Data from OpenStreetMap (openstreetmap.org/copyright) · © OpenMapTiles · OpenFreeMap";
  const MAGIC = [70, 80, 75, 49];  // "FPK1"

  // ---- Protobuf / vector tile reading ----------------------------------------
  function readVarint(buf, pos) {
    let result = 0, shift = 0, b;
    do { b = buf[pos.i++]; result += (b & 0x7f) * 2 ** shift; shift += 7; } while (b & 0x80);
    return result;
  }
  function messageFields(buf, start, end, onField) {
    const pos = { i: start };
    while (pos.i < end) {
      const key = readVarint(buf, pos), field = Math.floor(key / 8), wire = key & 7;
      if (wire === 0) onField(field, readVarint(buf, pos));
      else if (wire === 2) { const len = readVarint(buf, pos), s = pos.i; pos.i += len; onField(field, null, s, pos.i); }
      else if (wire === 5) pos.i += 4;
      else if (wire === 1) pos.i += 8;
      else throw new Error("Unreadable map tile");
    }
  }
  const zigzag = n => (n % 2 ? -(n + 1) / 2 : n / 2);
  const unzag = n => (n < 0 ? -2 * n - 1 : 2 * n);

  function decodeBuildingRings(buf) {
    const td = new TextDecoder(), out = { extent: 4096, rings: [] };
    messageFields(buf, 0, buf.length, (f, v, s, e) => {
      if (f !== 3) return;  // layers
      let name = "", extent = 4096; const feats = [];
      messageFields(buf, s, e, (lf, lv, ls, le) => {
        if (lf === 1) name = td.decode(buf.subarray(ls, le));
        else if (lf === 2) feats.push([ls, le]);
        else if (lf === 5) extent = lv;
      });
      if (name !== "building") return;
      out.extent = extent;
      for (const [fs, fe] of feats) {
        let type = 0, geom = null;
        messageFields(buf, fs, fe, (ff, fv, gs, ge) => {
          if (ff === 3) type = fv;
          else if (ff === 4) { geom = []; const p = { i: gs }; while (p.i < ge) geom.push(readVarint(buf, p)); }
        });
        if (type !== 3 || !geom) continue;  // polygons only
        let x = 0, y = 0, ring = null;
        for (let i = 0; i < geom.length;) {
          const c = geom[i++], cmd = c & 7, n = Math.floor(c / 8);
          if (cmd === 1 || cmd === 2) {
            for (let k = 0; k < n; k++) {
              x += zigzag(geom[i++]); y += zigzag(geom[i++]);
              if (cmd === 1) ring = [[x, y]]; else if (ring) ring.push([x, y]);
            }
          } else if (cmd === 7) { if (ring && ring.length >= 3) out.rings.push(ring); ring = null; }
        }
      }
    });
    return out;
  }

  // Trim a ring to a box (Sutherland–Hodgman). Keeps the ring's winding.
  function clipRing(ring, lo, hi, loY = lo, hiY = hi) {
    let pts = ring;
    for (const [axis, bound, keepAbove] of [[0, lo, true], [0, hi, false], [1, loY, true], [1, hiY, false]]) {
      const inside = p => keepAbove ? p[axis] >= bound : p[axis] <= bound, next = [];
      for (let i = 0; i < pts.length; i++) {
        const a = pts[i], b = pts[(i + 1) % pts.length], ia = inside(a), ib = inside(b);
        if (ia) next.push(a);
        if (ia !== ib) {
          const t = (bound - a[axis]) / (b[axis] - a[axis]);
          next.push([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]);
        }
      }
      pts = next;
      if (pts.length < 3) return null;
    }
    return pts;
  }

  // ---- Geography ---------------------------------------------------------------
  // Lon/lat box around a centre for a ground width and height in metres.
  function boxAround(lat, lon, w, h) {
    const kx = 111320 * Math.cos(lat * Math.PI / 180), ky = 110540;
    return { s: lat - h / 2 / ky, n: lat + h / 2 / ky, w: lon - w / 2 / kx, e: lon + w / 2 / kx };
  }
  function tileRange(bb) {
    const n = 2 ** TILE_Z, clamp = v => Math.min(n - 1, Math.max(0, Math.floor(v)));
    const tx = lon => clamp((lon + 180) / 360 * n);
    const ty = lat => clamp((1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * n);
    return { x0: tx(bb.w), x1: tx(bb.e), y0: ty(bb.n), y1: ty(bb.s) };
  }
  // Metres east/north of (lat0, lon0) for a point, in the same frame rings use.
  function offsetMetres(lat0, lon0, lat, lon) {
    const k = Math.cos(lat0 * Math.PI / 180);
    const x = (lon - lon0) / 360 * EARTH * k;
    const y = (R * Math.asinh(Math.tan(lat * Math.PI / 180)) - R * Math.asinh(Math.tan(lat0 * Math.PI / 180))) * k;
    return [x, y];
  }

  // ---- Loading buildings from tiles ------------------------------------------------
  async function tileTemplate(fetchFn, headers) {
    const r = await fetchFn(TILEJSON, { headers });
    if (!r.ok) throw new Error(`map tiles unavailable (error ${r.status})`);
    const tiles = (await r.json()).tiles;
    if (!tiles || !tiles[0]) throw new Error("map tiles unavailable");
    return tiles[0];
  }
  async function fetchTile(fetchFn, url, headers) {
    for (let attempt = 0; ; attempt++) {
      try {
        const r = await fetchFn(url, { headers });
        if (r.status === 404) return new Uint8Array(0);  // open sea beyond the data
        if (!r.ok) throw new Error(`error ${r.status}`);
        return new Uint8Array(await r.arrayBuffer());
      } catch (e) {
        if (attempt >= 2) throw e;
        await new Promise(res => setTimeout(res, 1500 * (attempt + 1)));
      }
    }
  }
  let cachedTemplate = null;
  /* Every building within w × h metres of (lat, lon), as rings in metres from it.
   * opts: fetch (defaults to global fetch), headers, onProgress(done, total). */
  async function buildFromTiles(lat, lon, w, h, opts = {}) {
    const fetchFn = opts.fetch || fetch, headers = opts.headers || {};
    const template = opts.template || cachedTemplate || (cachedTemplate = await tileTemplate(fetchFn, headers));
    const { x0, x1, y0, y1 } = tileRange(boxAround(lat, lon, w * 1.02, h * 1.02));
    const tiles = [];
    for (let x = x0; x <= x1; x++) for (let y = y0; y <= y1; y++) tiles.push([x, y]);
    if (tiles.length > MAX_TILES) throw new Error("that area is too big; choose a smaller width");
    const k = Math.cos(lat * Math.PI / 180);
    const X0 = lon / 360 * EARTH, Y0 = R * Math.asinh(Math.tan(lat * Math.PI / 180));
    const rings = []; let buildings = 0, done = 0, next = 0;
    async function worker() {
      while (next < tiles.length) {
        const [tx, ty] = tiles[next++];
        const data = await fetchTile(fetchFn, template.replace("{z}", TILE_Z).replace("{x}", tx).replace("{y}", ty), headers);
        if (data.length) {
          const { extent, rings: raw } = decodeBuildingRings(data), unit = EARTH / (extent * 2 ** TILE_Z);
          for (const r of raw) {
            const c = clipRing(r, -OVERLAP, extent + OVERLAP);
            if (!c) continue;
            let area = 0;
            for (let i = 0, j = r.length - 1; i < r.length; j = i++) area += (r[j][0] - r[i][0]) * (r[j][1] + r[i][1]);
            if (area > 0 && r[0][0] >= 0 && r[0][0] < extent && r[0][1] >= 0 && r[0][1] < extent) buildings++;
            rings.push(c.map(([px, py]) => [((tx * extent + px) * unit - EARTH / 2 - X0) * k,
                                            (EARTH / 2 - (ty * extent + py) * unit - Y0) * k]));
          }
        }
        if (opts.onProgress) opts.onProgress(++done, tiles.length);
      }
    }
    await Promise.all(Array.from({ length: Math.min(PARALLEL, tiles.length) }, worker));
    const version = template.split("/").slice(-4)[0] || "";
    return { rings, buildings, tiles: version };
  }

  // ---- Packs -------------------------------------------------------------------------
  function pushVarint(out, n) {
    while (n >= 0x80) { out.push((n % 0x80) | 0x80); n = Math.floor(n / 0x80); }
    out.push(n);
  }
  /* Rings (metres from the centre) trimmed to w × h, as an uncompressed pack.
   * header needs at least name, lat, lon, w, h. */
  function encodePack(rings, header) {
    const hw = header.w / 2, hh = header.h / 2, body = [], kept = [];
    for (const r of rings) {
      const c = clipRing(r, -hw, hw, -hh, hh);
      if (c) kept.push(c);
    }
    pushVarint(body, kept.length);
    let cx = 0, cy = 0;
    for (const r of kept) {
      const pts = [];
      for (const [x, y] of r) {
        const qx = Math.round(x / UNIT), qy = Math.round(y / UNIT);
        if (pts.length && pts[pts.length - 1][0] === qx && pts[pts.length - 1][1] === qy) continue;
        pts.push([qx, qy]);
      }
      pushVarint(body, pts.length);
      for (const [qx, qy] of pts) { pushVarint(body, unzag(qx - cx)); pushVarint(body, unzag(qy - cy)); cx = qx; cy = qy; }
    }
    const meta = new TextEncoder().encode(JSON.stringify({ v: 1, unit: UNIT, credit: CREDIT, ...header, rings: kept.length }));
    const out = new Uint8Array(8 + meta.length + body.length);
    out.set(MAGIC, 0);
    new DataView(out.buffer).setUint32(4, meta.length, true);
    out.set(meta, 8);
    out.set(body, 8 + meta.length);
    return out;
  }
  // Uncompressed pack -> { header, rings } with rings in metres from header's centre.
  function decodePack(bytes) {
    if (!MAGIC.every((b, i) => bytes[i] === b)) throw new Error("Not a footprints pack");
    const len = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(4, true);
    const header = JSON.parse(new TextDecoder().decode(bytes.subarray(8, 8 + len)));
    const pos = { i: 8 + len }, unit = header.unit || UNIT, rings = [];
    const n = readVarint(bytes, pos);
    let cx = 0, cy = 0;
    for (let r = 0; r < n; r++) {
      const m = readVarint(bytes, pos), ring = new Array(m);
      for (let p = 0; p < m; p++) {
        cx += zigzag(readVarint(bytes, pos)); cy += zigzag(readVarint(bytes, pos));
        ring[p] = [cx * unit, cy * unit];
      }
      rings.push(ring);
    }
    return { header, rings };
  }
  const isGzip = b => b[0] === 0x1f && b[1] === 0x8b;

  return { TILEJSON, TILE_Z, OVERLAP, MAX_TILES, EARTH, UNIT, CREDIT,
           decodeBuildingRings, clipRing, boxAround, tileRange, offsetMetres,
           buildFromTiles, encodePack, decodePack, isGzip };
});
