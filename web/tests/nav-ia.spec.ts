/**
 * Slice 2.1 — information architecture and nav (WEB-01/02/14).
 *
 *   Home · Pages (▸ Collections) · Schedule · Displays │ Integrations ·
 *   Staff Picks · Settings · Help & Docs
 *
 * Below 768px a bottom tab bar (Home · Pages · Schedule · Displays · More),
 * from 768px the rail; More holds the rest plus the Settings › Hub group
 * (07a `308:36070`), and Settings is a list-detail (07e §1).
 */
import type { Page } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

import { API_URL, configureBoard, expect, suppressWizard, test } from "./helpers";

const PHONE = { width: 390, height: 844 };
const TABLET = { width: 900, height: 984 };
const DESKTOP = { width: 1280, height: 800 };

const tabBar = (page: Page) => page.locator('[data-slot="sidebar-bottom-nav"]');
const rail = (page: Page) => page.getByRole("complementary", { name: "Main navigation" });

async function seriousA11y(page: Page) {
  await injectAxe(page);
  const violations = await getViolations(page, undefined, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
    rules: { "color-contrast": { enabled: false } },
  });
  return violations.filter((v) => v.impact === "critical" || v.impact === "serious");
}

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
});

test.describe("Phone (390): bottom nav and More", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(PHONE);
  });

  test("the tab bar is Home · Pages · Schedule · Displays · More, and the rail is hidden", async ({ page }) => {
    await page.goto("/");
    await expect(tabBar(page)).toBeVisible({ timeout: 15_000 });
    await expect(tabBar(page).locator("a, button")).toHaveText(["Home", "Pages", "Schedule", "Displays", /^More/]);
    await expect(rail(page)).toBeHidden();
  });

  test("a tab navigates and lights", async ({ page }) => {
    await page.goto("/");
    await tabBar(page).getByRole("link", { name: "Schedule" }).click();
    await expect(page).toHaveURL(/\/schedule$/);
    await expect(tabBar(page).getByRole("link", { name: "Schedule" })).toHaveAttribute("aria-current", "page");
  });

  test("the Pages tab stays lit inside Collections", async ({ page }) => {
    await page.goto("/collections");
    await expect(tabBar(page).getByRole("link", { name: "Pages" })).toHaveAttribute("aria-current", "page", {
      timeout: 15_000,
    });
  });

  test("More lists the rest of the IA, FiestaBot's row when set up, and the Settings › Hub group", async ({ page }) => {
    await page.goto("/");
    await tabBar(page).getByRole("button", { name: /^More/ }).click();
    const more = page.getByRole("dialog", { name: "Navigation menu" });
    await expect(more).toBeVisible();
    await expect(more.getByRole("navigation", { name: "More" }).getByRole("link")).toHaveText([
      "Integrations",
      "Staff Picks",
      "Settings",
      "Help & Docs",
    ]);
    const hub = more.getByRole("list", { name: /^Hub · / });
    await expect(hub.getByRole("link")).toHaveText(["Network", "AI provider", "System & backups", "Language & time"]);
    await expect(more.locator('[data-slot="hub-line"]')).toContainText(/Online · FiestaBoard /);
    expect(await seriousA11y(page)).toEqual([]);
  });

  test("a Hub group row opens its Settings section and closes More", async ({ page }) => {
    await page.goto("/");
    await tabBar(page).getByRole("button", { name: /^More/ }).click();
    await page.getByRole("dialog", { name: "Navigation menu" }).getByRole("link", { name: "Language & time" }).click();
    await expect(page).toHaveURL(/\/settings\/language-time$/);
    await expect(page.getByRole("heading", { level: 1, name: "Language & time" })).toBeVisible();
    await expect(page.getByRole("dialog", { name: "Navigation menu" })).toHaveCount(0);
  });

  test("Settings is a list, and a section is its own screen with a way back", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("list", { name: "You" })).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-slot="settings-detail"]')).toHaveCount(0);
    await page.getByRole("link", { name: "System & backups" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "System & backups" })).toBeVisible();
    await page.getByRole("link", { name: "Settings", exact: true }).first().click();
    await expect(page).toHaveURL(/\/settings$/);
    expect(await seriousA11y(page)).toEqual([]);
  });

  test("the page clears the tab bar: the last content can scroll above it", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("list", { name: "You" })).toBeVisible({ timeout: 15_000 });
    const offset = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue("--bottom-nav-offset").trim(),
    );
    expect(offset).toBe("88px");
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    const lastRow = page.getByRole("link", { name: "Language & time" });
    const rowBox = (await lastRow.boundingBox())!;
    const barBox = (await tabBar(page).boundingBox())!;
    expect(rowBox.y + rowBox.height).toBeLessThanOrEqual(barBox.y);
  });
});

test.describe("Wide phone (700): one full-width Settings pane", () => {
  for (const section of ["", "/network"]) {
    test(`uses the available width at /settings${section}`, async ({ page }) => {
      await page.setViewportSize({ width: 700, height: 900 });
      await page.goto(`/settings${section}`);
      const pane = page.locator(section ? '[data-slot="settings-detail"]' : '[data-slot="settings-index"]');
      await expect(pane).toBeVisible();
      await expect.poll(async () => (await pane.boundingBox())?.width ?? 0).toBeGreaterThan(600);
    });
  }
});

test.describe("Tablet (900): the rail from 768px", () => {
  test("shows the rail and no tab bar", async ({ page }) => {
    await page.setViewportSize(TABLET);
    await page.goto("/");
    await expect(rail(page)).toBeVisible({ timeout: 15_000 });
    await expect(tabBar(page)).toBeHidden();
    // 07 `61:17544`: the rail starts collapsed in the tablet band.
    await expect(page.getByLabel("Expand sidebar")).toBeVisible();
    await expect.poll(async () => (await rail(page).boundingBox())?.width ?? 0).toBeLessThan(80);
  });

  test("tablet toggles keep and restore the desktop preference", async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem("fiestaboard_sidebar_collapsed", "true"));
    await page.setViewportSize(TABLET);
    await page.goto("/settings/network");
    await page.getByLabel("Expand sidebar").click();
    await expect(page.getByLabel("Collapse sidebar")).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem("fiestaboard_sidebar_collapsed"))).toBe("true");
    await page.setViewportSize(DESKTOP);
    await expect(page.getByLabel("Expand sidebar")).toBeVisible();
    await expect.poll(async () => (await rail(page).boundingBox())?.width ?? 0).toBeLessThan(80);
  });

  test("Settings is list and detail side by side", async ({ page }) => {
    await page.setViewportSize(TABLET);
    await page.goto("/settings/network");
    await expect(page.getByRole("heading", { level: 2, name: "Network" })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("list", { name: /^Hub · / }).getByRole("link", { name: "Network" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });
});

test.describe("Desktop (1280): the rail", () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(DESKTOP);
  });

  test("lists Home · Pages · Collections · Schedule · Displays │ Integrations · Staff Picks · Settings · Help & Docs", async ({
    page,
  }) => {
    await page.goto("/");
    const nav = rail(page).getByRole("navigation", { name: "Primary navigation" });
    await expect(nav.getByRole("link")).toHaveText([
      "Home",
      "Pages",
      "Collections",
      "Schedule",
      "Displays",
      "Integrations",
      "Staff Picks",
      "Settings",
      "Help & Docs",
    ]);
  });

  test("the Settings row lights on a section; an old ?section= link lands on its path", async ({ page }) => {
    await page.goto("/settings?section=ai");
    await expect(page).toHaveURL(/\/settings\/ai-provider$/);
    await expect(
      rail(page).getByRole("navigation", { name: "Primary navigation" }).getByRole("link", { name: "Settings" }),
    ).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { level: 2, name: "AI provider" })).toBeVisible();
    expect(await seriousA11y(page)).toEqual([]);
  });
});

test.describe("1100 with FiestaBot open: Settings fits the room that is left", () => {
  // A provider is all the rail needs to offer FiestaBot; nothing here talks to it.
  test.beforeEach(async ({ request }) => {
    const res = await request.put(`${API_URL}/settings/ai`, {
      data: {
        enabled: true,
        providers: [
          {
            id: "nav-ia",
            name: "Nav IA",
            protocol: "openai",
            base_url: "http://127.0.0.1:9/v1",
            api_key: "test-key",
            models: ["test-model"],
            default_model: "test-model",
            headers: {},
          },
        ],
        default_provider_id: "nav-ia",
      },
    });
    expect(res.ok()).toBe(true);
  });

  test.afterEach(async ({ request }) => {
    await request.put(`${API_URL}/settings/ai`, {
      data: { enabled: false, providers: [], default_provider_id: null },
    });
  });

  test("the list and the open section stack instead of squeezing the section to nothing", async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 900 });
    await page.goto("/settings/network");
    await expect(page.getByRole("heading", { level: 2, name: "Network" })).toBeVisible({ timeout: 15_000 });
    await rail(page).getByRole("button", { name: "AI Assistant" }).click();
    await expect(page.locator("html.ai-drawer-open")).toHaveCount(1);

    const detail = page.locator('[data-slot="settings-detail"]');
    await expect.poll(async () => (await detail.boundingBox())?.width ?? 0).toBeGreaterThan(300);
    const list = (await page.locator('[data-slot="settings-index"]').boundingBox())!;
    const box = (await detail.boundingBox())!;
    // Stacked: the section sits under the list, not beside it.
    expect(box.y).toBeGreaterThanOrEqual(list.y + list.height);
    await page.screenshot({ path: "playwright-test-results/settings-1100-fiestabot.png" });
  });
});
