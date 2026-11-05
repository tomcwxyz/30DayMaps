#!/usr/bin/env node
/* Copies pinned, published open-source map libraries into static site folders.
 * Does not install dependencies or contact the network.
 *
 * npm install --no-save leaflet@1.9.4 maplibre-gl@5.9.0
 * node scripts/prepare_day05_vendor.cjs web
 * python -m http.server 8000
 *
 * In Pages CI use: node scripts/prepare_day05_vendor.cjs _site
 */
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const output = path.resolve(process.argv[2] || "web");
const root = process.cwd();
function copy(pkg, filename, relativeTarget) {
  const src = path.join(root, "node_modules", pkg, "dist", filename);
  const dest = path.join(output, relativeTarget);
  if (!fs.existsSync(src)) throw new Error("Required pinned dependency missing: " + src);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.cpSync(src, dest, { recursive: true, force: true });
  console.log("Vendor " + src + " -> " + dest);
}
copy("leaflet", "leaflet.js", "day05-wildlife/vendor/leaflet.js");
copy("leaflet", "leaflet.css", "day05-wildlife/vendor/leaflet.css");
copy("leaflet", "images", "day05-wildlife/vendor/images");
copy("maplibre-gl", "maplibre-gl.js", "day05-dale-head/vendor/maplibre-gl.js");
copy("maplibre-gl", "maplibre-gl.css", "day05-dale-head/vendor/maplibre-gl.css");

for (const [pkg, target] of [
  ["leaflet", "day05-wildlife/vendor/LICENCE.txt"],
  ["maplibre-gl", "day05-dale-head/vendor/LICENCE.txt"]
]) {
  const rootPackage = path.join(root, "node_modules", pkg);
  const filename = ["LICENSE", "LICENSE.txt", "LICENSE.md", "LICENCE"]
    .find(name => fs.existsSync(path.join(rootPackage, name)));
  if (!filename) {
    console.warn("Library licence file not found in npm package: " + pkg);
    continue;
  }
  const destination = path.join(output, target);
  fs.copyFileSync(path.join(rootPackage, filename), destination);
}
