/**
 * Auto-generated regression stubs from .claude/ux-coverage.json.
 * Subarea: settings.tab-advanced
 */
import {
  test,
  expect,
  configureBoard,
  loginIfNeeded,
  ensureAuthForFetch,
} from "../helpers";

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
   * Route: /settings (Advanced tab)
   * Expected (missing from current coverage):
   *   - log-level Select exercised
   *   - BetaSettings beta-channel toggle tested
   *   - download-diagnostics action clicked
   * See also: web/tests/settings.spec.ts:59; settings-full.spec.ts:259,281
   * Coverage status: partial
   *
   * Implementation note: the coverage doc references a few controls that
   * don't (currently) live on this tab — the Advanced tab today hosts
   * `DebugSettings` (collapsible) and `BetaSettings` (HTTPS toggle). This
   * test exercises what is actually rendered: the Debug Tools collapsible
   * with its Fill-Board character Select, and the Beta HTTPS toggle. If
   * the missing controls (log-level / download-diagnostics) are added
   * later, extend this test rather than create a new one.
   */
  test("settings.tab-advanced — debug collapsible, fill-board select, and beta HTTPS toggle render", async ({ page }) => {
    await page.goto("/settings?section=advanced");

    await expect(
      page.getByRole("heading", { name: "Settings", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // The Advanced tab should already be selected via the URL param,
    // but click it defensively in case the default falls back.
    await page.getByRole("tab", { name: "Advanced", exact: true }).click();

    // Beta Settings — HTTPS toggle is the load-bearing control on this tab.
    const httpsSwitch = page.getByRole("switch", { name: /https/i });
    await expect(httpsSwitch).toBeVisible({ timeout: 10_000 });
    // State-distinguishing assertion: the switch reports an aria-checked
    // value (true|false), not undefined. Confirms it's bound to data, not
    // stuck loading.
    const checked = await httpsSwitch.getAttribute("aria-checked");
    expect(checked === "true" || checked === "false").toBe(true);

    // Debug Tools collapsible — expand it and verify the Fill-Board
    // Select (the only Select on this tab) is exercisable.
    await page.getByText("Debug Tools").first().click();

    const fillCharSelect = page.locator("#fill-character");
    await expect(fillCharSelect).toBeVisible({ timeout: 5_000 });
    // The default selected character is Red (code 63) — assert state.
    await expect(fillCharSelect).toContainText(/red/i);

    // Network Diagnostics button is the other always-enabled action on
    // this tab (it doesn't require a configured board).
    await expect(
      page.getByRole("button", { name: /run network diagnostics/i }),
    ).toBeVisible();
  });
});
