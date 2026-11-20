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
      expect(name.width).toBeGreaterThanOrEqual(96);
      expect(name.y).toBeLessThan(40);
      // No section card header, breadcrumb or second title above the editor.
      await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toHaveCount(0);
      // The editor toolbar replaces the tab bar (BB-B-17).
      await expect(page.getByRole("navigation")).toHaveCount(0);
      const preview = await box(page, PREVIEW);
      expect(preview.y).toBeLessThan(100);
    });

    test("the preview stays docked while you type on the last line (BB-B-4)", async ({ page }) => {
      await openEditor(page);
      const editor = page.locator('[contenteditable="true"]').first();
      await editor.click();
      await page.keyboard.press("Control+End");
      await page.keyboard.type("X");
      await page.locator('[data-slot="page-editor-scroll"]').evaluate((el) => el.scrollTo(0, el.scrollHeight));
      await expect(page.locator(PREVIEW)).toBeInViewport({ ratio: 0.9 });
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

  test("the toolbar starts right of the rail (BB-B-17)", async ({ page }) => {
    await openEditor(page);
    const rail = await box(page, "aside");
    const toolbar = await box(page, TOOLBAR);
    expect(toolbar.x).toBeGreaterThanOrEqual(rail.x + rail.width - 1);
    expect(toolbar.x + toolbar.width).toBeLessThanOrEqual(844);
  });
});
