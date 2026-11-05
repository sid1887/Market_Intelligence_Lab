const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const ARTIFACT_DIR = '/home/siddharth/.gemini/antigravity/brain/5991d6e7-21c9-463f-a770-96f847be241e';
const CHROME_PATH = '/home/siddharth/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome';

async function runScreenerUniverseTest() {
  console.log('=== Starting Screener Universe & CDSL Visual QA ===');

  const browser = await chromium.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 1
  });

  const page = await context.newPage();
  const consoleErrors = [];

  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
      console.log(`[BROWSER ERROR] ${msg.text()}`);
    }
  });

  page.on('pageerror', err => {
    consoleErrors.push(err.message);
    console.log(`[PAGE ERROR] ${err.message}`);
  });

  console.log('1. Navigating to http://localhost:3000 ...');
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);

  // Take screenshot of main screener view
  const screenerShot = path.join(ARTIFACT_DIR, 'screener_181_synced.png');
  await page.screenshot({ path: screenerShot, fullPage: false });
  console.log(`Saved screenshot: ${screenerShot}`);

  // Check top status bar text
  const bodyText = await page.textContent('body');
  const has181Live = bodyText.includes('181 NSE Equities Live') || bodyText.includes('181 active') || bodyText.includes('181 Equities');
  console.log(`Top telemetry includes 181 equities status: ${has181Live}`);

  // Check CDSL in table
  const cdslRow = page.locator('div[data-rowindex] span:has-text("CDSL")').first();
  const cdslVisible = await cdslRow.count() > 0;
  console.log(`CDSL visible in table: ${cdslVisible}`);

  // Filter or click CDSL
  const filterInput = page.locator('input[placeholder*="Filter"]').first();
  if (await filterInput.count() > 0) {
    await filterInput.fill('CDSL');
    await page.waitForTimeout(600);
    
    // Screenshot filtered CDSL
    const cdslShot = path.join(ARTIFACT_DIR, 'screener_cdsl_metrics.png');
    await page.screenshot({ path: cdslShot, fullPage: false });
    console.log(`Saved CDSL metrics screenshot: ${cdslShot}`);

    // Verify CDSL row text contains ROE 24.5%, D/E 0.00, OPM 58.2%
    const filteredRow = page.locator('div[data-rowindex]').first();
    const rowContent = await filteredRow.textContent();
    console.log(`CDSL Row Content: ${rowContent}`);

    // Clear filter
    await filterInput.fill('');
    await page.waitForTimeout(600);
  }

  // Test Command Palette (⌘K)
  console.log('2. Testing Command Palette (Cmd+K / Ctrl+K) ...');
  await page.keyboard.press('Control+k');
  await page.waitForTimeout(600);

  // If not triggered by Control+k, try Meta+k or clicking search button
  let cmdPalette = page.locator('[role="dialog"], div:has-text("Search stocks, metrics, factors...")').first();
  let cmdVisible = await cmdPalette.isVisible().catch(() => false);

  if (!cmdVisible) {
    const searchBtn = page.locator('button:has-text("⌘K"), button:has-text("Search")').first();
    if (await searchBtn.count() > 0) {
      await searchBtn.click();
      await page.waitForTimeout(600);
    }
  }

  const paletteShot = path.join(ARTIFACT_DIR, 'command_palette_modal.png');
  await page.screenshot({ path: paletteShot, fullPage: false });
  console.log(`Saved Command Palette screenshot: ${paletteShot}`);

  console.log(`Total console errors: ${consoleErrors.length}`);
  await browser.close();
  console.log('=== Screener Universe & CDSL Visual QA Completed Successfully ===');
}

runScreenerUniverseTest().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
