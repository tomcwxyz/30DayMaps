"use strict";
// GET /api/download?f=<file>&x=<expiry>&s=<signature>: the links in digital-order emails.
//
// Print files live in a private Blob store. Each email link carries an expiry time and
// a signature made with DOWNLOAD_SECRET (shared with the GitHub workflow that sends the
// email), so links can't be forged or extended. A valid link gets a fresh one-hour
// download address from Blob and is redirected there.
//
// makeDownload({ brand, blob }) where blob() returns the @vercel/blob module (the site
// installs it; modules here can't resolve the site's node_modules).

const crypto = require("crypto");

function sign(secret, file, expiry) {
  return crypto.createHmac("sha256", secret).update(`${file}|${expiry}`).digest("base64url");
}

function makeDownload({ brand, blob }) {
  function page(res, code, text) {
    res.statusCode = code;
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    res.setHeader("Cache-Control", "no-store");
    res.end(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${brand} download</title><body style="font:16px/1.5 system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem">
<p>${text}</p><p>If you need a new link, reply to your order email.</p></body>`);
  }

  return async (req, res) => {
    const secret = process.env.DOWNLOAD_SECRET;
    if (!secret) return page(res, 501, "Downloads aren't set up yet.");
    const q = Object.fromEntries(new URL(req.url, "http://x").searchParams);
    const file = q.f || "", expiry = Number(q.x), given = q.s || "";
    if (!/^digital\/[A-Za-z0-9_-]+-print\.(png|pdf)$/.test(file) || !Number.isInteger(expiry)) return page(res, 400, "That download link isn't complete.");
    const expected = sign(secret, file, expiry);
    const a = Buffer.from(given), b = Buffer.from(expected);
    if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return page(res, 403, "That download link isn't valid.");
    if (expiry * 1000 < Date.now()) return page(res, 410, "That download link has expired.");
    try {
      const validUntil = Date.now() + 3600 * 1000;
      const api = blob();
      const signed = await api.issueSignedToken({ pathname: file, operations: ["get"], validUntil });
      const { presignedUrl } = await api.presignUrl(signed, { operation: "get", pathname: file, access: "private", validUntil });
      res.statusCode = 302;
      res.setHeader("Location", presignedUrl);
      res.setHeader("Cache-Control", "no-store");
      return res.end();
    } catch (e) {
      console.error("download failed:", e && e.name, e && e.message);
      return page(res, 404, "That file is no longer available.");
    }
  };
}

module.exports = { makeDownload, sign };
