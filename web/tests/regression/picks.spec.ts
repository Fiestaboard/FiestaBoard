/**
 * Auto-generated regression stubs from .claude/ux-coverage.json.
 * Subarea: picks (grid + card + device tabs)
 *
 * Priority cluster #4 from the auditor: entire picks page is untested — 8
 * uncovered nodes. Fill these early.
 *
 * Most tests stub /api/staff-picks via page.route so they are independent of
 * the on-disk picks.json. The two tab tests exercise the real multi-board
 * tab UI and rely on ensureTwoBoards + the real (or fixture) picks catalog.
 */
import {
  test,
  expect,
  configureBoard,
  API_URL,
  loginIfNeeded,
  ensureAuthForFetch,
  authHeaders,
  deleteAllPages,
  BOARD_HOST,
} from "../helpers";

// ---------------------------------------------------------------------------
// Local helpers (picks-only — promote to helpers.ts if reused elsewhere).
// ---------------------------------------------------------------------------

type Pick = {
  id: string;
  name: string;
  description: string;
  device_type: "flagship" | "note";
  tags: string[];
  image?: string | null;
  required_plugins: { id: string; name: string }[];
  featured_at?: string;
};

/** Build a minimal staff pick fixture. */
function makePick(overrides: Partial<Pick> & { id: string; name: string }): Pick {
  return {
    description: "Test pick",
    device_type: "flagship",
    tags: [],
    image: null,
    required_plugins: [],
    featured_at: "2026-05-24",
    ...overrides,
  };
}

/** Stub the /api/staff-picks list endpoint with a fixture array. */
async function stubPicks(page: import("@playwright/test").Page, picks: Pick[]) {
  await page.route("**/api/staff-picks", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(picks),
    });
  });
}

/**
 * Auth-aware variants of ensureTwoBoards / resetToSingleBoard.
 *
 * The shared helpers in helpers.ts call bare fetch() without authHeaders(),
 * which 401s when auth is enabled. These local copies route through
 * authHeaders() and are scoped to this spec. If we add more auth-enabled
 * multi-board specs, promote these (or fix the shared helpers).
 */
async function ensureTwoBoardsAuthed(): Promise<void> {
  const res = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`ensureTwoBoardsAuthed: get failed ${res.status}`);
  const data = await res.json();
  const boards = data.boards ?? [];
  if (boards.length >= 2) return;
  if (boards.length === 0) {
    // Re-prime a single Flagship board, then add Note.
    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        boards: [{
          name: "My Board",
          device_type: "flagship",
          board_color: "black",
          enabled: true,
          api_mode: "local",
          host: BOARD_HOST,
          local_api_key: "test-key",
        }],
      }),
    });
  }
  await fetch(`${API_URL}/settings/board/add`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ device_type: "note" }),
  });
}

async function resetToSingleBoardAuthed(): Promise<void> {
  await fetch(`${API_URL}/settings/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      boards: [{
        name: "My Board",
        device_type: "flagship",
        board_color: "black",
        enabled: true,
        api_mode: "local",
        host: BOARD_HOST,
        local_api_key: "test-key",
      }],
    }),
  });
}

/** Get IDs of currently-enabled plugins so we can construct a "missing" badge case. */
async function getEnabledPluginIds(): Promise<Set<string>> {
  const res = await fetch(`${API_URL}/plugins`, { headers: authHeaders() });
  if (!res.ok) return new Set();
  const data = await res.json();
  return new Set<string>(
    (data.plugins ?? []).filter((p: { enabled?: boolean }) => p.enabled).map((p: { id: string }) => p.id),
  );
}

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

test.describe("regression: picks.grid", () => {
  /**
   * UX node: picks.grid.loading
   * Route: /picks
   * Preconditions: api:pending
   * Expected: skeleton grid while picks catalog loads
   * Source refs: web/src/app/picks/page.tsx
   * Coverage status: covered
   */
  test("picks.grid.loading — grid loading skeleton", async ({ page }) => {
    // Hold the staff-picks response open so we observe the loading skeleton.
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/staff-picks", async (route) => {
      await gate;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.goto("/picks");
    // The grid renders 2 skeleton cards while picksLoading is true. Each card
    // contains multiple Skeleton primitives — assert at least a handful exist.
    const skeletons = page.locator("[data-slot='skeleton'], .animate-pulse");
    await expect(skeletons.first()).toBeVisible({ timeout: 10_000 });
    expect(await skeletons.count()).toBeGreaterThanOrEqual(2);

    release();
  });

  /**
   * UX node: picks.grid.empty
   * Route: /picks
   * Preconditions: picks:[]
   * Expected: empty-state copy
   * Source refs: web/src/app/picks/page.tsx
   * Coverage status: covered
   */
  test("picks.grid.empty — empty catalog state", async ({ page }) => {
    await stubPicks(page, []);
    await page.goto("/picks");
    await expect(
      page.getByText("No picks available for this board type yet."),
    ).toBeVisible({ timeout: 10_000 });
  });

  /**
   * UX node: picks.grid.populated
   * Route: /picks
   * Preconditions: picks:>=1
   * Expected: pick cards render with name, preview, and Import affordance
   * Source refs: web/src/app/picks/page.tsx
   * Coverage status: covered
   */
  test("picks.grid.populated — cards render with preview + Import affordance", async ({ page }) => {
    await stubPicks(page, [
      makePick({
        id: "regression-pick-1",
        name: "Regression Pick One",
        description: "First card",
      }),
      makePick({
        id: "regression-pick-2",
        name: "Regression Pick Two",
        description: "Second card",
      }),
    ]);

    await page.goto("/picks");
    await expect(page.getByRole("heading", { name: "Regression Pick One" })).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByRole("heading", { name: "Regression Pick Two" })).toBeVisible();
    // Both cards expose an enabled Import button.
    const importButtons = page.getByRole("button", { name: "Import", exact: true });
    expect(await importButtons.count()).toBe(2);
    await expect(importButtons.first()).toBeEnabled();
  });
});

test.describe("regression: picks.card", () => {
  /**
   * UX node: picks.card.missing-plugins
   * Route: /picks
   * Preconditions: pick:requires-missing-plugins
   * Expected: card surfaces 'Requires <plugin>' badge linking to /integrations
   * Source refs: web/src/app/picks/page.tsx
   * Coverage status: covered
   */
  test("picks.card.missing-plugins — missing plugin shown as warning link", async ({ page }) => {
    // Pick a definitely-not-enabled plugin id.
    const enabled = await getEnabledPluginIds();
    const fakePluginId = "definitely_not_a_real_plugin_xyz";
    expect(enabled.has(fakePluginId)).toBe(false);

    await stubPicks(page, [
      makePick({
        id: "needs-missing",
        name: "Needs Missing Plugin",
        required_plugins: [{ id: fakePluginId, name: "Mystery Plugin" }],
      }),
    ]);

    await page.goto("/picks");
    await expect(page.getByRole("heading", { name: "Needs Missing Plugin" })).toBeVisible({
      timeout: 10_000,
    });
    // The required-plugin chip links to /integrations when the plugin is missing.
    const requiresLink = page.getByRole("link", { name: /Mystery Plugin/ });
    await expect(requiresLink).toBeVisible();
    await expect(requiresLink).toHaveAttribute("href", "/integrations");
  });

  /**
   * UX node: picks.card.importing
   * Route: /picks
   * Preconditions: import-mutation:pending
   * Expected: 'Importing...' label on card Import button; card disabled
   * Source refs: web/src/app/picks/page.tsx
   * Coverage status: covered
   */
  test("picks.card.importing — Import pending state on card", async ({ page }) => {
    await stubPicks(page, [
      makePick({ id: "import-pending", name: "Import Pending Pick" }),
    ]);

    // Stub the share endpoint to be fast, but stall the actual import POST so
    // we can observe the "Importing..." button text and disabled state.
    await page.route("**/api/staff-picks/import-pending/share", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ share_string: "FAKE_SHARE_STRING" }),
      });
    });
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/pages/import", async (route) => {
      await gate;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ok",
          page: { id: "imported-1", name: "Import Pending Pick" },
        }),
      });
    });

    await page.goto("/picks");
    const importBtn = page.getByRole("button", { name: "Import", exact: true });
    await expect(importBtn).toBeVisible({ timeout: 10_000 });
    await importBtn.click();

    const pending = page.getByRole("button", { name: "Importing..." });
    await expect(pending).toBeVisible({ timeout: 5_000 });
    await expect(pending).toBeDisabled();

    release();
  });

  /**
   * UX node: picks.card.import-error
   * Route: /picks
   * Preconditions: import-mutation:error
   * Expected: error toast; card returns to idle; user can retry
   * Source refs: web/src/app/picks/page.tsx
   * Coverage status: covered
   */
  test("picks.card.import-error — error toast and retry-able state", async ({ page }) => {
    await stubPicks(page, [
      makePick({ id: "import-fail", name: "Import Fail Pick" }),
    ]);
    await page.route("**/api/staff-picks/import-fail/share", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ share_string: "FAKE_SHARE_STRING" }),
      });
    });
    await page.route("**/api/pages/import", async (route) => {
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Bad share string from regression test" }),
      });
    });

    await page.goto("/picks");
    const importBtn = page.getByRole("button", { name: "Import", exact: true });
    await expect(importBtn).toBeVisible({ timeout: 10_000 });
    await importBtn.click();

    // Sonner toast contains the error message.
    await expect(
      page.getByText(/Bad share string from regression test/),
    ).toBeVisible({ timeout: 5_000 });

    // Card returns to idle — Import button visible, enabled, and re-clickable.
    await expect(importBtn).toBeVisible();
    await expect(importBtn).toBeEnabled({ timeout: 5_000 });
  });
});

test.describe("regression: picks.tabs", () => {
  test.beforeEach(async () => {
    await ensureTwoBoardsAuthed();
  });

  test.afterEach(async () => {
    await deleteAllPages().catch(() => {});
    await resetToSingleBoardAuthed().catch(() => {});
  });

  /**
   * UX node: picks.tab-flagship
   * Route: /picks (Flagship tab)
   * Expected: tab selected and grid shows flagship-only picks
   * Source refs: web/src/app/picks/page.tsx
   * Coverage status: covered
   */
  test("picks.tab-flagship — flagship tab active and shows flagship picks", async ({ page }) => {
    await stubPicks(page, [
      makePick({ id: "flag-1", name: "Flagship Only Pick", device_type: "flagship" }),
      makePick({ id: "note-1", name: "Note Only Pick", device_type: "note" }),
    ]);

    await page.goto("/picks");
    const flagshipTab = page.getByRole("tab", { name: "Flagship" });
    await expect(flagshipTab).toBeVisible({ timeout: 10_000 });
    await expect(flagshipTab).toHaveAttribute("data-state", "active");

    await expect(page.getByRole("heading", { name: "Flagship Only Pick" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Note Only Pick" })).toHaveCount(0);
  });

  /**
   * UX node: picks.tab-note
   * Route: /picks (Note tab)
   * Expected: tab selected and grid shows note-only picks
   * Source refs: web/src/app/picks/page.tsx
   * Coverage status: covered
   */
  test("picks.tab-note — note tab active and shows note picks", async ({ page }) => {
    await stubPicks(page, [
      makePick({ id: "flag-2", name: "Flagship Only Pick", device_type: "flagship" }),
      makePick({ id: "note-2", name: "Note Only Pick", device_type: "note" }),
    ]);

    await page.goto("/picks");
    const noteTab = page.getByRole("tab", { name: "Note" });
    await expect(noteTab).toBeVisible({ timeout: 10_000 });
    await noteTab.click();
    await expect(noteTab).toHaveAttribute("data-state", "active");

    await expect(page.getByRole("heading", { name: "Note Only Pick" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Flagship Only Pick" })).toHaveCount(0);
  });
});
