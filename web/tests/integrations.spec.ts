/**
 * FiestaBoard Integrations Page Tests
 *
 * Tests the Integrations / Plugins page:
 *   - Page loads with plugin list
 *   - Plugin cards display name and status
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
  test("loads the integrations page with plugin list", async ({ page }) => {
    await page.goto("/integrations");

    // Wait for the page to load
    await expect(
      page.getByRole("heading", { name: /integrations/i })
    ).toBeVisible({ timeout: 15_000 });

    // At least one known plugin name from the default installation
    // should be visible on the page
    const pluginLocator = page
      .getByText("Weather", { exact: false })
      .or(page.getByText("Date", { exact: false }))
      .or(page.getByText("Stocks", { exact: false }))
      .or(page.getByText("Traffic", { exact: false }));

    await expect(pluginLocator.first()).toBeVisible({ timeout: 10_000 });
  });
});
