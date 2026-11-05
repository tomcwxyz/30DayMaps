/* Shared geodesy for Day 05 wildlife. Pure functions, usable in browser and Node. */
(function (root) {
  "use strict";
  function circlePolygon(lon, lat, radiusKm, sides = 36) {
    if (![lon, lat, radiusKm].every(Number.isFinite) || lat < -85 || lat > 85 ||
        lon < -180 || lon > 180 || radiusKm <= 0 || radiusKm > 100 || sides < 12) {
      throw new Error("Invalid location or radius. Choose a location in Britain and a distance up to 100 km.");
    }
    const earthKm = 6371.0088;
    const distance = radiusKm / earthKm;
    const latitude = lat * Math.PI / 180;
    const longitude = lon * Math.PI / 180;
    const points = [];
    for (let i = 0; i <= sides; i++) {
      const bearing = 2 * Math.PI * i / sides;
      const destLat = Math.asin(Math.sin(latitude) * Math.cos(distance) +
        Math.cos(latitude) * Math.sin(distance) * Math.cos(bearing));
      const destLon = longitude + Math.atan2(
        Math.sin(bearing) * Math.sin(distance) * Math.cos(latitude),
        Math.cos(distance) - Math.sin(latitude) * Math.sin(destLat)
      );
      points.push([destLon * 180 / Math.PI, destLat * 180 / Math.PI]);
    }
    // Exterior ring is anti-clockwise as required by GBIF's geospatial search.
    points.reverse();
    return "POLYGON((" + points.map(p => p[0].toFixed(6) + " " + p[1].toFixed(6)).join(",") + "))";
  }
  const api = { circlePolygon };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.SightGeo = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
