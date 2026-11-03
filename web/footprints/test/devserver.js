// Local stand-in for the host: serves the page and runs api/*.js like a serverless host.
//   node web/footprints/test/devserver.js            -> http://localhost:8787
// With MOCK_STRIPE=1 it also answers Stripe calls itself and logs what would be sent,
// so the whole order flow can be tried without a Stripe account.
"use strict";
const http = require("http");
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "..");
const PORT = +process.env.PORT || 8787;
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml" };

if (process.env.MOCK_STRIPE) {
  process.env.STRIPE_SECRET_KEY = process.env.STRIPE_SECRET_KEY || "sk_test_mock";
  process.env.STRIPE_API_BASE = `http://localhost:${PORT}/__mock_stripe`;
}

function shim(res) {
  res.status = code => { res.statusCode = code; return res; };
  res.json = obj => { res.setHeader("Content-Type", "application/json"); res.end(JSON.stringify(obj)); return res; };
  return res;
}

http.createServer((req, res) => {
  shim(res);
  const url = new URL(req.url, `http://${req.headers.host}`);
  let body = "";
  req.on("data", c => body += c);
  req.on("end", async () => {
    if (url.pathname.startsWith("/__mock_stripe/")) {
      const params = new URLSearchParams(body);
      console.log("MOCK STRIPE", url.pathname, JSON.stringify(Object.fromEntries(params)));
      return res.status(200).json({ id: "cs_test_mock123456789", url: `http://localhost:${PORT}/thanks.html?order=cs_test_mock123456789` });
    }
    if (url.pathname.startsWith("/api/")) {
      const name = url.pathname.slice(5).replace(/[^a-z]/g, "");
      const file = path.join(ROOT, "api", name + ".js");
      if (!fs.existsSync(file)) return res.status(404).json({ error: "not found" });
      req.body = body && (req.headers["content-type"] || "").includes("json") ? JSON.parse(body) : body;
      delete require.cache[require.resolve(file)];
      try { return await require(file)(req, res); } catch (e) { console.error(e); return res.status(500).json({ error: "server error" }); }
    }
    const rel = url.pathname === "/" ? "index.html" : url.pathname.slice(1);
    const file = path.join(ROOT, path.normalize(rel));
    if (!file.startsWith(ROOT) || rel.startsWith("api") || !fs.existsSync(file)) { res.statusCode = 404; return res.end("not found"); }
    res.setHeader("Content-Type", TYPES[path.extname(file)] || "application/octet-stream");
    fs.createReadStream(file).pipe(res);
  });
}).listen(PORT, () => console.log(`Footprints shop on http://localhost:${PORT}`));
