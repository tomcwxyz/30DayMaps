// Encoded polylines (Google's format, 5 decimal places, about a metre) for carrying a
// route inside a Stripe order, plus Douglas-Peucker thinning. Used by the page and the API.
(function (root) {
  "use strict";
  function encode(points) {
    let out = "", plat = 0, plon = 0;
    const put = v => { v = v < 0 ? ~(v << 1) : v << 1; while (v >= 0x20) { out += String.fromCharCode((0x20 | (v & 0x1f)) + 63); v >>= 5; } out += String.fromCharCode(v + 63); };
    for (const [lat, lon] of points) {
      const a = Math.round(lat * 1e5), b = Math.round(lon * 1e5);
      put(a - plat); put(b - plon); plat = a; plon = b;
    }
    return out;
  }
  function decode(str) {
    if (typeof str !== "string" || !/^[\x3f-\x7e]*$/.test(str)) throw new Error("Route data is damaged");
    const pts = []; let i = 0, lat = 0, lon = 0;
    const get = () => {
      let r = 0, s = 0, b;
      do { if (i >= str.length) throw new Error("Route data is damaged"); b = str.charCodeAt(i++) - 63; r |= (b & 0x1f) << s; s += 5; } while (b >= 0x20 && s < 35);
      return r & 1 ? ~(r >> 1) : r >> 1;
    };
    while (i < str.length) { lat += get(); lon += get(); pts.push([lat / 1e5, lon / 1e5]); }
    return pts;
  }
  // Keep the points that matter: drop any within `tol` metres of the line through its neighbours.
  function simplify(points, tol) {
    if (points.length < 3) return points.slice();
    const k = Math.cos(points[0][0] * Math.PI / 180) * 111320, m = 111320;
    const xy = points.map(([la, lo]) => [lo * k, la * m]);
    const keep = new Uint8Array(points.length); keep[0] = keep[points.length - 1] = 1;
    const stack = [[0, points.length - 1]];
    while (stack.length) {
      const [a, b] = stack.pop();
      const [ax, ay] = xy[a], [bx, by] = xy[b], dx = bx - ax, dy = by - ay, l2 = dx * dx + dy * dy;
      let worst = -1, at = -1;
      for (let i = a + 1; i < b; i++) {
        // distance to the segment (not the infinite line), so a loop's matching ends still work
        const t = l2 ? Math.max(0, Math.min(1, ((xy[i][0] - ax) * dx + (xy[i][1] - ay) * dy) / l2)) : 0;
        const d = Math.hypot(xy[i][0] - ax - t * dx, xy[i][1] - ay - t * dy);
        if (d > worst) { worst = d; at = i; }
      }
      if (worst > tol) { keep[at] = 1; stack.push([a, at], [at, b]); }
    }
    return points.filter((_, i) => keep[i]);
  }
  // Thinnest faithful version that encodes to at most maxChars.
  function fit(points, maxChars) {
    for (let tol = 1; tol < 2000; tol *= 1.5) {
      const s = simplify(points, tol), e = encode(s);
      if (e.length <= maxChars) return { points: s, encoded: e, tolerance: tol };
    }
    throw new Error("That route is too long to print");
  }
  const api = { encode, decode, simplify, fit };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Polyline = api;
})(typeof window !== "undefined" ? window : globalThis);
