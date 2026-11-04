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
  const d = shop.digital || {};
  const digital = Number.isInteger(d.price) && d.price > 0
    ? { label: d.label || "Digital file by email", price: d.price, linkDays: d.link_days || 30 } : null;
  // Printed copies need at least one priced size and a delivery price.
  const printOpen = Object.keys(sizes).length > 0 && shipping !== null;
  return {
    currency: shop.currency || "gbp",
    countries: shop.countries || ["GB"],
    sizes: printOpen ? sizes : {}, shipping: printOpen ? shipping : null, digital,
    note: shop.note || "", digitalNote: shop.digital_note || "",
    // Open for orders only with a Stripe key and something priced to sell.
    open: Boolean(process.env.STRIPE_SECRET_KEY) && (printOpen || digital !== null),
  };
}

module.exports = { loadShop };
