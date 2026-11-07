"use strict";
// GET /api/download: signed links from digital-order emails. See web/shop/download.js.
const { makeDownload, sign } = require("../../shop/download");

module.exports = makeDownload({ brand: "Footprints", blob: () => module.exports._blob || require("@vercel/blob") });
module.exports.sign = sign;
