/**
 * Auto-generated regression stubs from .claude/ux-coverage.json.
 * Subarea: settings.tab-advanced
 */
import { configureBoard, ensureAuthForFetch, expect, loginIfNeeded, test } from "../helpers";

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

test.describe("regression: settings.advanced", () => {
  /**
   * UX node: settings.tab-advanced
   * Route: /settings/system (was the Advanced tab)
   * Expected (missing from current coverage):
   *   - log-level Select exercised
   *   - download-diagnostics action clicked
   * See also: web/tests/settings.spec.ts:59; settings-full.spec.ts:259,281
   * Coverage status: partial
   *
   * Implementation note: the coverage doc references a few controls that
   * don't (currently) live on this tab — the Advanced tab today hosts only
   * `DebugSettings` (collapsible). The Beta card is gone (settings v6): the
   * transition plugins switch moved to each display's Transition section,
   * the output plugins switch to the Integrations page, and HTTPS (Beta)
   * was removed in settings v5. This test exercises what is actually
   * rendered: the Debug Tools collapsible with its Fill-Board character
   * Select, and that no beta switch is left here. If
   * the missing controls (log-level / download-diagnostics) are added
   * later, extend this test rather than create a new one.
   */
  test("settings.tab-advanced — debug collapsible and fill-board select render, no beta toggles", async ({ page }) => {
    await page.goto("/settings?section=advanced");

    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    // The Advanced tab folded into System & backups (slice 2.1); the old
    // link redirects there.
    await expect(page).toHaveURL(/\/settings\/system$/);
    await expect(
      page.getByRole("list", { name: /^Hub · / }).getByRole("link", { name: "System & backups" }),
    ).toHaveAttribute("aria-current", "page", { timeout: 15_000 });

    // Debug Tools (the old Advanced tab, settings v6): no beta switch is left here.
    await expect(page.getByText("Debug Tools").first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("switch", { name: "Transition Plugins" })).toHaveCount(0);
    await expect(page.getByRole("switch", { name: /output plugins/i })).toHaveCount(0);
    await expect(page.getByRole("switch", { name: /https/i })).toHaveCount(0);

    // Debug Tools collapsible — expand it and verify the Fill-Board
    // Select is exercisable.
    await page.getByText("Debug Tools").first().click();

    const fillCharSelect = page.locator("#fill-character");
    await expect(fillCharSelect).toBeVisible({ timeout: 5_000 });
    // The default selected character is Red (code 63) — assert state.
    await expect(fillCharSelect).toContainText(/red/i);

    // Network Diagnostics button is the other always-enabled action on
    // this tab (it doesn't require a configured board).
    await expect(page.getByRole("button", { name: /run network diagnostics/i })).toBeVisible();
  });
});
