/**
 * FiestaBoard Mobile Viewport E2E Tests
 *
 * Ensures critical user flows work on small screens (375x812, iPhone-ish).
 * The repo recently fixed mobile UI regressions; this suite catches future ones.
 *
 * Issue: #500 — E2E: add Playwright tests for critical user flows
 */
import {
  configureBoard,
  createCollection,
  createPage,
  deleteAllCollections,
  deleteAllPages,
  expect,
  suppressWizard,
  test,
} from "./helpers";

const MOBILE_VIEWPORT = { width: 375, height: 812 };

test.beforeEach(async ({ page }) => {
  await page.setViewportSize(MOBILE_VIEWPORT);
  await configureBoard();
  await suppressWizard(page);
});

test.afterEach(async () => {
  await deleteAllPages();
});

test.describe("Mobile — Navigation", () => {
  test("hamburger menu opens and shows navigation links", async ({ page }) => {
    await page.goto("/");

    // Wait for the page to render
    await page.waitForLoadState("networkidle");

    // Hamburger / menu button should be visible at mobile width
    const menuButton = page
      .getByRole("button", { name: /menu|open/i })
      .or(page.locator("[aria-label='Open menu'], [aria-label='Menu'], button.hamburger"))
      .first();

    if (await menuButton.isVisible({ timeout: 8_000 }).catch(() => false)) {
      await menuButton.click();

      // Navigation links should appear
      const navLinks = [
        page.getByRole("link", { name: /dashboard/i }),
        page.getByRole("link", { name: /pages/i }),
        page.getByRole("link", { name: /schedule/i }),
      ];

      let visibleCount = 0;
      for (const link of navLinks) {
        if (
          await link
            .first()
            .isVisible({ timeout: 3_000 })
            .catch(() => false)
        ) {
          visibleCount++;
        }
      }
      expect(visibleCount).toBeGreaterThan(0);
    } else {
      // If there's no hamburger, navigation may be always-visible — that's ok
      const navLinks = page.getByRole("navigation").first();
      await expect(navLinks).toBeVisible({ timeout: 10_000 });
    }
  });

  test("can navigate to Pages on mobile", async ({ page }) => {
    await page.goto("/pages");
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });
  });

  test("can navigate to Schedule on mobile", async ({ page }) => {
    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });
  });

  test("can navigate to Settings on mobile", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("Mobile — Dashboard", () => {
  test("dashboard renders correctly on mobile", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Dashboard heading should be visible
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

    // No horizontal overflow (basic check: viewport width matches page width)
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(MOBILE_VIEWPORT.width + 20); // allow 20px tolerance
  });

  test("board display is visible on mobile", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Dashboard should render without errors — board display may be a grid, canvas,
    // or an empty-state message depending on app state
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

    // No error state visible
    await expect(page.getByText(/crash|unhandled exception/i)).not.toBeVisible();
  });
});

test.describe("Mobile — Pages", () => {
  test("pages list is usable on mobile", async ({ page }) => {
    await createPage("Mobile Test Page", ["MOBILE", "", "", "", "", ""]);

    await page.goto("/pages");
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });

    // The page we created should be listed
    await expect(page.getByText("Mobile Test Page")).toBeVisible({
      timeout: 10_000,
    });
  });

  test("create page button is accessible on mobile", async ({ page }) => {
    await page.goto("/pages");
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });

    // New Page / Create Page button should be reachable
    const createBtn = page
      .getByRole("link", { name: /new page|create page/i })
      .or(page.getByRole("button", { name: /new page|create page/i }))
      .first();

    await expect(createBtn).toBeVisible({ timeout: 8_000 });
  });

  test("page editor form is usable on mobile", async ({ page }) => {
    await page.goto("/pages/new");

    // Page name input should be reachable and fillable
    const nameInput = page.getByPlaceholder("My Custom Page");
    await expect(nameInput).toBeVisible({ timeout: 15_000 });
    await nameInput.fill("Mobile Created Page");

    // Input should have the value we typed
    await expect(nameInput).toHaveValue("Mobile Created Page");
  });
});

test.describe("Mobile — Integrations", () => {
  test("integrations page loads on mobile", async ({ page }) => {
    await page.goto("/integrations");
    await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible({ timeout: 15_000 });
  });

  test("installed and marketplace tabs are reachable on mobile", async ({ page }) => {
    await page.goto("/integrations");
    await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible({ timeout: 15_000 });

    const installedTab = page.getByRole("tab", { name: /installed/i });
    const marketplaceTab = page.getByRole("tab", { name: /marketplace/i });

    if (await installedTab.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await installedTab.click();
      await marketplaceTab.click();
      // Should switch without error
      await expect(page.getByRole("heading", { name: /integrations/i })).toBeVisible();
    }
  });
});

test.describe("Mobile — Board preview fits viewport", () => {
  test("dashboard board preview stays inside its frame at phone width", async ({ page }) => {
    await page.goto("/");
    const firstTile = page.getByTestId("char-tile-0-0");
    await expect(firstTile).toBeVisible({ timeout: 15_000 });
    // Let ScaledBoardDisplay's measure + rAF scale pass settle
    await page.waitForTimeout(500);

    const geometry = await page.evaluate(() => {
      const t0 = document.querySelector('[data-testid="char-tile-0-0"]');
      const t21 = document.querySelector('[data-testid="char-tile-0-21"]');
      if (!t0 || !t21) return null;
      const frame = t0.closest('[class*="border-["]');
      if (!frame) return null;
      const fr = frame.getBoundingClientRect();
      const r0 = t0.getBoundingClientRect();
      const r21 = t21.getBoundingClientRect();
      return {
        frameInViewport: fr.left >= 0 && fr.right <= window.innerWidth,
        tilesInsideFrame: r0.left >= fr.left - 0.5 && r21.right <= fr.right + 0.5,
      };
    });

    expect(geometry).not.toBeNull();
    expect(geometry?.frameInViewport).toBe(true);
    expect(geometry?.tilesInsideFrame).toBe(true);
  });
});

test.describe("Mobile — Long names stay inside the viewport", () => {
  const LONG_NAME = "An Extremely Long Page Name That Someone Might Actually Type On Their Phone 2026 Edition";

  test("schedule form select and day chips fit with long page names", async ({ page }) => {
    await createPage(LONG_NAME);

    await page.goto("/schedule");
    await page.getByRole("button", { name: /add schedule/i }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 10_000 });

    // The select popup sizes to the widest item; long page names used to
    // blow the panel past the viewport (position is clamped, width is
    // not — ui/select.tsx caps it).
    await dialog.getByRole("combobox").first().click();
    const panel = page.getByRole("listbox");
    await expect(panel).toBeVisible({ timeout: 5_000 });
    const panelBox = await panel.boundingBox();
    expect(panelBox).not.toBeNull();
    if (panelBox) {
      expect(panelBox.x).toBeGreaterThanOrEqual(0);
      expect(panelBox.x + panelBox.width).toBeLessThanOrEqual(MOBILE_VIEWPORT.width);
    }
    await page.keyboard.press("Escape");

    // Day-pattern chip rows (All Days / Weekdays / Weekends) must wrap
    // rather than clip their trailing chips at phone width.
    const chipRows = await page.evaluate((vw) => {
      const rows = document.querySelectorAll('[role="dialog"] [data-testid="day-pattern-chips"]');
      return {
        count: rows.length,
        overflowing: [...rows].filter((el) => el.getBoundingClientRect().right > vw + 2).length,
      };
    }, MOBILE_VIEWPORT.width);
    expect(chipRows.count).toBeGreaterThan(0); // guard against a vacuous pass
    expect(chipRows.overflowing).toBe(0);
  });

  test("collections card truncates long collection and page names", async ({ page }) => {
    const pageId = await createPage(LONG_NAME);
    await createCollection("A Collection With An Unreasonably Long Name For Mobile Testing Purposes", [pageId], 60);

    try {
      await page.goto("/collections");
      await expect(page.getByText(/unreasonably long name/i).first()).toBeVisible({ timeout: 10_000 });

      // No left-bound condition: an element pushed ENTIRELY past the right
      // edge (r.left >= viewport) is just as broken as a partly-clipped one.
      const overflowing = await page.evaluate((vw) => {
        return [...document.querySelectorAll("main *")].filter((el) => {
          const r = el.getBoundingClientRect();
          return r.width > 0 && r.height > 0 && r.right > vw + 2;
        }).length;
      }, MOBILE_VIEWPORT.width);
      expect(overflowing).toBe(0);
    } finally {
      await deleteAllCollections().catch(() => {});
    }
  });

  test("schedule calendar zoom control stays on screen", async ({ page }) => {
    await page.goto("/schedule");
    await page.getByRole("button", { name: /calendar/i }).click();

    const zoomControls = page.locator(".ml-auto.flex.items-center").first();
    await expect(zoomControls).toBeVisible({ timeout: 10_000 });

    const box = await zoomControls.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(MOBILE_VIEWPORT.width);
    }
  });
});

test.describe("Mobile — Editor toolbar dropdowns", () => {
  test("colors picker stays inside the viewport at phone width", async ({ page }) => {
    await page.goto("/pages/new?device=flagship");

    // The editor persists rich/plain mode per browser — make sure we're in Rich
    const richTab = page.getByRole("button", { name: /rich/i }).first();
    await expect(richTab).toBeVisible({ timeout: 15_000 });
    await richTab.click();

    const colorsButton = page.getByRole("button", { name: "Colors" });
    await expect(colorsButton).toBeVisible({ timeout: 10_000 });
    await colorsButton.click();

    const panel = page.getByTestId("toolbar-dropdown-panel");
    await expect(panel).toBeVisible({ timeout: 5_000 });

    const box = await panel.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(MOBILE_VIEWPORT.width);
    }
  });
});
