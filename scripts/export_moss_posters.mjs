/* Capture three actual precomputed NBN Atlas moss map views at A3/300 dpi.
 * No image generation or fabricated cartography. Fails on absent real data.
 */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const base = 'http://127.0.0.1:8765/web/moss/poster.html';
const dir = 'web/moss/exports';
const views = [
  { key: 'bog', name: 'day04-bog-mosses-a3-300dpi.png' },
  { key: 'stone', name: 'day04-stone-and-wall-mosses-a3-300dpi.png' },
  { key: 'all', name: 'day04-all-eight-recorded-a3-300dpi.png' }
];
await mkdir(dir, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  args: ['--disable-dev-shm-usage']
});
try {
  for (const { key, name } of views) {
    // CSS pixel dimensions × DPR 3 = 3507 × 4962 A3 portrait pixels.
    const context = await browser.newContext({
      viewport: { width: 1169, height: 1654 },
      deviceScaleFactor: 3,
      colorScheme: 'light',
      reducedMotion: 'reduce'
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    try {
      await page.goto(base + '?view=' + key, {
        waitUntil: 'domcontentloaded',
        timeout: 60_000
      });
      await page.waitForFunction(() => !!window.__mossPoster, null, {
        timeout: 60_000
      });
      const state = await page.evaluate(() => window.__mossPoster);
      assert(state.ready, 'Poster failed to load verified data: ' + JSON.stringify(state));
      assert.equal(state.view, key);
      assert.equal(state.sourceSquares, 2777, 'Snapshot unexpectedly changed: audit before printing');
      assert(state.clusterCount >= 8, 'Missing real derived cluster geometries');
      assert.equal(
        await page.locator('.leaflet-record-clusters-pane path.cluster-shape').count(),
        state.clusterCount,
        'Number of rendered cluster polygons differs from source'
      );
      if (key === 'all') {
        assert.equal(state.eightSpeciesSquares, 197);
        assert.equal(state.clusterCount, 20);
        assert.equal(state.clusterSquares, 130);
        assert((await page.locator('#note').innerText()).includes('67'));
        assert.equal(
          await page.locator('.leaflet-source-squares-pane path').count(),
          state.eightSpeciesSquares,
          'All eight-species evidence squares must be present'
        );
      } else {
        assert.equal(state.clusterCount, key === 'bog' ? 26 : 12);
        assert.equal(state.clusterSquares, key === 'bog' ? 270 : 347);
      }
      await page.evaluate(async () => { await document.fonts.ready; });
      // The basemap is the same OpenStreetMap tile layer as the live map.
      // Do not quietly export a map with missing geography.
      await page.waitForFunction(
        () => document.querySelectorAll('.leaflet-tile-loaded').length >= 4,
        null, { timeout: 30_000 }
      );
      await page.waitForTimeout(1500);
      assert.deepEqual(errors, [], 'JavaScript errors rendering real moss poster');
      const outfile = dir + '/' + name;
      await page.screenshot({
        path: outfile,
        fullPage: true,
        animations: 'disabled',
        timeout: 60_000
      });
      console.log(JSON.stringify({
        file: outfile,
        pixels: state.screenshotPixels,
        view: key,
        clusters: state.clusterCount,
        clusterSquares: state.clusterSquares,
        eightSpeciesSquares: state.eightSpeciesSquares,
        sourceDate: state.sourceTimestamp,
        loadedOSMTiles: await page.locator('.leaflet-tile-loaded').count()
      }));
    } finally {
      await context.close();
    }
  }
} finally {
  await browser.close();
}
