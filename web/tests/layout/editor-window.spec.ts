import { mkdir } from "node:fs/promises";
import path from "node:path";

import { expect, type Page, test } from "@playwright/test";

import { mockHub } from "./creator-ide-hub";

// BB-E-3, BB-E-4: the desktop editor gets the window (Figma 53:137378,
// 184:159319). Owner decision D1: the editor collapses the nav to the icon
// rail and gives the reader's own choice back on leaving; an explicit toggle
// in the editor becomes the new choice. D2: the Explorer is collapsible, open
// by default for multi-board and big-board pages, closed for a Flagship or
// Note, remembered per board kind.

const SIDEBAR_KEY = "fiestaboard_sidebar_collapsed";

async function openApp(page: Page, width: number, options: { path?: string; theme?: "light" | "dark" } = {}) {
  await page.setViewportSize({ width, height: width >= 1440 ? 900 : width >= 1280 ? 800 : 768 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const query = new URLSearchParams({
    theme: options.theme ?? "light",
    path: options.path ?? "/pages/edit/kitchen-morning",
  });
  await page.goto(`/tests/layout/editor-window.html?${query}`);
}

const expandRail = (page: Page) => page.getByRole("button", { name: "Expand sidebar" });
const collapseRail = (page: Page) => page.getByRole("button", { name: "Collapse sidebar" });
const pageName = (page: Page) => page.getByRole("textbox", { name: /page name/i });
// The name's room in the header (BB-E-4): the field itself hugs the name (UX-1-5).
const nameRoom = (page: Page) => page.locator('[data-slot="page-editor-name"]');
const explorer = (page: Page) => page.getByRole("navigation", { name: "Explorer" });
const storedCollapsed = (page: Page) => page.evaluate((key) => localStorage.getItem(key), SIDEBAR_KEY);

for (const width of [1440, 1280, 1024]) {
  for (const theme of ["light", "dark"] as const) {
    test(`${width}px ${theme}: the editor has the window; the name and the whole board fit (BB-E-3, -4)`, async ({
      page,
    }, testInfo) => {
      page.on("pageerror", (error) => console.error("editor-window page error:", error.message));
      await mockHub(page);
      await openApp(page, width, { theme });
      await expect(pageName(page)).toHaveValue("Kitchen morning");
      await expect(page.locator('[data-slot="creator-ide"]')).toBeVisible();

      // D1: the nav is the icon rail in the editor, and the reader's stored
      // choice (expanded: nothing stored) is not overwritten.
      await expect(expandRail(page)).toBeVisible();
      expect(await storedCollapsed(page)).toBeNull();
      const rail = await page.locator("aside[data-rail-breakpoint]").boundingBox();
      expect(rail!.x + rail!.width).toBeLessThanOrEqual(96);

      // D2: a Flagship page opens with the Explorer closed, and says how to open it.
      await expect(explorer(page)).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Explorer", exact: true, pressed: false })).toBeVisible();

      // BB-E-4: the name gets at least 240 px and every header action stays on screen.
      const name = await nameRoom(page).boundingBox();
      expect(name!.width).toBeGreaterThanOrEqual(240);
      const publish = await page.getByRole("button", { name: "Save & update board" }).boundingBox();
      expect(publish!.x + publish!.width).toBeLessThanOrEqual(width);

      // BB-E-3: the preview pane gets a real share of the window (it was 373 /
      // 293 / 165 px with the 256 px nav and the Explorer open), and at Fit
      // the whole 22-column board shows. (Actual size crops by design; #2573.)
      const preview = await page.locator('[data-slot="editor-preview"]').boundingBox();
      console.log(
        `editor-window ${width}: name ${Math.round(name!.width)} px, preview ${Math.round(preview!.width)} px`,
      );
      // 1024–1279 has no Figma frame (D8, settled with the E4 grid): there the
      // floor is 22 tiles at 16 px or more.
      expect(preview!.width).toBeGreaterThanOrEqual(width >= 1280 ? width * 0.4 : 360);
      // The preview offers Fit / Actual only when the board doesn't already fit (#2579).
      const fit = page.locator('[data-slot="board-preview-mode-option"]', { hasText: /^Fit$/ });
      if (await fit.count()) await fit.click();
      await expect(
        page.locator('[data-slot="board-viewport-scaled"], [data-slot="board-viewport"]').first(),
      ).toBeVisible();
      for (const text of await page.locator('[data-slot="board-viewport-indicator-text"]').allTextContents()) {
        expect(text).not.toMatch(/Columns \d+–\d+ of 22/);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

      const shots = process.env.EDITOR_WINDOW_SHOTS || testInfo.outputPath("editor-window-shots");
      await mkdir(shots, { recursive: true });
      await page.evaluate(() => document.fonts.ready);
      await page.screenshot({ path: path.join(shots, `editor-${width}-${theme}.png`) });

      // With the Explorer opened, the name keeps its 240 px and the actions stay on screen.
      await page.getByRole("button", { name: "Explorer", exact: true, pressed: false }).click();
      await expect(explorer(page)).toBeVisible();
      expect((await nameRoom(page).boundingBox())!.width).toBeGreaterThanOrEqual(240);
      const publishWithExplorer = await page.getByRole("button", { name: "Save & update board" }).boundingBox();
      expect(publishWithExplorer!.x + publishWithExplorer!.width).toBeLessThanOrEqual(width);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: path.join(shots, `editor-${width}-${theme}-explorer.png`) });
    });
  }
}

/** The header row's content fits its box: nothing clipped or pushed past the card. */
async function expectHeaderFits(page: Page) {
  const header = page.locator('[data-slot="card-header"]').first();
  const row = header.locator("> div").first();
  const [rowBox, headerBox] = [(await row.boundingBox())!, (await header.boundingBox())!];
  const overflow = await row.evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(overflow, "header row content wider than the row").toBeLessThanOrEqual(0);
  expect(rowBox.x + rowBox.width).toBeLessThanOrEqual(headerBox.x + headerBox.width + 0.5);
  for (const button of await header.getByRole("button").all()) {
    const b = (await button.boundingBox())!;
    expect(b.x + b.width, `${await button.getAttribute("aria-label")} past the header`).toBeLessThanOrEqual(
      headerBox.x + headerBox.width + 0.5,
    );
  }
}

for (const width of [1440, 1280, 1024]) {
  for (const notScheduled of [false, true]) {
    test(`${width}px, ${notScheduled ? "not live (Save / Show now)" : "live (Save draft / Update)"}: the header fits, Explorer closed and open (BB-E-4)`, async ({
      page,
    }) => {
      await mockHub(page, { notScheduled });
      await openApp(page, width);
      await expect(pageName(page)).toHaveValue("Kitchen morning");
      await expect(
        page.getByRole("button", { name: notScheduled ? /show now/i : "Save & update board" }),
      ).toBeVisible();
      await expectHeaderFits(page);
      expect((await nameRoom(page).boundingBox())!.width).toBeGreaterThanOrEqual(240);
      await page.getByRole("button", { name: "Explorer", exact: true, pressed: false }).click();
      await expect(explorer(page)).toBeVisible();
      await expectHeaderFits(page);
      expect((await nameRoom(page).boundingBox())!.width).toBeGreaterThanOrEqual(240);
    });
  }
}

test.describe("D1: the nav rail in the editor", () => {
  test("collapses on entering the editor and restores an expanded nav on leaving", async ({ page }) => {
    await mockHub(page);
    await openApp(page, 1440, { path: "/pages" });
    await expect(collapseRail(page)).toBeVisible();
    await page.getByRole("link", { name: "Open Kitchen morning" }).click();
    await expect(pageName(page)).toHaveValue("Kitchen morning");
    await expect(expandRail(page)).toBeVisible();
    expect(await storedCollapsed(page)).toBeNull();
    await page.getByRole("button", { name: "Back to Pages" }).click();
    await expect(page.getByRole("link", { name: "Open Kitchen morning" })).toBeVisible();
    await expect(collapseRail(page)).toBeVisible();
  });

  test("an explicit toggle in the editor becomes the global choice", async ({ page }) => {
    await mockHub(page);
    await openApp(page, 1440, { path: "/pages" });
    await page.getByRole("link", { name: "Open Kitchen morning" }).click();
    await expect(expandRail(page)).toBeVisible();
    // Expand, then collapse again: the app stays collapsed everywhere afterwards.
    await expandRail(page).click();
    await expect(collapseRail(page)).toBeVisible();
    expect(await storedCollapsed(page)).toBe("false");
    await collapseRail(page).click();
    await expect(expandRail(page)).toBeVisible();
    expect(await storedCollapsed(page)).toBe("true");
    await page.getByRole("button", { name: "Back to Pages" }).click();
    await expect(page.getByRole("link", { name: "Open Kitchen morning" })).toBeVisible();
    await expect(expandRail(page)).toBeVisible();
  });

  test("expanding in the editor keeps the nav expanded on leaving, and the next visit collapses it again", async ({
    page,
  }) => {
    await mockHub(page);
    await openApp(page, 1440, { path: "/pages" });
    await page.getByRole("link", { name: "Open Kitchen morning" }).click();
    await expandRail(page).click();
    await page.getByRole("button", { name: "Back to Pages" }).click();
    await expect(collapseRail(page)).toBeVisible();
    await page.getByRole("link", { name: "Open Kitchen morning" }).click();
    await expect(expandRail(page)).toBeVisible();
    expect(await storedCollapsed(page)).toBe("false");
  });
});

test.describe("D2: the Explorer", () => {
  test("a Flagship page opens it closed; the reader's toggle is remembered for Flagship pages", async ({ page }) => {
    await mockHub(page);
    await openApp(page, 1440);
    await expect(explorer(page)).toHaveCount(0);
    const before = await nameRoom(page).boundingBox();
    await page.getByRole("button", { name: "Explorer", exact: true, pressed: false }).click();
    await expect(explorer(page)).toBeVisible();
    // Opening it never squeezes the name under 240 px.
    expect((await nameRoom(page).boundingBox())!.width).toBeGreaterThanOrEqual(Math.min(240, before!.width));
    await page.reload();
    await expect(pageName(page)).toHaveValue("Kitchen morning");
    await expect(explorer(page)).toBeVisible();
    await page.getByRole("button", { name: "Explorer", exact: true, pressed: true }).click();
    await expect(explorer(page)).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Explorer", exact: true, pressed: false })).toBeFocused();
  });

  test("a big-board (FiestaPanel) page opens it; closing it there leaves Flagship pages alone", async ({ page }) => {
    await mockHub(page, { deviceType: "panel" });
    await openApp(page, 1440);
    await expect(pageName(page)).toHaveValue("Kitchen morning");
    await expect(explorer(page)).toBeVisible();
    await page.getByRole("button", { name: "Explorer", exact: true, pressed: true }).click();
    await expect(explorer(page)).toHaveCount(0);
    await page.reload();
    await expect(pageName(page)).toHaveValue("Kitchen morning");
    await expect(explorer(page)).toHaveCount(0);
    expect(
      await page.evaluate(() => [
        localStorage.getItem("fiestaboard_ide_explorer:panel"),
        localStorage.getItem("fiestaboard_ide_explorer:flagship"),
      ]),
    ).toEqual(["closed", null]);
  });
});
