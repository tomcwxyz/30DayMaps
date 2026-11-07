"use strict";
// POST /api/checkout {recipe, product, ...}: checks the design, prices it from shop.json
// (never from the browser) and returns a Stripe Checkout URL. The recipe rides along in
// the payment's metadata, so each paid order in Stripe carries everything needed to print it.
//
// makeCheckout(site) where site = {
//   loadShop(): shopFrom(...) result
//   order(body): { recipe (clean object), place, paper, sessionMetadata? } or throws Error(message for customers)
//   printName(recipe), printDescription(recipe, size), digitalName(recipe), digitalDescription(recipe)
//   shop?: name saved on the order so fulfilment knows which shop it's from (omitted = footprints)
// }

function form(obj, prefix, out = new URLSearchParams()) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}[${k}]` : k;
    if (v === undefined || v === null) continue;
    if (Array.isArray(v)) v.forEach((item, i) => typeof item === "object"
      ? form(item, `${key}[${i}]`, out) : out.append(`${key}[${i}]`, String(item)));
    else if (typeof v === "object") form(v, key, out);
    else out.append(key, String(v));
  }
  return out;
}

function originOf(req) {
  if (process.env.SITE_URL) return process.env.SITE_URL.replace(/\/$/, "");
  const proto = req.headers["x-forwarded-proto"] || "https";
  return `${proto}://${req.headers["x-forwarded-host"] || req.headers.host}`;
}

function makeCheckout(site) {
  return async (req, res) => {
    if (req.method !== "POST") { res.setHeader("Allow", "POST"); return res.status(405).json({ error: "Use POST" }); }
    const shop = site.loadShop();
    if (!shop.open) return res.status(503).json({ error: "The shop isn't open yet." });

    let o, product;
    try {
      const body = typeof req.body === "string" ? JSON.parse(req.body) : req.body;
      o = site.order(body || {});
      product = (body && body.product) || "print";
      if (product !== "print" && product !== "digital") throw new Error("Choose a printed copy or a digital file");
    } catch (e) {
      return res.status(400).json({ error: e.message });
    }
    const { recipe } = o;
    const siteUrl = originOf(req);
    const recipeJson = JSON.stringify(recipe);
    const tag = site.shop ? { shop: site.shop } : {};
    const common = {
      mode: "payment",
      cancel_url: `${siteUrl}/`,
      phone_number_collection: { enabled: false },
      metadata: { recipe: recipeJson, product, place: o.place, paper: o.paper, ...tag, ...(o.sessionMetadata || {}) },
      payment_intent_data: { metadata: { recipe: recipeJson, product, ...tag } },
    };
    let order;
    if (product === "digital") {
      if (!shop.digital) return res.status(400).json({ error: "Digital files aren't for sale at the moment." });
      order = {
        ...common,
        success_url: `${siteUrl}/thanks.html?order={CHECKOUT_SESSION_ID}&type=digital`,
        line_items: [{ quantity: 1, price_data: {
          currency: shop.currency, unit_amount: shop.digital.price,
          product_data: { name: site.digitalName(recipe).slice(0, 250), description: site.digitalDescription(recipe).slice(0, 500) },
        } }],
        custom_text: shop.digitalNote ? { submit: { message: shop.digitalNote.slice(0, 1200) } } : undefined,
      };
    } else {
      const size = shop.sizes[o.paper];
      if (!size) return res.status(400).json({ error: "That size isn't for sale as a print. Choose another paper size." });
      order = {
        ...common,
        success_url: `${siteUrl}/thanks.html?order={CHECKOUT_SESSION_ID}`,
        line_items: [{ quantity: 1, price_data: {
          currency: shop.currency, unit_amount: size.price,
          product_data: { name: site.printName(recipe).slice(0, 250), description: site.printDescription(recipe, size).slice(0, 500) },
        } }],
        shipping_address_collection: { allowed_countries: shop.countries },
        shipping_options: [{ shipping_rate_data: {
          type: "fixed_amount", display_name: shop.shipping.label,
          fixed_amount: { amount: shop.shipping.price, currency: shop.currency },
        } }],
        custom_text: shop.note ? { submit: { message: shop.note.slice(0, 1200) } } : undefined,
      };
    }
    const params = form(order);

    try {
      const r = await fetch(`${process.env.STRIPE_API_BASE || "https://api.stripe.com"}/v1/checkout/sessions`, {
        method: "POST",
        headers: { Authorization: `Bearer ${process.env.STRIPE_SECRET_KEY}`, "Content-Type": "application/x-www-form-urlencoded" },
        body: params,
      });
      const data = await r.json();
      if (!r.ok || !data.url) {
        console.error("Stripe error", r.status, data && data.error && data.error.message);
        return res.status(502).json({ error: "Payment page couldn't be opened. Please try again in a minute." });
      }
      return res.status(200).json({ url: data.url });
    } catch (e) {
      console.error("Stripe unreachable", e);
      return res.status(502).json({ error: "Payment page couldn't be opened. Please try again in a minute." });
    }
  };
}

module.exports = { makeCheckout, form };
