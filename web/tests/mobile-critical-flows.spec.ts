/**
 * FiestaBoard Mobile Viewport E2E Tests
 *
 * Ensures critical user flows work on small screens (375x812, iPhone-ish).
 * The repo recently fixed mobile UI regressions; this suite catches future ones.
 *
 * Issue: #500 — E2E: add Playwright tests for critical user flows
 */
import {
  test,
  expect,
  configureBoard,
  suppressWizard,
  createPage,
  deleteAllPages,
  API_URL,
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
        if (await link.first().isVisible({ timeout: 3_000 }).catch(() => false)) {
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
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("can navigate to Schedule on mobile", async ({ page }) => {
    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("can navigate to Settings on mobile", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: /settings/i }),
    ).toBeVisible({ timeout: 15_000 });
  });
});

test.describe("Mobile — Dashboard", () => {
  test("dashboard renders correctly on mobile", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // Dashboard heading should be visible
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    // No horizontal overflow (basic check: viewport width matches page width)
    const scrollWidth = await page.evaluate(() => document.body.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(MOBILE_VIEWPORT.width + 20); // allow 20px tolerance
  });

  test("board display is visible on mobile", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    // The board display (6x22 grid or its container) should be present
    const boardDisplay = page
      .locator("[data-testid='board-display'], .board-display, canvas")
      .or(page.getByText(/active page|no page/i))
      .first();

    await expect(boardDisplay).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Mobile — Pages", () => {
  test("pages list is usable on mobile", async ({ page }) => {
    await createPage("Mobile Test Page", ["MOBILE", "", "", "", "", ""]);

    await page.goto("/pages");
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // The page we created should be listed
    await expect(page.getByText("Mobile Test Page")).toBeVisible({
      timeout: 10_000,
    });
  });

  test("create page button is accessible on mobile", async ({ page }) => {
    await page.goto("/pages");
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

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
    await expect(
      page.getByRole("heading", { name: /integrations/i }),
    ).toBeVisible({ timeout: 15_000 });
  });

  test("installed and marketplace tabs are reachable on mobile", async ({ page }) => {
    await page.goto("/integrations");
    await expect(
      page.getByRole("heading", { name: /integrations/i }),
    ).toBeVisible({ timeout: 15_000 });

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
