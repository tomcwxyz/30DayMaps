// node --test web/footprints/test
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const { validateRecipe } = require("../api/_recipe");

const good = { lat: 54.97383333, lon: -1.6132, name: "Newcastle", title: "Home", subtitle: "Where\nwe met",
  kicker: "", paper: "A3", orient: "landscape", width_km: 4.53, theme: "night", source: "os", price: 1 };

test("cleans and rounds a good design", () => {
  const r = validateRecipe(good);
  assert.deepStrictEqual(r, { v: 1, lat: 54.97383, lon: -1.6132, name: "Newcastle", title: "Home",
    subtitle: "Where we met", kicker: "", paper: "A3", orient: "landscape", width_km: 4.5, theme: "night", source: "osm" });
});
test("ignores anything extra the browser sends, like a price", () => {
  assert.ok(!("price" in validateRecipe(good)));
});
for (const [what, change] of [["bad paper", { paper: "A0" }], ["bad theme", { theme: "neon" }],
  ["no title", { title: "  " }], ["long title", { title: "x".repeat(61) }],
  ["long subtitle", { subtitle: "x".repeat(141) }], ["wide", { width_km: 25 }], ["lat", { lat: "north" }],
  ["object text", { title: { a: 1 } }]]) {
  test(`refuses ${what}`, () => assert.throws(() => validateRecipe({ ...good, ...change })));
}
test("worst case still fits Stripe's 500 character metadata", () => {
  const r = validateRecipe({ ...good, name: "n".repeat(60), title: "t".repeat(60), subtitle: "s".repeat(140), kicker: "k".repeat(40) });
  assert.ok(JSON.stringify(r).length <= 500);
});
