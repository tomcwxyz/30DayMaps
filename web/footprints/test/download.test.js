"use strict";
const test = require("node:test");
const assert = require("node:assert");
const dl = require("../api/download.js");

function res() {
  const r = { statusCode: 0, headers: {} };
  r.setHeader = (k, v) => { r.headers[k] = v; };
  r.end = b => { r.body = b; };
  return r;
}
const file = "digital/pi_3Abc123-print.png";
const later = Math.floor(Date.now() / 1000) + 3600;
const link = (f, x, s) => `/api/download?${new URLSearchParams({ f, x: String(x), s })}`;

test.beforeEach(() => {
  process.env.DOWNLOAD_SECRET = "test-secret";
  dl._blob = {
    issueSignedToken: async o => ({ delegationToken: "d", clientSigningToken: "c", validUntil: o.validUntil, pathname: o.pathname }),
    presignUrl: async (t, o) => ({ presignedUrl: `https://store.private.blob.test/${o.pathname}?sig=1` }),
  };
});

test("a valid link redirects to a fresh short-lived download", async () => {
  const r = res();
  await dl({ url: link(file, later, dl.sign("test-secret", file, later)) }, r);
  assert.strictEqual(r.statusCode, 302);
  assert.strictEqual(r.headers.Location, `https://store.private.blob.test/${file}?sig=1`);
});

test("forged, altered, expired and outside-folder links are refused", async () => {
  const cases = [
    [link(file, later, "forged"), 403],
    [link("digital/pi_3Abc123-print.pdf", later, dl.sign("test-secret", file, later)), 403],   // signature is for another file
    [link(file, later + 999999, dl.sign("test-secret", file, later)), 403],                    // expiry extended
    [link(file, 1000, dl.sign("test-secret", file, 1000)), 410],                               // expired
    [link("orders/pi_1-print.png", later, dl.sign("test-secret", "orders/pi_1-print.png", later)), 400],  // not a digital file
  ];
  for (const [url, code] of cases) {
    const r = res();
    await dl({ url }, r);
    assert.strictEqual(r.statusCode, code, url);
  }
});

test("matches the signature the Python fulfilment makes", () => {
  // maps/fulfil.py download_link() signs "file|expiry" with HMAC-SHA256, base64url without padding
  assert.strictEqual(dl.sign("k", "digital/pi_1-print.png", 1700000000), "oHmjMTwLso0H9eIenufXhz0F-pXfGGhDgUG-pxljm2s");
});

test("off until the secret is set", async () => {
  delete process.env.DOWNLOAD_SECRET;
  const r = res();
  await dl({ url: link(file, later, "x") }, r);
  assert.strictEqual(r.statusCode, 501);
});
