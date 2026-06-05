/**
 * FiestaBoard Visual Regression Tests
 *
 * Playwright screenshot comparison tests for critical UI states.
 * Uses `toHaveScreenshot()` with a 0.3% pixel threshold to catch
 * real regressions while tolerating minor anti-aliasing differences.
 *
 * Baseline workflow:
 *   1. First run generates baselines in __snapshots__/ (tests fail by design)
 *   2. Commit generated baselines to the repo
 *   3. Subsequent runs compare against committed baselines
 *
 * To update baselines after intentional UI changes:
 *   npx playwright test --update-snapshots visual-regression
 *
 * Issue: #503
 */
import type { Page } from "@playwright/test";

import {
  configureBoard,
  createPage,
  createSchedule,
  deleteAllPages,
  deleteAllSchedules,
  expect,
  suppressWizard,
  test,
} from "./helpers";

/**
 * Visual test config: 0.3% pixel diff ratio for cross-environment tolerance.
 * This is strict enough to catch real CSS regressions while allowing for
 * minor anti-aliasing and sub-pixel rendering differences across CI runs.
 * Adjust if false positives occur (document the reason for any change).
 */
const SCREENSHOT_OPTIONS = {
  maxDiffPixelRatio: 0.003,
  threshold: 0.2, // per-pixel colour tolerance (0–1 scale)
};

/** Snapshot name helper — keeps names consistent. */
const snap = (name: string) => `${name}.png`;

/**
 * Hide blinking cursors, selection highlights, and caret indicators
 * that would cause non-deterministic screenshots in the WYSIWYG editor.
 */
async function maskEditorCursor(page: Page) {
  await page.addStyleTag({
    content: `
      /* Hide blinking text cursor */
      [contenteditable] { caret-color: transparent !important; }
      /* Hide selection highlights */
      ::selection { background: transparent !important; }
      ::-moz-selection { background: transparent !important; }
      /* Hide any custom cursor overlay elements */
      .ProseMirror-cursor, .cursor-blink, .ql-cursor { display: none !important; }
    `,
  });
}

/**
 * Hide current-date highlighting in the schedule calendar.
 * Calendar components typically highlight "today" which changes daily.
 */
async function maskCalendarToday(page: Page) {
  await page.addStyleTag({
    content: `
      /* Neutralise today-highlighting in calendar views */
      [data-today="true"],
      .rdp-day_today,
      .fc-day-today,
      .react-calendar__tile--now,
      .today,
      [aria-current="date"] {
        background-color: transparent !important;
        border-color: inherit !important;
        color: inherit !important;
        font-weight: inherit !important;
      }
    `,
  });
}

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

    await expect(page).toHaveScreenshot(snap("dashboard-default"), {
      ...SCREENSHOT_OPTIONS,
      mask: [page.locator("time, [data-testid='timestamp'], .uptime")],
    });
  });

  test("dashboard dark mode", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Toggle to dark mode via the theme button (next-themes)
    const themeToggle = page.getByRole("button", { name: /theme|dark|light|toggle/i }).first();

    if (await themeToggle.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await themeToggle.click();
      // Wait for dark mode class to be applied
      await page.waitForFunction(
        () =>
          document.documentElement.classList.contains("dark") ||
          document.documentElement.getAttribute("data-theme") === "dark",
        { timeout: 5_000 },
      );
    } else {
      // Fallback: force dark mode on <html>
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
      localStorage.setItem("theme", "light");
    });
    // Wait for light mode to take effect
    await page.waitForFunction(() => !document.documentElement.classList.contains("dark"), { timeout: 5_000 });

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
    await page.waitForLoadState("networkidle");
    await maskEditorCursor(page);

    // Wait for the editor to be ready
    await expect(page.getByText(/create page/i).first()).toBeVisible({ timeout: 15_000 });

    await expect(page).toHaveScreenshot(snap("page-editor-empty"), {
      ...SCREENSHOT_OPTIONS,
    });
  });

  test("page editor with content", async ({ page }) => {
    await page.goto("/pages/new");
    await page.waitForLoadState("networkidle");
    await maskEditorCursor(page);

    await expect(page.getByText(/create page/i).first()).toBeVisible({ timeout: 15_000 });

    // Fill page name
    const nameInput = page.getByPlaceholder("My Custom Page");
    if (await nameInput.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await nameInput.fill("Visual Test Page");
    }

    // Type into the WYSIWYG editor
    const editor = page.locator('[contenteditable="true"]').first();
    if (await editor.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await editor.click();
      await page.keyboard.type("HELLO VISUAL WORLD");
      // Blur editor to dismiss cursor before screenshot
      await page.keyboard.press("Escape");
      await editor.evaluate((el) => (el as HTMLElement).blur());
    }

    await expect(page).toHaveScreenshot(snap("page-editor-with-content"), {
      ...SCREENSHOT_OPTIONS,
    });
  });

  test("page editor with template variables", async ({ page }) => {
    await page.goto("/pages/new");
    await page.waitForLoadState("networkidle");
    await maskEditorCursor(page);

    await expect(page.getByText(/create page/i).first()).toBeVisible({ timeout: 15_000 });

    const nameInput = page.getByPlaceholder("My Custom Page");
    if (await nameInput.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await nameInput.fill("Template Var Page");
    }

    const editor = page.locator('[contenteditable="true"]').first();
    if (await editor.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await editor.click();
      await page.keyboard.type("{date} {time}");
      await page.keyboard.press("Escape");
      await editor.evaluate((el) => (el as HTMLElement).blur());
    }

    await expect(page).toHaveScreenshot(snap("page-editor-template-vars"), {
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
    // Fix Date.now() after navigation so calendar renders a consistent date.
    // setFixedTime keeps timers running (unlike clock.install+pauseAt which
    // freezes them and prevents React from rendering).
    await page.clock.setFixedTime(new Date("2025-06-15T10:00:00Z"));
    await maskCalendarToday(page);
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    await expect(page).toHaveScreenshot(snap("schedule-empty"), {
      ...SCREENSHOT_OPTIONS,
    });
  });

  test("schedule page with entries", async ({ page }) => {
    await deleteAllSchedules();
    const pageId1 = await createPage("Morning News", ["GOOD MORNING", "", "", "", "", ""]);
    const pageId2 = await createPage("Afternoon Update", ["AFTERNOON", "", "", "", "", ""]);
    await createSchedule(pageId1, "07:00", "12:00", "weekdays");
    await createSchedule(pageId2, "13:00", "18:00", "weekdays");

    await page.goto("/schedule");
    // Fix Date.now() after navigation so calendar renders a consistent date.
    await page.clock.setFixedTime(new Date("2025-06-15T10:00:00Z"));
    await maskCalendarToday(page);
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });
    // Wait for schedule data to render (look for page names in the list)
    await expect(page.getByText("Morning News").first())
      .toBeVisible({ timeout: 10_000 })
      .catch(() => {
        // Schedule might render differently; fall back to networkidle
      });
    await page.waitForLoadState("networkidle");

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
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await expect(page).toHaveScreenshot(snap("settings-general"), {
      ...SCREENSHOT_OPTIONS,
      // Mask version numbers and system info which change between builds
      mask: [
        page.getByText(/v?\d+\.\d+\.\d+/).first(),
        page.locator("[data-testid='version'], [data-testid='system-info']"),
        page.locator("time, [data-testid='timestamp'], .uptime"),
      ],
    });
  });

  test("settings board configuration", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    // Scroll to board config section if it exists
    const boardSection = page.getByText(/board configuration|board type|board settings|boards/i).first();
    if (await boardSection.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await boardSection.scrollIntoViewIfNeeded();
      // Wait for the element to be in view
      await expect(boardSection).toBeInViewport();
    }

    await expect(page).toHaveScreenshot(snap("settings-board-config"), {
      ...SCREENSHOT_OPTIONS,
      mask: [
        page.getByText(/v?\d+\.\d+\.\d+/).first(),
        page.locator("[data-testid='version'], [data-testid='system-info']"),
      ],
    });
  });
});

// ---------------------------------------------------------------------------
// 5. Plugin Integrations
// ---------------------------------------------------------------------------

test.describe("Visual — Plugin Integrations", () => {
  test("integrations page installed tab", async ({ page }) => {
    await page.goto("/integrations");
    await expect(page.getByRole("heading", { name: "Integrations", exact: true })).toBeVisible({ timeout: 15_000 });

    // Ensure Installed tab is active
    const installedTab = page.getByRole("tab", { name: /installed/i });
    if (await installedTab.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await installedTab.click();
    }
    await page.waitForLoadState("networkidle");

    await expect(page).toHaveScreenshot(snap("integrations-installed"), {
      ...SCREENSHOT_OPTIONS,
    });
  });

  test("integrations page marketplace tab", async ({ page }) => {
    await page.goto("/integrations");
    await expect(page.getByRole("heading", { name: "Integrations", exact: true })).toBeVisible({ timeout: 15_000 });

    const marketplaceTab = page.getByRole("tab", { name: /marketplace/i });
    if (await marketplaceTab.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await marketplaceTab.click();
      await page.waitForLoadState("networkidle");
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
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });
    await page.waitForLoadState("networkidle");

    await expect(page).toHaveScreenshot(snap("pages-list-empty"), {
      ...SCREENSHOT_OPTIONS,
    });
  });

  test("pages list with pages", async ({ page }) => {
    await deleteAllPages();
    await createPage("Morning Dashboard", ["MORNING", "", "", "", "", ""]);
    await createPage("Evening Update", ["EVENING", "", "", "", "", ""]);

    await page.goto("/pages");
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });
    // Wait for page cards to render
    await expect(page.getByText("Morning Dashboard").first()).toBeVisible({ timeout: 10_000 });

    await expect(page).toHaveScreenshot(snap("pages-list-with-pages"), {
      ...SCREENSHOT_OPTIONS,
      // Mask timestamps on page cards if they show creation time
      mask: [page.locator("time, [data-testid='timestamp']")],
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

    // Capture just the sidebar if identifiable
    const sidebar = page.locator("[data-testid='sidebar'], nav, aside").first();

    if (await sidebar.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await expect(sidebar).toHaveScreenshot(snap("sidebar-default"), {
        ...SCREENSHOT_OPTIONS,
      });
    } else {
      // Full page fallback with clip to sidebar region
      await expect(page).toHaveScreenshot(snap("sidebar-default"), {
        ...SCREENSHOT_OPTIONS,
        fullPage: false,
        clip: { x: 0, y: 0, width: 240, height: 600 },
      });
    }
  });
});
