const { test } = require('node:test');
const assert = require('node:assert/strict');
const { circlePolygon } = require('../web/day05-wildlife/geo.js');

function coords(wkt) {
  assert.match(wkt, /^POLYGON\(\(/);
  return wkt.slice(9, -2).split(',').map(pair => pair.trim().split(/\s+/).map(Number));
}
function distanceKm(a, b) {
  const rad = Math.PI / 180, latA = a[1] * rad, latB = b[1] * rad;
  const dlat = (b[1] - a[1]) * rad, dlon = (b[0] - a[0]) * rad;
  return 6371.0088 * 2 * Math.asin(Math.sqrt(Math.sin(dlat / 2) ** 2 +
    Math.cos(latA) * Math.cos(latB) * Math.sin(dlon / 2) ** 2));
}
test('polygon is closed, well formed and counter-clockwise', () => {
  const points = coords(circlePolygon(-1.578, 54.617, 5));
  assert.equal(points.length, 37);
  assert.deepEqual(points[0], points.at(-1));
  const twiceArea = points.slice(0, -1).reduce((sum, p, i) => {
    const q = points[i + 1];
    return sum + p[0] * q[1] - q[0] * p[1];
  }, 0);
  assert.ok(twiceArea > 0, 'exterior ring must be CCW');
});
test('locations on boundary are the requested radius from centre', () => {
  const centre = [-1.578, 54.617];
  for (const km of [1, 3, 5, 10]) {
    const points = coords(circlePolygon(centre[0], centre[1], km));
    for (const p of points.slice(0, -1)) {
      assert.ok(Math.abs(distanceKm(centre, p) - km) < 0.002,
        'boundary needs to match radius to within 2m');
    }
  }
});
test('changes in location and radius change the output', () => {
  assert.notEqual(circlePolygon(-1.578, 54.617, 1), circlePolygon(-1.578, 54.617, 10));
  assert.notEqual(circlePolygon(-1.578, 54.617, 5), circlePolygon(-3.202, 54.527, 5));
});
test('rejects invalid radii or positions', () => {
  for (const v of [0, -1, Infinity, NaN, 101]) assert.throws(() => circlePolygon(-1, 54, v));
  assert.throws(() => circlePolygon(-1, 90, 5));
});
