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
import { configureBoard, expect, test } from "./helpers";

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
    await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible({ timeout: 15_000 });

    // Both tabs should be present
    await expect(page.getByRole("tab", { name: /installed/i })).toBeVisible({ timeout: 5_000 });
    await expect(page.getByRole("tab", { name: /marketplace/i })).toBeVisible({ timeout: 5_000 });
  });

  test("Installed tab shows installed plugins", async ({ page }) => {
    await page.goto("/integrations");

    // The Installed tab should be active by default
    await expect(page.getByRole("tab", { name: /installed/i })).toBeVisible({ timeout: 15_000 });

    // At least one known plugin name from the default installation
    // should be visible in the Installed list. Scoped to the tab panel: a
    // page-wide substring match also finds the sidebar's collapsed "Update
    // to x.y.z" item ("Date" in "Update"), which is hidden whenever a newer
    // release exists, and `.first()` then resolves to it.
    const installed = page.getByRole("tabpanel", { name: /installed/i });
    const pluginLocator = installed
      .getByText("Weather", { exact: false })
      .or(installed.getByText("Date", { exact: false }))
      .or(installed.getByText("Stocks", { exact: false }))
      .or(installed.getByText("Traffic", { exact: false }));

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
    await page
      .getByRole("button", { name: /add from git/i })
      .first()
      .click();

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

    await page
      .getByRole("button", { name: /add from git/i })
      .first()
      .click();
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

    await page
      .getByRole("button", { name: /add from git/i })
      .first()
      .click();
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

    await page
      .getByRole("button", { name: /add from git/i })
      .first()
      .click();
    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 5_000 });

    // Cancel closes the dialog
    await page.getByRole("button", { name: /cancel/i }).click();
    await expect(page.getByRole("dialog")).not.toBeVisible({ timeout: 3_000 });
  });
});

// ---------------------------------------------------------------------------
// Check for Updates
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Drill-in motion
// ---------------------------------------------------------------------------

test.describe("Drill-in motion", () => {
  test("holds a plugin page's body back until the header has settled", async ({ page }) => {
    // The sub-header grows for one Reveal beat as a plugin opens; the body
    // waits that beat so it is not seen half-faded while being pushed down.
    // jsdom cannot see this: the delay has to win over FiestaUI's own
    // `animation` shorthand in the real cascade.
    await page.goto("/integrations?tab=marketplace");
    const open = page.locator("a[href*='/integrations/']").first();
    await expect(open).toBeVisible({ timeout: 15_000 });

    await open.click();
    await expect(page).toHaveURL(/\/integrations\/[^?]+/, { timeout: 10_000 });

    const timing = await page
      .locator("[data-slot=page-outlet] > *")
      .first()
      .evaluate((el) => {
        // Resolve the token the way the browser does, on a probe element.
        const probe = document.createElement("div");
        probe.style.transitionDuration = "var(--motion-duration-base)";
        document.body.append(probe);
        const base = getComputedStyle(probe).transitionDuration;
        probe.remove();
        const cs = getComputedStyle(el);
        return { name: cs.animationName, delay: cs.animationDelay, base };
      });
    expect(timing.name).toBe("page-outlet-enter");
    expect(timing.base).not.toBe("0s");
    expect(timing.delay).toBe(timing.base);
  });
});

test.describe("Check for Updates", () => {
  test("saves the auto-update switch from the page toolbar", async ({ page }) => {
    // Plugin updates moved here from Settings in 10.0.
    await page.goto("/integrations");
    await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible({ timeout: 15_000 });

    // It rides with the Installed tab on the toolbar row, not in the header.
    const toolbar = page.locator("[data-slot=page-toolbar]");
    const toggle = toolbar.getByRole("switch", { name: "Auto-update plugins" });
    await expect(toggle).toBeVisible({ timeout: 10_000 });
    await expect(page.locator("[data-slot=page-header]").getByRole("switch")).toHaveCount(0);
    const wasOn = (await toggle.getAttribute("aria-checked")) === "true";

    const save = page.waitForResponse(
      (resp) => resp.url().includes("/settings/plugins") && resp.request().method() === "PUT",
      { timeout: 10_000 },
    );
    await toggle.click();
    expect((await save).status()).toBe(200);
    await expect(toggle).toHaveAttribute("aria-checked", wasOn ? "false" : "true", { timeout: 5_000 });

    // Put it back.
    const restore = page.waitForResponse(
      (resp) => resp.url().includes("/settings/plugins") && resp.request().method() === "PUT",
      { timeout: 10_000 },
    );
    await toggle.click();
    expect((await restore).status()).toBe(200);
    await expect(toggle).toHaveAttribute("aria-checked", wasOn ? "true" : "false", { timeout: 5_000 });
  });

  test("hides the auto-update switch on the Marketplace tab", async ({ page }) => {
    await page.goto("/integrations");
    const toggle = page.getByRole("switch", { name: "Auto-update plugins" });
    await expect(toggle).toBeVisible({ timeout: 15_000 });

    await page.getByRole("tab", { name: /marketplace/i }).click();

    await expect(toggle).toHaveCount(0);
  });

  test("keeps the auto-update switch on one line on a phone", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/integrations");
    const toggle = page.getByRole("switch", { name: "Auto-update plugins" });
    await expect(toggle).toBeVisible({ timeout: 15_000 });
    const label = page.getByText("Auto-update plugins", { exact: true });
    const [sw, lb] = [await toggle.boundingBox(), await label.boundingBox()];
    // One line: the label sits beside the switch and does not wrap.
    expect(lb!.height).toBeLessThan(sw!.height + 8);
    expect(Math.abs(lb!.y + lb!.height / 2 - (sw!.y + sw!.height / 2))).toBeLessThan(4);
  });

  test("shows Check for updates as the section header's action", async ({ page }) => {
    await page.goto("/integrations");
    await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible({ timeout: 15_000 });

    const header = page.locator("[data-slot=page-header]");
    await expect(header.getByRole("button", { name: /check for updates/i })).toBeVisible({ timeout: 5_000 });
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
    await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: /check for updates/i }).click();

    await expect(page.getByText("All plugins are up to date")).toBeVisible({ timeout: 5_000 });
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
    await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("button", { name: /check for updates/i }).click();

    await expect(page.getByText("1 plugin update available")).toBeVisible({ timeout: 5_000 });
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
    await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible({ timeout: 15_000 });

    // Wait for the initial plugin list load to complete
    await page.waitForLoadState("networkidle").catch(() => {});
    const countAfterLoad = pluginsRequestCount;

    await page.getByRole("button", { name: /check for updates/i }).click();

    // Error toast should appear
    await expect(page.getByText(/Couldn't check for updates/)).toBeVisible({ timeout: 5_000 });

    // The finally block must trigger a plugin list refresh even on error
    await expect.poll(() => pluginsRequestCount, { timeout: 5_000 }).toBeGreaterThan(countAfterLoad);
  });
});
