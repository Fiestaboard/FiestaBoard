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
  test("loads settings page with all sections listed", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    // The list-detail (slice 2.1) lists the reader's own sections ("You")
    // and the hub's ("Hub · <name>"); boards moved to Displays (plan D21).
    const you = page.getByRole("list", { name: "You" });
    const hub = page.getByRole("list", { name: /^Hub · / });
    await expect(you.getByRole("link")).toHaveText(["Account", "Appearance", "Accessibility"], { timeout: 15_000 });
    await expect(hub.getByRole("link")).toHaveText(["Network", "AI provider", "System & backups", "Language & time"]);
    // Scheduling now belongs to display Playback; there is no Hardware,
    // Behavior or Integrations section, and no tab strip at all.
    for (const gone of ["Hardware", "Behavior", "Scheduling", "Integrations"]) {
      await expect(
        page.locator('[data-slot="settings-index"]').getByRole("link", { name: gone, exact: true }),
      ).toHaveCount(0);
    }
    await expect(page.getByRole("tab")).toHaveCount(0);

    // Network carries MQTT (moved from Integrations, then General)
    await hub.getByRole("link", { name: "Network" }).click();
    await expect(page).toHaveURL(/\/settings\/network$/);
    await expect(page.getByText("Home Assistant (MQTT)")).toBeVisible({ timeout: 10_000 });

    // Installed hubs keep Debug Tools here. Setup is only available while
    // the hub has no displays; existing displays are managed in Displays.
    await hub.getByRole("link", { name: "System & backups" }).click();
    await expect(page).toHaveURL(/\/settings\/system$/);
    await expect(page.getByText("Debug Tools").first()).toBeVisible({
      timeout: 5_000,
    });
    await expect(page.getByText("Setup Wizard", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Run Setup Wizard", exact: true })).toHaveCount(0);
    await expect(page.getByText("About This FiestaBoard")).toHaveCount(0);
  });

  test("an old ?section=behavior link opens display Playback", async ({ page }) => {
    await page.goto("/settings?section=behavior");
    await expect(page.getByRole("tab", { name: "Playback", exact: true })).toHaveAttribute("aria-selected", "true", {
      timeout: 15_000,
    });
    await expect(page).toHaveURL(/\/displays\/[^/?]+\?section=playback$/);
    const playback = page.getByRole("region", { name: "Playback", exact: true });
    await expect(playback).toBeVisible({ timeout: 10_000 });
    await expect(playback.getByRole("heading", { name: "Silence Schedule", exact: true })).toBeVisible();
    await expect(playback.getByRole("switch", { name: "Silence Schedule", exact: true })).toBeVisible();
    await expect(playback.getByRole("heading", { name: "Update Intervals", exact: true })).toBeVisible();
  });

  test("an old ?section=integrations link opens AI provider", async ({ page }) => {
    await page.goto("/settings?section=integrations");
    await expect(page).toHaveURL(/\/settings\/ai-provider$/, { timeout: 15_000 });
    await expect(
      page.getByRole("list", { name: /^Hub · / }).getByRole("link", { name: "AI provider" }),
    ).toHaveAttribute("aria-current", "page", { timeout: 15_000 });
    await expect(page.getByRole("heading", { level: 2, name: "AI provider", exact: true })).toBeVisible();
    await expect(page.getByText("AI Providers", { exact: true })).toBeVisible({ timeout: 10_000 });
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
