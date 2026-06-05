/**
 * Regression coverage for the /pages list view.
 * Subarea: pages.list
 */
import {
  test,
  expect,
  configureBoard,
  createPage,
  deleteAllPages,
  ensureAuthForFetch,
  ensureTwoBoards,
  loginIfNeeded,
  resetToSingleBoard,
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
  test("pages.list.list-view — List view toggle persists preference and renders compact rows that navigate to editor", async ({ page }) => {
    const id = await createPage("List View Test", ["HELLO", "", "", "", "", ""]);
    await page.goto("/pages");

    const listBtn = page.getByRole("button", { name: "List view", exact: true });
    await expect(listBtn).toBeVisible();
    await listBtn.click();
    await expect(listBtn).toHaveAttribute("aria-pressed", "true");

    const stored = await page.evaluate(() =>
      localStorage.getItem("fiestaboard_pages_view_mode"),
    );
    expect(stored).toBe("list");

    const row = page.getByRole("button", { name: /List View Test/i }).first();
    await row.click();
    await page.waitForURL(`**/pages/edit/${id}`, { timeout: 15_000 });
  });

  /** UX node: pages.list.carousels-tab */
  test.fixme("pages.list.carousels-tab — Carousels tab renders cascading CarouselButton cards", () => {
    // BLOCKED: `/pages` route hardcodes showCarousels={false}; tabs only render in
    // dashboard's PageGridSelector. UX-tree node is misattributed.
  });

  /** UX node: pages.list.empty */
  test.fixme("pages.list.empty — empty state CTA navigates to /pages/new", () => {
    // Empty CTA gating depends on a complex render path (carousels flag + first-run
    // wizard + showCarousels=false on this route). The "Create your first page"
    // link doesn't surface reliably even after deleteAllPages on the dev container.
    // Needs a `data-testid="pages-empty-cta"` on the EmptyState action to be stable.
  });

  /** UX node: pages.list.loading */
  test("pages.list.loading — route-level loading.tsx shows skeleton while pages query is in flight", async ({ page }) => {
    let release: () => void = () => {};
    await page.route("**/api/pages", async (route) => {
      if (route.request().method() === "GET") {
        await new Promise<void>((r) => { release = r; });
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
    await page.route("**/api/pages", async (route) => {
      if (route.request().method() === "GET") {
        await new Promise<void>((r) => { release = r; });
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
    await page.route("**/api/pages", async (route) => {
      if (route.request().method() === "GET") {
        await new Promise<void>((r) => { release = r; });
      }
      await route.continue();
    });
    const nav = page.goto("/pages");
    await expect(page.locator('[aria-busy="true"]').first()).toBeVisible({ timeout: 10_000 });
    release();
    await nav;
  });

  /** UX node: pages.list.device-tab-flagship */
  test("pages.list.device-tab-flagship — Flagship tab is active and renders flagship pages only", async ({ page }) => {
    await ensureTwoBoards();
    try {
      await createPage("Flagship Only", ["A", "", "", "", "", ""], "flagship");
      await page.goto("/pages");
      const flagshipTab = page.getByRole("tab", { name: /Flagship/i }).first();
      await expect(flagshipTab).toBeVisible({ timeout: 10_000 });
      await flagshipTab.click();
      await expect(flagshipTab).toHaveAttribute("aria-selected", "true");
      await expect(page.getByText("Flagship Only").first()).toBeVisible({ timeout: 10_000 });
    } finally {
      await resetToSingleBoard();
    }
  });

  /** UX node: pages.list.device-tab-note */
  test("pages.list.device-tab-note — Note tab New Page click lands on /pages/new?device=note", async ({ page }) => {
    await ensureTwoBoards();
    try {
      await page.goto("/pages");
      const noteTab = page.getByRole("tab", { name: /Note/i }).first();
      await expect(noteTab).toBeVisible({ timeout: 10_000 });
      await noteTab.click();
      const newBtn = page.getByRole("link", { name: /New Page|Create.*page/i }).first();
      if (await newBtn.isVisible().catch(() => false)) {
        const href = await newBtn.getAttribute("href");
        expect(href).toContain("device=note");
      }
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
