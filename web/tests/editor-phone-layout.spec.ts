/**
 * Bug bash BB-B-3, BB-B-4, BB-B-5, BB-B-17: the phone editor's vertical space
 * and keyboard layout against Figma 57:64661 ("Typing · Preview docked") and
 * 316:90600 (New Page).
 */
import type { Page } from "@playwright/test";

import { configureBoard, createPage, deletePage, expect, suppressWizard, test } from "./helpers";

const PREVIEW = '[data-slot="editor-preview"]';
const TOOLBAR = '[data-slot="editor-toolbar"][data-size="touch"]';

let pageId: string | undefined;

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
  pageId = await createPage("Kitchen morning with a long name", [
    "GOOD MORNING",
    "72",
    "NICE OUT",
    "N JUDAH 4 MIN",
    "HAVE A GREAT DAY",
    "",
  ]);
});

test.afterEach(async () => {
  if (pageId) await deletePage(pageId);
});

async function openEditor(page: Page) {
  await page.goto(`/pages/edit/${pageId}`);
  await expect(page.locator('[contenteditable="true"]').first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator(PREVIEW)).toBeVisible();
}

const box = async (page: Page, selector: string) => (await page.locator(selector).first().boundingBox())!;

for (const [width, height] of [
  [360, 780],
  [390, 844],
  [412, 915],
] as const) {
  test.describe(`phone editor at ${width}×${height}`, () => {
    test.use({ viewport: { width, height }, hasTouch: true, isMobile: true });

    test("the name is readable and the header is the top of the screen (BB-B-3, BB-B-4)", async ({ page }) => {
      await openEditor(page);
      const name = await box(page, "#page-name");
      // Beside the IDE's Save draft + Update or the builder's Save + Show now.
      expect(name.width).toBeGreaterThanOrEqual(90);
      expect(name.y).toBeLessThan(40);
      // No section card header, breadcrumb or second title above the editor.
      await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toHaveCount(0);
      // The editor toolbar replaces the tab bar (BB-B-17).
      await expect(page.getByRole("navigation")).toHaveCount(0);
      const preview = await box(page, PREVIEW);
      expect(preview.y).toBeLessThan(100);
    });

    test("a new page's name is readable beside Save and Show now (BB-B-3, 316:90600)", async ({ page }) => {
      await page.goto("/pages/new");
      await expect(page.locator('[contenteditable="true"]').first()).toBeVisible({ timeout: 15_000 });
      expect((await box(page, "#page-name")).width).toBeGreaterThanOrEqual(90);
      await page.locator("#page-name").fill("Kitchen morning");
      // Two lines at most: the name is never cut mid-word onto a third.
      expect((await box(page, "#page-name")).height).toBeLessThanOrEqual(44);
    });

    test("the preview stays docked while you type on the last line (BB-B-4)", async ({ page }) => {
      await openEditor(page);
      const editor = page.locator('[contenteditable="true"]').first();
      await editor.click();
      await page.keyboard.press("Control+End");
      await page.keyboard.type("X");
      // Scroll the template up under the docked preview.
      await page.locator('[data-slot="page-editor-scroll"]').evaluate((el) => el.scrollBy(0, 240));
      const preview = await box(page, PREVIEW);
      expect(preview.y).toBeLessThan(100);
      await expect(page.locator(PREVIEW)).toBeInViewport();
    });
  });
}

test.describe("keyboard up (390 × 508)", () => {
  test.use({ viewport: { width: 390, height: 508 }, hasTouch: true, isMobile: true });

  test("the line being typed stays above the toolbar (BB-B-5)", async ({ page }) => {
    await openEditor(page);
    await page.locator('[contenteditable="true"]').first().click();
    await page.keyboard.press("Control+End");
    await page.keyboard.type("TYPING");
    const toolbar = await box(page, TOOLBAR);
    await expect
      .poll(() => page.evaluate(() => getSelection()!.getRangeAt(0).getBoundingClientRect().bottom))
      .toBeLessThanOrEqual(toolbar.y);
  });
});

test.describe("landscape phone (844 × 390)", () => {
  test.use({ viewport: { width: 844, height: 390 }, hasTouch: true, isMobile: true });

  // A short viewport keeps the phone chrome (BB-A-13, #2559), so here too the
  // editor's toolbar replaces the tab bar: no rail or tab bar is drawn under
  // it, and it spans the screen (BB-B-17).
  test("the toolbar replaces the phone nav and spans the screen (BB-B-17, BB-A-13)", async ({ page }) => {
    await openEditor(page);
    await expect(page.locator("aside:visible")).toHaveCount(0);
    await expect(page.locator("nav:visible")).toHaveCount(0);
    const toolbar = await box(page, TOOLBAR);
    expect(toolbar.x).toBeLessThanOrEqual(1);
    expect(toolbar.x + toolbar.width).toBeGreaterThanOrEqual(843);
  });
});

test.describe("touch tablet with the rail (1024 × 768)", () => {
  test.use({ viewport: { width: 1024, height: 768 }, hasTouch: true, isMobile: true });

  test("the toolbar starts right of the rail (BB-B-17)", async ({ page }) => {
    await openEditor(page);
    const rail = await box(page, "aside:visible");
    const toolbar = await box(page, TOOLBAR);
    expect(toolbar.x).toBeGreaterThanOrEqual(rail.x + rail.width - 1);
    expect(toolbar.x + toolbar.width).toBeLessThanOrEqual(1024);
  });
});
