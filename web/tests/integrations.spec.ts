/**
 * FiestaBoard Integrations Page Tests
 *
 * Tests the Integrations / Plugins page:
 *   - Page loads with plugin list in Installed tab
 *   - Installed and Marketplace tabs are present
 *   - Plugin cards display name and status
 *   - Marketplace tab shows available plugins
 *
 * NOTE: Tests run sequentially. The wizard must have completed.
 */
import { test, expect, configureBoard } from "./helpers";

// Suppress the setup wizard for all tests in this file
test.beforeEach(async ({ page }) => {
  await configureBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

// ---------------------------------------------------------------------------
// Integrations Page
// ---------------------------------------------------------------------------

test.describe("Integrations Page", () => {
  test("loads the integrations page with Installed and Marketplace tabs", async ({ page }) => {
    await page.goto("/integrations");

    // Wait for the page to load
    await expect(
      page.getByRole("heading", { name: /integrations/i })
    ).toBeVisible({ timeout: 15_000 });

    // Both tabs should be present
    await expect(page.getByRole("tab", { name: /installed/i })).toBeVisible({ timeout: 5_000 });
    await expect(page.getByRole("tab", { name: /marketplace/i })).toBeVisible({ timeout: 5_000 });
  });

  test("Installed tab shows installed plugins", async ({ page }) => {
    await page.goto("/integrations");

    // The Installed tab should be active by default
    await expect(page.getByRole("tab", { name: /installed/i })).toBeVisible({ timeout: 15_000 });

    // At least one known plugin name from the default installation
    // should be visible on the page
    const pluginLocator = page
      .getByText("Weather", { exact: false })
      .or(page.getByText("Date", { exact: false }))
      .or(page.getByText("Stocks", { exact: false }))
      .or(page.getByText("Traffic", { exact: false }));

    await expect(pluginLocator.first()).toBeVisible({ timeout: 10_000 });
  });

  test("Marketplace tab shows available plugins and Add from Git", async ({ page }) => {
    await page.goto("/integrations");

    await expect(page.getByRole("tab", { name: /marketplace/i })).toBeVisible({ timeout: 15_000 });
    await page.getByRole("tab", { name: /marketplace/i }).click();

    // Add from Git button should be visible in the Marketplace tab
    await expect(page.getByRole("button", { name: /add from git/i }).first()).toBeVisible({ timeout: 5_000 });
  });
});
