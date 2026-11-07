"use strict";
const fs = require("fs");
const path = require("path");
const { shopFrom } = require("../../shop/shop");

function loadShop() {
  const file = process.env.SHOP_JSON || path.join(__dirname, "..", "shop.json");  // override for local tests
  return shopFrom(JSON.parse(fs.readFileSync(file, "utf8")));
}

module.exports = { loadShop };
