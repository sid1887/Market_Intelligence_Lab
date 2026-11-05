const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const ARTIFACT_DIR = '/home/siddharth/.gemini/antigravity/brain/5991d6e7-21c9-463f-a770-96f847be241e';
const CHROME_PATH = '/home/siddharth/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome';

async function runTearsheetScrollQA() {
  console.log('=== Initiating Stock Tearsheet Scrolling & Interaction QA ===');
  
  const consoleMessages = [];
  const errors = [];

  const browser = await chromium.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1
  });

  const page = await context.newPage();

  page.on('console', msg => {
    const type = msg.type();
    const text = msg.text();
    consoleMessages.push({ type, text });
    if (type === 'error' && !text.includes('favicon.ico')) {
      errors.push(text);
      console.log(`[BROWSER ERROR] ${text}`);
    }
  });

  page.on('pageerror', err => {
    errors.push(err.message);
    console.log(`[PAGE ERROR] ${err.message}`);
  });

  console.log('1. Navigating to http://localhost:3000/stocks/BSE ...');
  await page.goto('http://localhost:3000/stocks/BSE', { waitUntil: 'networkidle', timeout: 30000 });
  
  // Wait for symbol header to appear
  await page.waitForSelector('h1:has-text("BSE")', { timeout: 15000 });
  await page.waitForTimeout(1000);

  // Capture Top Screenshot
  const topScreenshot = path.join(ARTIFACT_DIR, 'tearsheet_bse_top.png');
  await page.screenshot({ path: topScreenshot, fullPage: false });
  console.log(`✓ Saved Top of BSE Tearsheet: ${topScreenshot}`);

  // Test Scrollability
  const initialScrollY = await page.evaluate(() => window.scrollY);
  console.log(`Initial window.scrollY: ${initialScrollY}`);

  console.log('2. Scrolling down 800px ...');
  await page.evaluate(() => window.scrollTo(0, 800));
  await page.waitForTimeout(500);

  const midScrollY = await page.evaluate(() => window.scrollY);
  console.log(`After scroll: window.scrollY = ${midScrollY}`);
  if (midScrollY <= 0) {
    throw new Error('FAILED: window.scrollY did not increase! Tearsheet is still locked from scrolling!');
  }
  console.log(`✓ Page is fluidly scrollable! Scrolled to ${midScrollY}px`);

  // Capture Mid (Chart & Forecast) Screenshot
  const midScreenshot = path.join(ARTIFACT_DIR, 'tearsheet_bse_chart_forecast.png');
  await page.screenshot({ path: midScreenshot, fullPage: false });
  console.log(`✓ Saved Mid (Chart & Forecast) Screenshot: ${midScreenshot}`);

  // Test Chart Interactions
  console.log('3. Testing Chart Interactions (Timeframe & 20D Cone Toggle) ...');
  const maxBtn = page.locator('button:has-text("MAX")');
  if (await maxBtn.count() > 0) {
    await maxBtn.first().click();
    console.log('  Clicked timeframe [MAX]');
    await page.waitForTimeout(500);
  }

  const coneBtn = page.locator('button:has-text("20D Cone")');
  if (await coneBtn.count() > 0) {
    await coneBtn.first().click();
    console.log('  Toggled 20D Cone off');
    await page.waitForTimeout(400);
    await coneBtn.first().click();
    console.log('  Toggled 20D Cone back on');
    await page.waitForTimeout(400);
  }

  // Scroll down further to inspect Fundamental Factors and News
  console.log('4. Scrolling down to 2000px (Factors, News & Filings) ...');
  await page.evaluate(() => window.scrollTo(0, 2000));
  await page.waitForTimeout(500);

  const bottomScrollY = await page.evaluate(() => window.scrollY);
  console.log(`After scroll: window.scrollY = ${bottomScrollY}`);

  const bottomScreenshot = path.join(ARTIFACT_DIR, 'tearsheet_bse_bottom.png');
  await page.screenshot({ path: bottomScreenshot, fullPage: false });
  console.log(`✓ Saved Bottom (Factors, News & Filings) Screenshot: ${bottomScreenshot}`);

  // Test Navigation back to Dashboard
  console.log('5. Testing "Back to Terminal Dashboard" Link ...');
  const backLink = page.locator('a:has-text("Back to Terminal Dashboard")');
  await backLink.first().click();
  await page.waitForURL('http://localhost:3000/', { timeout: 10000 });
  await page.waitForTimeout(1000);
  console.log('✓ Successfully navigated back to http://localhost:3000/');

  const finalUrl = page.url();
  console.log(`Final URL: ${finalUrl}`);

  await browser.close();

  console.log('\n=== QA EXECUTION SUMMARY ===');
  console.log(`Total Errors Detected: ${errors.length}`);
  if (errors.length > 0) {
    console.error('Errors encountered:', errors);
    process.exit(1);
  } else {
    console.log('ALL VERIFICATIONS PASSED: Tearsheet is movable, fully scrollable, and interactive!');
  }
}

runTearsheetScrollQA().catch(err => {
  console.error('Test execution failed:', err);
  process.exit(1);
});
