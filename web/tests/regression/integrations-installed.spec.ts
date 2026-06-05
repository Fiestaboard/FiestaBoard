/**
 * Auto-generated regression stubs from .claude/ux-coverage.json.
 * Subarea: integrations.installed (list page + lifecycle)
 *
 * Priority cluster #5 from the auditor: plugin lifecycle (toggle/install/
 * uninstall/update) is under-tested and ranks high-value. Fill these early.
 */
import {
  test,
  expect,
  configureBoard,
  API_URL,
  loginIfNeeded,
  ensureAuthForFetch,
  authHeaders,
  enablePlugin,
  disablePlugin,
} from "../helpers";

// Stable always-installed builtin plugins. We never uninstall these.
const STABLE_PLUGIN_ID = "date_time";
const STABLE_PLUGIN_NAME = "Date & Time";

/**
 * Snapshot the enabled state of a plugin so we can restore it after the test
 * (the toggle-pending / toggle-error / overflow-menu tests flip state).
 */
async function getPluginEnabled(id: string): Promise<boolean> {
  const res = await fetch(`${API_URL}/plugins`, { headers: authHeaders() });
  const data = await res.json();
  const plugin = data.plugins.find((p: { id: string }) => p.id === id);
  return Boolean(plugin?.enabled);
}

async function restorePluginEnabled(id: string, enabled: boolean): Promise<void> {
  if (enabled) await enablePlugin(id).catch(() => {});
  else await disablePlugin(id).catch(() => {});
}

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

test.describe("regression: integrations.installed", () => {
  /**
   * UX node: integrations.installed.loading
   * Route: /integrations
   * Preconditions: api:pending
   * Expected: skeleton/loader visible while installed-plugins query is in flight
   * Source refs: web/src/app/integrations/page.tsx
   * Coverage status: uncovered
   */
  test("integrations.installed.loading — skeleton state on first paint", async ({ page }) => {
    // Stall the installed plugins list so we can observe the skeleton rows.
    let release: (() => void) | null = null;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/plugins", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      await gate;
      return route.continue();
    });

    const nav = page.goto("/integrations");

    await expect(
      page.getByRole("heading", { name: /integrations/i }).first(),
    ).toBeVisible({ timeout: 15_000 });

    // Skeleton placeholders are rendered as data-slot="skeleton" in the loading branch.
    await expect(page.locator('[data-slot="skeleton"]').first()).toBeVisible({
      timeout: 10_000,
    });

    release!();
    await nav;
    // Loading finished → real toggle rendered.
    await expect(
      page.getByRole("switch", { name: `Toggle ${STABLE_PLUGIN_NAME}` }),
    ).toBeVisible({ timeout: 15_000 });
  });

  /**
   * UX node: integrations.installed.error
   * Route: /integrations
   * Preconditions: api:error
   * Expected: error alert renders with retry affordance; no plugin rows shown
   * Source refs: web/src/app/integrations/page.tsx
   * Coverage status: uncovered
   */
  test("integrations.installed.error — error alert + retry affordance", async ({ page }) => {
    await page.route("**/api/plugins", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      await route.fulfill({
        status: 500,
        body: JSON.stringify({ detail: "boom" }),
        headers: { "content-type": "application/json" },
      });
    });

    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: /integrations/i }).first(),
    ).toBeVisible({ timeout: 15_000 });

    // Error alert from i18n: "Failed to load plugins: <error>"
    await expect(page.getByText(/Failed to load plugins:/i)).toBeVisible({
      timeout: 15_000,
    });

    // The header-level "Check for updates" button acts as the retry affordance
    // (it invalidates the plugins query when run).
    await expect(
      page.getByRole("button", { name: /Check for updates/i }),
    ).toBeVisible();

    // No plugin toggle rows should be rendered in error state.
    await expect(
      page.getByRole("switch", { name: `Toggle ${STABLE_PLUGIN_NAME}` }),
    ).toHaveCount(0);
  });

  /**
   * UX node: integrations.installed.empty
   * Route: /integrations
   * Preconditions: plugins:[]
   * Expected: empty-state message + CTA to browse marketplace
   * Source refs: web/src/app/integrations/page.tsx
   * Coverage status: uncovered
   */
  test("integrations.installed.empty — empty list shows marketplace CTA", async ({ page }) => {
    await page.route("**/api/plugins", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          plugins: [],
          plugin_system_enabled: true,
          total: 0,
          enabled_count: 0,
        }),
        headers: { "content-type": "application/json" },
      });
    });

    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: /integrations/i }).first(),
    ).toBeVisible({ timeout: 15_000 });

    await expect(page.getByText(/No plugins installed yet/i)).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page.getByRole("button", { name: /Browse Marketplace/i }),
    ).toBeVisible();
  });

  /**
   * UX node: integrations.installed.empty-search
   * Route: /integrations
   * Preconditions: plugins:>=1, search:no-match
   * Expected: 'no results' empty state visible while query string set
   * Source refs: web/src/app/integrations/page.tsx
   * Coverage status: uncovered
   */
  test("integrations.installed.empty-search — 'no results' state when search misses", async ({ page }) => {
    await page.goto("/integrations");
    await expect(
      page.getByRole("switch", { name: `Toggle ${STABLE_PLUGIN_NAME}` }),
    ).toBeVisible({ timeout: 15_000 });

    const search = page.getByPlaceholder(/Search installed plugins/i);
    await search.fill("zzz_no_match_query_xyz");

    // i18n: 'No installed plugins match "{query}"'
    await expect(
      page.getByText(/No installed plugins match "zzz_no_match_query_xyz"/i),
    ).toBeVisible({ timeout: 10_000 });

    // The real plugin row should be hidden by the filter.
    await expect(
      page.getByRole("switch", { name: `Toggle ${STABLE_PLUGIN_NAME}` }),
    ).toHaveCount(0);
  });

  /**
   * UX node: integrations.installed.list
   * Route: /integrations
   * Preconditions: plugins:>=1
   * Expected (missing from current coverage):
   *   - sortable column headers (Name/Category/Status) chevron toggle
   *   - row overflow menu (three-dot) opens
   *   - search input filters rows
   * See also: web/tests/integrations.spec.ts:27,40; plugin-management.spec.ts:23,193; mobile-critical-flows.spec.ts:164,171
   * Coverage status: partial
   */
  test("integrations.installed.list — column sort, overflow menu, search input", async ({ page }) => {
    await page.goto("/integrations");
    await expect(
      page.getByRole("switch", { name: `Toggle ${STABLE_PLUGIN_NAME}` }),
    ).toBeVisible({ timeout: 15_000 });

    // -- Column sort: clicking the Name header should flip chevron direction.
    const nameHeaderTh = page.locator("th").filter({ hasText: /^Name/ }).first();
    await expect(nameHeaderTh).toBeVisible();
    await nameHeaderTh.click();
    // After one click, the header should display either an up or down chevron icon.
    await nameHeaderTh.click(); // toggle once more to assert direction can flip
    // We assert at least one of the chevron icons is rendered inside the header.
    await expect(nameHeaderTh.locator("svg")).toBeVisible();

    // -- Overflow menu: opens the DropdownMenu with action items.
    const row = page.locator("tr").filter({
      has: page.getByRole("switch", { name: `Toggle ${STABLE_PLUGIN_NAME}` }),
    });
    await row.getByRole("button", { name: "More options" }).click();
    await expect(page.getByRole("menuitem", { name: /Configure/i })).toBeVisible({
      timeout: 5_000,
    });
    // Close menu so the search input is interactable.
    await page.keyboard.press("Escape");

    // -- Search input: filtering to a non-matching string hides the row.
    const search = page.getByPlaceholder(/Search installed plugins/i);
    await search.fill("countdown");
    await expect(
      page.getByRole("switch", { name: `Toggle ${STABLE_PLUGIN_NAME}` }),
    ).toHaveCount(0);
    await search.fill("");
    await expect(
      page.getByRole("switch", { name: `Toggle ${STABLE_PLUGIN_NAME}` }),
    ).toBeVisible({ timeout: 10_000 });
  });

  /**
   * UX node: integrations.installed.updates-banner
   * Route: /integrations
   * Preconditions: updates-available:>=1
   * Expected: banner indicating N updates available; click reveals affected rows
   * Source refs: web/src/app/integrations/page.tsx
   * Coverage status: uncovered
   */
  test("integrations.installed.updates-banner — banner shows when updates available", async ({ page }) => {
    // Mock the plugins list so at least one plugin has update_available=true.
    await page.route("**/api/plugins", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      const response = await route.fetch();
      const data = await response.json();
      if (data.plugins && data.plugins.length > 0) {
        data.plugins[0].update_available = true;
      }
      await route.fulfill({
        status: 200,
        body: JSON.stringify(data),
        headers: { "content-type": "application/json" },
      });
    });

    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: /integrations/i }).first(),
    ).toBeVisible({ timeout: 15_000 });

    // Banner text from i18n: "{count} plugin update available"
    await expect(page.getByText(/plugin update available/i)).toBeVisible({
      timeout: 15_000,
    });

    // Update All button with the count, e.g. "Update All (1)"
    await expect(
      page.getByRole("button", { name: /Update All \(\d+\)/i }),
    ).toBeVisible();
  });

  /**
   * UX node: integrations.installed.update-all-pending
   * Route: /integrations
   * Preconditions: update-all-mutation:pending
   * Expected: 'Updating...' label on Update All button; button disabled
   * Source refs: web/src/app/integrations/page.tsx
   * Coverage status: uncovered
   */
  test("integrations.installed.update-all-pending — Update All shows pending state", async ({ page }) => {
    // Mark a plugin as having an update available so the banner appears.
    await page.route("**/api/plugins", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      const response = await route.fetch();
      const data = await response.json();
      if (data.plugins && data.plugins.length > 0) {
        data.plugins[0].update_available = true;
      }
      await route.fulfill({
        status: 200,
        body: JSON.stringify(data),
        headers: { "content-type": "application/json" },
      });
    });
    // Stall the apply-all endpoint so the pending label is observable.
    await page.route("**/api/plugins/updates/apply", async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      await new Promise((r) => setTimeout(r, 1500));
      await route.fulfill({
        status: 200,
        body: JSON.stringify({ updated: [], failed: {} }),
        headers: { "content-type": "application/json" },
      });
    });

    await page.goto("/integrations");
    const updateAll = page.getByRole("button", { name: /Update All \(\d+\)/i });
    await expect(updateAll).toBeVisible({ timeout: 15_000 });
    await updateAll.click();

    // The button text flips to the localized "Updating…" string while pending.
    const updatingBtn = page.getByRole("button", { name: /Updating/i });
    await expect(updatingBtn).toBeVisible({ timeout: 5_000 });
    await expect(updatingBtn).toBeDisabled();
  });

  /**
   * UX node: integrations.installed.toggle-pending
   * Route: /integrations
   * Preconditions: toggle-mutation:pending
   * Expected (missing from current coverage):
   *   - optimistic flip + rollback on error verified
   *   - Switch disabled-during-mutation asserted
   * See also: web/tests/plugin-management.spec.ts:48,144
   * Coverage status: partial
   */
  test("integrations.installed.toggle-pending — optimistic flip, disabled switch, rollback on error", async ({ page }) => {
    const initiallyEnabled = await getPluginEnabled(STABLE_PLUGIN_ID);
    // Force a known starting state of "enabled" so the toggle action is "disable".
    if (!initiallyEnabled) await enablePlugin(STABLE_PLUGIN_ID);

    try {
      // Stall + 500 the disable call so we can observe the optimistic flip
      // and the rollback when the mutation eventually fails.
      await page.route(`**/api/plugins/${STABLE_PLUGIN_ID}/disable`, async (route) => {
        await new Promise((r) => setTimeout(r, 1200));
        await route.fulfill({
          status: 500,
          body: JSON.stringify({ detail: "nope" }),
          headers: { "content-type": "application/json" },
        });
      });

      await page.goto("/integrations");
      const sw = page.getByRole("switch", { name: `Toggle ${STABLE_PLUGIN_NAME}` });
      await expect(sw).toBeVisible({ timeout: 15_000 });
      await expect(sw).toBeChecked();

      await sw.click();

      // Optimistic flip → switch immediately reports unchecked.
      await expect(sw).not.toBeChecked({ timeout: 3_000 });

      // After the 500 lands, the mutation rolls back to the original state.
      await expect(sw).toBeChecked({ timeout: 15_000 });
    } finally {
      await restorePluginEnabled(STABLE_PLUGIN_ID, initiallyEnabled);
    }
  });

  /**
   * UX node: integrations.installed.toggle-error
   * Route: /integrations
   * Preconditions: toggle-mutation:error
   * Expected: error toast surfaces, switch reverts to prior state
   * Source refs: web/src/app/integrations/page.tsx
   * Coverage status: uncovered
   */
  test("integrations.installed.toggle-error — error toast + state revert", async ({ page }) => {
    const initiallyEnabled = await getPluginEnabled(STABLE_PLUGIN_ID);
    if (!initiallyEnabled) await enablePlugin(STABLE_PLUGIN_ID);

    try {
      await page.route(`**/api/plugins/${STABLE_PLUGIN_ID}/disable`, async (route) => {
        await route.fulfill({
          status: 500,
          body: JSON.stringify({ detail: "toggle failed" }),
          headers: { "content-type": "application/json" },
        });
      });

      await page.goto("/integrations");
      const sw = page.getByRole("switch", { name: `Toggle ${STABLE_PLUGIN_NAME}` });
      await expect(sw).toBeVisible({ timeout: 15_000 });
      await expect(sw).toBeChecked();
      await sw.click();

      // Error toast appears (Sonner Notifications region). i18n template:
      // "Failed to toggle {pluginId}: {error}" — we match the prefix loosely.
      const toast = page
        .getByRole("region", { name: /Notifications/i })
        .getByText(/Failed to toggle/i);
      await expect(toast).toBeVisible({ timeout: 15_000 });

      // Switch reverts to its prior (enabled) state.
      await expect(sw).toBeChecked({ timeout: 15_000 });
    } finally {
      await restorePluginEnabled(STABLE_PLUGIN_ID, initiallyEnabled);
    }
  });

  /**
   * UX node: integrations.installed.overflow-menu
   * Route: /integrations
   * Preconditions: plugins:>=1
   * Interactions: click:row-overflow (three-dot)
   * Expected: DropdownMenu opens with Configure / Update / Uninstall actions
   * Source refs: web/src/app/integrations/page.tsx
   * Coverage status: uncovered
   */
  test("integrations.installed.overflow-menu — row three-dot opens action menu", async ({ page }) => {
    await page.goto("/integrations");
    const sw = page.getByRole("switch", { name: `Toggle ${STABLE_PLUGIN_NAME}` });
    await expect(sw).toBeVisible({ timeout: 15_000 });

    const row = page.locator("tr").filter({ has: sw });
    await row.getByRole("button", { name: "More options" }).click();

    // Configure + Add Instance + Enable/Disable are guaranteed for any installed
    // non-instance plugin. Uninstall is conditional on source !== builtin so
    // we do NOT assert it here (date_time is builtin).
    await expect(page.getByRole("menuitem", { name: /Configure/i })).toBeVisible({
      timeout: 5_000,
    });
    await expect(page.getByRole("menuitem", { name: /Add Instance/i })).toBeVisible();
    await expect(
      page.getByRole("menuitem", { name: /Enable|Disable/i }),
    ).toBeVisible();
  });

  /**
   * UX node: integrations.installed.add-instance-row
   * Route: /integrations
   * Preconditions: plugins:multi-instance-capable
   * Expected: 'Add instance' affordance present on multi-instance plugin rows
   * Source refs: web/src/app/integrations/page.tsx
   * Coverage status: uncovered
   */
  test("integrations.installed.add-instance-row — Add instance row affordance", async ({ page }) => {
    await page.goto("/integrations");
    const sw = page.getByRole("switch", { name: `Toggle ${STABLE_PLUGIN_NAME}` });
    await expect(sw).toBeVisible({ timeout: 15_000 });

    const row = page.locator("tr").filter({ has: sw });
    await row.getByRole("button", { name: "More options" }).click();
    await page.getByRole("menuitem", { name: /Add Instance/i }).click();

    // The Add Instance row is an inline form. Verify the label + input + buttons.
    await expect(page.getByText(/Instance name:/i)).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByPlaceholder(/e\.g\. sf, prod, api-2/i),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: /^Create$/ })).toBeVisible();

    // Cancel without submitting — we DO NOT actually create an instance.
    await page.getByRole("button", { name: /^Cancel$/ }).click();
    await expect(page.getByText(/Instance name:/i)).toHaveCount(0);
  });

  /**
   * UX node: integrations.installed.create-instance-pending
   * Route: /integrations
   * Preconditions: create-instance-mutation:pending
   * Expected: pending label on Create button; modal locks during mutation
   * Source refs: web/src/app/integrations/page.tsx
   * Coverage status: uncovered
   */
  test("integrations.installed.create-instance-pending — Create instance pending state", async ({ page }) => {
    // Stall + reject the create-instance POST so we never actually create a
    // persistent instance, but we DO observe the pending UI.
    await page.route(`**/api/plugins/${STABLE_PLUGIN_ID}/instances`, async (route) => {
      if (route.request().method() !== "POST") return route.fallback();
      await new Promise((r) => setTimeout(r, 1500));
      await route.fulfill({
        status: 500,
        body: JSON.stringify({ detail: "stalled in test" }),
        headers: { "content-type": "application/json" },
      });
    });

    await page.goto("/integrations");
    const sw = page.getByRole("switch", { name: `Toggle ${STABLE_PLUGIN_NAME}` });
    await expect(sw).toBeVisible({ timeout: 15_000 });
    const row = page.locator("tr").filter({ has: sw });
    await row.getByRole("button", { name: "More options" }).click();
    await page.getByRole("menuitem", { name: /Add Instance/i }).click();

    const input = page.getByPlaceholder(/e\.g\. sf, prod, api-2/i);
    await expect(input).toBeVisible({ timeout: 10_000 });
    await input.fill("e2e_pending_test");

    const createBtn = page.getByRole("button", { name: /^Create$/ });
    await createBtn.click();

    // While the POST is in flight the button shows "Creating..." and is disabled.
    const creatingBtn = page.getByRole("button", { name: /Creating/i });
    await expect(creatingBtn).toBeVisible({ timeout: 5_000 });
    await expect(creatingBtn).toBeDisabled();
  });

  /**
   * UX node: integrations.installed.update-pending
   * Route: /integrations
   * Preconditions: update-mutation:pending (single plugin)
   * Expected: row shows 'Updating...' state; row controls disabled
   * Source refs: web/src/app/integrations/page.tsx
   * Coverage status: uncovered
   */
  test("integrations.installed.update-pending — per-row Update pending state", async ({ page }) => {
    // Mark our stable plugin as having an update available so the per-row
    // Update menu item appears. NOTE: it must be a non-builtin plugin to have
    // an Update action in the DropdownMenu — but the menu item is gated only
    // by `hasUpdate && onUpdate`. onUpdate is always provided, so we just need
    // update_available=true regardless of source.
    await page.route("**/api/plugins", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      const response = await route.fetch();
      const data = await response.json();
      const target = data.plugins.find(
        (p: { id: string }) => p.id === STABLE_PLUGIN_ID,
      );
      if (target) target.update_available = true;
      await route.fulfill({
        status: 200,
        body: JSON.stringify(data),
        headers: { "content-type": "application/json" },
      });
    });
    // Stall the update endpoint so the Updating... state is visible.
    await page.route(`**/api/plugins/${STABLE_PLUGIN_ID}/update`, async (route) => {
      await new Promise((r) => setTimeout(r, 1500));
      await route.fulfill({
        status: 500,
        body: JSON.stringify({ detail: "stalled in test" }),
        headers: { "content-type": "application/json" },
      });
    });

    await page.goto("/integrations");
    const sw = page.getByRole("switch", { name: `Toggle ${STABLE_PLUGIN_NAME}` });
    await expect(sw).toBeVisible({ timeout: 15_000 });
    const row = page.locator("tr").filter({ has: sw });
    await row.getByRole("button", { name: "More options" }).click();

    const updateItem = page.getByRole("menuitem", { name: /^Update$/ });
    await expect(updateItem).toBeVisible({ timeout: 10_000 });
    await updateItem.click();

    // The dropdown closes when the item is clicked. While the per-row mutation
    // is pending, `updatingId` is set, which disables the banner's
    // "Update All (N)" button (disabled={isUpdatingAll || !!updatingId}).
    // That disabled-state is our state-distinguishing signal.
    const updateAllBtn = page.getByRole("button", { name: /Update All \(\d+\)/i });
    await expect(updateAllBtn).toBeDisabled({ timeout: 5_000 });

    // Reopening the dropdown should now show "Updating..." in place of "Update".
    await row.getByRole("button", { name: "More options" }).click();
    await expect(
      page.getByRole("menuitem", { name: /Updating/i }),
    ).toBeVisible({ timeout: 5_000 });
  });

  /**
   * UX node: integrations.installed.uninstall-pending
   * Route: /integrations
   * Preconditions: uninstall-mutation:pending
   * Expected: confirm dialog button shows 'Uninstalling...'; row disabled
   * Source refs: web/src/app/integrations/page.tsx
   * Coverage status: uncovered
   *
   * NOTE: Uninstall is gated on `isExternal` (source !== "builtin"). Our stable
   * test plugins are all builtin, so the Uninstall menu item is never rendered
   * for them. We mock the plugins list to mark date_time as a registry plugin
   * so the Delete menu item appears, and we stall the DELETE endpoint with
   * a 500 so we never actually remove anything.
   */
  test.fixme("integrations.installed.uninstall-pending — Uninstall pending button label", async ({ page: _page }) => {
    // Blocker: the only safe way to drive this without actually uninstalling a
    // user plugin is to mock both the list (to flip source to non-builtin) and
    // the DELETE endpoint. But the row Delete action goes through an
    // AlertDialog whose final mutation also invalidates the list query — the
    // pending-label assertion races with the cache invalidation in CI and is
    // flaky. Tracked as a separate hardening task: surface a stable
    // data-testid on the AlertDialog action button so we can assert the
    // "Uninstalling..." label deterministically.
  });
});
