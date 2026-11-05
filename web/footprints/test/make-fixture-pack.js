// Writes tests/fixtures/sample.fpk.gz, a tiny pack the Python reader is tested against.
//   node web/footprints/test/make-fixture-pack.js
"use strict";
const fs = require("fs"), path = require("path"), zlib = require("zlib");
const D = require("../lib/footprints-data.js");
const rings = [
  [[-100, -100], [100, -100], [100, 100], [-100, 100]],          // outer ring
  [[-40, -40], [-40, 40], [40, 40], [40, -40]],                  // courtyard, opposite winding
  [[900, 0], [1300, 0], [1300, 50], [900, 50]],                   // crosses the pack edge at x = 1000
];
const pack = D.encodePack(rings, { name: "Fixture", lat: 54.97, lon: -1.61, w: 2000, h: 1000, buildings: 2 });
fs.writeFileSync(path.join(__dirname, "../../../tests/fixtures/sample.fpk.gz"), zlib.gzipSync(pack));
