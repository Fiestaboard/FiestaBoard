/**
 * Slice 2.7 (WEB-17): the page editor's `?` keyboard-shortcut list.
 *
 * Figma 07 `57:27771`: the header's "Shortcuts" button (`57:28576`) and the
 * `?` key open one list (`57:28953`), hung under the template column. The
 * toolbar's "? All shortcuts" hint (`57:28704`) was a second entry point to
 * the same list and is gone (D5, bug bash BB-E-20). Phones get no trigger
 * (FiestaUI 1.4d hides it without a fine pointer), but a hardware keyboard's
 * `?` still opens the list — the touch-context case below is the CI check the
 * 1.4d parity review asked 2.7 to add.
 */
import type { Page } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

import { API_URL, authHeaders, configureBoard, deletePage, expect, suppressWizard, test } from "./helpers";

const LIST = { name: "Keyboard shortcuts" } as const;

async function openEditor(page: Page) {
  await page.goto("/pages/new");
  await expect(page.locator("#page-name")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('[contenteditable="true"]').first()).toBeVisible({ timeout: 15_000 });
}

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
});

test.describe("Editor keyboard shortcuts (desktop)", () => {
  test("? opens the list in the template column, listing the editor's real shortcuts", async ({ page }) => {
    // Give the Figma column placement room below its anchor. At a shorter
    // height the kit may flip the popup to keep the whole list on screen.
    await page.setViewportSize({ width: 1280, height: 900 });
    await openEditor(page);
    await page.locator("body").press("?");
    const list = page.getByRole("dialog", LIST);
    await expect(list).toBeVisible();
    await expect(list.getByRole("term")).toHaveText([
      "Undo",
      "Redo",
      "Insert a formula",
      "Apply a formula (formula editor)",
      "Close a picker",
      "Leave draw mode",
      "Save",
      "Inspect the preview",
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
    await page.setViewportSize({ width: 1280, height: 720 });
    await expect
      .poll(async () => {
        const bounds = await list.boundingBox();
        return (
          !!bounds &&
          bounds.x >= 0 &&
          bounds.y >= 0 &&
          bounds.x + bounds.width <= 1280 &&
          bounds.y + bounds.height <= 720
        );
      })
      .toBe(true);

    await page.keyboard.press("Escape");
    await expect(list).toBeHidden();
  });

  test("the listed preview keys scroll an overflowing Note array and toggle Fit", async ({ page }) => {
    const response = await fetch(`${API_URL}/v1/pages`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        name: "Keyboard viewport array",
        type: "template",
        device_type: "note_array",
        notes_wide: 3,
        notes_tall: 1,
        template: ["SCROLL THIS ARRAY", "", ""],
      }),
    });
    expect(response.ok).toBe(true);
    const { id } = await response.json();
    try {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.addInitScript(() => localStorage.setItem("fiestaboard:boardPreviewMode", "actual"));
      await page.goto(`/pages/edit/${id}`);
      await expect(page.getByPlaceholder("My Custom Page")).toHaveValue("Keyboard viewport array");
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
      await expect(page.getByRole("group", { name: "Preview size" })).toHaveCount(1);
      await expect(page.getByRole("button", { name: "Fit", exact: true })).toHaveAttribute("aria-pressed", "true");
      await page.keyboard.press("f");
      await expect(viewport).toHaveAttribute("data-mode", "actual");
      await expect(page.getByRole("button", { name: "Actual size", exact: true })).toHaveAttribute(
        "aria-pressed",
        "true",
      );
    } finally {
      await deletePage(id);
    }
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

  // D5 as Fable ruled it (FABLE-AUDIT-REVIEW-1, UX-1-6, supersedes DD-W139 D5):
  // the toolbar row's "? All shortcuts" is the one entry wherever that row
  // shows (768 px and up with a fine pointer); the header has no Shortcuts
  // button. The phone and touch editor keep their More-sheet row.
  test("the toolbar's All shortcuts is the only desktop entry point and opens the list", async ({ page }) => {
    await openEditor(page);
    await expect(page.getByRole("button", { name: "Shortcuts", exact: true })).toHaveCount(0);
    const hint = page.getByRole("button", { name: /All shortcuts/ });
    await expect(hint).toHaveCount(1);
    await hint.click();
    await expect(page.getByRole("dialog", LIST)).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", LIST)).toBeHidden();
  });

  for (const width of [768, 1024]) {
    test(`at ${width}px the toolbar row keeps the one entry, and ? and ⌘/ open the list`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1024 });
      await openEditor(page);
      const preview = page.locator('[data-slot="editor-preview"]');
      await expect(preview).toBeVisible();
      await expect(preview).toHaveAttribute("data-variant", width < 1024 ? "docked" : "pane");
      await expect(page.getByRole("button", { name: /show preview|hide preview/i })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Shortcuts", exact: true })).toHaveCount(0);
      const hint = page.getByRole("button", { name: /All shortcuts/ });
      await expect(hint).toHaveCount(1);
      await hint.click();
      await expect(page.getByRole("dialog", LIST)).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog", LIST)).toBeHidden();
      for (const key of ["?", "ControlOrMeta+Slash"]) {
        await page.locator("body").press(key);
        await expect(page.getByRole("dialog", LIST)).toBeVisible();
        await page.keyboard.press("Escape");
        await expect(page.getByRole("dialog", LIST)).toBeHidden();
      }

      // Crossing the desktop boundary keeps exactly one entry point: the toolbar's.
      await page.setViewportSize({ width: 1280, height: 720 });
      await expect(page.getByRole("button", { name: /All shortcuts/ })).toHaveCount(1);
      await expect(page.getByRole("button", { name: "Shortcuts", exact: true })).toHaveCount(0);
    });
  }

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
    await page.keyboard.press("Escape");
    // More owns the touch sheet; its shortcut action opens the one stable
    // popup, which must receive and retain keyboard focus outside that sheet.
    await page
      .locator('[data-slot="editor-toolbar"][data-size="touch"]')
      .getByRole("button", { name: "More", exact: true })
      .click();
    await page.getByRole("button", { name: "Shortcuts", exact: true }).click();
    await expect(list).toHaveCount(1);
    await expect(list).toBeVisible();
    await expect.poll(() => list.evaluate((popup) => popup.contains(document.activeElement))).toBe(true);
    await page.keyboard.press("Tab");
    await expect.poll(() => list.evaluate((popup) => popup.contains(document.activeElement))).toBe(true);
    await page.keyboard.press("Escape");
    await expect(list).toBeHidden();
  });
});
