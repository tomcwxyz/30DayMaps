"use strict";
// POST /api/checkout {recipe, route?, product}: see web/shop/checkout.js. A GPX route
// goes in the Checkout session's metadata (route_0, route_1, …) so Stripe holds the
// whole order and nothing the customer uploads is stored anywhere else.
const { loadShop } = require("./_shop");
const { validateRecipe, routeMetadata } = require("./_recipe");
const { makeCheckout } = require("../../shop/checkout");

const STYLE = { poster: "poster", contours: "contours", ridgelines: "ridgelines", skyline: "skyline", panorama: "panorama" };

module.exports = makeCheckout({
  shop: "peaks",
  loadShop,
  order(body) {
    const recipe = validateRecipe(body.recipe);
    return { recipe, place: recipe.name, paper: recipe.paper, sessionMetadata: routeMetadata(body.route, recipe) };
  },
  printName: r => `Peaks print: ${r.title}`,
  printDescription: (r, size) => `${size.label}, ${r.style === "panorama" ? "panoramic" : r.orient} · ${STYLE[r.style]} · ${r.theme} colours${r.route ? " · your route" : ""}${r.runner ? ` · ${r.runner}` : ""} · ${r.name}`,
  digitalName: r => `Peaks digital print: ${r.title}`,
  digitalDescription: r => `High-resolution PNG (sharp printed up to A2) and a PDF that scales to any size, by email · ${STYLE[r.style]} · ${r.name}`,
});
