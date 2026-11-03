/** Pure, dependency-free geographic clustering; radius is in kilometres. */
export function greatCircleKm(a, b) {
  const toRadians = n => n * Math.PI / 180;
  const p1 = toRadians(a.lat), p2 = toRadians(b.lat);
  const dp = p2 - p1, dl = toRadians(b.lon - a.lon);
  const t = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 6371.0088 * 2 * Math.atan2(Math.sqrt(t), Math.sqrt(Math.max(0, 1 - t)));
}
export function clusterNearby(sites, radiusKm) {
  if (!Number.isFinite(radiusKm) || radiusKm < 0) throw new RangeError("radius must be non-negative");
  const result = [], visited = new Set();
  for (let i = 0; i < sites.length; i++) {
    if (visited.has(i)) continue;
    const stack = [i], members = [];
    visited.add(i);
    while (stack.length) {
      const j = stack.pop();
      members.push(sites[j]);
      for (let k = 0; k < sites.length; k++) {
        if (visited.has(k)) continue;
        if (greatCircleKm(sites[j], sites[k]) <= radiusKm) {
          visited.add(k);
          stack.push(k);
        }
      }
    }
    const lat = members.reduce((sum, p) => sum + p.lat, 0) / members.length;
    const lon = members.reduce((sum, p) => sum + p.lon, 0) / members.length;
    result.push({ sites: members, lat, lon });
  }
  return result.sort((a, b) => b.sites.length - a.sites.length || a.sites[0].name.localeCompare(b.sites[0].name));
}
