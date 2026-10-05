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
import { configureBoard, expect, test } from "./helpers";

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
  test("loads settings page with all tab sections visible", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    // Tab strip exposes the five sections; boards moved to Displays (plan D21)
    for (const section of ["General", "Behavior", "Integrations", "System", "Advanced"]) {
      await expect(page.getByRole("tab", { name: section, exact: true })).toBeVisible({ timeout: 5_000 });
    }
    await expect(page.getByRole("tab", { name: "Hardware", exact: true })).toHaveCount(0);

    // Behavior tab contains the Update Intervals and Silence Schedule cards
    await page.getByRole("tab", { name: "Behavior", exact: true }).click();
    await expect(page.getByText("Update Intervals").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("Silence Schedule").first()).toBeVisible();

    // Advanced tab contains Debug Tools
    await page.getByRole("tab", { name: "Advanced", exact: true }).click();
    await expect(page.getByText("Debug Tools").first()).toBeVisible({
      timeout: 5_000,
    });

    // System tab contains the Setup Wizard card
    await page.getByRole("tab", { name: "System", exact: true }).click();
    await expect(page.getByText("Setup Wizard").first()).toBeVisible({
      timeout: 5_000,
    });
  });

  test("can navigate to integrations from settings", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    // Click the integrations link/button
    const integrationsLink = page
      .getByRole("link", { name: /integrations/i })
      .or(page.getByRole("button", { name: /integrations/i }));

    await expect(integrationsLink.first()).toBeVisible({ timeout: 5_000 });
    await integrationsLink.first().click();
    await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible({ timeout: 10_000 });
  });

  test("an old Settings → Hardware link opens Displays", async ({ page }) => {
    await page.goto("/settings?section=hardware");
    await expect(page).toHaveURL(/\/displays$/, { timeout: 15_000 });
    await expect(page.getByRole("heading", { name: "Displays", level: 1 })).toBeVisible({ timeout: 15_000 });
  });
});
