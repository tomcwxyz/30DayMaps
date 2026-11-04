"use strict";
const test = require("node:test");
const assert = require("node:assert");
const webhook = require("../api/stripe-webhook");

function fakeRes() {
  const res = { statusCode: 0, headers: {}, body: null };
  res.setHeader = (k, v) => { res.headers[k] = v; };
  res.end = text => { res.body = JSON.parse(text); };
  return res;
}
const paid = { id: "evt_1", type: "checkout.session.completed",
  data: { object: { id: "cs_test_abc", payment_status: "paid", metadata: { recipe: "{}" } } } };

function withFetch(handler) {
  const calls = [];
  global.fetch = async (url, opts = {}) => { calls.push({ url, opts }); return handler(url, opts); };
  return calls;
}
const reply = (status, body) => ({ status, ok: status >= 200 && status < 300, json: async () => body });

test.beforeEach(() => {
  process.env.STRIPE_SECRET_KEY = "sk_test_x";
  process.env.GITHUB_TOKEN = "ghp_x";
  process.env.GITHUB_REPO = "owner/repo";
});

test("a paid order starts the print workflow with only the session ID", async () => {
  const calls = withFetch(url => url.includes("/v1/events/") ? reply(200, paid) : reply(204, null));
  const res = fakeRes();
  await webhook({ method: "POST", body: { id: "evt_1", type: "forged", data: { object: { id: "cs_live_evil" } } } }, res);
  assert.strictEqual(res.statusCode, 200);
  assert.match(calls[0].url, /\/v1\/events\/evt_1$/);
  assert.match(calls[1].url, /\/repos\/owner\/repo\/actions\/workflows\/fulfil\.yml\/dispatches$/);
  assert.deepStrictEqual(JSON.parse(calls[1].opts.body), { ref: "main", inputs: { session: "cs_test_abc" } });
});

test("uses Stripe's copy of the event, not the posted body", async () => {
  withFetch(url => url.includes("/v1/events/") ? reply(200, { ...paid, type: "charge.refunded" }) : reply(204, null));
  const res = fakeRes();
  await webhook({ method: "POST", body: paid }, res);
  assert.deepStrictEqual(res.body, { ignored: "charge.refunded" });
});

test("unpaid sessions and non-shop payments are ignored", async () => {
  const unpaid = { ...paid, data: { object: { ...paid.data.object, payment_status: "unpaid" } } };
  const calls = withFetch(() => reply(200, unpaid));
  const res = fakeRes();
  await webhook({ method: "POST", body: { id: "evt_1" } }, res);
  assert.strictEqual(res.statusCode, 200);
  assert.strictEqual(calls.length, 1);
});

test("bad or unknown event IDs are refused", async () => {
  withFetch(() => reply(404, {}));
  for (const body of [{ id: "../../charges" }, {}, "not json", { id: "evt_404" }]) {
    const res = fakeRes();
    await webhook({ method: "POST", body }, res);
    assert.strictEqual(res.statusCode, 400);
  }
});

test("a failed GitHub call asks Stripe to retry", async () => {
  withFetch(url => url.includes("/v1/events/") ? reply(200, paid) : reply(401, {}));
  const res = fakeRes();
  await webhook({ method: "POST", body: { id: "evt_1" } }, res);
  assert.strictEqual(res.statusCode, 502);
});

test("does nothing until configured", async () => {
  delete process.env.GITHUB_TOKEN;
  const res = fakeRes();
  await webhook({ method: "POST", body: { id: "evt_1" } }, res);
  assert.strictEqual(res.statusCode, 503);
});
