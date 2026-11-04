"use strict";
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const shopFile = path.join(os.tmpdir(), `shop-test-${process.pid}.json`);
function writeShop(over = {}) {
  fs.writeFileSync(shopFile, JSON.stringify({
    currency: "gbp", countries: ["GB"],
    sizes: { A3: { label: "A3 print", price: 3500 }, A2: { label: "A2 print", price: null } },
    shipping: { label: "UK delivery", price: 500 },
    digital: { label: "Digital file by email", price: 500, link_days: 30 },
    note: "print note", digital_note: "digital note", ...over,
  }));
}
process.env.SHOP_JSON = shopFile;
process.env.STRIPE_SECRET_KEY = "sk_test_x";
process.env.SITE_URL = "https://shop.example";
const checkout = require("../api/checkout");
const config = require("../api/config");

const recipe = { lat: 54.97, lon: -1.61, name: "Heaton", title: "Home", subtitle: "", kicker: "",
  paper: "A2", orient: "portrait", width_km: 3, theme: "night" };
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

test("digital file: £5, any size, no address, consent note, product saved", async () => {
  writeShop(); const sent = stripe(); const r = res();
  await checkout({ method: "POST", body: { recipe, product: "digital" }, headers: {} }, r);
  assert.strictEqual(r.statusCode, 200);
  const p = sent[0];
  assert.strictEqual(p["line_items[0][price_data][unit_amount]"], "500");
  assert.match(p["line_items[0][price_data][product_data][name]"], /digital print: Home/);
  assert.ok(!Object.keys(p).some(k => k.startsWith("shipping")));
  assert.strictEqual(p["custom_text[submit][message]"], "digital note");
  assert.strictEqual(p["metadata[product]"], "digital");
  assert.strictEqual(p["payment_intent_data[metadata][product]"], "digital");
  assert.match(p.success_url, /type=digital$/);
});

test("printed copy still needs a priced size and collects an address", async () => {
  writeShop(); const sent = stripe(); let r = res();
  await checkout({ method: "POST", body: { recipe, product: "print" }, headers: {} }, r);
  assert.strictEqual(r.statusCode, 400);  // A2 isn't priced
  r = res();
  await checkout({ method: "POST", body: { recipe: { ...recipe, paper: "A3" } }, headers: {} }, r);
  assert.strictEqual(r.statusCode, 200);
  assert.strictEqual(sent[0]["metadata[product]"], "print");
  assert.strictEqual(sent[0]["shipping_address_collection[allowed_countries][0]"], "GB");
});

test("unknown products and switched-off digital are refused", async () => {
  writeShop({ digital: { price: null } }); stripe(); let r = res();
  await checkout({ method: "POST", body: { recipe, product: "digital" }, headers: {} }, r);
  assert.strictEqual(r.statusCode, 400);
  r = res();
  await checkout({ method: "POST", body: { recipe, product: "free" }, headers: {} }, r);
  assert.strictEqual(r.statusCode, 400);
});

test("a digital-only shop is open and offers no printed sizes", async () => {
  writeShop({ shipping: { label: "UK", price: null } }); const r = res();
  config({}, r);
  assert.strictEqual(r.body.open, true);
  assert.deepStrictEqual(r.body.sizes, {});
  assert.deepStrictEqual(r.body.digital, { label: "Digital file by email", price: 500, linkDays: 30 });
});
