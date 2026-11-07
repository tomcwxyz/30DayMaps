"use strict";
// GET /api/config: what the page may offer for sale. Never exposes the Stripe key.

function makeConfig({ loadShop, limits }) {
  return (req, res) => {
    const shop = loadShop();
    res.setHeader("Cache-Control", "no-store");
    res.status(200).json({
      open: shop.open,
      currency: shop.currency,
      sizes: shop.open ? shop.sizes : {},
      shipping: shop.open && shop.shipping ? { label: shop.shipping.label, price: shop.shipping.price } : null,
      digital: shop.open && shop.digital ? { label: shop.digital.label, price: shop.digital.price, linkDays: shop.digital.linkDays } : null,
      limits,
    });
  };
}

module.exports = { makeConfig };
