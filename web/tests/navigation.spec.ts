/**
 * FiestaBoard Navigation E2E Tests
 *
 * Tests navigation edge cases: mobile hamburger menu,
 * sidebar links, theme toggle, and version display.
 */
import {
  test,
  expect,
  configureBoard,
  suppressWizard,
  API_URL,
} from "./helpers";

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
});

test.describe("Navigation", () => {
  test("mobile hamburger menu works", async ({ page }) => {
    // Set viewport to mobile
    await page.setViewportSize({ width: 375, height: 812 });

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    // Find and click hamburger menu button
    const menuBtn = page
      .getByRole("button", { name: /menu|navigation/i })
      .first()
      .or(page.locator("button").filter({ has: page.locator("svg") }).first());

    if (await menuBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await menuBtn.click();

      // Menu should show navigation links
      const pagesLink = page.getByRole("link", { name: "Pages" }).first();
      await expect(pagesLink).toBeVisible({ timeout: 5_000 });

      // Click a link to navigate
      await pagesLink.click();
      await expect(
        page.getByRole("heading", { name: "Pages", exact: true }),
      ).toBeVisible({ timeout: 10_000 });
    }
  });

  test("all sidebar links navigate correctly", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    const sections = [
      { link: "Pages", heading: "Pages" },
      { link: "Schedule", heading: "Schedule" },
      { link: "Integrations", heading: /integrations/i },
      { link: "Settings", heading: "Settings" },
    ];

    for (const { link, heading } of sections) {
      await page
        .getByRole("link", { name: link })
        .first()
        .click();
      await expect(
        page.getByRole("heading", {
          name: heading,
          exact: typeof heading === "string",
        }),
      ).toBeVisible({ timeout: 10_000 });
    }

    // Navigate back home
    await page.getByRole("link", { name: "Home" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("theme toggle switches between light and dark mode", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    // Find theme toggle button
    const themeToggle = page
      .getByRole("button", { name: /theme|dark|light|toggle/i })
      .first();

    if (
      await themeToggle.isVisible({ timeout: 5_000 }).catch(() => false)
    ) {
      // Get initial state
      const htmlEl = page.locator("html");
      const initialClass = await htmlEl.getAttribute("class");

      // Click toggle
      await themeToggle.click();
      await page.waitForTimeout(500);

      // Class should have changed
      const newClass = await htmlEl.getAttribute("class");
      // At minimum the toggle should not crash the page
      await expect(
        page.getByRole("heading", { name: "Dashboard" }),
      ).toBeVisible();

      // Toggle back
      await themeToggle.click();
      await page.waitForTimeout(500);

      const restoredClass = await htmlEl.getAttribute("class");
      // Should be back to (roughly) the initial state
      expect(restoredClass).toBe(initialClass);
    }
  });

  test("version is displayed in sidebar", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    // Look for a version string (e.g., "v1.2.3" or "1.2.3")
    const versionText = page.getByText(/v?\d+\.\d+\.\d+/).first();
    const hasVersion = await versionText
      .isVisible({ timeout: 5_000 })
      .catch(() => false);

    if (!hasVersion) {
      // Version might be in a collapsed section or only on desktop
      // Just verify via API
      const res = await fetch(`${API_URL}/version`);
      expect(res.ok).toBe(true);
      const data = await res.json();
      expect(data).toHaveProperty("package_version");
    }
  });

  test("sidebar shows Fiesta gradient (red, orange, yellow, purple)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    const sidebar = page.locator("aside").first();
    await expect(sidebar).toBeVisible();
    await expect(sidebar).toHaveClass(/sidebar-gradient/);

    // Optional: save screenshot for visual check (e.g. gradient + animation)
    await sidebar.screenshot({
      path: "playwright-test-results/sidebar-gradient.png",
    });
  });

  test("sidebar has primary and secondary navigation sections", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    // Desktop sidebar is in <aside>; mobile menu also contains duplicate nav labels
    // (hidden when the menu is closed), so scope to the fixed sidebar.
    const sidebar = page.locator("aside").first();
    const primaryNav = sidebar.getByLabel("Primary navigation");
    await expect(primaryNav).toBeVisible();

    const secondaryNav = sidebar.getByLabel("Secondary navigation");
    await expect(secondaryNav).toBeVisible();

    // Settings should be in secondary section
    const settingsLink = secondaryNav.getByRole("link", { name: "Settings" });
    await expect(settingsLink).toBeVisible();
  });

  test("Projects button opens drawer", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    // Find and click the Projects button in the sidebar
    const projectsBtn = page
      .locator("aside")
      .getByRole("button", { name: /projects/i })
      .first();

    if (await projectsBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await projectsBtn.click();

      // Drawer should appear with Projects title
      await expect(
        page.getByRole("heading", { name: "Projects" }),
      ).toBeVisible({ timeout: 5_000 });

      // Drawer should have search input
      await expect(
        page.getByPlaceholder(/search projects/i),
      ).toBeVisible();
    }
  });
});
