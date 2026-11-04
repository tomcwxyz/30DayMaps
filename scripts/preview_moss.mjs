import assert from 'node:assert/strict';
import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';

const root = 'web/moss';
const base = 'http://127.0.0.1:8765/web/moss/';
await mkdir(root, { recursive: true });
const browser = await chromium.launch({ headless: true });

async function capture(name, viewport, { mobile = false, view = 'coverage' } = {}) {
  const context = await browser.newContext({
    viewport, deviceScaleFactor: 1, isMobile: mobile, hasTouch: mobile,
    colorScheme: 'light', reducedMotion: 'reduce'
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(base, { waitUntil: 'domcontentloaded', timeout: 60_000 });
    await page.waitForFunction(() => {
      const status = document.getElementById('status')?.textContent || '';
      return status.includes('10 km squares with at least one');
    }, { timeout: 60_000 });

    const source = await page.evaluate(async () => {
      const data = await (await fetch('./moss.geojson')).json();
      const meta = await (await fetch('./moss-clusters-manifest.json')).json();
      const totalSpecies = 8;
      return {
        total: data.features.length,
        allEight: data.features.filter(f =>
          Object.keys(f.properties.species).length === totalSpecies).length,
        clusters: meta.profiles['all-focus'].clusters,
        linked: meta.profiles['all-focus'].cells_in_clusters
      };
    });

    // Overview includes *every* recorded source cell; no cluster threshold.
    assert(await page.locator('[data-group="coverage"]').getAttribute('aria-pressed') === 'true');
    assert((await page.locator('#status').innerText()).includes(source.total.toLocaleString('en-GB')));
    assert.equal(await page.locator('#colour-legend .legend-item').count(), 8);
    assert.equal(await page.locator('#strength-section').isVisible(), false);
    assert.equal(await page.locator('path.cluster-shape').count(), 0);

    // Both categorical leading-species and sequential richness colouring work.
    await page.locator('[data-colour="richness"]').click();
    assert.equal(await page.locator('[data-colour="richness"]').getAttribute('aria-pressed'), 'true');
    assert((await page.locator('#colour-legend').innerText()).includes('8 of 8 species'));
    await page.locator('[data-colour="leading"]').click();

    // The all-eight mode includes *every* co-recorded square, not just the
    // larger components, and also draws the connected cluster outlines.
    await page.locator('[data-group="all"]').click();
    await page.waitForFunction(() =>
      (document.getElementById('status')?.textContent || '').includes('squares with all 8'));
    const allStatus = await page.locator('#status').innerText();
    assert(allStatus.includes(source.allEight.toLocaleString('en-GB')));
    assert(allStatus.includes((source.allEight - source.linked).toLocaleString('en-GB') + ' outside clusters'));
    assert.equal(await page.locator('path.cluster-shape').count(), source.clusters);
    assert.equal(await page.locator('#strength-section').isVisible(), false);

    // Confirm habitat clustering still works and retains concentration controls.
    await page.locator('[data-group="bog"]').click();
    assert.equal(await page.locator('#strength-section').isVisible(), true);
    assert((await page.locator('#status').innerText()).includes('bog mosses clusters'));

    await page.locator('[data-group="' + view + '"]').click();
    if (view === 'coverage') {
      assert((await page.locator('#status').innerText()).includes(source.total.toLocaleString('en-GB')));
    } else {
      assert.equal(await page.locator('path.cluster-shape').count(), source.clusters);
    }
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(2200);

    // Genuine overlay geometries must render; do not accept a blank map.
    const overlayCount = await page.locator('.leaflet-coverage-pane canvas').count();
    assert(overlayCount > 0, 'Real source squares did not render to canvas');
    assert.deepEqual(errors, [], 'Browser JavaScript exceptions');
    const filename = root + '/' + name + '.png';
    await page.screenshot({ path: filename, fullPage: true, animations: 'disabled' });
    console.log('Verified and captured', filename, 'with', source.total,
      'source cells,', source.allEight, 'eight-species squares and',
      source.clusters, 'all-eight clusters');
  } finally {
    await context.close();
  }
}

try {
  await capture('preview-desktop', { width: 1440, height: 950 });
  await capture('preview-mobile', { width: 390, height: 844 }, { mobile: true });
  await capture('preview-all-eight', { width: 1440, height: 950 }, { view: 'all' });
} finally {
  await browser.close();
}
