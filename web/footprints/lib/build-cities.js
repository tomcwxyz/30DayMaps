// Builds the prepared city files from OpenFreeMap tiles.
//   node web/footprints/lib/build-cities.js            all cities in cities/cities.json
//   node web/footprints/lib/build-cities.js paris rome only these
// Writes cities/<slug>.fpk.gz and cities/index.json (what the page's gallery reads).
// Thumbnails are drawn afterwards by `python -m maps.city_thumbs`.
"use strict";
const fs = require("fs"), path = require("path"), zlib = require("zlib");
const D = require("./footprints-data.js");

const DIR = path.join(__dirname, "..", "cities");
const ASPECT = 1.35;   // height / width: the tallest map (A-series portrait) is 1.3
const USER_AGENT = "30DayMaps-footprints/0.2 (+https://github.com/tomcwxyz/30DayMaps)";

async function main() {
  const list = JSON.parse(fs.readFileSync(path.join(DIR, "cities.json"), "utf8")).cities;
  const only = process.argv.slice(2);
  const indexFile = path.join(DIR, "index.json");
  const index = fs.existsSync(indexFile) ? JSON.parse(fs.readFileSync(indexFile, "utf8")) : { cities: [] };
  const built = new Map(index.cities.map(c => [c.slug, c]));
  for (const c of list) {
    if (only.length && !only.includes(c.slug)) continue;
    const w = c.width_km * 1000, h = Math.round(w * ASPECT), t0 = Date.now();
    const r = await D.buildFromTiles(c.lat, c.lon, w, h, { headers: { "User-Agent": USER_AGENT } });
    const pack = zlib.gzipSync(D.encodePack(r.rings, {
      name: c.name, lat: c.lat, lon: c.lon, w, h, buildings: r.buildings, tiles: r.tiles, built: new Date().toISOString(),
    }), { level: 9 });
    fs.writeFileSync(path.join(DIR, `${c.slug}.fpk.gz`), pack);
    built.set(c.slug, { ...c, w, h, buildings: r.buildings, bytes: pack.length, tiles: r.tiles, built: new Date().toISOString().slice(0, 10) });
    console.log(`${c.slug}: ${r.buildings} buildings, ${(pack.length / 1e6).toFixed(2)} MB, ${((Date.now() - t0) / 1000).toFixed(0)} s`);
  }
  // Keep the list's order; drop cities no longer listed.
  const out = { credit: D.CREDIT, cities: list.map(c => built.get(c.slug)).filter(Boolean) };
  fs.writeFileSync(indexFile, JSON.stringify(out, null, 1) + "\n");
}
main().catch(e => { console.error(e); process.exit(1); });
