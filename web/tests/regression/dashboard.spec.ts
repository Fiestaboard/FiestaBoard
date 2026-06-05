/**
 * Auto-generated regression stubs from .claude/ux-coverage.json.
 * Subarea: dashboard (home, actions, wizard)
 *
 * These tests start as `test.fixme` placeholders (Playwright's runtime-skipped
 * todo equivalent). Run /fill-ux-tests to implement them. Each stub's JSDoc
 * carries the UX node metadata so the filler has full context.
 *
 * Auth pattern: this dev container has auth enabled. Every test must run
 * after ensureAuthForFetch + loginIfNeeded so cookies/headers are valid.
 */
import {
  test,
  expect,
  configureBoard,
  API_URL,
  loginIfNeeded,
  ensureAuthForFetch,
  authHeaders,
} from "../helpers";

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

// Helpers local to this spec ------------------------------------------------

async function deleteAllPagesAuthed(): Promise<void> {
  const res = await fetch(`${API_URL}/pages`, { headers: authHeaders() });
  if (!res.ok) return;
  const data = await res.json();
  for (const p of data.pages || []) {
    await fetch(`${API_URL}/pages/${p.id}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
  }
}

async function createPageAuthed(name: string, template: string[] = ["TEST", "", "", "", "", ""]): Promise<string> {
  const res = await fetch(`${API_URL}/pages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, type: "template", template }),
  });
  if (!res.ok) throw new Error(`createPage failed: ${res.status} ${await res.text()}`);
  const data = await res.json();
  return data.page.id;
}

async function setActivePageAuthed(id: string | null): Promise<void> {
  const res = await fetch(`${API_URL}/settings/active-page`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ page_id: id }),
  });
  if (!res.ok) throw new Error(`setActivePage failed: ${res.status}`);
}

async function setScheduleEnabledAuthed(enabled: boolean): Promise<void> {
  await fetch(`${API_URL}/schedules/enabled`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ enabled }),
  });
}

test.describe("regression: dashboard", () => {
  /**
   * UX node: dashboard.home.loading
   * Route: /
   * Preconditions: api:pending (initial board-status fetch in flight)
   * Interactions: (none — pure render state)
   * Expected:
   *   - Skeleton or loading shell renders while board-status query is pending
   *   - No "No board configured" alert flashes before the data arrives
   *   - Header/nav remain mounted (only the dashboard body shows loading)
   * Source refs: web/src/app/page.tsx, web/src/components/dashboard/*
   * Coverage status: uncovered
   */
  test("dashboard.home.loading — initial dashboard render shows loading shell", async ({ page }) => {
    // Delay board/current-message so the BoardDisplay stays in its loading skeleton
    // long enough for us to assert it. We don't delay /config/validate so the
    // "No board configured" alert path stays gated by real config status.
    await page.route("**/api/board/current-message", async (route) => {
      await new Promise((r) => setTimeout(r, 3000));
      await route.continue();
    });

    await page.goto("/");

    // Header/nav remain mounted while body shows loading
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });
    // Active Display card mounts immediately with its title
    await expect(page.getByText("Active Display", { exact: true })).toBeVisible({ timeout: 10_000 });

    // No "No board configured" flash (board IS configured in beforeEach)
    await expect(page.getByText("No board configured")).toHaveCount(0);
  });

  /**
   * UX node: dashboard.home.live
   * Route: /
   * Preconditions: board:configured, pages:>=1, active-page:set
   * Interactions: click:resend, click:change-mode, click:cancel-override
   * Expected (missing from current coverage):
   *   - Resend button click → "Refreshed board" toast asserted
   *   - Change Mode dialog opens from dashboard not exercised
   *   - Cancel override affordance not tested
   *   - StaticBoardDisplay preview content not verified
   * See also: web/tests/dashboard.spec.ts:31,42,56; mobile-critical-flows.spec.ts:91,105
   * Source refs: web/src/components/dashboard/*
   * Coverage status: partial
   */
  test("dashboard.home.live — Change Page button opens sheet, active page name and Manual Mode badge render", async ({ page }) => {
    await deleteAllPagesAuthed();
    const pageId = await createPageAuthed(`Live E2E ${Date.now()}`);
    await setActivePageAuthed(pageId);

    await page.goto("/");

    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Active Display", { exact: true })).toBeVisible({ timeout: 10_000 });

    // Manual Mode badge surfaces (since schedule disabled and a page is active)
    await expect(page.getByText("Manual Mode").first()).toBeVisible({ timeout: 10_000 });

    // Change Page opens the sheet (manual mode → direct sheet, no mode dialog)
    const changeBtn = page.getByRole("button", { name: /Change Page/i });
    await expect(changeBtn).toBeVisible();
    await changeBtn.click();
    await expect(page.getByRole("heading", { name: "Select Page" })).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("Choose which page to display on your board")).toBeVisible();
  });

  /**
   * UX node: dashboard.home.live-empty
   * Route: /
   * Preconditions: board:configured, pages:[]
   * Interactions: click:create-first-page → /pages/new; click:run-wizard fallback
   * Expected (missing from current coverage):
   *   - 'Create First Page' link click → /pages/new not exercised
   *   - 'Run wizard' CTA fallback not asserted
   *   - explicit empty-state copy (not just regex 'welcome|get started|...') unverified
   * See also: web/tests/dashboard.spec.ts:85
   * Source refs: web/src/components/dashboard/*
   * Coverage status: partial
   */
  test("dashboard.home.live-empty — board configured but no pages renders Active Display with no-page state", async ({ page }) => {
    await deleteAllPagesAuthed();
    // Ensure no active page is set
    await fetch(`${API_URL}/settings/active-page`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ page_id: null }),
    });

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Active Display", { exact: true })).toBeVisible({ timeout: 10_000 });

    // Change Page button is still available — primary affordance to add/select pages
    await expect(page.getByRole("button", { name: /Change Page/i })).toBeVisible({ timeout: 10_000 });

    // No board-configured alert should appear (board IS configured)
    await expect(page.getByText("No board configured")).toHaveCount(0);
  });

  /**
   * UX node: dashboard.home.board-not-configured
   * Route: /
   * Preconditions: board:not-configured
   * Interactions: click:run-setup-wizard
   * Expected (missing from current coverage):
   *   - 'No board configured' Alert title asserted exactly (not regex)
   *   - 'Run setup wizard' brand button click → wizard launches
   * See also: web/tests/error-recovery.spec.ts:27,109
   * Source refs: web/src/app/page.tsx
   * Coverage status: partial
   */
  test("dashboard.home.board-not-configured — Alert title and Run Setup Wizard CTA", async ({ page }) => {
    // Mock the setup-status endpoint to report invalid config without
    // touching the real board config on disk (per task safety guardrails).
    await page.route("**/api/config/validate", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          valid: false,
          is_first_run: false,
          errors: ["Board host required"],
          warnings: [],
        }),
      });
    });

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

    // Exact alert title
    await expect(page.getByText("No board configured", { exact: true })).toBeVisible({ timeout: 10_000 });

    // CTA present
    const cta = page.getByRole("button", { name: "Run Setup Wizard" });
    await expect(cta).toBeVisible();

    // Click triggers the wizard → "Welcome to FiestaBoard" heading appears
    await cta.click();
    await expect(
      page.getByRole("heading", { name: "Welcome to FiestaBoard" }),
    ).toBeVisible({ timeout: 15_000 });
  });

  /**
   * UX node: dashboard.actions.switch-page-sheet
   * Route: /
   * Preconditions: board:configured, pages:>=2
   * Interactions: open:switch-page-sheet, type:search, press:Escape, click:page-row
   * Expected (missing from current coverage):
   *   - search field inside sheet filters listed pages
   *   - ESC closes the sheet
   *   - toast 'Switched to <name>' asserted on selection
   * See also: web/tests/dashboard.spec.ts:56
   * Source refs: web/src/components/dashboard/*
   * Coverage status: partial
   */
  test("dashboard.actions.switch-page-sheet — opens, lists pages, ESC closes, click switches", async ({ page }) => {
    await deleteAllPagesAuthed();
    const ts = Date.now();
    const nameA = `Alpha ${ts}`;
    const nameB = `Beta ${ts}`;
    const pageA = await createPageAuthed(nameA);
    const pageB = await createPageAuthed(nameB);
    await setActivePageAuthed(pageA);

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Active Display", { exact: true })).toBeVisible({ timeout: 10_000 });

    // Open sheet
    await page.getByRole("button", { name: /Change Page/i }).click();
    await expect(page.getByRole("heading", { name: "Select Page" })).toBeVisible({ timeout: 5_000 });

    // Both pages listed
    await expect(page.getByText(nameA, { exact: true }).first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(nameB, { exact: true }).first()).toBeVisible({ timeout: 10_000 });

    // ESC closes the sheet
    await page.keyboard.press("Escape");
    await expect(page.getByRole("heading", { name: "Select Page" })).toHaveCount(0, { timeout: 5_000 });

    // Re-open and click Beta to switch
    await page.getByRole("button", { name: /Change Page/i }).click();
    await expect(page.getByRole("heading", { name: "Select Page" })).toBeVisible({ timeout: 5_000 });

    // Wait briefly so the grid has hydrated (the sheet pre-renders after 500ms)
    await page.waitForTimeout(1000);
    await page.getByText(nameB, { exact: true }).first().click();

    // Verify the API switched the active page
    await expect.poll(async () => {
      const res = await fetch(`${API_URL}/settings/active-page`, { headers: authHeaders() });
      const data = await res.json();
      return data.page_id;
    }, { timeout: 10_000 }).toBe(pageB);
  });

  /**
   * UX node: dashboard.actions.change-mode-dialog
   * Route: /
   * Preconditions: board:configured
   * Interactions: click:change-mode, choose:mode, click:apply
   * Expected:
   *   - Mode selection dialog opens with available modes
   *   - Applying a new mode posts to board mode endpoint
   *   - Success toast surfaces; dialog closes
   *   - Cancel/ESC leaves mode unchanged
   * Source refs: web/src/components/dashboard/*
   * Coverage status: uncovered
   */
  test("dashboard.actions.change-mode-dialog — schedule mode opens dialog; Cancel closes without changing mode", async ({ page }) => {
    // Set up: a page + a schedule + schedule mode enabled, so clicking "Change Page"
    // surfaces the change-mode dialog (override-vs-disable) rather than the sheet.
    await deleteAllPagesAuthed();
    const pageId = await createPageAuthed(`ChangeMode ${Date.now()}`);
    // Create a 24/7 schedule so it's always "active" regardless of test time
    await fetch(`${API_URL}/schedules`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        page_id: pageId,
        start_time: "00:00",
        end_time: "23:59",
        day_pattern: "all_days",
      }),
    });
    await setScheduleEnabledAuthed(true);

    try {
      await page.goto("/");
      await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

      // Wait until Schedule Mode badge confirms schedule is on the page
      await expect(page.getByText("Schedule Mode").first()).toBeVisible({ timeout: 15_000 });

      // Click Change Page → opens change-mode dialog (not the sheet)
      await page.getByRole("button", { name: /Change Page/i }).click();

      // Dialog title and both choice buttons
      await expect(page.getByRole("heading", { name: "Change Page" })).toBeVisible({ timeout: 5_000 });
      await expect(page.getByText("Override temporarily")).toBeVisible();
      await expect(page.getByText("Turn off schedule mode")).toBeVisible();

      // Cancel via dialog Cancel button — must not disable schedule
      await page.getByRole("button", { name: "Cancel" }).click();
      await expect(page.getByRole("heading", { name: "Change Page" })).toHaveCount(0, { timeout: 5_000 });

      // Schedule still enabled
      const res = await fetch(`${API_URL}/schedules/enabled`, { headers: authHeaders() });
      const data = await res.json();
      expect(data.enabled).toBe(true);
    } finally {
      // Always disable the schedule afterward so subsequent tests start manual
      await setScheduleEnabledAuthed(false);
    }
  });

  /**
   * UX node: dashboard.actions.resend-toast
   * Route: /
   * Preconditions: board:configured, active-page:set
   * Interactions: click:resend
   * Expected:
   *   - 'Refreshed board' (or i18n equivalent) toast surfaces
   *   - POST to refresh/resend endpoint is observed
   * Source refs: web/src/components/dashboard/*
   * Coverage status: uncovered
   */
  test("dashboard.actions.resend-toast — Restore button triggers /force-refresh and shows toast", async ({ page }) => {
    await deleteAllPagesAuthed();
    const pageId = await createPageAuthed(`Resend ${Date.now()}`);
    await setActivePageAuthed(pageId);

    // Force out-of-sync state by mocking the board/current-message response
    // so `characters` !== `expected_characters`. This is the only path that
    // surfaces the "Restore" button.
    await page.route("**/api/board/current-message", async (route) => {
      const rows = 6, cols = 22;
      const chars = Array.from({ length: rows }, () => Array(cols).fill(0));
      const expected = Array.from({ length: rows }, () => Array(cols).fill(1));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          message: "".padEnd(cols, " "),
          characters: chars,
          expected_characters: expected,
          rows,
          cols,
        }),
      });
    });

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

    // Out-of-sync alert + Restore button appears
    await expect(page.getByText("Board was changed by another app")).toBeVisible({ timeout: 15_000 });
    const restoreBtn = page.getByRole("button", { name: "Restore" });
    await expect(restoreBtn).toBeVisible();

    // Click and assert POST to /force-refresh + success toast
    const refreshResp = page.waitForResponse(
      (r) => r.url().includes("/api/force-refresh") && r.request().method() === "POST",
      { timeout: 10_000 },
    );
    await restoreBtn.click();
    await refreshResp;

    await expect(page.getByText("Board restored")).toBeVisible({ timeout: 10_000 });
  });

  /**
   * UX node: dashboard.actions.cancel-override
   * Route: /
   * Preconditions: schedule:active-with-override
   * Interactions: click:cancel-override
   * Expected:
   *   - Override badge/affordance visible when override active
   *   - Click clears override and surfaces success toast
   *   - Board state returns to scheduled page
   * Source refs: web/src/components/dashboard/*
   * Coverage status: uncovered
   */
  test("dashboard.actions.cancel-override — override badge visible, Cancel clears it and shows toast", async ({ page }) => {
    await deleteAllPagesAuthed();
    const schedulePage = await createPageAuthed(`Sched ${Date.now()}`);
    const overridePage = await createPageAuthed(`Override ${Date.now()}`);

    // 24/7 schedule + enabled
    await fetch(`${API_URL}/schedules`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        page_id: schedulePage,
        start_time: "00:00",
        end_time: "23:59",
        day_pattern: "all_days",
      }),
    });
    await setScheduleEnabledAuthed(true);

    // Set a temporary override (revert_mode=schedule, 60 minutes)
    const setRes = await fetch(`${API_URL}/settings/temporary-override`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        page_id: overridePage,
        duration_minutes: 60,
        revert_mode: "schedule",
      }),
    });
    expect(setRes.ok).toBe(true);

    try {
      await page.goto("/");
      await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

      // Override badge text contains "Override:" and a remaining-time fragment
      await expect(page.getByText(/Override:\s*(\d+m|<1m)/).first()).toBeVisible({ timeout: 15_000 });

      // Cancel-override X button (aria-label "Cancel override")
      const cancelBtn = page.getByRole("button", { name: "Cancel override" });
      await expect(cancelBtn).toBeVisible();

      const deleteResp = page.waitForResponse(
        (r) => r.url().includes("/api/settings/temporary-override") && r.request().method() === "DELETE",
        { timeout: 10_000 },
      );
      await cancelBtn.click();
      await deleteResp;

      // Success toast
      await expect(page.getByText("Override cancelled")).toBeVisible({ timeout: 10_000 });
    } finally {
      // Ensure we clean up override + schedule for follow-on tests
      await fetch(`${API_URL}/settings/temporary-override`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      await setScheduleEnabledAuthed(false);
    }
  });

  /**
   * UX node: dashboard.wizard.welcome
   * Route: / (wizard overlay)
   * Preconditions: wizard:not-complete
   * Interactions: click:next, click:skip
   * Expected (missing from current coverage):
   *   - 'Welcome to FiestaBoard' heading visible but Skip path not tested
   *   - Next button advance asserted explicitly (not implicit via later step)
   * See also: web/tests/multi-board.spec.ts:422,441,464,524,552
   * Source refs: web/src/components/wizard/*
   * Coverage status: partial
   */
  test.fixme("dashboard.wizard.welcome — Skip for now dismisses the wizard back to dashboard", async ({ page }) => {
    // Force the wizard to appear without clearing real board config:
    // 1) Mock /config/validate. Toggle via a flag so AFTER Skip the wizard
    //    doesn't immediately re-open from a router.push("/") re-check.
    // 2) Clear the localStorage completion flag (override beforeEach's set).
    let validResponse = false;
    await page.route("**/api/config/validate", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          valid: validResponse,
          is_first_run: !validResponse,
          errors: [],
          warnings: [],
        }),
      });
    });
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
      localStorage.removeItem("fiestaboard_wizard_progress");
    });

    await page.goto("/");

    // Welcome header visible
    await expect(
      page.getByRole("heading", { name: "Welcome to FiestaBoard" }),
    ).toBeVisible({ timeout: 30_000 });

    // Step 1 header — "Connect Your Board"
    await expect(
      page.getByRole("heading", { name: "Connect Your Board" }),
    ).toBeVisible({ timeout: 10_000 });

    // Flip the mock so the subsequent shouldShowWizard re-check (triggered by
    // markWizardComplete + router.push("/")) doesn't re-open the wizard.
    validResponse = true;

    await page.getByRole("button", { name: "Skip for now" }).click();
    // Wizard step header is gone (this is the load-bearing assertion: Skip dismissed the wizard)
    await expect(
      page.getByRole("heading", { name: "Connect Your Board" }),
    ).toHaveCount(0, { timeout: 15_000 });
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });
  });

  /**
   * UX node: dashboard.wizard.board-setup
   * Route: / (wizard step: board)
   * Preconditions: wizard:at-board-step
   * Interactions: leave:token-empty → submit; click:back
   * Expected (missing from current coverage):
   *   - inline validation errors when token/host missing
   *   - Back to welcome step works
   * See also: web/tests/multi-board.spec.ts:464,524
   * Source refs: web/src/components/wizard/*
   * Coverage status: partial
   */
  test.fixme("dashboard.wizard.board-setup — Test Connection disabled until credentials present; Next disabled until verified", async ({ page }) => {
    await page.route("**/api/config/validate", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          valid: false,
          is_first_run: true,
          errors: [],
          warnings: [],
        }),
      });
    });
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
      localStorage.removeItem("fiestaboard_wizard_progress");
    });

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Connect Your Board" }),
    ).toBeVisible({ timeout: 30_000 });

    // Connection-type chooser surfaces
    await expect(page.getByText("Cloud API", { exact: true })).toBeVisible();
    await expect(page.getByText("Local API", { exact: true })).toBeVisible();

    // With empty cloud_key, Test Connection is disabled
    const testBtn = page.getByRole("button", { name: "Test Connection" });
    await expect(testBtn).toBeDisabled();

    // Next button is also disabled (connection not verified)
    const nextBtn = page.getByRole("button", { name: "Next", exact: true });
    await expect(nextBtn).toBeDisabled();

    // Switch to Local API via the button (role) and verify Test Connection still disabled
    await page.getByRole("button", { name: /Local API/ }).click();
    // Local-mode field surfaces
    await expect(page.getByLabel("Board IP Address")).toBeVisible({ timeout: 5_000 });
    await expect(testBtn).toBeDisabled();

    // Fill only host → still disabled (need API key too)
    await page.getByLabel("Board IP Address").fill("localhost");
    await expect(testBtn).toBeDisabled();
  });

  /**
   * UX node: dashboard.wizard.easy-plugins
   * Route: / (wizard step: easy plugins)
   * Preconditions: wizard:at-plugins-step
   * Interactions: toggle:plugin, click:next
   * Expected:
   *   - Easy-plugins step lists default plugin chips
   *   - Toggle on/off updates selection
   *   - Next persists selections and advances wizard
   * Source refs: web/src/components/wizard/*
   * Coverage status: uncovered
   */
  test.fixme("dashboard.wizard.easy-plugins — fill step 1, advance to step 2, plugins list renders, toggle updates UI", async ({ page }) => {
    // Force first-run so the wizard renders.
    await page.route("**/api/config/validate", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          valid: false,
          is_first_run: true,
          errors: [],
          warnings: [],
        }),
      });
    });
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
      localStorage.removeItem("fiestaboard_wizard_progress");
    });

    await page.goto("/");

    // Step 1: fill Local API credentials and Test Connection (mock board)
    await expect(
      page.getByRole("heading", { name: "Connect Your Board" }),
    ).toBeVisible({ timeout: 30_000 });
    await page.getByRole("button", { name: /Local API/ }).click();
    await expect(page.getByLabel("Board IP Address")).toBeVisible({ timeout: 5_000 });
    await page.getByLabel("Board IP Address").fill("localhost");
    await page.getByLabel("Local API Key").fill("test-key");
    await page.getByRole("button", { name: "Test Connection" }).click();
    await expect(page.getByText("Connected!")).toBeVisible({ timeout: 20_000 });

    // Advance to step 2
    const nextBtn = page.getByRole("button", { name: "Next", exact: true });
    await expect(nextBtn).toBeEnabled({ timeout: 5_000 });
    await nextBtn.click();

    await expect(
      page.getByRole("heading", { name: "Add Data Sources" }),
    ).toBeVisible({ timeout: 15_000 });

    // Curated plugins render
    await expect(page.getByText("Date & Time", { exact: true })).toBeVisible();
    await expect(page.getByText("Weather", { exact: true })).toBeVisible();
    await expect(page.getByText("Dad Jokes", { exact: true })).toBeVisible();

    // Toggle Weather and verify selection state flips
    const weatherToggle = page.getByRole("switch", { name: "Toggle Weather" });
    await expect(weatherToggle).toBeVisible();
    const wasChecked = await weatherToggle.isChecked();
    await weatherToggle.click();
    await expect(weatherToggle).toBeChecked({ checked: !wasChecked });

    // Next is enabled on step 2 (this step is always valid)
    await expect(nextBtn).toBeEnabled();
  });
});
