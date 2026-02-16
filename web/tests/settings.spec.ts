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

    // Board Connection section
    await expect(page.getByText("Board Connection").first()).toBeVisible();

    // Debug Tools section
    await expect(page.getByText("Debug Tools").first()).toBeVisible();

    // Setup Wizard re-run button
    await expect(page.getByText("Setup Wizard").first()).toBeVisible();
  });

  test("can toggle dev mode", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true })
    ).toBeVisible({ timeout: 15_000 });

    // Find the dev mode switch
    const devModeSwitch = page.locator("#dev-mode");
    if (await devModeSwitch.isVisible({ timeout: 5_000 }).catch(() => false)) {
      // Get initial state
      const initialChecked = await devModeSwitch.isChecked();

      // Toggle it and wait for the API response
      const toggleResponse = page.waitForResponse(
        (r) => r.url().includes("/dev-mode") && r.status() === 200
      );
      await devModeSwitch.click();
      await toggleResponse;

      // Verify it changed
      const newChecked = await devModeSwitch.isChecked();
      expect(newChecked).toBe(!initialChecked);

      // Toggle back to original and wait for the API response
      const revertResponse = page.waitForResponse(
        (r) => r.url().includes("/dev-mode") && r.status() === 200
      );
      await devModeSwitch.click();
      await revertResponse;
    }
  });

  test("can navigate to integrations from settings", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true })
    ).toBeVisible({ timeout: 15_000 });

    // Look for a link or button that goes to integrations
    const integrationsLink = page
      .getByRole("link", { name: /integrations/i })
      .or(page.getByRole("button", { name: /integrations/i }));

    if (
      await integrationsLink
        .first()
        .isVisible({ timeout: 5_000 })
        .catch(() => false)
    ) {
      await integrationsLink.first().click();
      await expect(
        page.getByRole("heading", { name: /integrations/i })
      ).toBeVisible({ timeout: 10_000 });
    }
  });
});
