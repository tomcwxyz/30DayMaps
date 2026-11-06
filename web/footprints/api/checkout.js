"use strict";
// POST /api/checkout {recipe}: validates the design, prices it from shop.json (never
// from the browser) and returns a Stripe Checkout URL. The recipe rides along in the
// payment's metadata, so each paid order in Stripe carries everything needed to print it.
const { loadShop } = require("./_shop");
const { validateRecipe } = require("./_recipe");

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

module.exports = async (req, res) => {
  if (req.method !== "POST") { res.setHeader("Allow", "POST"); return res.status(405).json({ error: "Use POST" }); }
  const shop = loadShop();
  if (!shop.open) return res.status(503).json({ error: "The shop isn't open yet." });

  let recipe, product;
  try {
    const body = typeof req.body === "string" ? JSON.parse(req.body) : req.body;
    recipe = validateRecipe(body && body.recipe);
    product = (body && body.product) || "print";
    if (product !== "print" && product !== "digital") throw new Error("Choose a printed copy or a digital file");
  } catch (e) {
    return res.status(400).json({ error: e.message });
  }
  const site = originOf(req);
  const recipeJson = JSON.stringify(recipe);
  const common = {
    mode: "payment",
    cancel_url: `${site}/`,
    phone_number_collection: { enabled: false },
    metadata: { recipe: recipeJson, product, place: recipe.name, paper: recipe.paper },
    payment_intent_data: { metadata: { recipe: recipeJson, product } },
  };
  let order;
  if (product === "digital") {
    if (!shop.digital) return res.status(400).json({ error: "Digital files aren't for sale at the moment." });
    order = {
      ...common,
      success_url: `${site}/thanks.html?order={CHECKOUT_SESSION_ID}&type=digital`,
      line_items: [{ quantity: 1, price_data: {
        currency: shop.currency, unit_amount: shop.digital.price,
        product_data: {
          name: `Footprints digital print: ${recipe.title}`.slice(0, 250),
          description: `High-resolution PNG (sharp printed up to A2) and a PDF that scales to any size, by email · ${recipe.name}`,
        },
      } }],
      custom_text: shop.digitalNote ? { submit: { message: shop.digitalNote.slice(0, 1200) } } : undefined,
    };
  } else {
    const size = shop.sizes[recipe.paper];
    if (!size) return res.status(400).json({ error: "That size isn't for sale as a print. Choose another paper size." });
    order = {
      ...common,
      success_url: `${site}/thanks.html?order={CHECKOUT_SESSION_ID}`,
      line_items: [{ quantity: 1, price_data: {
        currency: shop.currency, unit_amount: size.price,
        product_data: {
          name: `Footprints print: ${recipe.title}`.slice(0, 250),
          description: `${size.label}, ${recipe.orient} · ${recipe.theme} colours · ${recipe.width_km} km across · ${recipe.name}`,
        },
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
