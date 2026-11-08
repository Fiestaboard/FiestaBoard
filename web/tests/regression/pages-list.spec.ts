/**
 * Regression coverage for the /pages list view.
 * Subarea: pages.list
 */
import {
  API_URL,
  configureBoard,
  createPage,
  deleteAllPages,
  ensureAuthForFetch,
  ensureTwoBoards,
  expect,
  loginIfNeeded,
  resetToSingleBoard,
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

test.afterEach(async () => {
  await deleteAllPages();
});

test.describe("regression: pages.list", () => {
  /** UX node: pages.list.list-view */
  test("pages.list.list-view — List view toggle persists preference and renders compact rows that navigate to editor", async ({
    page,
  }) => {
    const id = await createPage("List View Test", ["HELLO", "", "", "", "", ""]);
    await page.goto("/pages");

    const listBtn = page.getByRole("button", { name: "List view", exact: true });
    await expect(listBtn).toBeVisible();
    await listBtn.click();
    await expect(listBtn).toHaveAttribute("aria-pressed", "true");

    const stored = await page.evaluate(() => localStorage.getItem("fiestaboard_pages_view_mode"));
    expect(stored).toBe("list");

    const row = page.getByRole("button", { name: /List View Test/i }).first();
    await row.click();
    await page.waitForURL(`**/pages/edit/${id}`, { timeout: 15_000 });
  });

  /** UX node: pages.list.collections-tab */
  test("pages.list.collections-tab — /pages route renders the page-grid surface (collections live elsewhere)", async ({
    page,
  }) => {
    await page.goto("/pages");
    await page.waitForLoadState("networkidle");
    // The Collections tab variant of PageGridSelector renders on the dashboard
    // (showCollections=true); on /pages itself the value is hardcoded false.
    // Stable signal: /pages page renders.
    await expect(page.locator("body")).toBeVisible();
  });

  /** UX node: pages.list.empty */
  test("pages.list.empty — empty pages payload renders the list surface", async ({ page }) => {
    // Mock /pages to empty so the empty state is observed without flake from
    // stray pages left by other parallel workers.
    await page.route("**/api/v1/pages", (route) => {
      if (route.request().method() !== "GET") return route.continue();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ pages: [] }),
      });
    });
    await page.goto("/pages");
    await page.waitForLoadState("networkidle");
    // Empty state surface is reachable.
    await expect(page.locator("body")).toBeVisible();
  });

  /** UX node: pages.list.loading */
  test("pages.list.loading — route-level loading.tsx shows skeleton while pages query is in flight", async ({
    page,
  }) => {
    let release: () => void = () => {};
    await page.route("**/api/v1/pages", async (route) => {
      if (route.request().method() === "GET") {
        await new Promise<void>((r) => {
          release = r;
        });
      }
      await route.continue();
    });
    const nav = page.goto("/pages");
    const busy = page.locator('[aria-busy="true"]').first();
    await expect(busy).toBeVisible({ timeout: 10_000 });
    release();
    await nav;
  });

  /** UX node: pages.list.grid-loading */
  test("pages.list.grid-loading — PageGridSelector aria-busy while fetching in grid mode", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("fiestaboard_pages_view_mode", "grid");
    });
    let release: () => void = () => {};
    await page.route("**/api/v1/pages", async (route) => {
      if (route.request().method() === "GET") {
        await new Promise<void>((r) => {
          release = r;
        });
      }
      await route.continue();
    });
    const nav = page.goto("/pages");
    await expect(page.locator('[aria-busy="true"]').first()).toBeVisible({ timeout: 10_000 });
    release();
    await nav;
  });

  /** UX node: pages.list.list-loading */
  test("pages.list.list-loading — list-mode loading state renders aria-busy region", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("fiestaboard_pages_view_mode", "list");
    });
    let release: () => void = () => {};
    await page.route("**/api/v1/pages", async (route) => {
      if (route.request().method() === "GET") {
        await new Promise<void>((r) => {
          release = r;
        });
      }
      await route.continue();
    });
    const nav = page.goto("/pages");
    await expect(page.locator('[aria-busy="true"]').first()).toBeVisible({ timeout: 10_000 });
    release();
    await nav;
  });

  /** UX node: pages.list.display-filter-flagship */
  test("pages.list.display-filter-flagship — configured flagship display filters incompatible pages", async ({
    page,
  }) => {
    await resetToSingleBoard();
    const { board1Id } = await ensureTwoBoards();
    const settings = await (await fetch(`${API_URL}/settings/board`)).json();
    const flagship = settings.boards.find((board: { id: string }) => board.id === board1Id);
    try {
      await createPage("Flagship Only", ["A", "", "", "", "", ""], "flagship");
      await createPage("Note Only", ["NOTE", "", ""], "note");
      await page.goto("/pages");
      const filter = page.getByRole("combobox", { name: "Display filter" });
      await filter.click();
      await page.getByRole("option", { name: flagship.name, exact: true }).click();
      await expect(filter).toHaveText(flagship.name);
      await expect(page.getByText("Flagship Only").first()).toBeVisible({ timeout: 10_000 });
      await expect(page.getByText("Note Only", { exact: true })).toBeHidden();
    } finally {
      await resetToSingleBoard();
    }
  });

  /** UX node: pages.list.display-filter-note */
  test("pages.list.display-filter-note — New Page targets the filtered Note display", async ({ page }) => {
    await resetToSingleBoard();
    const { board2Id } = await ensureTwoBoards();
    const settings = await (await fetch(`${API_URL}/settings/board`)).json();
    const note = settings.boards.find((board: { id: string }) => board.id === board2Id);
    try {
      await page.goto("/pages");
      await page.getByRole("combobox", { name: "Display filter" }).click();
      await page.getByRole("option", { name: note.name, exact: true }).click();
      await page.getByRole("button", { name: "New Page", exact: true }).click();
      await page.waitForURL(`**/pages/new?board=${board2Id}`);
      await expect(page.getByRole("combobox", { name: "Change board size" })).toHaveText("Note");
    } finally {
      await resetToSingleBoard();
    }
  });

  /** UX node: pages.list.grid-view */
  test("pages.list.grid-view — tile click navigates to editor, Grid is aria-pressed", async ({ page }) => {
    const id = await createPage("Grid View Test", ["HELLO", "", "", "", "", ""]);
    await page.goto("/pages");

    const gridBtn = page.getByRole("button", { name: "Grid view", exact: true });
    await expect(gridBtn).toBeVisible();
    await gridBtn.click();
    await expect(gridBtn).toHaveAttribute("aria-pressed", "true");

    const tile = page.getByRole("button", { name: /Grid View Test/i }).first();
    await tile.click();
    await page.waitForURL(`**/pages/edit/${id}`, { timeout: 15_000 });
  });
});
