/**
 * FiestaBoard Navigation E2E Tests
 *
 * Tests navigation edge cases: mobile hamburger menu,
 * sidebar links, theme toggle, and version display.
 */
import { API_URL, configureBoard, expect, suppressWizard, test } from "./helpers";

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
});

test.describe("Navigation", () => {
  test("mobile hamburger menu works", async ({ page }) => {
    // Set viewport to mobile
    await page.setViewportSize({ width: 375, height: 812 });

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

    // Find and click hamburger menu button
    const menuBtn = page
      .getByRole("button", { name: /menu|navigation/i })
      .first()
      .or(
        page
          .locator("button")
          .filter({ has: page.locator("svg") })
          .first(),
      );

    if (await menuBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await menuBtn.click();

      // Menu should show navigation links
      const pagesLink = page.getByRole("link", { name: "Pages" }).first();
      await expect(pagesLink).toBeVisible({ timeout: 5_000 });

      // Click a link to navigate
      await pagesLink.click();
      await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 10_000 });
    }
  });

  test("all sidebar links navigate correctly", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

    // Settings is not in this list any more — it left the rail for the
    // footer menu, and "reach it from the menu" is its own test below.
    const sections = [
      { link: "Pages", heading: "Pages" },
      { link: "Schedule", heading: "Schedule" },
      { link: "Integrations", heading: /integrations/i },
    ];

    for (const { link, heading } of sections) {
      await page.getByRole("link", { name: link }).first().click();
      await expect(
        page.getByRole("heading", {
          name: heading,
          exact: typeof heading === "string",
        }),
      ).toBeVisible({ timeout: 10_000 });
    }

    // Navigate back home
    await page.getByRole("link", { name: "Home" }).first().click();
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 10_000 });
  });

  test("Settings is reachable from the footer menu", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

    await page.locator('aside [data-slot="sidebar-settings-trigger"]').click();
    await page.getByRole("menuitem", { name: "Settings" }).click();

    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 10_000 });
  });

  test("theme switches between light and dark from the footer menu", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

    const htmlEl = page.locator("html");

    // One open, three choices. A radio group does not close its menu on
    // pick — that is the point of it, and re-clicking the trigger between
    // choices would close the menu rather than reopen it, then race the
    // exit animation. Each assertion names the state it expects rather
    // than "whatever the other one was", which a two-state toggle could
    // only ever do.
    await page.locator('aside [data-slot="sidebar-settings-trigger"]').click();

    await page.getByRole("menuitemradio", { name: "Dark" }).click();
    await expect(htmlEl).toHaveClass(/\bdark\b/);

    await page.getByRole("menuitemradio", { name: "Light" }).click();
    await expect(htmlEl).not.toHaveClass(/\bdark\b/);

    // System is what a fresh install runs on, and what the toggle this
    // replaces had no way to express.
    await page.getByRole("menuitemradio", { name: "System" }).click();
    await expect(page.getByRole("menuitemradio", { name: "System" })).toHaveAttribute("aria-checked", "true");
  });

  test("the About box reports the version the API reports", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

    const res = await fetch(`${API_URL}/version`);
    expect(res.ok).toBe(true);
    const { running_version: runningVersion } = await res.json();

    await page.locator('aside [data-slot="sidebar-settings-trigger"]').click();
    await page.getByRole("menuitem", { name: /About FiestaBoard/ }).click();

    const about = page.getByRole("dialog");
    await expect(about).toBeVisible();
    // The number on screen is the number the server is running, not a
    // build-time constant baked into the bundle.
    await expect(about.getByText(runningVersion, { exact: false }).first()).toBeVisible();
    await expect(about.getByText("MIT License")).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(about).not.toBeVisible();
  });

  test("sidebar shows Fiesta gradient (red, orange, yellow, purple)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

    const sidebar = page.locator("aside").first();
    await expect(sidebar).toBeVisible();
    await expect(sidebar).toHaveClass(/sidebar-gradient/);

    // Optional: save screenshot for visual check (e.g. gradient + animation)
    await sidebar.screenshot({
      path: "playwright-test-results/sidebar-gradient.png",
    });
  });

  test("sidebar renders one flat navigation list", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

    // Desktop sidebar is in <aside>; mobile menu also contains duplicate nav labels
    // (hidden when the menu is closed), so scope to the fixed sidebar.
    const sidebar = page.locator("aside").first();
    const nav = sidebar.getByLabel("Primary navigation");
    await expect(nav).toBeVisible();

    // @fiestaboard/ui v5.12 merged the rail's two lists into one, so there is
    // no "Secondary navigation" landmark left to find.
    await expect(sidebar.getByLabel("Secondary navigation")).toHaveCount(0);

    // The list is destinations only: Settings and the assistant both left it
    // in @fiestaboard/ui 7.0.0, which is what stopped the rail highlighting
    // two rows at once whenever the AI drawer was open.
    await expect(nav.getByRole("link", { name: "Settings" })).toHaveCount(0);
    await expect(nav.getByRole("button", { name: "AI Assistant" })).toHaveCount(0);
    await expect(sidebar.locator('[data-slot="sidebar-settings-trigger"]')).toBeVisible();
  });

  test("Collections is a direct link in primary navigation", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

    const sidebar = page.locator("aside").first();
    const primaryNav = sidebar.getByLabel("Primary navigation");
    const collectionsLink = primaryNav.getByRole("link", { name: /collections/i });
    await expect(collectionsLink).toBeVisible();
    await expect(collectionsLink).toHaveAttribute("href", "/collections");
  });
});
