"use strict";
// GET /api/config: what the page may offer for sale. Never exposes the Stripe key.
const { loadShop } = require("./_shop");
const { LIMITS } = require("./_recipe");

module.exports = (req, res) => {
  const shop = loadShop();
  res.setHeader("Cache-Control", "no-store");
  res.status(200).json({
    open: shop.open,
    currency: shop.currency,
    sizes: shop.open ? shop.sizes : {},
    shipping: shop.open ? { label: shop.shipping.label, price: shop.shipping.price } : null,
    limits: LIMITS,
  });
};
