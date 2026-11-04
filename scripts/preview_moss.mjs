import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';

const output = 'web/moss';
const base = 'http://127.0.0.1:8765/web/moss/';
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });

async function capture(name, viewport, options = {}) {
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 1,
    isMobile: !!options.mobile,
    hasTouch: !!options.mobile,
    colorScheme: 'light',
    reducedMotion: 'reduce'
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(base, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForFunction(() => {
    const status = document.getElementById('status')?.textContent || '';
    const paths = document.querySelectorAll('path.cluster-shape').length;
    return paths > 0 && status.includes('clusters');
  }, { timeout: 60000 });
  await page.evaluate(() => document.fonts.ready);
  // Give basemap tiles a brief chance to load; overlays are fully data driven.
  await page.waitForTimeout(3000);
  const seen = await page.locator('path.cluster-shape').count();
  if (seen < 10) throw new Error('Screenshot would be blank: ' + seen + ' cluster polygons');
  if (errors.length) console.warn('Browser warnings:', errors);
  const path = output + '/' + name + '.png';
  await page.screenshot({ path, fullPage: true, animations: 'disabled' });
  console.log('Captured ' + path + ' with ' + seen + ' actual cluster paths');
  await context.close();
}
try {
  await capture('preview-desktop', { width: 1440, height: 950 });
  await capture('preview-mobile', { width: 390, height: 844 }, { mobile: true });
} finally {
  await browser.close();
}
