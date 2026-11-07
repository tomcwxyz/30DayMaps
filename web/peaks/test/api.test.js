"use strict";
// node --test web/peaks/test/*.test.js
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const shopFile = path.join(os.tmpdir(), `peaks-shop-test-${process.pid}.json`);
fs.writeFileSync(shopFile, JSON.stringify({
  currency: "gbp", countries: ["GB"],
  sizes: { A3: { label: "A3 print", price: 2600 }, pano90: { label: "90 × 30 cm", price: 3000 }, pano75: { label: "75 × 25 cm", price: null } },
  shipping: { label: "Free UK delivery", price: 0 },
  digital: { label: "Digital file by email", price: 500, link_days: 30 },
}));
process.env.SHOP_JSON = shopFile;
process.env.STRIPE_SECRET_KEY = "sk_test_x";
process.env.SITE_URL = "https://peaks.example";

const P = require("../lib/polyline.js");
const { validateRecipe, routeMetadata, ROUTE_CHUNK } = require("../api/_recipe");
const checkout = require("../api/checkout");
const config = require("../api/config");
const download = require("../api/download");

const base = { place: "helvellyn", lat: 54.527, lon: -3.0164, name: "Helvellyn", region: "Lake District", style: "poster",
  theme: "paper", labels: true, details: true, title: "Helvellyn", subtitle: "54.5270° N", paper: "A3", orient: "portrait",
  width: 7, detail: 90, rows: 64, seen: "view:helvellyn-from-place-fell", dist: 10, facing: 262, fov: 130, reach: 32, route: 0 };

function res() {
  const r = { statusCode: 0, headers: {} };
  r.setHeader = (k, v) => { r.headers[k] = v; };
  r.status = c => { r.statusCode = c; return r; };
  r.json = b => { r.body = b; return r; };
  return r;
}
function stripe() {
  const sent = [];
  global.fetch = async (url, opts) => { sent.push(Object.fromEntries(new URLSearchParams(opts.body))); return { ok: true, json: async () => ({ url: "https://checkout.stripe.test/x" }) }; };
  return sent;
}
const round = Array.from({ length: 400 }, (_, i) => [54.53 + 0.01 * Math.sin(i / 60), -3.0 + 0.015 * Math.cos(i / 60) + i * 1e-5]);

test("polyline round-trips to about a metre", () => {
  const back = P.decode(P.encode(round));
  assert.strictEqual(back.length, round.length);
  for (let i = 0; i < round.length; i++) { assert.ok(Math.abs(back[i][0] - round[i][0]) < 1e-5); assert.ok(Math.abs(back[i][1] - round[i][1]) < 1e-5); }
});

test("fit thins a route until it fits", () => {
  const long = Array.from({ length: 20000 }, (_, i) => [54 + i * 1e-5 + 1e-4 * Math.sin(i), -3 + i * 2e-5]);
  const f = P.fit(long, 19200);
  assert.ok(f.encoded.length <= 19200 && f.points.length < long.length);
});

test("recipe: clean, bounded, and checked for the style", () => {
  const r = validateRecipe(base);
  assert.strictEqual(r.labels, 1); assert.strictEqual(r.place, "helvellyn");
  assert.ok(JSON.stringify(r).length <= 500);
  assert.throws(() => validateRecipe({ ...base, style: "cubist" }), /style/);
  assert.throws(() => validateRecipe({ ...base, paper: "pano90" }), /paper/);
  assert.throws(() => validateRecipe({ ...base, style: "panorama", paper: "A3" }), /paper/);
  assert.doesNotThrow(() => validateRecipe({ ...base, style: "panorama", paper: "pano90" }));
  assert.throws(() => validateRecipe({ ...base, title: "" }), /title/);
  assert.throws(() => validateRecipe({ ...base, width: 500 }), /range/);
  assert.throws(() => validateRecipe({ ...base, style: "skyline", route: 10 }), /skyline/);
  assert.strictEqual(validateRecipe({ ...base, place: "../../etc" }).place, "");
  assert.strictEqual(validateRecipe({ ...base, seen: "<script>" }).seen, "S");
});

test("route: must match the recipe, stay on the map and fit in Stripe", () => {
  const enc = P.encode(round);
  const r = validateRecipe({ ...base, route: round.length });
  const meta = routeMetadata(enc, r);
  assert.strictEqual(Object.values(meta).join(""), enc);
  assert.ok(Object.values(meta).every(v => v.length <= ROUTE_CHUNK));
  assert.throws(() => routeMetadata(enc, { ...r, route: 5 }), /damaged/);
  assert.throws(() => routeMetadata("", r), /missing/);
  assert.throws(() => routeMetadata(P.encode([[54, -3], [56, -3]]), { ...r, route: 2 }), /across/);
  assert.deepStrictEqual(routeMetadata(undefined, validateRecipe(base)), {});
});

test("checkout: print order carries recipe, shop and route; prices from shop.json", async () => {
  const sent = stripe(); const r = res();
  const enc = P.encode(round);
  await checkout({ method: "POST", body: { recipe: { ...base, route: round.length }, route: enc, product: "print" }, headers: {} }, r);
  assert.strictEqual(r.statusCode, 200);
  const p = sent[0];
  assert.strictEqual(p["metadata[shop]"], "peaks");
  assert.strictEqual(p["payment_intent_data[metadata][shop]"], "peaks");
  assert.strictEqual(p["line_items[0][price_data][unit_amount]"], "2600");
  assert.match(p["line_items[0][price_data][product_data][name]"], /^Peaks print: Helvellyn/);
  assert.match(p["line_items[0][price_data][product_data][description]"], /your route/);
  const chunks = Object.keys(p).filter(k => /^metadata\[route_\d+\]$/.test(k)).sort((a, b) => +a.match(/\d+/)[0] - +b.match(/\d+/)[0]);
  assert.strictEqual(chunks.map(k => p[k]).join(""), enc);
  assert.ok(!Object.keys(p).some(k => k.startsWith("payment_intent_data[metadata][route")));  // the payment keeps room for progress notes
  assert.ok(Object.keys(p).filter(k => k.startsWith("metadata[")).length <= 50);
});

test("checkout: a panorama sheet sells as a print when it has a price, else digital only", async () => {
  const sent = stripe();
  const pano = { ...base, style: "panorama", paper: "pano90" };
  let r = res(); await checkout({ method: "POST", body: { recipe: pano, product: "print" }, headers: {} }, r);
  assert.strictEqual(r.statusCode, 200);
  assert.strictEqual(sent[0]["line_items[0][price_data][unit_amount]"], "3000");
  assert.match(sent[0]["line_items[0][price_data][product_data][description]"], /panoramic/);
  r = res(); await checkout({ method: "POST", body: { recipe: { ...pano, paper: "pano75" }, product: "print" }, headers: {} }, r);
  assert.strictEqual(r.statusCode, 400);
  r = res(); await checkout({ method: "POST", body: { recipe: { ...pano, paper: "pano75" }, product: "digital" }, headers: {} }, r);
  assert.strictEqual(r.statusCode, 200);
  assert.throws(() => validateRecipe({ ...pano, paper: "pano60" }), /paper/);
});

test("config lists what's on sale and never the key", () => {
  const r = res(); config({}, r);
  assert.deepStrictEqual(Object.keys(r.body.sizes), ["A3", "pano90"]);
  assert.ok(!JSON.stringify(r.body).includes("sk_test"));
});

test("download links are checked the same way as footprints", async () => {
  process.env.DOWNLOAD_SECRET = "s3cret";
  const out = { headers: {}, setHeader(k, v) { this.headers[k] = v; }, end(b) { this.body = b; } };
  await download({ url: "/api/download?f=digital/pi_1-print.png&x=1&s=nope" }, out);
  assert.strictEqual(out.statusCode, 403);
  assert.match(out.body, /Peaks download/);
});
