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
  API_URL,
  authHeaders,
  chooseVestaboardInWizard,
  configureBoard,
  ensureAuthForFetch,
  expect,
  loginIfNeeded,
  test,
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
  return data.id;
}

/** Sorted ids of every saved page, for before/after comparison. */
async function listPageIdsAuthed(): Promise<string[]> {
  const res = await fetch(`${API_URL}/pages`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`listPages failed: ${res.status}`);
  const data = await res.json();
  return (data.pages || []).map((p: { id: string }) => p.id).sort();
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
    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible({ timeout: 15_000 });
    // Active Display card mounts immediately with its title
    await expect(page.getByTestId("now-showing")).toBeVisible({ timeout: 10_000 });

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
  test("dashboard.home.live — Change Page opens the dialog, active page name and Manual Mode badge render", async ({
    page,
  }) => {
    await deleteAllPagesAuthed();
    const pageId = await createPageAuthed(`Live E2E ${Date.now()}`);
    await setActivePageAuthed(pageId);

    await page.goto("/");

    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("now-showing")).toBeVisible({ timeout: 10_000 });

    // Manual Mode badge surfaces (since schedule disabled and a page is active)
    await expect(page.getByText("Manual Mode").first()).toBeVisible({ timeout: 10_000 });

    // Change Page opens the one Change Page dialog (2.2; ForceSet is gone)
    const changeBtn = page.getByRole("button", { name: "Change Page", exact: true });
    await expect(changeBtn).toBeVisible();
    await changeBtn.click();
    const dialog = page.getByRole("dialog", { name: "Change Page" });
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    await expect(dialog.getByText(/Nothing changes until you choose Show now\./)).toBeVisible();
  });

  /**
   * UX node: dashboard.actions.compose-one-off
   * Route: /
   * Preconditions: board:configured, schedule:disabled (manual mode)
   * Interactions: click:compose (PageHeader) → type:message → Until I cancel → click:show-now
   * Expected:
   *   - "Compose a message" in the PageHeader (its one entry, 2.2) opens the dialog
   *   - Send posts an inline temporary override carrying the typed template
   *   - No page is created: the saved-page list is unchanged afterwards
   *   - The override is indefinite (expires_at is null), so the message stays
   *     on the board until it is cancelled (issue #1787)
   * Source refs: web/src/components/compose-page-dialog.tsx, web/src/components/active-page-display.tsx
   * Coverage status: covered
   */
  test("dashboard.actions.compose-one-off — a composed message is sent without being saved as a page", async ({
    page,
  }) => {
    await deleteAllPagesAuthed();
    const pageId = await createPageAuthed(`Compose Base ${Date.now()}`);
    await setActivePageAuthed(pageId);
    await setScheduleEnabledAuthed(false);

    // Snapshot the store rather than assuming a count: deleting the LAST page
    // makes the backend auto-create a "Welcome" default (src/pages/service.py),
    // so `deleteAllPagesAuthed` never actually leaves zero pages. The contract
    // under test is "the send adds nothing", which is what a before/after
    // comparison states — a hardcoded length would only restate the fixture.
    const pageIdsBefore = await listPageIdsAuthed();
    expect(pageIdsBefore).toContain(pageId);

    try {
      await page.goto("/");
      await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible({ timeout: 15_000 });

      // The one Compose entry is the PageHeader's (2.2, WEB-08)
      await page.getByRole("button", { name: "Compose a message", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Compose a message" })).toBeVisible({ timeout: 5_000 });

      // Manual Mode with no next change: Until I cancel is preselected
      await expect(page.getByRole("radio", { name: "Until I cancel" })).toHaveAttribute("aria-checked", "true");

      // Show now is inert until there is something to send
      const sendBtn = page.getByRole("button", { name: "Show now", exact: true });
      await expect(sendBtn).toBeDisabled();

      await page.getByRole("textbox", { name: /Message/i }).fill("ONE OFF HELLO");
      await expect(sendBtn).toBeEnabled();
      await sendBtn.click();

      // Dialog closes and the override badge takes over the mode badge
      await expect(page.getByRole("heading", { name: "Compose a message" })).toHaveCount(0, { timeout: 10_000 });

      // The override carries the inline content and never expires on its own
      await expect
        .poll(
          async () => {
            const res = await fetch(`${API_URL}/settings/temporary-override`, { headers: authHeaders() });
            return await res.json();
          },
          { timeout: 10_000 },
        )
        .toMatchObject({
          active: true,
          page_id: null,
          expires_at: null,
          template: ["ONE OFF HELLO"],
        });

      // Nothing was persisted: the page store is byte-for-byte the set it was
      // before the send.
      expect(await listPageIdsAuthed()).toEqual(pageIdsBefore);
    } finally {
      await fetch(`${API_URL}/settings/temporary-override`, { method: "DELETE", headers: authHeaders() });
    }
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
  test("dashboard.home.live-empty — board configured but no pages renders Active Display with no-page state", async ({
    page,
  }) => {
    await deleteAllPagesAuthed();
    // Ensure no active page is set
    await fetch(`${API_URL}/settings/active-page`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ page_id: null }),
    });

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("now-showing")).toBeVisible({ timeout: 10_000 });

    // Change Page button is still available — primary affordance to add/select pages
    await expect(page.getByRole("button", { name: "Change Page", exact: true })).toBeVisible({ timeout: 10_000 });

    // No board-configured alert should appear (board IS configured)
    await expect(page.getByText("No board configured")).toHaveCount(0);
  });

  /** Empty hubs offer the two-step Add dialog and an explicit setup re-run. */
  test("dashboard.home.no-displays — Add display and the supported empty-hub rerun", async ({ page }) => {
    await mockEmptyHub(page, false);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("heading", { name: "No displays yet", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Add display", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Add a display", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Welcome to FiestaBoard" })).toHaveCount(0);
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Run setup again", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Welcome to FiestaBoard", exact: true })).toBeVisible();
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
  test("dashboard.actions.switch-page-sheet — Change Page opens, lists and searches pages, ESC closes, Show now switches", async ({
    page,
  }) => {
    await deleteAllPagesAuthed();
    const ts = Date.now();
    const nameA = `Alpha ${ts}`;
    const nameB = `Beta ${ts}`;
    const pageA = await createPageAuthed(nameA);
    const pageB = await createPageAuthed(nameB);
    await setActivePageAuthed(pageA);

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("now-showing")).toBeVisible({ timeout: 10_000 });

    // Open Change Page
    const dialog = page.getByRole("dialog", { name: "Change Page" });
    await page.getByRole("button", { name: "Change Page", exact: true }).click();
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    // Both pages listed; search filters them
    await expect(dialog.getByRole("button", { name: new RegExp(nameA) })).toBeVisible({ timeout: 10_000 });
    await expect(dialog.getByRole("button", { name: new RegExp(nameB) })).toBeVisible({ timeout: 10_000 });
    await dialog.getByRole("searchbox", { name: "Search pages and collections" }).fill("Beta");
    await expect(dialog.getByRole("button", { name: new RegExp(nameA) })).toHaveCount(0);

    // ESC closes it
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0, { timeout: 5_000 });

    // Re-open, pick Beta, Show now (Manual Mode: Until I cancel pins it)
    await page.getByRole("button", { name: "Change Page", exact: true }).click();
    await dialog.getByRole("button", { name: new RegExp(nameB) }).click();
    await dialog.getByRole("button", { name: "Show now" }).click();

    // Verify the API switched the active page
    await expect
      .poll(
        async () => {
          const res = await fetch(`${API_URL}/settings/active-page`, { headers: authHeaders() });
          const data = await res.json();
          return data.page_id;
        },
        { timeout: 10_000 },
      )
      .toBe(pageB);
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
  test("dashboard.actions.change-mode-dialog — schedule mode opens Change Page; Cancel closes without changing mode", async ({
    page,
  }) => {
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
      await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible({ timeout: 15_000 });

      // Wait until Schedule Mode badge confirms schedule is on the page
      await expect(page.getByText("Schedule Mode").first()).toBeVisible({ timeout: 15_000 });

      // Change Page opens the one dialog (2.2): the "Override temporarily /
      // Turn off schedule mode" choice is gone. Picking holds an Override.
      await page.getByRole("button", { name: "Change Page", exact: true }).click();
      const dialog = page.getByRole("dialog", { name: "Change Page" });
      await expect(dialog).toBeVisible({ timeout: 5_000 });
      await expect(page.getByText("Override temporarily")).toHaveCount(0);
      await expect(page.getByText("Turn off schedule mode")).toHaveCount(0);

      // Cancel closes without changing anything
      await dialog.getByRole("button", { name: "Cancel" }).click();
      await expect(dialog).toHaveCount(0, { timeout: 5_000 });

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
  test("dashboard.actions.resend-toast — Restore button restores this board and shows toast", async ({ page }) => {
    await deleteAllPagesAuthed();
    const pageId = await createPageAuthed(`Resend ${Date.now()}`);
    await setActivePageAuthed(pageId);

    // Force out-of-sync state by mocking the board/current-message response
    // so `characters` !== `expected_characters`. This is the only path that
    // surfaces the "Restore" button.
    await page.route("**/api/board/current-message", async (route) => {
      const rows = 6,
        cols = 22;
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
    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible({ timeout: 15_000 });

    // Out-of-sync alert + Restore button appears
    await expect(page.getByTestId("board-out-of-sync").getByText(/is out of sync$/)).toBeVisible({ timeout: 15_000 });
    const restoreBtn = page.getByRole("button", { name: /^Show .+ again$/ });
    await expect(restoreBtn).toBeVisible();

    // Click and assert this board's restore (single-board Home → the
    // `primary` alias), not the install-wide /force-refresh, + success toast
    const forceRefreshes: string[] = [];
    page.on("request", (r) => {
      if (r.method() === "POST" && r.url().includes("/api/force-refresh")) forceRefreshes.push(r.url());
    });
    const restoreResp = page.waitForResponse(
      (r) => r.url().includes("/api/v1/boards/primary/restore") && r.request().method() === "POST",
      { timeout: 10_000 },
    );
    await restoreBtn.click();
    const response = await restoreResp;
    expect(response.status()).toBe(200);
    expect((await response.json()).sent).toBe(true);

    await expect(page.getByText("Board restored")).toBeVisible({ timeout: 10_000 });
    expect(forceRefreshes).toEqual([]);
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
  test("dashboard.actions.cancel-override — override badge visible, Cancel clears it and shows toast", async ({
    page,
  }) => {
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
      await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible({ timeout: 15_000 });

      // The Override badge and its countdown (2.2: "59m left")
      const card = page.getByTestId("now-showing");
      await expect(card.getByText("Override", { exact: true })).toBeVisible({ timeout: 15_000 });
      await expect(card.getByRole("timer")).toHaveText(/(\d+m|1h) left/);

      // Cancel override is the outline button on the card
      const cancelBtn = page.getByRole("button", { name: "Cancel override" });
      await expect(cancelBtn).toBeVisible();

      const deleteResp = page.waitForResponse(
        (r) => r.url().includes("/api/settings/temporary-override") && r.request().method() === "DELETE",
        { timeout: 10_000 },
      );
      await cancelBtn.click();
      await deleteResp;

      // Success toast
      await expect(page.getByText("Override canceled")).toBeVisible({ timeout: 10_000 });
    } finally {
      // Ensure we clean up override + schedule for follow-on tests
      await fetch(`${API_URL}/settings/temporary-override`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      await setScheduleEnabledAuthed(false);
    }
  });

  /** A first-run wizard requires an empty fleet as well as first-run validation. */
  async function mockEmptyHub(page: import("@playwright/test").Page, firstRun: boolean) {
    await page.route("**/api/config/validate", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ valid: false, is_first_run: firstRun, errors: [], warnings: [] }),
      }),
    );
    await page.route("**/api/settings/board", async (route) => {
      if (route.request().method() !== "GET") return route.continue();
      const response = await route.fetch();
      const settings = await response.json();
      await route.fulfill({ response, json: { ...settings, boards: [] } });
    });
  }

  test("dashboard.wizard.welcome — Get started advances to Choose output", async ({ page }) => {
    await mockEmptyHub(page, true);
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
      localStorage.removeItem("fiestaboard_wizard_progress");
    });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Welcome to FiestaBoard", exact: true })).toBeVisible();
    await expect(page.getByLabel("Name this hub", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Restore from a backup…", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Get started", exact: true }).click();
    await expect(page.getByRole("heading", { name: "What will FiestaBoard drive?", exact: true })).toBeVisible();
    await expect(page.getByRole("radio", { name: /Vestaboard/ })).toBeVisible();
  });

  test("dashboard.wizard.board-setup — missing credentials block Continue and Back returns to outputs", async ({
    page,
  }) => {
    await mockEmptyHub(page, true);
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
      localStorage.removeItem("fiestaboard_wizard_progress");
    });
    await page.goto("/");
    await chooseVestaboardInWizard(page);
    await expect(page.getByRole("button", { name: "Continue", exact: true })).toBeDisabled();
    await expect(page.getByRole("button", { name: "Test connection", exact: true })).toBeDisabled();
    await expect(page.getByLabel("Address", { exact: true })).toHaveValue("");
    await expect(page.getByLabel("Local API key", { exact: true })).toHaveAttribute("type", "password");
    await page.getByRole("button", { name: "Back", exact: true }).click();
    await expect(page.getByRole("heading", { name: "What will FiestaBoard drive?", exact: true })).toBeVisible();
  });

  test("dashboard.wizard.easy-plugins — optional selections update the review without installing", async ({ page }) => {
    await mockEmptyHub(page, true);
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
      localStorage.setItem(
        "fiestaboard_wizard_progress",
        JSON.stringify({
          currentStep: 3,
          outputId: "vestaboard",
          outputName: "Vestaboard",
          boardConfig: { device_type: "flagship", board_color: "black", output_config: { api_mode: "local" } },
          plugins: { date_time: { enabled: false, timezone: "UTC" }, registry_selected: [] },
        }),
      );
    });
    const installs: string[] = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && /\/plugins\/.*\/(install|enable)/.test(request.url()))
        installs.push(request.url());
    });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Add data sources", exact: true })).toBeVisible();
    const weather = page.getByRole("button", { name: /Weather/ });
    await expect(weather).toHaveAttribute("aria-pressed", "false");
    await weather.click();
    await expect(weather).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByText("1 selected", { exact: true })).toBeVisible();
    await weather.click();
    await expect(weather).toHaveAttribute("aria-pressed", "false");
    await expect(page.getByText("0 selected", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: /Calendar/ }).click();
    await page.getByRole("button", { name: "Continue", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Ready to go", exact: true })).toBeVisible();
    await expect(page.locator("dl")).toContainText("Calendar Sub");
    expect(installs).toEqual([]);
    await expect(page.getByRole("button", { name: "Finish setup", exact: true })).toBeVisible();
  });
});
