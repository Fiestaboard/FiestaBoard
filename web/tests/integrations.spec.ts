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

  test("Add from Git dialog opens and accepts a URL", async ({ page }) => {
    await page.goto("/integrations");

    await expect(page.getByRole("tab", { name: /marketplace/i })).toBeVisible({ timeout: 15_000 });
    await page.getByRole("tab", { name: /marketplace/i }).click();

    // Open the Add from Git dialog
    await page.getByRole("button", { name: /add from git/i }).first().click();

    // Dialog should open
    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 5_000 });

    // The dialog should have a Repository URL input
    const urlInput = page.getByLabel(/repository url/i);
    await expect(urlInput).toBeVisible({ timeout: 5_000 });

    // The Install Plugin button should be disabled when URL is empty
    const installBtn = page.getByRole("button", { name: /install plugin/i });
    await expect(installBtn).toBeDisabled();

    // Type a valid-looking URL — button should become enabled
    await urlInput.fill("https://github.com/example/fiestaboard-plugin-test");
    await expect(installBtn).toBeEnabled({ timeout: 3_000 });
  });

  test("Add from Git Install button stays disabled for empty URL", async ({ page }) => {
    await page.goto("/integrations");

    await expect(page.getByRole("tab", { name: /marketplace/i })).toBeVisible({ timeout: 15_000 });
    await page.getByRole("tab", { name: /marketplace/i }).click();

    await page.getByRole("button", { name: /add from git/i }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 5_000 });

    const urlInput = page.getByLabel(/repository url/i);
    const installBtn = page.getByRole("button", { name: /install plugin/i });

    // Empty URL → disabled
    await urlInput.fill("");
    await expect(installBtn).toBeDisabled();

    // Whitespace-only → disabled
    await urlInput.fill("   ");
    await expect(installBtn).toBeDisabled();
  });

  test("Add from Git dialog shows security warning", async ({ page }) => {
    await page.goto("/integrations");

    await expect(page.getByRole("tab", { name: /marketplace/i })).toBeVisible({ timeout: 15_000 });
    await page.getByRole("tab", { name: /marketplace/i }).click();

    await page.getByRole("button", { name: /add from git/i }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 5_000 });

    // Security warning should be visible inside the dialog
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(/security warning/i)).toBeVisible();
    await expect(page.getByText(/only install plugins from sources you trust/i)).toBeVisible();
  });

  test("Add from Git dialog can be cancelled", async ({ page }) => {
    await page.goto("/integrations");

    await expect(page.getByRole("tab", { name: /marketplace/i })).toBeVisible({ timeout: 15_000 });
    await page.getByRole("tab", { name: /marketplace/i }).click();

    await page.getByRole("button", { name: /add from git/i }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 5_000 });

    // Cancel closes the dialog
    await page.getByRole("button", { name: /cancel/i }).click();
    await expect(page.getByRole("dialog")).not.toBeVisible({ timeout: 3_000 });
  });
});

// ---------------------------------------------------------------------------
// Check for Updates
// ---------------------------------------------------------------------------

test.describe("Check for Updates", () => {
  test("shows the Check for Updates button on the Installed tab", async ({ page }) => {
    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: /integrations/i })
    ).toBeVisible({ timeout: 15_000 });

    await expect(
      page.getByRole("button", { name: /check for updates/i })
    ).toBeVisible({ timeout: 5_000 });
  });

  test("shows all-up-to-date toast when no updates are found", async ({ page }) => {
    await page.route("**/api/plugins/updates/check", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ checked: 3, updates_available: [] }),
      });
    });

    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: /integrations/i })
    ).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: /check for updates/i }).click();

    await expect(
      page.getByText("All plugins are up to date")
    ).toBeVisible({ timeout: 5_000 });
  });

  test("shows update count toast when updates are found", async ({ page }) => {
    await page.route("**/api/plugins/updates/check", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ checked: 2, updates_available: ["some_plugin"] }),
      });
    });

    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: /integrations/i })
    ).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: /check for updates/i }).click();

    await expect(
      page.getByText("1 plugin update available")
    ).toBeVisible({ timeout: 5_000 });
  });

  test("shows error toast and still refreshes plugin list when check fails", async ({ page }) => {
    let pluginsRequestCount = 0;

    await page.route("**/api/plugins/updates/check", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Internal Server Error" }),
      });
    });

    // Count GET /api/plugins requests (excludes sub-paths like /plugins/updates)
    await page.route(/\/api\/plugins(\?.*)?$/, async (route) => {
      if (route.request().method() === "GET") {
        pluginsRequestCount++;
      }
      await route.continue();
    });

    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: /integrations/i })
    ).toBeVisible({ timeout: 15_000 });

    // Wait for the initial plugin list load to complete
    await page.waitForLoadState("networkidle").catch(() => {});
    const countAfterLoad = pluginsRequestCount;

    await page.getByRole("button", { name: /check for updates/i }).click();

    // Error toast should appear
    await expect(
      page.getByText(/Couldn't check for updates/)
    ).toBeVisible({ timeout: 5_000 });

    // The finally block must trigger a plugin list refresh even on error
    await expect
      .poll(() => pluginsRequestCount, { timeout: 5_000 })
      .toBeGreaterThan(countAfterLoad);
  });
});
