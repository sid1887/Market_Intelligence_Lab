const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const ARTIFACT_DIR = '/home/siddharth/.gemini/antigravity/brain/5991d6e7-21c9-463f-a770-96f847be241e';
const CHROME_PATH = '/home/siddharth/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome';

async function testCopilotDeliberation() {
  console.log('=== Initiating Milestone B12.0 Playwright Multi-Agent Copilot QA ===');

  const consoleMessages = [];
  const errors = [];

  const browser = await chromium.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const context = await browser.newContext({
    viewport: { width: 1600, height: 950 },
    deviceScaleFactor: 1
  });

  const page = await context.newPage();

  page.on('console', msg => {
    const type = msg.type();
    const text = msg.text();
    consoleMessages.push({ type, text });
    if (type === 'error' && !text.includes('favicon.ico') && !text.includes('ERR_ABORTED')) {
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

  console.log('2. Opening Quant Copilot Drawer via Keyboard Shortcut (Control+J)...');
  await page.keyboard.press('Control+j');
  await page.waitForTimeout(1000);

  // Check if drawer is visible
  let drawer = page.locator('aside:has-text("QUANT COPILOT")');
  if (await drawer.count() === 0) {
    console.log('Keyboard shortcut not caught, clicking floating button...');
    const triggerBtn = page.locator('button:has-text("Quant Copilot")');
    await triggerBtn.first().click();
    await page.waitForTimeout(1000);
  }

  drawer = page.locator('aside:has-text("QUANT COPILOT")');
  const isDrawerVisible = await drawer.isVisible();
  console.log(`Drawer visibility: ${isDrawerVisible}`);
  if (!isDrawerVisible) {
    throw new Error('FAILED: Quant Copilot drawer did not open!');
  }
  console.log('✓ Quant Copilot drawer opened successfully.');

  console.log('3. Triggering "Debate Bull vs Bear Thesis" Action Chip...');
  const debateBtn = page.locator('button:has-text("Debate Bull vs Bear Thesis")');
  await debateBtn.first().click();

  console.log('4. Waiting for multi-agent deliberation streaming stages...');
  // Wait for Bull Analyst to show text
  await page.waitForSelector('text=Bull Analyst', { timeout: 10000 });
  console.log('  ✓ Bull Analyst card rendered.');

  // Wait for Bear Analyst to show text
  await page.waitForSelector('text=Bear Analyst', { timeout: 15000 });
  console.log('  ✓ Bear Analyst card rendered.');

  // Wait for Portfolio Manager Judge to show text
  await page.waitForSelector('text=Portfolio Manager Debate Judge', { timeout: 15000 });
  console.log('  ✓ Portfolio Manager Judge card rendered.');

  // Wait for completion (progress reaching 100% or "Deliberation concluded")
  await page.waitForSelector('text=Deliberation concluded successfully', { timeout: 20000 });
  console.log('  ✓ Deliberation completed successfully with full multi-agent synthesis!');

  await page.waitForTimeout(1500);

  // Capture Screenshot of Deliberation
  const screenshotPath = path.join(ARTIFACT_DIR, 'copilot_deliberation.png');
  await page.screenshot({ path: screenshotPath, fullPage: false });
  console.log(`5. ✓ Saved Deliberation Screenshot to: ${screenshotPath}`);

  await browser.close();

  console.log('\n=== PLAYWRIGHT COPILOT QA SUMMARY ===');
  console.log(`Total Errors Encountered: ${errors.length}`);
  if (errors.length > 0) {
    console.error('Encountered errors:', errors);
    process.exit(1);
  } else {
    console.log('ALL VERIFICATIONS PASSED: Multi-Agent In-Terminal Copilot is production ready!');
  }
}

testCopilotDeliberation().catch(err => {
  console.error('Test execution failure:', err);
  process.exit(1);
});
