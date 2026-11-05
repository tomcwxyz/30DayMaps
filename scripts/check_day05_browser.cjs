#!/usr/bin/env node
/* Headless Chrome checks for real Day 05 pages, no fabricated observations.
 * Usage: npm install --no-save playwright@1.56.0
 *        DAY05_BROWSER_BASE=http://127.0.0.1:8000 node scripts/check_day05_browser.cjs
 */
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");
const base = (process.env.DAY05_BROWSER_BASE || "http://127.0.0.1:8000").replace(/\/$/, "");
const folder = process.env.DAY05_BROWSER_OUTPUT || "browser-screenshots";
fs.mkdirSync(folder, { recursive: true });
const report = { date: new Date().toISOString(), base, checks: [], failures: [] };
const link = section => base + "/" + section;
function pass(message, detail) {
  report.checks.push({ message, detail: detail || "" });
  console.log("PASS " + message + (detail ? " — " + detail : ""));
}
async function checkWildlife(browser) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
  const errors = [];
  page.on("pageerror", err => errors.push(String(err)));
  await page.goto(link("day05-wildlife/"), { waitUntil: "domcontentloaded", timeout: 45000 });
  assert.match(await page.title(), /outside your window/i);
  await page.locator("#map.leaflet-container").waitFor({ timeout: 30000 });
  pass("Wildlife Leaflet canvas loaded");
  await page.waitForFunction(() => /published records|No published records matched|Couldn't load GBIF/i.test(document.querySelector("#status")?.textContent || ""), null, { timeout: 70000 });
  let status = (await page.locator("#status").textContent()).trim();
  assert.doesNotMatch(status, /Couldn't load GBIF/i);
  pass("Wildlife live GBIF browser request", status);
  await page.selectOption("#month", "5");
  await page.waitForFunction(() => (document.querySelector("#guide-title")?.textContent || "").includes("May"));
  pass("Wildlife month selector", "May");
  await page.selectOption("#month", "11");
  await page.selectOption("#radius", "10");
  await page.waitForFunction(() => (document.querySelector("#guide-subtitle")?.textContent || "").includes("10 km"));
  pass("Wildlife radius selector", "10 km");
  await page.selectOption("#radius", "5");
  await page.locator(".species-item").first().waitFor({ timeout: 60000 });
  await page.locator(".species-item").first().click();
  await page.locator("#seasonality:not([hidden])").waitFor({ timeout: 45000 });
  assert.equal(await page.locator("#season-bars .season-month").count(), 12);
  pass("Wildlife full twelve-month source chart");
  await page.screenshot({ path: path.join(folder, "wildlife-desktop.png"), fullPage: true });
  if (errors.length) throw new Error("Wildlife page errors: " + errors.join("; "));
  await page.close();
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await mobile.goto(link("day05-wildlife/"), { waitUntil: "domcontentloaded", timeout: 45000 });
  await mobile.locator("#map.leaflet-container").waitFor({ timeout: 30000 });
  await mobile.screenshot({ path: path.join(folder, "wildlife-mobile.png"), fullPage: true });
  pass("Wildlife mobile map rendered");
  await mobile.close();
}

async function testCompassStability(page, device) {
  await page.locator("#overview-view").click();
  await page.waitForFunction(() => document.querySelector("#map")?.dataset.direction !== undefined);
  const before = Number(await page.locator("#map").getAttribute("data-terrain-changes"));
  for (const [direction, bearing] of [["south","180"],["west","270"],["north","0"],["east","90"],["west","270"]]) {
    await page.locator("[data-direction=" + direction + "]").click();
    await page.waitForFunction(value => document.querySelector("#map")?.dataset.direction === value, bearing);
    assert.equal(Number(await page.locator("#map").getAttribute("data-terrain-changes")), before,
      "Changing direction to " + direction + " rebuilt the 3D terrain");
  }
  pass(device + " direction switches", "Five directions, no terrain rebuilds");
  await page.locator("#exaggerate").click();
  await page.waitForFunction(value => Number(document.querySelector("#map")?.dataset.terrainChanges) === value + 1, before);
  await page.locator("[data-direction=south]").click();
  assert.equal(Number(await page.locator("#map").getAttribute("data-terrain-changes")), before + 1);
  pass(device + " relief then rotate", "Exactly one terrain update");
  await page.screenshot({ path: path.join(folder, "dale-head-" + device.toLowerCase() + "-directions.png"), fullPage: true });
  await page.locator("#summit-view").click();
  await page.locator("#panorama:not([hidden])").waitFor({ timeout: 15000 });
  for (const [direction, bearing] of [["west","270°"],["north","0°"],["south","180°"]]) {
    await page.locator("[data-direction=" + direction + "]").click();
    await page.waitForFunction(value => document.querySelector("#compass-direction")?.textContent.trim() === value, bearing);
  }
  pass(device + " summit compass", "Three headings immediately reflected");
}

async function checkDale(browser) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
  const errors = [];
  page.on("pageerror", err => errors.push(String(err)));
  await page.goto(link("day05-dale-head/"), { waitUntil: "domcontentloaded", timeout: 45000 });
  assert.match(await page.title(), /mountain sees/i);
  await page.locator("#map canvas").waitFor({ timeout: 35000 });
  pass("Dale Head 3D canvas loaded");
  const directory = path.join("_site", "day05-dale-head", "data");
  if (fs.existsSync(path.join(directory, "viewshed-manifest.json"))) {
    await page.waitForFunction(() => document.querySelector("#viewshed-view")?.disabled === false, null, { timeout: 45000 });
    await page.locator("#viewshed-view").click();
    await page.locator("#viewshed-legend:not([hidden])").waitFor({ timeout: 15000 });
    pass("Dale Head real computed viewshed toggles");
  } else {
    assert.equal(await page.locator("#viewshed-view").isDisabled(), true);
    pass("Dale Head truthful viewshed-unavailable state");
  }
  if (fs.existsSync(path.join(directory, "peaks.json"))) {
    await page.locator("#peak-guide:not([hidden])").waitFor({ timeout: 30000 });
    const count = await page.locator(".peak-button").count();
    assert.ok(count > 0);
    await page.locator(".peak-button").first().click();
    const hasPanorama = fs.existsSync(path.join(directory, "panorama.json"));
    if (hasPanorama) {
      await page.locator("#panorama:not([hidden])").waitFor({ timeout: 18000 });
      pass("Dale Head computed landscape panorama opened");
    }
    await page.screenshot({ path: path.join(folder, "dale-head-after-peak.png"), fullPage: true });
    try {
      await page.waitForFunction(() => (document.querySelector("#status")?.textContent || "").includes("Looking towards"), null, { timeout: 15000 });
    } catch (error) {
      const text = (await page.locator("#status").textContent() || "").trim();
      throw new Error("Summit camera did not turn; status: " + text +
        "; page errors: " + errors.join("; ") + "; original: " + error.message);
    }
    pass("Dale Head summit names and direction control", String(count) + " labelled summits");
  } else {
    assert.equal(await page.locator("#peak-guide").getAttribute("hidden") !== null, true);
    pass("Dale Head did not invent absent summit names");
  }
  await page.screenshot({ path: path.join(folder, "dale-head-desktop.png"), fullPage: true });
  if (errors.length) throw new Error("Dale Head page errors: " + errors.join("; "));
  await page.close();
  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await mobile.goto(link("day05-dale-head/"), { waitUntil: "domcontentloaded", timeout: 45000 });
  await mobile.locator("#map canvas").waitFor({ timeout: 35000 });
  await mobile.screenshot({ path: path.join(folder, "dale-head-mobile.png"), fullPage: true });
  pass("Dale Head mobile canvas rendered");
  await mobile.close();
}
(async () => {
  let browser;
  try {
    browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--no-sandbox", "--enable-webgl", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
    for (const [name, action] of [["Wildlife", checkWildlife], ["Dale Head", checkDale]]) {
      try { await action(browser); }
      catch (err) { report.failures.push({ name, error: String(err), stack: String(err.stack || "").slice(0, 1800) }); console.error("FAIL " + name + ": " + String(err)); }
    }
  } catch (err) { report.failures.push({ name: "Browser", error: String(err) }); }
  finally {
    if (browser) await browser.close();
    fs.writeFileSync(path.join(folder, "report.json"), JSON.stringify(report, null, 2));
  }
  if (report.failures.length) process.exitCode = 1;
})();