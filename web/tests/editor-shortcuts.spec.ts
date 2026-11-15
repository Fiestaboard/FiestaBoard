/**
 * Slice 2.7 (WEB-17): the page editor's `?` keyboard-shortcut list.
 *
 * Figma 07 `57:27771`: the header's "Shortcuts" button (`57:28576`), the
 * "? All shortcuts" hint (`57:28704`) and the `?` key all open one list
 * (`57:28953`), hung under the template column. Phones get no trigger
 * (FiestaUI 1.4d hides it without a fine pointer), but a hardware keyboard's
 * `?` still opens the list — the touch-context case below is the CI check the
 * 1.4d parity review asked 2.7 to add.
 */
import type { Page } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

import { configureBoard, expect, suppressWizard, test } from "./helpers";

const LIST = { name: "Keyboard shortcuts" } as const;

async function openEditor(page: Page) {
  await page.goto("/pages/new");
  await expect(page.getByText("Create Page").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('[contenteditable="true"]').first()).toBeVisible({ timeout: 15_000 });
}

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
});

test.describe("Editor keyboard shortcuts (desktop)", () => {
  test("? opens the list in the template column, listing the editor's real shortcuts", async ({ page }) => {
    await openEditor(page);
    await page.locator("body").press("?");
    const list = page.getByRole("dialog", LIST);
    await expect(list).toBeVisible();
    await expect(list.getByRole("term")).toHaveText([
      "Undo",
      "Redo",
      "Apply a formula (formula editor)",
      "Close a picker",
      "Leave draw mode",
      "Move the preview by one Note or column",
      "Jump to the start or end of the preview",
      "Fit / Actual size (preview focused)",
    ]);

    // 07 hangs the list in the template column, at its left edge (DD-W30).
    // Measure once the open animation (a zoom from 95%) has settled.
    await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== "running"));
    const template = page.locator('[data-ai-anchor="page-editor.template"]').first();
    const [listBox, templateBox] = await Promise.all([list.boundingBox(), template.boundingBox()]);
    expect(listBox && templateBox).toBeTruthy();
    expect(Math.abs(listBox!.x - templateBox!.x)).toBeLessThanOrEqual(2);
    expect(listBox!.y).toBeGreaterThanOrEqual(0);
    expect(listBox!.y + listBox!.height).toBeLessThanOrEqual(page.viewportSize()!.height);

    await page.keyboard.press("Escape");
    await expect(list).toBeHidden();
  });

  test("the listed preview keys scroll the converted editor viewport and toggle Fit", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openEditor(page);
    const viewport = page.locator("[data-slot=board-viewport]").first();
    const scroller = viewport.locator("[data-slot=board-viewport-scroller]");
    await expect(viewport).toHaveAttribute("data-mode", "actual");
    await expect(viewport).toHaveAttribute("data-overflow", "true");
    await scroller.focus();
    await page.keyboard.press("End");
    await expect.poll(() => scroller.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
    await page.keyboard.press("Home");
    await expect.poll(() => scroller.evaluate((el) => el.scrollLeft)).toBe(0);
    await page.keyboard.press("f");
    await expect(viewport).toHaveAttribute("data-mode", "fit");
    await page.keyboard.press("f");
    await expect(viewport).toHaveAttribute("data-mode", "actual");
  });

  test("? stays a typed character in the page name and in the template", async ({ page }) => {
    await openEditor(page);
    const name = page.getByPlaceholder("My Custom Page");
    await name.fill("");
    await name.press("?");
    await expect(name).toHaveValue("?");
    const editor = page.locator('[contenteditable="true"]').first();
    await editor.click();
    await page.keyboard.press("?");
    await expect(editor).toContainText("?");
    await expect(page.getByRole("dialog", LIST)).toHaveCount(0);
  });

  test("? inside the formula modal belongs to the modal, and Esc then closes only the modal", async ({ page }) => {
    await openEditor(page);
    await page.locator('[contenteditable="true"]').first().click();
    await page.getByRole("button", { name: "Insert formula" }).click();
    const modal = page.getByRole("dialog", { name: "Formula editor" });
    await expect(modal).toBeVisible();
    const tab = modal.getByRole("tab", { name: "Functions" });
    await tab.focus();
    await page.keyboard.press("?");
    await expect(page.getByRole("dialog", LIST)).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(modal).toBeHidden();
    await expect(page.getByRole("dialog", LIST)).toHaveCount(0);
  });

  test("the ? All shortcuts hint sits at the right end of the template toolbar", async ({ page }) => {
    await openEditor(page);
    const hint = page.getByRole("button", { name: /All shortcuts/ });
    const toolbarButton = page.getByRole("button", { name: "Insert formula" });
    const [hintBox, toolBox] = await Promise.all([hint.boundingBox(), toolbarButton.boundingBox()]);
    expect(hintBox && toolBox).toBeTruthy();
    // Same row as the toolbar's buttons, right of them.
    expect(Math.abs(hintBox!.y + hintBox!.height / 2 - (toolBox!.y + toolBox!.height / 2))).toBeLessThanOrEqual(4);
    expect(hintBox!.x).toBeGreaterThan(toolBox!.x);
  });

  for (const width of [768, 1024]) {
    test(`at ${width}px the hint stays above the toolbar without adding a toolbar line`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1024 });
      await openEditor(page);
      const hint = page.getByRole("button", { name: /All shortcuts/ });
      await expect(hint).toHaveCount(1);
      const formula = page.getByRole("button", { name: "Insert formula" });
      const [hintBox, toolBox] = await Promise.all([hint.boundingBox(), formula.boundingBox()]);
      expect(hintBox && toolBox).toBeTruthy();
      expect(hintBox!.y + hintBox!.height).toBeLessThanOrEqual(toolBox!.y);
      if (width === 768) {
        const previewBox = await page.getByRole("button", { name: "Hide preview and live output" }).boundingBox();
        expect(previewBox).toBeTruthy();
        expect(
          Math.abs(hintBox!.y + hintBox!.height / 2 - (previewBox!.y + previewBox!.height / 2)),
        ).toBeLessThanOrEqual(4);
      }
      await hint.click();
      await expect(page.getByRole("dialog", LIST)).toBeVisible();
      await page.keyboard.press("Escape");

      // Crossing the desktop boundary moves the single hint into the toolbar.
      await page.setViewportSize({ width: 1280, height: 720 });
      await expect(hint).toHaveCount(1);
      await expect
        .poll(async () => {
          const [h, t] = await Promise.all([hint.boundingBox(), formula.boundingBox()]);
          // A media-query update reparents the hint between these measurements.
          // Keep polling until both current elements have layout boxes.
          if (!h || !t) return Number.POSITIVE_INFINITY;
          return Math.abs(h.y + h.height / 2 - (t.y + t.height / 2));
        })
        .toBeLessThanOrEqual(4);
    });
  }

  test("the header Shortcuts button and the ? All shortcuts hint both open the list", async ({ page }) => {
    await openEditor(page);
    await page.getByRole("button", { name: "Shortcuts", exact: true }).click();
    await expect(page.getByRole("dialog", LIST)).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", LIST)).toBeHidden();

    await page.getByRole("button", { name: /All shortcuts/ }).click();
    await expect(page.getByRole("dialog", LIST)).toHaveCount(1);
  });

  test("the open list has no critical or serious axe violations", async ({ page }) => {
    await openEditor(page);
    await page.locator("body").press("?");
    await expect(page.getByRole("dialog", LIST)).toBeVisible();
    await injectAxe(page);
    const violations = await getViolations(page, '[data-slot="shortcut-list-popover"]', {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
      rules: { "color-contrast": { enabled: false } },
    });
    const failing = violations.filter((v) => v.impact === "critical" || v.impact === "serious");
    expect(failing, JSON.stringify(failing, null, 2)).toEqual([]);
  });
});

test.describe("Editor keyboard shortcuts (touch, no fine pointer)", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test("hides both triggers, and ? from a keyboard still opens the list on screen", async ({ page }) => {
    await openEditor(page);
    expect(await page.evaluate(() => matchMedia("(any-pointer: fine)").matches)).toBe(false);
    await expect(page.getByRole("button", { name: "Shortcuts", exact: true })).toBeHidden();
    await expect(page.getByRole("button", { name: /All shortcuts/ })).toBeHidden();

    await page.locator("body").press("?");
    const list = page.getByRole("dialog", LIST);
    await expect(list).toBeVisible();
    const box = await list.boundingBox();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  });
});
