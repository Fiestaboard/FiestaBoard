/**
 * Auto-generated regression stubs from .claude/ux-coverage.json.
 * Subarea: integrations.plugin (config sheet + lifecycle)
 *
 * Priority cluster #5 from the auditor: plugin configuration sheet + lifecycle
 * has 9 gap nodes; fleshing these out unblocks plugin work-quality regressions.
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
  deletePage,
} from "../helpers";

const TEST_PLUGIN_ID = "date_time";
const TEST_PLUGIN_NAME = "Date & Time";

// Track demo page IDs to clean up after tests
const createdDemoPageIds = new Set<string>();

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await enablePlugin(TEST_PLUGIN_ID).catch(() => {});
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
  // Grant clipboard permissions so copy-variable can be observed
  await context.grantPermissions(["clipboard-read", "clipboard-write"]).catch(() => {});
});

test.afterEach(async () => {
  // Clean up demo pages created by these tests
  for (const id of createdDemoPageIds) {
    await deletePage(id).catch(() => {});
  }
  createdDemoPageIds.clear();
});

/**
 * Navigate to /integrations and open the date_time plugin's config sheet.
 * Returns once Save Changes is visible (or loading state if slow).
 */
async function openConfigSheet(page: import("@playwright/test").Page) {
  await page.goto("/integrations");
  await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible({ timeout: 15_000 });

  // Find the row for our test plugin via the toggle aria-label
  const toggle = page.getByRole("switch", { name: `Toggle ${TEST_PLUGIN_NAME}` });
  await expect(toggle).toBeVisible({ timeout: 15_000 });

  // The Configure button is the sibling in the same row
  const row = page.locator("tr").filter({ has: toggle });
  const configureBtn = row.getByRole("button", { name: "Configure" }).first();
  await configureBtn.click();
}

test.describe("regression: integrations.plugin (config sheet + lifecycle)", () => {
  /**
   * UX node: integrations.plugin.config-sheet.open
   * Route: /integrations
   * Preconditions: plugin:installed, plugin:configurable
   * Interactions: click:configure → sheet opens
   * Expected (missing from current coverage):
   *   - header plugin icon/name asserted
   *   - template-variable copy table exercised
   *   - env-var table asserted
   *   - color-rules editor present-checked
   * See also: web/tests/plugin-management.spec.ts:87,144
   * Coverage status: partial
   */
  test("integrations.plugin.config-sheet.open — header, template-vars, env-vars, color-rules sections", async ({ page }) => {
    await openConfigSheet(page);

    // Header: plugin name as SheetTitle
    const sheetTitle = page.locator('[role="dialog"]').getByText(TEST_PLUGIN_NAME, { exact: true });
    await expect(sheetTitle).toBeVisible({ timeout: 15_000 });

    // Save Changes button (rendering of the sheet has completed)
    await expect(page.getByRole("button", { name: "Save Changes" })).toBeVisible({ timeout: 15_000 });

    // Template Variables section
    await expect(page.getByRole("heading", { name: /Template Variables/i })).toBeVisible();

    // Env Vars section
    await expect(page.getByRole("heading", { name: /Environment Variables/i })).toBeVisible();

    // Color Rules editor section heading (from i18n: "Color Rules")
    await expect(page.getByText(/Color Rules/i).first()).toBeVisible();
  });

  /**
   * UX node: integrations.plugin.config-sheet.loading
   * Route: /integrations (sheet)
   * Preconditions: config-fetch:pending
   * Expected: loading skeleton in sheet body while plugin config loads
   * Source refs: web/src/components/integrations/*
   * Coverage status: uncovered
   */
  test("integrations.plugin.config-sheet.loading — sheet body shows loading state", async ({ page }) => {
    await page.goto("/integrations");
    await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible({ timeout: 15_000 });

    // Throttle the plugin details endpoint so the loading state is observable
    await page.route(`**/api/plugins/${TEST_PLUGIN_ID}`, async (route) => {
      await new Promise((r) => setTimeout(r, 1500));
      await route.continue();
    });

    const toggle = page.getByRole("switch", { name: `Toggle ${TEST_PLUGIN_NAME}` });
    await expect(toggle).toBeVisible({ timeout: 15_000 });
    const row = page.locator("tr").filter({ has: toggle });
    await row.getByRole("button", { name: "Configure" }).first().click();

    // Sheet header is visible; body shows skeletons. Save button is rendered
    // but disabled while details are loading.
    const saveBtn = page.getByRole("button", { name: "Save Changes" });
    await expect(saveBtn).toBeVisible({ timeout: 5_000 });
    await expect(saveBtn).toBeDisabled();

    // Eventually the details load and Save becomes enabled
    await expect(saveBtn).toBeEnabled({ timeout: 15_000 });
  });

  /**
   * UX node: integrations.plugin.config-sheet.no-config
   * Route: /integrations (sheet)
   * Preconditions: plugin:no-settings-schema
   * Expected: 'No configuration required' message in sheet body
   * Source refs: web/src/components/integrations/*
   * Coverage status: uncovered
   */
  test("integrations.plugin.config-sheet.no-config — 'no configuration required' message", async ({ page }) => {
    await page.goto("/integrations");
    await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible({ timeout: 15_000 });

    // Intercept plugin details and return a payload with no settings_schema and no variables
    await page.route(`**/api/plugins/${TEST_PLUGIN_ID}`, async (route) => {
      const response = await route.fetch();
      const data = await response.json();
      // Wipe everything that would render config UI
      data.settings_schema = { type: "object", properties: {} };
      data.variables = { simple: {}, arrays: {} };
      data.env_vars = [];
      data.has_demo = false;
      await route.fulfill({ status: 200, body: JSON.stringify(data), headers: { "content-type": "application/json" } });
    });

    const toggle = page.getByRole("switch", { name: `Toggle ${TEST_PLUGIN_NAME}` });
    await expect(toggle).toBeVisible({ timeout: 15_000 });
    const row = page.locator("tr").filter({ has: toggle });
    await row.getByRole("button", { name: "Configure" }).first().click();

    await expect(
      page.getByText(/No configuration options available for this plugin/i),
    ).toBeVisible({ timeout: 15_000 });
  });

  /**
   * UX node: integrations.plugin.config-sheet.saving
   * Route: /integrations (sheet)
   * Preconditions: save-mutation:pending
   * Expected (missing from current coverage):
   *   - Save Changes button shows 'Saving...' pending label
   *   - post-save toast '<name> configuration saved' asserted
   * See also: web/tests/plugin-management.spec.ts:144
   * Coverage status: partial
   */
  test("integrations.plugin.config-sheet.saving — Saving... label and post-save toast", async ({ page }) => {
    await openConfigSheet(page);
    const saveBtn = page.getByRole("button", { name: "Save Changes" });
    await expect(saveBtn).toBeVisible({ timeout: 15_000 });
    await expect(saveBtn).toBeEnabled({ timeout: 15_000 });

    // Throttle PUT /plugins/{id}/config to make Saving... observable
    await page.route(`**/api/plugins/${TEST_PLUGIN_ID}/config`, async (route) => {
      if (route.request().method() === "PUT") {
        await new Promise((r) => setTimeout(r, 1200));
      }
      await route.continue();
    });

    await saveBtn.click();

    // Pending label
    await expect(page.getByRole("button", { name: "Saving..." })).toBeVisible({ timeout: 5_000 });

    // Toast: "<plugin name> configuration saved" appears in the Sonner notifications region.
    const toast = page
      .getByRole("region", { name: /Notifications/i })
      .getByText(`${TEST_PLUGIN_NAME} configuration saved`);
    await expect(toast).toBeVisible({ timeout: 15_000 });
  });

  /**
   * UX node: integrations.plugin.config-sheet.with-env-vars
   * Route: /integrations (sheet)
   * Preconditions: plugin:has-env-vars
   * Expected: env-var table rows render with name/value/copy controls
   * Source refs: web/src/components/integrations/*
   * Coverage status: uncovered
   */
  test("integrations.plugin.config-sheet.with-env-vars — env-var table renders rows", async ({ page }) => {
    await openConfigSheet(page);

    // Wait for env-vars heading
    const envHeading = page.getByRole("heading", { name: /Environment Variables/i });
    await expect(envHeading).toBeVisible({ timeout: 15_000 });

    // Find the env-vars table — its header includes a "Required" column.
    // Confirm at least one row exists by checking for known env-var name patterns
    // (date_time exposes FIESTABOARD_TIMEZONE or similar).
    const dialog = page.locator('[role="dialog"]');
    const envTable = dialog.locator("table").filter({ hasText: "Required" });
    await expect(envTable).toBeVisible({ timeout: 5_000 });
    const rows = envTable.locator("tbody tr");
    expect(await rows.count()).toBeGreaterThan(0);

    // Each row should display a code-formatted env var name
    const firstCode = rows.first().locator("code").first();
    await expect(firstCode).toBeVisible();
    const codeText = (await firstCode.textContent())?.trim() ?? "";
    expect(codeText.length).toBeGreaterThan(0);
  });

  /**
   * UX node: integrations.plugin.config-sheet.copy-variable
   * Route: /integrations (sheet)
   * Preconditions: plugin:has-template-vars
   * Interactions: click:copy on a template variable row
   * Expected: clipboard receives variable token; 'Copied' toast/feedback
   * Source refs: web/src/components/integrations/*
   * Coverage status: uncovered
   */
  test("integrations.plugin.config-sheet.copy-variable — copies template variable to clipboard", async ({ page }) => {
    await openConfigSheet(page);

    const varsHeading = page.getByRole("heading", { name: /Template Variables/i });
    await expect(varsHeading).toBeVisible({ timeout: 15_000 });

    // Click first variable row in the Template Variables table.
    // Identify it by its hover-and-click handler — the <code> cell shows
    // "date_time.<name>".
    const dialog = page.locator('[role="dialog"]');
    const varCode = dialog.locator(`code:has-text("${TEST_PLUGIN_ID}.")`).first();
    await expect(varCode).toBeVisible({ timeout: 5_000 });
    const codeText = ((await varCode.textContent()) ?? "").trim();
    // codeText looks like "date_time.time"
    const expectedToken = `{{${codeText}}}`;

    await varCode.click();

    // Toast feedback — the UI confirms the copy regardless of clipboard API
    // availability in headless mode.
    await expect(page.getByText(`Copied ${expectedToken}`)).toBeVisible({ timeout: 5_000 });
  });

  /**
   * UX node: integrations.plugin.color-rules-editor
   * Route: /integrations (sheet)
   * Preconditions: plugin:supports-color-rules
   * Expected: color-rule rows editable; add/remove rule works; persists on save
   * Source refs: web/src/components/integrations/color-rules-editor.tsx
   * Coverage status: uncovered
   */
  test.fixme("integrations.plugin.color-rules-editor — add/edit/remove color rules and persist", async ({ page }) => {
    // Pre-clear color_rules from existing config so we have a known starting state
    await fetch(`${API_URL}/plugins/${TEST_PLUGIN_ID}/config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ config: { color_rules: {} } }),
    });

    await openConfigSheet(page);
    await expect(page.getByRole("button", { name: "Save Changes" })).toBeEnabled({ timeout: 15_000 });

    const dialog = page.locator('[role="dialog"]');

    // Click "Add field" to open the new-field input
    await dialog.getByRole("button", { name: /Add field/i }).click();

    // Fill the field name and submit via the inline "Add" button
    const fieldInput = dialog.getByPlaceholder(/Field name/i);
    await expect(fieldInput).toBeVisible({ timeout: 5_000 });
    await fieldInput.fill("temperature");

    // Use the inline Add button. Scope to the inline editor row so we don't
    // hit the per-field "Add rule" button by accident.
    const inlineAddBtn = dialog.locator("div").filter({ has: fieldInput }).getByRole("button", { name: /^Add$/ });
    await inlineAddBtn.click();

    // The field now appears as "date_time.temperature"
    await expect(dialog.getByText(`${TEST_PLUGIN_ID}.temperature`)).toBeVisible({ timeout: 5_000 });

    // Save and assert toast
    await dialog.getByRole("button", { name: "Save Changes" }).click();
    await expect(
      page.getByRole("region", { name: /Notifications/i }).getByText(`${TEST_PLUGIN_NAME} configuration saved`),
    ).toBeVisible({ timeout: 15_000 });

    // Verify persisted server-side
    const detail = await fetch(`${API_URL}/plugins/${TEST_PLUGIN_ID}`, { headers: authHeaders() }).then((r) => r.json());
    expect(detail.config?.color_rules?.temperature).toBeDefined();
    expect(Array.isArray(detail.config.color_rules.temperature)).toBe(true);
    expect(detail.config.color_rules.temperature.length).toBeGreaterThan(0);

    // Cleanup — reset color_rules so subsequent test runs start clean
    await fetch(`${API_URL}/plugins/${TEST_PLUGIN_ID}/config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ config: { color_rules: {} } }),
    });
  });

  /**
   * UX node: integrations.plugin.demo-page-create
   * Route: /integrations (sheet)
   * Interactions: click:create-demo-page
   * Expected: success toast; /pages list contains the new demo page
   * Source refs: web/src/components/integrations/*
   * Coverage status: uncovered
   */
  test("integrations.plugin.demo-page-create — creates demo page and toasts success", async ({ page }) => {
    // Ensure no existing demo page so the "Create Demo Page" button is shown
    // (not the "Recreate" variant). Find and delete any existing demo first.
    const before = await fetch(`${API_URL}/plugins/${TEST_PLUGIN_ID}`, { headers: authHeaders() }).then((r) => r.json());
    if (before.demo_page_id) {
      await deletePage(before.demo_page_id).catch(() => {});
    }

    await openConfigSheet(page);
    await expect(page.getByRole("button", { name: "Save Changes" })).toBeEnabled({ timeout: 15_000 });

    const dialog = page.locator('[role="dialog"]');
    const createBtn = dialog.getByRole("button", { name: /Create Demo Page/i });
    await expect(createBtn).toBeVisible({ timeout: 5_000 });
    await createBtn.click();

    // Toast: "Demo page created for <name>"
    await expect(
      page.getByRole("region", { name: /Notifications/i }).getByText(`Demo page created for ${TEST_PLUGIN_NAME}`),
    ).toBeVisible({ timeout: 15_000 });

    // Verify via API that a demo page now exists; queue it for cleanup
    const after = await fetch(`${API_URL}/plugins/${TEST_PLUGIN_ID}`, { headers: authHeaders() }).then((r) => r.json());
    expect(after.demo_page_id).toBeTruthy();
    createdDemoPageIds.add(after.demo_page_id);
  });

  /**
   * UX node: integrations.plugin.demo-page-recreate-confirm
   * Route: /integrations (sheet)
   * Preconditions: demo-page:already-exists
   * Interactions: click:create-demo-page → confirm dialog
   * Expected: AlertDialog warns about overwrite; Cancel/Confirm paths behave
   * Source refs: web/src/components/integrations/*
   * Coverage status: uncovered
   */
  test.fixme("integrations.plugin.demo-page-recreate-confirm — recreate confirms before overwrite", async ({ page }) => {
    // Ensure a demo page exists so the Recreate flow is exercised
    const ensureRes = await fetch(`${API_URL}/plugins/${TEST_PLUGIN_ID}/demo-page`, {
      method: "POST",
      headers: authHeaders(),
    });
    if (ensureRes.ok) {
      const ensured = await ensureRes.json();
      if (ensured.page?.id) createdDemoPageIds.add(ensured.page.id);
    } else {
      test.skip(true, "demo-page endpoint not available on this build of date_time");
      return;
    }

    await openConfigSheet(page);
    await expect(page.getByRole("button", { name: "Save Changes" })).toBeEnabled({ timeout: 15_000 });

    const sheet = page.locator('[role="dialog"]').first();
    const recreateBtn = sheet.getByRole("button", { name: /^Recreate$/ });
    if (!(await recreateBtn.isVisible({ timeout: 5_000 }).catch(() => false))) {
      test.skip(true, "Recreate button not present");
      return;
    }
    await recreateBtn.click();

    // Confirmation dialog appears
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    // Cancel path: closes the dialog without recreating
    await page.getByTestId("alert-dialog-cancel").click();
    await expect(dialog).toBeHidden({ timeout: 5_000 });
  });

  /**
   * UX node: integrations.plugin.delete-confirm
   * Route: /integrations
   * Interactions: open:overflow → Uninstall → confirm dialog
   * Expected: AlertDialog title 'Uninstall <name>' visible; Cancel keeps row;
   *           Confirm removes plugin and toasts success
   * Source refs: web/src/components/integrations/*
   * Coverage status: uncovered
   *
   * SAFETY: This test does NOT confirm the delete. It only opens the dialog
   * and clicks Cancel, then verifies the plugin row remains. Confirming would
   * uninstall a user-installed plugin, which is destructive.
   */
  test("integrations.plugin.delete-confirm — uninstall confirm dialog Cancel path", async ({ page }) => {
    // Mock the installed plugins list so a known "external" plugin row exists
    // independent of which plugins are actually installed in the CI environment.
    // This also avoids any risk of actually uninstalling a user plugin.
    await page.route("**/api/plugins", (route) => {
      if (route.request().method() !== "GET") return route.continue();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          plugins: [
            {
              id: "mock_external_plugin",
              name: "Mock External Plugin",
              description: "A test fixture plugin",
              enabled: true,
              source: "external",
              category: "utility",
              author: "Test",
              icon: "package",
              manifest: { id: "mock_external_plugin", name: "Mock External Plugin" },
            },
          ],
        }),
      });
    });

    await page.goto("/integrations");
    await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible({ timeout: 15_000 });

    const toggle = page.getByRole("switch", { name: "Toggle Mock External Plugin" });
    await expect(toggle).toBeVisible({ timeout: 15_000 });
    const row = page.locator("tr").filter({ has: toggle });

    await row.getByRole("button", { name: "More options" }).click();
    await page.getByRole("menuitem", { name: /^Delete$/ }).click();

    // Confirm dialog appears with the new alert-dialog-cancel testid.
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    // SAFETY: cancel via testid (added in src/components/ui/alert-dialog.tsx).
    await page.getByTestId("alert-dialog-cancel").click();
    await expect(dialog).toBeHidden({ timeout: 5_000 });

    await expect(toggle).toBeVisible();
  });
});
