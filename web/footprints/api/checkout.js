"use strict";
// POST /api/checkout {recipe, product}: see web/shop/checkout.js.
const { loadShop } = require("./_shop");
const { validateRecipe } = require("./_recipe");
const { makeCheckout } = require("../../shop/checkout");

module.exports = makeCheckout({
  loadShop,
  order(body) {
    const recipe = validateRecipe(body.recipe);
    return { recipe, place: recipe.name, paper: recipe.paper };
  },
  printName: r => `Footprints print: ${r.title}`,
  printDescription: (r, size) => `${size.label}, ${r.orient} · ${r.theme} colours · ${r.width_km} km across · ${r.name}`,
  digitalName: r => `Footprints digital print: ${r.title}`,
  digitalDescription: r => `High-resolution PNG (sharp printed up to A2) and a PDF that scales to any size, by email · ${r.name}`,
});
