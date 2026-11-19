/**
 * Market Intelligence Lab — End-to-End Playwright Test Suite
 * Workstream A9 — Critical user interaction journeys & validation invariants
 */

import { test, expect } from "@playwright/test";

test.describe("MIL Cockpit Critical Paths", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("should render the cockpit header and brand identity", async ({ page }) => {
    await expect(page.locator("text=MIL.QUANT")).toBeVisible();
    await expect(page.locator("text=V8")).toBeVisible();
  });

  test("should toggle view modes: table, heatmap, and cards", async ({ page }) => {
    // 1. Default table view
    const tableButton = page.locator("button:has-text('Screener')");
    await expect(tableButton).toBeVisible();

    // 2. Switch to Cards mode (L1)
    const cardsButton = page.locator("button:has-text('Cards')");
    if (await cardsButton.isVisible()) {
      await cardsButton.click();
      await expect(page).toHaveURL(/view=cards/);
    }

    // 3. Switch to Heatmap mode
    const heatmapButton = page.locator("button:has-text('Heatmap')");
    if (await heatmapButton.isVisible()) {
      await heatmapButton.click();
      await expect(page).toHaveURL(/view=heatmap/);
    }
  });

  test("should open Command Palette via ⌘K shortcut", async ({ page }) => {
    await page.keyboard.press("Meta+k");
    const searchInput = page.locator("input[placeholder*='Search']");
    await expect(searchInput).toBeVisible();
  });

  test("should open Quant Copilot drawer via ⌘J shortcut", async ({ page }) => {
    await page.keyboard.press("Meta+j");
    await expect(page.locator("text=Quant Deliberation Committee")).toBeVisible();
  });

  test("should navigate to Portfolio and verify positions blotter", async ({ page }) => {
    await page.click("a[href='/portfolio']");
    await expect(page).toHaveURL("/portfolio");
    await expect(page.locator("text=Active Holdings")).toBeVisible();
  });

  test("should navigate to Backtest terminal and verify strategy presets", async ({ page }) => {
    await page.click("a[href='/backtest']");
    await expect(page).toHaveURL("/backtest");
    await expect(page.locator("text=Walk-Forward Backtesting Engine")).toBeVisible();
  });
});
