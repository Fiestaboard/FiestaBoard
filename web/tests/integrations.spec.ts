/**
 * FiestaBoard Integrations Page Tests
 *
 * Tests the Integrations / Plugins page:
 *   - Page loads with plugin list
 *   - Plugin cards display name and status
 *
 * NOTE: Tests run sequentially. The wizard must have completed.
 */
import { test, expect } from "./helpers";

// Suppress the setup wizard for all tests in this file
test.beforeEach(async ({ page }) => {
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

    // The page should display some plugin cards or a list
    // Plugins are grouped by category — look for any plugin name
    // that should be present in the default installation
    const pluginNames = [
      "Weather",
      "Date",
      "Time",
      "Stocks",
      "Traffic",
    ];

    // At least one known plugin name should be visible
    let foundPlugin = false;
    for (const name of pluginNames) {
      const el = page.getByText(name, { exact: false }).first();
      if (await el.isVisible({ timeout: 2_000 }).catch(() => false)) {
        foundPlugin = true;
        break;
      }
    }

    expect(foundPlugin).toBe(true);
  });
});
