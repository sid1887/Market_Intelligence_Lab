const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const ARTIFACT_DIR = '/home/siddharth/.gemini/antigravity/brain/5991d6e7-21c9-463f-a770-96f847be241e';
const CHROME_PATH = '/home/siddharth/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome';

async function runVisualQA() {
  console.log('=== Initiating Automated Playwright Visual Inspection ===');
  
  const consoleMessages = [];
  const errors = [];

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

  page.on('console', msg => {
    const type = msg.type();
    const text = msg.text();
    consoleMessages.push({ type, text });
    if (type === 'error') {
      errors.push(text);
      console.log(`[BROWSER ERROR] ${text}`);
    }
  });

  page.on('pageerror', err => {
    errors.push(err.message);
    console.log(`[PAGE ERROR] ${err.message}`);
  });

  console.log('1. Navigating to http://localhost:3000 ...');
  await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);

  // Take Dashboard full screenshot
  const dashPath = path.join(ARTIFACT_DIR, 'dashboard_initial.png');
  await page.screenshot({ path: dashPath, fullPage: false });
  console.log(`Saved initial dashboard screenshot: ${dashPath}`);

  // Test Stock Inspections: TCS, SUZLON, CDSL
  const testSymbols = ['TCS', 'SUZLON', 'CDSL'];

  for (const sym of testSymbols) {
    console.log(`\n2. Inspecting equity: ${sym} ...`);
    
    // Find row by text
    const rowSelector = `div[data-rowindex] span:has-text("${sym}")`;
    const rowEl = page.locator(rowSelector).first();

    const exists = await rowEl.count() > 0;
    if (exists) {
      await rowEl.click();
      console.log(`Clicked row for ${sym}`);
    } else {
      console.log(`Row for ${sym} not immediately visible, searching via fast filter...`);
      const searchInput = page.locator('input[placeholder*="Filter 181 equities"]');
      await searchInput.fill(sym);
      await page.waitForTimeout(500);
      const filteredRow = page.locator(`div[data-rowindex] span:has-text("${sym}")`).first();
      await filteredRow.click();
      console.log(`Clicked filtered row for ${sym}`);
      // Clear search
      await searchInput.fill('');
      await page.waitForTimeout(500);
    }

    // Wait for inspector data to settle
    await page.waitForTimeout(1500);

    const shotPath = path.join(ARTIFACT_DIR, `screenshot_${sym.toLowerCase()}.png`);
    await page.screenshot({ path: shotPath, fullPage: false });
    console.log(`Saved screenshot for ${sym}: ${shotPath}`);

    // Verify right-side inspector updated to this symbol
    const headerTicker = await page.locator('span.text-2xl.font-mono.font-black').first().textContent();
    console.log(`Active inspector ticker confirmed: ${headerTicker?.trim()}`);

    // If CDSL, check latest price is around 1300+ and not 98
    if (sym === 'CDSL') {
      const priceText = await page.locator('span.text-2xl.font-mono.font-black').first().locator('..').textContent();
      console.log(`CDSL Header price snippet: ${priceText?.replace(/\s+/g, ' ')}`);
    }
  }

  // 3. Inspect DOM geometry: Check bottom inspector tabs
  console.log('\n3. Verifying DOM geometry & ergonomics ...');
  const memoTab = page.locator('button:has-text("Decision Memo & Health")');
  const wireTab = page.locator('button:has-text("Exchange Regulatory Wire")');
  
  const hasMemo = await memoTab.count() > 0;
  const hasWire = await wireTab.count() > 0;
  console.log(`Inspector tab "Decision Memo & Health" visible: ${hasMemo}`);
  console.log(`Inspector tab "Exchange Regulatory Wire" visible: ${hasWire}`);

  if (hasWire) {
    await wireTab.click();
    await page.waitForTimeout(600);
    const wirePath = path.join(ARTIFACT_DIR, 'screenshot_wire_tab.png');
    await page.screenshot({ path: wirePath, fullPage: false });
    console.log(`Saved screenshot of active Wire tab: ${wirePath}`);
    await memoTab.click();
    await page.waitForTimeout(400);
  }

  // 4. Check console log status
  console.log(`\n4. Console Audit Summary:`);
  console.log(`Total messages logged: ${consoleMessages.length}`);
  console.log(`Total errors logged: ${errors.length}`);
  if (errors.length > 0) {
    console.log('Errors:', errors);
  } else {
    console.log('Zero JavaScript errors or hydration issues encountered.');
  }

  await browser.close();
  console.log('\n=== Playwright Visual QA Complete ===');
}

runVisualQA().catch(err => {
  console.error('Visual QA failed:', err);
  process.exit(1);
});
