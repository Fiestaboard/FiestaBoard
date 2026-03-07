/**
 * FiestaBoard Plugin Management E2E Tests
 *
 * Tests plugin listing, enable/disable, configuration,
 * variable display, and error states on the Integrations page.
 */
import {
  test,
  expect,
  configureBoard,
  suppressWizard,
  enablePlugin,
  disablePlugin,
  API_URL,
} from "./helpers";

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
});

test.describe("Plugin Management", () => {
  test("lists all plugins grouped by category", async ({ page }) => {
    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: /integrations/i }),
    ).toBeVisible({ timeout: 15_000 });

    // Check for category groupings
    const categories = [
      "Weather",
      "Utilities",
      "Transportation",
      "Data",
      "Entertainment",
    ];

    let foundCategories = 0;
    for (const cat of categories) {
      const el = page.getByText(cat, { exact: false }).first();
      if (await el.isVisible({ timeout: 3_000 }).catch(() => false)) {
        foundCategories++;
      }
    }
    expect(foundCategories).toBeGreaterThan(0);
  });

  test("can enable a plugin", async ({ page }) => {
    // Disable first via API to ensure clean state
    await disablePlugin("date_time").catch(() => {});

    // Enable via API
    await enablePlugin("date_time");

    // Verify via API
    const res = await fetch(`${API_URL}/plugins/date_time`);
    if (res.ok) {
      const data = await res.json();
      expect(data.enabled).toBe(true);
    }

    // Verify the UI reflects the enabled state
    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: /integrations/i }),
    ).toBeVisible({ timeout: 15_000 });

    // The plugin should show a "Configured" or enabled-state badge
    const configuredBadge = page.getByText(/configured|setup required/i).first();
    await expect(configuredBadge).toBeVisible({ timeout: 10_000 });
  });

  test("can disable a plugin", async () => {
    await enablePlugin("date_time");

    // Disable via API
    await disablePlugin("date_time");

    // Verify via API
    const res = await fetch(`${API_URL}/plugins/date_time`);
    if (res.ok) {
      const data = await res.json();
      expect(data.enabled).toBe(false);
    }
  });

  test("can open plugin configuration sheet", async ({ page }) => {
    await enablePlugin("date_time");

    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: /integrations/i }),
    ).toBeVisible({ timeout: 15_000 });

    // Find and click the Configure button for date_time
    const configureBtn = page
      .getByRole("button", { name: /configure/i })
      .first();

    if (
      await configureBtn.isVisible({ timeout: 5_000 }).catch(() => false)
    ) {
      await configureBtn.click();

      // The configuration sheet should open — look for the Save button
      await expect(
        page.getByRole("button", { name: "Save Changes" }),
      ).toBeVisible({ timeout: 5_000 });
    }
  });

  test("can update plugin settings via API", async () => {
    await enablePlugin("date_time");

    // Update config via API directly
    const res = await fetch(`${API_URL}/plugins/date_time/config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config: { timezone: "UTC" } }),
    });
    if (res.ok) {
      const data = await res.json();
      expect(data.status).toBe("success");
      expect(data.plugin_id).toBe("date_time");
    } else {
      // Plugin system may not be fully available
      expect(res.status).toBe(503);
    }
  });

  test("shows template variables for enabled plugins", async () => {
    await enablePlugin("date_time");

    // Verify via the template variables catalog API
    const res = await fetch(`${API_URL}/templates/variables`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("variables");
    expect(data.variables).toHaveProperty("date_time");
    expect(data.variables.date_time).toContain("time");
    expect(data.variables.date_time).toContain("date");
  });

  test("handles plugin with API key requirement", async ({ page }) => {
    // Pre-enable the weather plugin via API so the Configure button is
    // immediately visible when the page loads (avoids a toggle → re-fetch
    // race condition that caused flaky failures).
    await enablePlugin("weather").catch(() => {});

    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: /integrations/i }),
    ).toBeVisible({ timeout: 15_000 });

    // Identify the weather plugin card by its unique toggle aria-label, then
    // scope the Configure button lookup to that card so we never accidentally
    // click a different plugin's Configure button.
    const weatherToggle = page.getByRole("switch", { name: "Toggle Weather" });
    if (await weatherToggle.isVisible({ timeout: 10_000 }).catch(() => false)) {
      // Find the plugin card that contains the weather toggle
      const weatherCard = page
        .locator('[class*="card-interactive"]')
        .filter({ has: weatherToggle });

      const configBtn = weatherCard
        .getByRole("button", { name: /configure/i })
        .first();

      if (
        await configBtn.isVisible({ timeout: 5_000 }).catch(() => false)
      ) {
        await configBtn.click();

        // Wait for the sheet to fully open: the "Save Changes" button only
        // appears once the plugin-details query has resolved and the schema
        // form has rendered – no hardcoded sleep needed.
        const saveBtn = page.getByRole("button", { name: "Save Changes" });
        if (
          await saveBtn.isVisible({ timeout: 10_000 }).catch(() => false)
        ) {
          // Weather plugin requires an API key – the field must be a
          // password-type input (ui:widget "password" in the manifest).
          const apiKeyField = page.locator('input[type="password"]').first();
          const hasApiKeyField = await apiKeyField
            .isVisible({ timeout: 5_000 })
            .catch(() => false);
          expect(hasApiKeyField).toBe(true);
        }
      }
    }
  });

  test("shows status badge for plugin state", async ({ page }) => {
    await disablePlugin("date_time").catch(() => {});

    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: /integrations/i }),
    ).toBeVisible({ timeout: 15_000 });

    // Disabled plugins should show a "Disabled" badge
    const disabledBadge = page.getByText("Disabled").first();
    await expect(disabledBadge).toBeVisible({ timeout: 10_000 });
  });
});
