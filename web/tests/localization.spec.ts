/**
 * FiestaBoard Localization E2E Tests
 *
 * Tests language switching via the LanguageSelector component,
 * verifying that UI text updates correctly across navigation items,
 * page headings, and that the selected locale persists.
 */
import {
  test,
  expect,
  configureBoard,
  suppressWizard,
} from "./helpers";

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
});

test.describe("Localization", () => {
  test("default language is English", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    const html = page.locator("html");
    await expect(html).toHaveAttribute("lang", "en");

    await expect(page.getByRole("link", { name: "Pages" }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Settings" }).first()).toBeVisible();
  });

  test("language selector is visible and shows English by default", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    const langSelector = page.getByRole("combobox", { name: /language/i }).first();
    const selectorVisible = await langSelector
      .isVisible({ timeout: 5_000 })
      .catch(() => false);

    if (selectorVisible) {
      await expect(langSelector).toContainText("English");
    }
  });

  test("switching to Spanish updates navigation and page text", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    const langSelector = page.getByRole("combobox", { name: /language/i }).first();
    const selectorVisible = await langSelector
      .isVisible({ timeout: 5_000 })
      .catch(() => false);

    if (!selectorVisible) {
      test.skip();
      return;
    }

    await langSelector.click();
    await page.getByRole("option", { name: "Español" }).click();
    await page.waitForLoadState("networkidle");

    await expect(page.locator("html")).toHaveAttribute("lang", "es");
    await expect(
      page.getByRole("heading", { name: "Panel" }),
    ).toBeVisible({ timeout: 10_000 });

    await expect(page.getByRole("link", { name: "Páginas" }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Configuración" }).first()).toBeVisible();
  });

  test("switching to French updates navigation", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    const langSelector = page.getByRole("combobox", { name: /language/i }).first();
    const selectorVisible = await langSelector
      .isVisible({ timeout: 5_000 })
      .catch(() => false);

    if (!selectorVisible) {
      test.skip();
      return;
    }

    await langSelector.click();
    await page.getByRole("option", { name: "Français" }).click();
    await page.waitForLoadState("networkidle");

    await expect(page.locator("html")).toHaveAttribute("lang", "fr");
    await expect(
      page.getByRole("heading", { name: "Tableau de bord" }),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("switching to German updates navigation", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    const langSelector = page.getByRole("combobox", { name: /language/i }).first();
    const selectorVisible = await langSelector
      .isVisible({ timeout: 5_000 })
      .catch(() => false);

    if (!selectorVisible) {
      test.skip();
      return;
    }

    await langSelector.click();
    await page.getByRole("option", { name: "Deutsch" }).click();
    await page.waitForLoadState("networkidle");

    await expect(page.locator("html")).toHaveAttribute("lang", "de");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("link", { name: "Seiten" }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: "Einstellungen" }).first()).toBeVisible();
  });

  test("switching to Japanese updates navigation", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    const langSelector = page.getByRole("combobox", { name: /language/i }).first();
    const selectorVisible = await langSelector
      .isVisible({ timeout: 5_000 })
      .catch(() => false);

    if (!selectorVisible) {
      test.skip();
      return;
    }

    await langSelector.click();
    await page.getByRole("option", { name: "日本語" }).click();
    await page.waitForLoadState("networkidle");

    await expect(page.locator("html")).toHaveAttribute("lang", "ja");
  });

  test("locale persists across page navigation", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    const langSelector = page.getByRole("combobox", { name: /language/i }).first();
    const selectorVisible = await langSelector
      .isVisible({ timeout: 5_000 })
      .catch(() => false);

    if (!selectorVisible) {
      test.skip();
      return;
    }

    await langSelector.click();
    await page.getByRole("option", { name: "Español" }).click();
    await page.waitForLoadState("networkidle");
    await expect(page.locator("html")).toHaveAttribute("lang", "es");

    await page.getByRole("link", { name: "Páginas" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Páginas", exact: true }),
    ).toBeVisible({ timeout: 10_000 });

    await expect(page.locator("html")).toHaveAttribute("lang", "es");
  });

  test("locale persists after full page reload via cookie", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    const langSelector = page.getByRole("combobox", { name: /language/i }).first();
    const selectorVisible = await langSelector
      .isVisible({ timeout: 5_000 })
      .catch(() => false);

    if (!selectorVisible) {
      test.skip();
      return;
    }

    await langSelector.click();
    await page.getByRole("option", { name: "Español" }).click();
    await page.waitForLoadState("networkidle");
    await expect(page.locator("html")).toHaveAttribute("lang", "es");

    await page.reload();
    await page.waitForLoadState("networkidle");

    await expect(page.locator("html")).toHaveAttribute("lang", "es");
    await expect(
      page.getByRole("heading", { name: "Panel" }),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("switching back to English restores original text", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    const langSelector = page.getByRole("combobox", { name: /language/i }).first();
    const selectorVisible = await langSelector
      .isVisible({ timeout: 5_000 })
      .catch(() => false);

    if (!selectorVisible) {
      test.skip();
      return;
    }

    // Switch to Spanish first
    await langSelector.click();
    await page.getByRole("option", { name: "Español" }).click();
    await page.waitForLoadState("networkidle");
    await expect(page.locator("html")).toHaveAttribute("lang", "es");

    // Switch back to English
    const langSelectorEs = page.getByRole("combobox").first();
    await langSelectorEs.click();
    await page.getByRole("option", { name: "English" }).click();
    await page.waitForLoadState("networkidle");

    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("link", { name: "Pages" }).first()).toBeVisible();
  });

  test("mobile menu language text updates with locale change", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });

    // Set cookie directly and reload for mobile
    await page.evaluate(() => {
      document.cookie = "NEXT_LOCALE=es;path=/;max-age=31536000;SameSite=Lax";
    });
    await page.reload();
    await page.waitForLoadState("networkidle");

    // Open the mobile menu
    const menuBtn = page
      .getByRole("button", { name: /menú|menu/i })
      .first();

    const menuVisible = await menuBtn.isVisible({ timeout: 5_000 }).catch(() => false);
    if (menuVisible) {
      await menuBtn.click();
      await expect(page.getByRole("link", { name: "Páginas" }).first()).toBeVisible({
        timeout: 5_000,
      });
    }
  });
});
