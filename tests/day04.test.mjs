import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { greatCircleKm, clusterNearby } from "../web/day04/clusters.js";
import { getPhase } from "../web/day04/flock.js";
import { roosts, sources, conservationLinks } from "../web/day04/roosts.js";

test("curated sites carry valid, distinct indicative coordinates and named sources", () => {
  assert.ok(roosts.length >= 15);
  assert.equal(new Set(roosts.map(x => x.id)).size, roosts.length);
  for (const point of roosts) {
    assert.match(point.name, /\w/);
    assert.ok(point.lat >= 49 && point.lat <= 59, point.name + " latitude out of bounds");
    assert.ok(point.lon >= -8.5 && point.lon <= 2.5, point.name + " longitude out of bounds");
    assert.ok(sources[point.source]?.startsWith("https://"), point.name + " missing source");
    assert.ok(["wetland", "coast"].includes(point.habitat));
  }
});

test("distance is symmetric, zero at identity, and about 111 km per latitude degree", () => {
  const a = { lat: 52, lon: 0 }, b = { lat: 53, lon: 0 };
  assert.equal(greatCircleKm(a, a), 0);
  assert.ok(Math.abs(greatCircleKm(a, b) - 111.2) < 1);
  assert.ok(Math.abs(greatCircleKm(b, a) - greatCircleKm(a, b)) < .000001);
});

test("clustering keeps isolated sites, groups connected neighbours, does not change input", () => {
  const spots = [{ name: "A", lat: 52, lon: 0 }, { name: "B", lat: 52.2, lon: 0 },
    { name: "C", lat: 52.4, lon: 0 }, { name: "D", lat: 54, lon: 0 }];
  const original = JSON.stringify(spots);
  const groups = clusterNearby(spots, 30);
  assert.deepEqual(groups.map(c => c.sites.length), [3, 1]);
  assert.equal(JSON.stringify(spots), original);
  assert.equal(clusterNearby(spots, 0).length, 4);
  assert.throws(() => clusterNearby(spots, -2), RangeError);
});

test("the mapped site list cannot be misread as bird abundance", () => {
  assert.ok(roosts.every(r => !("count" in r) && !("birds" in r) && !("current" in r)));
  const page = readFileSync(new URL("../web/day04/index.html", import.meta.url), "utf8");
  assert.match(page, /not all UK roosts/);
  assert.match(page, /SIMULATED FLOCK/);
  assert.match(page, /not tracked birds|not a reconstruction/i);
  assert.match(page, /siteCount/);
});

test("flocking phases progress from scattered to roost and reduced-motion is supported", () => {
  assert.equal(getPhase(0).title, "Scattered");
  assert.equal(getPhase(57).title, "Murmuration");
  assert.equal(getPhase(99).title, "Roost");
  const js = readFileSync(new URL("../web/day04/flock.js", import.meta.url), "utf8");
  assert.match(js, /prefers-reduced-motion: reduce/);
  assert.match(js, /cancelAnimationFrame/);
});

test("conservation actions use accessible, external, trustworthy links", () => {
  assert.equal(conservationLinks.length, 4);
  for (const item of conservationLinks) {
    assert.ok(item.label && item.detail);
    assert.match(item.href, /^https:\/\/(www\.)?(rspb\.org\.uk|starlingsintheuk\.co\.uk)\//);
  }
});
