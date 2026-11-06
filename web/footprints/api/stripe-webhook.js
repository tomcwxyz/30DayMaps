"use strict";
// POST /api/stripe-webhook: Stripe calls this when a payment completes.
//
// Rather than trusting the posted body, it re-fetches the event from Stripe with the
// secret key, so a forged call can't start a print. For a paid shop order it starts the
// "Print order" GitHub workflow with the Checkout session ID, and nothing else: the
// workflow looks the order up in Stripe itself. Repeat calls are harmless, because the
// workflow checks whether the order has already gone to print.

const HANDLED = new Set(["checkout.session.completed", "checkout.session.async_payment_succeeded"]);

function send(res, code, obj) {
  res.statusCode = code;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(obj));
}

async function readJson(req) {
  if (req.body && typeof req.body === "object" && !Buffer.isBuffer(req.body)) return req.body;
  let text = typeof req.body === "string" ? req.body : Buffer.isBuffer(req.body) ? req.body.toString("utf8") : null;
  if (text == null) {
    text = await new Promise((resolve, reject) => {
      let data = "";
      req.on("data", c => { data += c; });
      req.on("end", () => resolve(data));
      req.on("error", reject);
    });
  }
  return JSON.parse(text || "{}");
}

module.exports = async (req, res) => {
  // One log line per call (status and outcome only, never order details) so a missing
  // order can be traced in Vercel's logs.
  const reply = (code, obj) => { console.log(`stripe-webhook ${code} ${JSON.stringify(obj)}`); return send(res, code, obj); };
  if (req.method !== "POST") { res.setHeader("Allow", "POST"); return reply(405, { error: "Use POST" }); }
  const key = process.env.STRIPE_SECRET_KEY;
  const github = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO || "tomcwxyz/30DayMaps";
  if (!key || !github) return reply(503, { error: "Order processing isn't set up", missing: [!key && "STRIPE_SECRET_KEY", !github && "GITHUB_TOKEN"].filter(Boolean) });

  let id;
  try { id = (await readJson(req)).id; } catch { return reply(400, { error: "Bad request" }); }
  if (typeof id !== "string" || !/^evt_[A-Za-z0-9]+$/.test(id)) return reply(400, { error: "Bad request" });

  const stripeBase = process.env.STRIPE_API_BASE || "https://api.stripe.com";
  let event;
  try {
    const r = await fetch(`${stripeBase}/v1/events/${id}`, { headers: { Authorization: `Bearer ${key}` } });
    if (r.status === 404) return reply(400, { error: "Unknown event" });
    if (!r.ok) throw new Error(`Stripe ${r.status}`);
    event = await r.json();
  } catch (e) {
    console.error("Couldn't check event with Stripe:", e.message);
    return reply(502, { error: "Try again" });  // Stripe retries
  }

  if (!HANDLED.has(event.type)) return reply(200, { ignored: event.type });
  const session = event.data && event.data.object;
  if (!session || session.payment_status !== "paid" || !session.metadata || !session.metadata.recipe) {
    return reply(200, { ignored: "not a paid shop order" });
  }

  const githubBase = process.env.GITHUB_API_BASE || "https://api.github.com";
  try {
    const r = await fetch(`${githubBase}/repos/${repo}/actions/workflows/fulfil.yml/dispatches`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${github}`, Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json", "User-Agent": "footprints-shop",
      },
      body: JSON.stringify({ ref: process.env.PRINT_WORKFLOW_BRANCH || "main", inputs: { session: session.id } }),
    });
    if (r.status !== 204) throw new Error(`GitHub ${r.status} ${(await r.text()).slice(0, 200)}`);
  } catch (e) {
    console.error("Couldn't start the print job:", e.message);
    return reply(502, { error: "Try again" });  // Stripe retries for up to three days
  }
  return reply(200, { started: true });
};
