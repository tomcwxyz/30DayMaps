"use strict";
const fs = require("fs");
const path = require("path");

function loadShop() {
  const file = process.env.SHOP_JSON || path.join(__dirname, "..", "shop.json");  // override for local tests
  const shop = JSON.parse(fs.readFileSync(file, "utf8"));
  const sizes = {};
  for (const [key, s] of Object.entries(shop.sizes || {})) {
    if (Number.isInteger(s.price) && s.price > 0) sizes[key] = { label: s.label, price: s.price };
  }
  const shipping = Number.isInteger(shop.shipping?.price) && shop.shipping.price >= 0 ? shop.shipping : null;
  return {
    currency: shop.currency || "gbp",
    countries: shop.countries || ["GB"],
    sizes, shipping, note: shop.note || "",
    // Open for orders only with a Stripe key, at least one priced size and a delivery price.
    open: Boolean(process.env.STRIPE_SECRET_KEY) && Object.keys(sizes).length > 0 && shipping !== null,
  };
}

module.exports = { loadShop };
