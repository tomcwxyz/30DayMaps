"use strict";
// GET /api/config: what the page may offer for sale. Never exposes the Stripe key.
const { loadShop } = require("./_shop");
const { LIMITS } = require("./_recipe");
const { makeConfig } = require("../../shop/config");

module.exports = makeConfig({ loadShop, limits: LIMITS });
