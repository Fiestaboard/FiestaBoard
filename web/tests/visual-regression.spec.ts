/**
 * FiestaBoard Visual Regression Tests
 *
 * Playwright screenshot comparison tests for critical UI states.
 * Tests use `toHaveScreenshot()` with a 3% pixel threshold to allow
 * for minor anti-aliasing and rendering differences across environments.
 *
 * First run: generates baseline snapshots in __snapshots__/
 * Subsequent runs: compares against baseline; CI fails on regressions.
 *
 * To update baselines: npx playwright test --update-snapshots visual-regression
 *
 * Issue: #503
 */
import {
  test,
  expect,
  configureBoard,
  suppressWizard,
  createPage,
  createSchedule,
  deleteAllPages,
  deleteAllSchedules,
  enablePlugin,
  disablePlugin,
  API_URL,
} from "./helpers";

/** Visual test config: allow up to 3% pixel difference for cross-env rendering. */
const SCREENSHOT_OPTIONS = {
  maxDiffPixelRatio: 0.03,
  threshold: 0.2, // per-pixel colour diff tolerance (0-1)
};

/** Snapshot name helper — keeps names consistent with the file path. */
const snap = (name: string) => `${name}.png`;

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
});

// ---------------------------------------------------------------------------
// 1. Dashboard
// ---------------------------------------------------------------------------

test.describe("Visual — Dashboard", () => {
  test("dashboard default state", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    // Mask any elements that change every render (timestamps, counters)
    await expect(page).toHaveScreenshot(snap("dashboard-default"), {
      ...SCREENSHOT_OPTIONS,
      mask: [
        page.locator("time, [data-testid='timestamp'], .uptime"),
      ],
    });
  });

  test("dashboard dark mode", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Toggle to dark mode
    const themeToggle = page
      .getByRole("button", { name: /dark mode|toggle theme|theme/i })
      .or(page.locator("[data-testid='theme-toggle']"))
      .first();

    if (await themeToggle.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await themeToggle.click();
      await page.waitForTimeout(500); // wait for CSS transition
    } else {
      // Force dark mode via class/attribute
      await page.evaluate(() => {
        document.documentElement.classList.add("dark");
        document.documentElement.setAttribute("data-theme", "dark");
      });
    }

    await expect(page).toHaveScreenshot(snap("dashboard-dark"), {
      ...SCREENSHOT_OPTIONS,
      mask: [page.locator("time, [data-testid='timestamp'], .uptime")],
    });
  });

  test("dashboard light mode", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Ensure light mode
    await page.evaluate(() => {
      document.documentElement.classList.remove("dark");
      document.documentElement.setAttribute("data-theme", "light");
    });
    await page.waitForTimeout(300);

    await expect(page).toHaveScreenshot(snap("dashboard-light"), {
      ...SCREENSHOT_OPTIONS,
      mask: [page.locator("time, [data-testid='timestamp'], .uptime")],
    });
  });
});

// ---------------------------------------------------------------------------
// 2. Page Editor / WYSIWYG
// ---------------------------------------------------------------------------

test.describe("Visual — Page Editor", () => {
  test.afterEach(async () => {
    await deleteAllPages();
  });

  test("page editor empty state", async ({ page }) => {
    await page.goto("/pages/new");
    await expect(page.getByText("Create Page").first()).toBeVisible({
      timeout: 15_000,
    });

    await expect(page).toHaveScreenshot(snap("page-editor-empty"), {
      ...SCREENSHOT_OPTIONS,
    });
  });

  test("page editor with content", async ({ page }) => {
    await page.goto("/pages/new");
    await expect(page.getByText("Create Page").first()).toBeVisible({
      timeout: 15_000,
    });

    // Fill name
    const nameInput = page.getByPlaceholder("My Custom Page");
    await nameInput.fill("Visual Test Page");

    // Fill editor if available
    const editor = page.locator('[contenteditable="true"]').first();
    if (await editor.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await editor.click();
      await page.keyboard.type("HELLO VISUAL WORLD");
    }

    await expect(page).toHaveScreenshot(snap("page-editor-with-content"), {
      ...SCREENSHOT_OPTIONS,
    });
  });
});

// ---------------------------------------------------------------------------
// 3. Schedule Calendar
// ---------------------------------------------------------------------------

test.describe("Visual — Schedule Calendar", () => {
  test.afterEach(async () => {
    await deleteAllSchedules();
    await deleteAllPages();
  });

  test("schedule page empty state", async ({ page }) => {
    await deleteAllSchedules();
    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    await expect(page).toHaveScreenshot(snap("schedule-empty"), {
      ...SCREENSHOT_OPTIONS,
    });
  });

  test("schedule page with entries", async ({ page }) => {
    await deleteAllSchedules();
    const pageId = await createPage("Morning News", ["GOOD MORNING", "", "", "", "", ""]);
    const pageId2 = await createPage("Afternoon Update", ["AFTERNOON", "", "", "", "", ""]);
    await createSchedule(pageId, "07:00", "12:00", "weekdays");
    await createSchedule(pageId2, "13:00", "18:00", "weekdays");

    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible({ timeout: 15_000 });
    // Wait for schedule entries to render
    await page.waitForTimeout(1_000);

    await expect(page).toHaveScreenshot(snap("schedule-with-entries"), {
      ...SCREENSHOT_OPTIONS,
    });
  });
});

// ---------------------------------------------------------------------------
// 4. Settings
// ---------------------------------------------------------------------------

test.describe("Visual — Settings", () => {
  test("settings general section", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: /settings/i }),
    ).toBeVisible({ timeout: 15_000 });

    await expect(page).toHaveScreenshot(snap("settings-general"), {
      ...SCREENSHOT_OPTIONS,
      // Mask version numbers and system info which may vary
      mask: [
        page.getByText(/v\d+\.\d+\.\d+/).first(),
        page.locator("[data-testid='version'], [data-testid='system-info']"),
      ],
    });
  });

  test("settings page scrolled to board configuration", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: /settings/i }),
    ).toBeVisible({ timeout: 15_000 });

    // Scroll to board config section
    const boardSection = page.getByText(/board configuration|board type|board settings/i).first();
    if (await boardSection.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await boardSection.scrollIntoViewIfNeeded();
      await page.waitForTimeout(300);
    }

    await expect(page).toHaveScreenshot(snap("settings-board-config"), {
      ...SCREENSHOT_OPTIONS,
    });
  });
});

// ---------------------------------------------------------------------------
// 5. Plugin Integrations
// ---------------------------------------------------------------------------

test.describe("Visual — Plugin Integrations", () => {
  test("integrations page installed tab", async ({ page }) => {
    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: /integrations/i }),
    ).toBeVisible({ timeout: 15_000 });

    // Ensure Installed tab is active
    const installedTab = page.getByRole("tab", { name: /installed/i });
    if (await installedTab.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await installedTab.click();
    }
    await page.waitForTimeout(500);

    await expect(page).toHaveScreenshot(snap("integrations-installed"), {
      ...SCREENSHOT_OPTIONS,
    });
  });

  test("integrations page marketplace tab", async ({ page }) => {
    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: /integrations/i }),
    ).toBeVisible({ timeout: 15_000 });

    const marketplaceTab = page.getByRole("tab", { name: /marketplace/i });
    if (await marketplaceTab.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await marketplaceTab.click();
      await page.waitForTimeout(500);
    }

    await expect(page).toHaveScreenshot(snap("integrations-marketplace"), {
      ...SCREENSHOT_OPTIONS,
    });
  });
});

// ---------------------------------------------------------------------------
// 6. Pages List
// ---------------------------------------------------------------------------

test.describe("Visual — Pages List", () => {
  test.afterEach(async () => {
    await deleteAllPages();
  });

  test("pages list empty state", async ({ page }) => {
    await deleteAllPages();
    await page.goto("/pages");
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true }),
    ).toBeVisible({ timeout: 15_000 });
    await page.waitForTimeout(500);

    await expect(page).toHaveScreenshot(snap("pages-list-empty"), {
      ...SCREENSHOT_OPTIONS,
    });
  });

  test("pages list with pages", async ({ page }) => {
    await deleteAllPages();
    await createPage("Morning Dashboard", ["MORNING", "", "", "", "", ""]);
    await createPage("Evening Update", ["EVENING", "", "", "", "", ""]);

    await page.goto("/pages");
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true }),
    ).toBeVisible({ timeout: 15_000 });
    await page.waitForTimeout(500);

    await expect(page).toHaveScreenshot(snap("pages-list-with-pages"), {
      ...SCREENSHOT_OPTIONS,
    });
  });
});

// ---------------------------------------------------------------------------
// 7. Navigation Sidebar
// ---------------------------------------------------------------------------

test.describe("Visual — Navigation", () => {
  test("sidebar navigation default state", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Capture just the sidebar
    const sidebar = page
      .locator("[data-testid='sidebar'], nav, aside")
      .first();

    if (await sidebar.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await expect(sidebar).toHaveScreenshot(snap("sidebar-default"), {
        ...SCREENSHOT_OPTIONS,
      });
    } else {
      // Full page fallback if no discrete sidebar element
      await expect(page).toHaveScreenshot(snap("sidebar-default"), {
        ...SCREENSHOT_OPTIONS,
        fullPage: false,
        clip: { x: 0, y: 0, width: 240, height: 600 },
      });
    }
  });
});
