/**
 * FiestaBoard Settings Integration Tests
 *
 * Tests the Settings page UI including:
 *   - Settings page loads with all sections
 *   - Dev mode toggle
 *   - Navigation to Integrations
 *
 * NOTE: Tests run sequentially and depend on the board being
 * configured (Setup Wizard must have completed in an earlier suite).
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
// Settings Page
// ---------------------------------------------------------------------------

test.describe("Settings Page", () => {
  test("loads settings page with all sections visible", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true })
    ).toBeVisible({ timeout: 15_000 });

    // General Settings section should be present
    await expect(page.getByText("General Settings").first()).toBeVisible({
      timeout: 10_000,
    });

    // Boards section
    await expect(page.getByText("Boards").first()).toBeVisible();

    // Advanced section (collapsed by default) contains Debug Tools and Setup Wizard
    const advancedHeading = page.getByRole("heading", { name: "Advanced" });
    await expect(advancedHeading).toBeVisible({ timeout: 5_000 });
    await advancedHeading.click();

    // Debug Tools section (inside Advanced)
    await expect(page.getByText("Debug Tools").first()).toBeVisible({ timeout: 5_000 });

    // Setup Wizard re-run button (inside Advanced)
    await expect(page.getByText("Setup Wizard").first()).toBeVisible();
  });

  test("can navigate to integrations from settings", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true })
    ).toBeVisible({ timeout: 15_000 });

    // Click the integrations link/button
    const integrationsLink = page
      .getByRole("link", { name: /integrations/i })
      .or(page.getByRole("button", { name: /integrations/i }));

    await expect(integrationsLink.first()).toBeVisible({ timeout: 5_000 });
    await integrationsLink.first().click();
    await expect(
      page.getByRole("heading", { name: /integrations/i })
    ).toBeVisible({ timeout: 10_000 });
  });
});
