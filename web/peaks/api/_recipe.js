// The recipe: everything needed to re-draw a customer's print exactly, small enough for
// one Stripe metadata value (500 characters). A GPX route travels separately, as an
// encoded polyline split across up to ROUTE_CHUNKS metadata values.
"use strict";
const { decode } = require("../lib/polyline.js");

const PAPERS = ["A4", "A3", "A2", "A1", "50x70", "square"];
const PANOS = ["pano75", "pano90"];
const THEMES = ["paper", "white", "fog", "alpine", "sand", "blush", "navy", "moss", "ochre", "cyanotype", "night", "ink", "slate", "forest", "oxblood", "bands", "relief", "glacier"];
const CONTRASTS = ["soft", "bold"];   // standard is left out
const STYLES = ["poster", "contours", "ridgelines", "skyline", "panorama"];
const DIRS = ["S", "SW", "W", "NW", "N", "NE", "E", "SE"];
const LIMITS = { name: 60, region: 40, title: 60, subtitle: 140, runner: 40, time: 12 };
const MAX_JSON = 500;
const ROUTE_CHUNK = 480, ROUTE_CHUNKS = 40, ROUTE_MAX_POINTS = 5000, ROUTE_MAX_KM = 150;

function cleanText(value, max) {
  if (value == null) return "";
  if (typeof value !== "string") throw new Error("Text fields must be text");
  const text = value.normalize("NFC").replace(/[\u0000-\u001F\u007F\u2028\u2029]/g, " ").replace(/\s+/g, " ").trim();
  if ([...text].length > max) throw new Error(`Text is too long (max ${max} characters)`);
  return text;
}

function num(value, lo, hi, what, step = 0) {
  const n = Number(value);
  if (!Number.isFinite(n) || n < lo || n > hi) throw new Error(`${what} is out of range`);
  return step ? Math.round(n / step) * step : n;
}

// Returns a clean recipe or throws an Error with a message safe to show customers.
function validateRecipe(input) {
  if (!input || typeof input !== "object") throw new Error("Missing design");
  const style = String(input.style);
  if (!STYLES.includes(style)) throw new Error("Unknown print style");
  const seen = String(input.seen || "S");
  const r = {
    v: 1,
    place: /^[a-z0-9-]{1,40}$/.test(input.place || "") ? input.place : "",
    lat: Math.round(num(input.lat, -85, 85, "Latitude") * 1e5) / 1e5,
    lon: Math.round(num(input.lon, -180, 180, "Longitude") * 1e5) / 1e5,
    name: cleanText(input.name, LIMITS.name) || "Mountain",
    region: cleanText(input.region, LIMITS.region),
    style,
    theme: String(input.theme),
    labels: input.labels ? 1 : 0,
    details: input.details ? 1 : 0,
    title: cleanText(input.title, LIMITS.title),
    subtitle: cleanText(input.subtitle, LIMITS.subtitle),
    paper: String(input.paper),
    orient: input.orient === "landscape" ? "landscape" : "portrait",
    width: num(input.width, 2, 50, "Width", 0.5),
    detail: num(input.detail, 30, 160, "Contour lines", 5),
    rows: num(input.rows, 24, 140, "Ridgelines", 2),
    seen: DIRS.includes(seen) || /^view:[a-z0-9-]{1,40}$/.test(seen) ? seen : "S",
    dist: num(input.dist, 3, 40, "Distance", 0.5),
    facing: num(input.facing, 0, 359, "Facing", 1),
    fov: num(input.fov, 60, 360, "Width of view", 5),
    reach: num(input.reach, 10, 60, "Distance to look", 1),
    route: Math.round(num(input.route || 0, 0, ROUTE_MAX_POINTS, "Route")),
    round: /^[a-z0-9-]{1,40}$/.test(String(input.round || "")) ? String(input.round) : "",   // a ready-made route, for its credit
  };
  // the run itself, all optional: who, when (yyyy-mm-dd), how long, and whether to list the summits
  const runner = cleanText(input.runner, LIMITS.runner), time = cleanText(input.time, LIMITS.time);
  const date = String(input.date || "");
  if (time && !/^[0-9hms:. ]+$/i.test(time)) throw new Error("Write the time like 23:41:07");
  if (date && !(/^\d{4}-\d{2}-\d{2}$/.test(date) && !isNaN(Date.parse(date)))) throw new Error("That date isn't valid");
  if (r.route) {
    if (runner) r.runner = runner;
    if (date) r.date = date;
    if (time) r.time = time;
    if (input.stops && r.round) r.stops = 1;
  }
  if (!r.route) r.round = "";
  if (!r.title) throw new Error("Add a title");
  if (!THEMES.includes(r.theme)) throw new Error("Unknown colours");
  if (CONTRASTS.includes(input.contrast)) r.contrast = input.contrast;
  if (style === "panorama" ? !PANOS.includes(r.paper) : !PAPERS.includes(r.paper)) throw new Error("Unknown paper size");
  if (r.route && style === "skyline") throw new Error("Routes can't be drawn as a skyline");
  if (JSON.stringify(r).length > MAX_JSON) throw new Error("Design text is too long; shorten the subtitle or the runner's name");
  return r;
}

// Checks an encoded route against its recipe and splits it into metadata values.
function routeMetadata(encoded, recipe) {
  if (!recipe.route) return {};
  if (typeof encoded !== "string" || !encoded) throw new Error("The route is missing; load your GPX file again");
  if (encoded.length > ROUTE_CHUNK * ROUTE_CHUNKS) throw new Error("That route is too long to print");
  const pts = decode(encoded);
  if (pts.length !== recipe.route || pts.length < 2) throw new Error("The route is damaged; load your GPX file again");
  let s = 90, n = -90, w = 180, e = -180;
  for (const [la, lo] of pts) {
    if (!(la >= -85 && la <= 85 && lo >= -180 && lo <= 180)) throw new Error("The route has points off the map");
    s = Math.min(s, la); n = Math.max(n, la); w = Math.min(w, lo); e = Math.max(e, lo);
  }
  const km = Math.hypot((n - s) * 111.32, (e - w) * 111.32 * Math.cos((n + s) / 2 * Math.PI / 180));
  if (km > ROUTE_MAX_KM) throw new Error(`Routes can be up to ${ROUTE_MAX_KM} km across`);
  const out = {};
  for (let i = 0; i * ROUTE_CHUNK < encoded.length; i++) out[`route_${i}`] = encoded.slice(i * ROUTE_CHUNK, (i + 1) * ROUTE_CHUNK);
  return out;
}

module.exports = { validateRecipe, routeMetadata, PAPERS, PANOS, THEMES, STYLES, LIMITS, MAX_JSON, ROUTE_CHUNK, ROUTE_CHUNKS };
