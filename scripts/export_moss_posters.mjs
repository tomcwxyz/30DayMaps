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
      const verification = await page.evaluate(async profile => {
        const source = await (await fetch('./moss.geojson')).json();
        const clusters = await (await fetch('./moss-clusters.geojson')).json();
        const manifest = await (await fetch('./moss-clusters-manifest.json')).json();
        const taxa = await (await fetch('./moss-manifest.json')).json();
        const selected = clusters.features.filter(f =>
          f.properties.group === profile.group && f.properties.level === 'focus');
        return {
          sourceSquares: source.features.length,
          clusterCount: selected.length,
          clusterSquares: manifest.profiles[profile.key].cells_in_clusters,
          allEightSquares: source.features.filter(f =>
            taxa.species.every(s => (f.properties.species[s.name] || 0) > 0)).length
        };
      }, { group: key === 'all' ? 'all' : key, key: state.profile });
      assert.equal(state.sourceSquares, verification.sourceSquares);
      assert.equal(state.clusterCount, verification.clusterCount);
      assert.equal(state.clusterSquares, verification.clusterSquares);
      assert(state.sourceSquares >= 100, 'NBN source unexpectedly empty');
      assert(state.clusterCount > 0, 'No source-derived cluster geometries');
      assert.equal(
        await page.locator('.leaflet-record-clusters-pane path.cluster-shape').count(),
        state.clusterCount,
        'Number of rendered cluster polygons differs from source'
      );
      if (key === 'all') {
        assert.equal(state.eightSpeciesSquares, verification.allEightSquares);
        assert(state.eightSpeciesSquares >= state.clusterSquares);
        assert((await page.locator('#note').innerText())
          .includes(String(state.eightSpeciesSquares - state.clusterSquares)));
        assert.equal(
          await page.locator('.leaflet-source-squares-pane path').count(),
          state.eightSpeciesSquares,
          'All eight-species evidence squares must be present'
        );
      } else {
        assert(state.clusterSquares >= state.clusterCount * 3);
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
