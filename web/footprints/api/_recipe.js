// The recipe: everything needed to re-render a customer's print exactly.
// Kept small so it fits in one Stripe metadata value (500 characters).
"use strict";

const PAPERS = ["A4", "A3", "A2", "A1", "50x70", "square"];
const THEMES = ["paper", "night", "blue", "ink"];
const LIMITS = { name: 60, title: 60, subtitle: 140, kicker: 40 };
const MAX_JSON = 500;

function cleanText(value, max) {
  if (value == null) return "";
  if (typeof value !== "string") throw new Error("Text fields must be text");
  const text = value.normalize("NFC").replace(/[\u0000-\u001F\u007F\u2028\u2029]/g, " ").replace(/\s+/g, " ").trim();
  if ([...text].length > max) throw new Error(`Text is too long (max ${max} characters)`);
  return text;
}

function num(value, lo, hi, what) {
  const n = Number(value);
  if (!Number.isFinite(n) || n < lo || n > hi) throw new Error(`${what} is out of range`);
  return n;
}

// Returns a clean recipe or throws an Error with a message safe to show customers.
function validateRecipe(input) {
  if (!input || typeof input !== "object") throw new Error("Missing design");
  const r = {
    v: 1,
    lat: Math.round(num(input.lat, -85, 85, "Latitude") * 1e5) / 1e5,
    lon: Math.round(num(input.lon, -180, 180, "Longitude") * 1e5) / 1e5,
    name: cleanText(input.name, LIMITS.name) || "Place",
    title: cleanText(input.title, LIMITS.title),
    subtitle: cleanText(input.subtitle, LIMITS.subtitle),
    kicker: cleanText(input.kicker, LIMITS.kicker),
    paper: String(input.paper),
    orient: input.orient === "landscape" ? "landscape" : "portrait",
    width_km: Math.round(num(input.width_km, 0.5, 20, "Width") * 10) / 10,
    theme: String(input.theme),
    source: "osm",  // print what the customer saw: the web page uses OpenStreetMap
  };
  if (!r.title) throw new Error("Add a title");
  if (!PAPERS.includes(r.paper)) throw new Error("Unknown paper size");
  if (!THEMES.includes(r.theme)) throw new Error("Unknown colours");
  if (JSON.stringify(r).length > MAX_JSON) throw new Error("Design text is too long; shorten the title or subtitle");
  return r;
}

module.exports = { validateRecipe, PAPERS, THEMES, LIMITS, MAX_JSON };
