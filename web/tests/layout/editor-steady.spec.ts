import { mkdir } from "node:fs/promises";
import path from "node:path";

import { expect, type Locator, type Page, test } from "@playwright/test";

import { mockHub } from "./creator-ide-hub";

// FP-1a (editor UX pass, UX-AUDIT-1 + FABLE-AUDIT-REVIEW-1): a steady
// workspace. Each column is its own stack, so nothing that opens in one column
// moves the other (UX-8-3); the rich toolbar's host keeps its height while the
// editor chunk loads (BB-E-32); the toolbar hugs its tools with "? All
// shortcuts" at the right (UX-2-1); "Template" heads its card at every width
// (UX-3-3, UX-10-1); at 900 the template and the preview sit side by side
// (UX-4-5, Figma 61:17544).

const heights: Record<number, number> = { 1440: 900, 1280: 800, 1024: 768, 900: 1180, 390: 844 };

async function open(page: Page, width: number, options: { theme?: "light" | "dark"; path?: string } = {}) {
  await page.setViewportSize({ width, height: heights[width] ?? 900 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const query = new URLSearchParams({
    theme: options.theme ?? "light",
    path: options.path ?? "/pages/edit/kitchen-morning",
  });
  await page.goto(`/tests/layout/editor-window.html?${query}`);
}

const box = async (locator: Locator) => (await locator.boundingBox())!;
const templateColumn = (page: Page) => page.locator('[data-slot="page-editor-template-column"]');
const previewColumn = (page: Page) => page.locator('[data-slot="page-editor-preview-column"]');
const templateCard = (page: Page) => page.locator('[data-slot="page-editor-template-card"]');

/** The tops of the template column, its card, the Console and the Timeline. */
async function leftColumnTops(page: Page) {
  return page.evaluate(() =>
    [
      '[data-slot="page-editor-template-column"]',
      '[data-slot="template-card"]',
      "#ide-console",
      '[data-slot="ide-timeline"]',
    ].map((selector) => Math.round(document.querySelector(selector)!.getBoundingClientRect().top)),
  );
}

for (const width of [1440, 1024]) {
  test(`${width}px: growth in the preview column never moves the template column (UX-8-3)`, async ({ page }) => {
    await mockHub(page);
    await open(page, width);
    await expect(page.getByRole("region", { name: "Console" })).toBeVisible();
    await expect(page.getByRole("tablist", { name: "Inspector" })).toBeVisible();
    const before = await leftColumnTops(page);
    // What the formula editor, Inspect's hint or the Missing card do: grow the
    // preview column under the preview card (the workbench's right half).
    await page.locator('[data-slot="editor-preview"]').evaluate((preview) => {
      const grow = document.createElement("div");
      grow.dataset.testid = "grow";
      grow.style.height = "175px";
      preview.after(grow);
    });
    await expect(page.getByTestId("grow")).toBeAttached();
    expect(await leftColumnTops(page)).toEqual(before);
  });

  test(`${width}px: growth under the template never moves the preview column (UX-8-3)`, async ({ page }) => {
    await mockHub(page);
    await open(page, width);
    const inspector = page.locator("#ide-inspector");
    await expect(inspector).toBeVisible();
    const before = {
      preview: (await box(page.locator('[data-slot="editor-preview"]'))).y,
      inspector: (await box(inspector)).y,
    };
    // The formula workbench's left half ("Line N produces") opens under the template card.
    await templateCard(page).evaluate((card) => {
      const grow = document.createElement("div");
      grow.dataset.testid = "grow";
      grow.style.height = "175px";
      card.after(grow);
    });
    await expect(page.getByTestId("grow")).toBeAttached();
    expect({
      preview: (await box(page.locator('[data-slot="editor-preview"]'))).y,
      inspector: (await box(inspector)).y,
    }).toEqual(before);
  });
}

test("1440px: the Console starts right under the template card, no dead band (UX-3-1)", async ({ page }) => {
  await mockHub(page);
  await open(page, 1440);
  const consoleRegion = page.locator("#ide-console").first();
  await expect(consoleRegion).toBeVisible();
  // The last thing the template column says before the IDE: the card, or the warnings under it.
  const above = await page.locator('[data-slot="ide-template-regions"]').evaluate((regions) => {
    const column = regions.closest('[data-slot="page-editor-template-column"]')!;
    const stack = column.querySelector('[data-slot="page-editor-template-card"]')!.parentElement!;
    return [...stack.children].reduce((max, el) => Math.max(max, el.getBoundingClientRect().bottom), 0);
  });
  const consoleBox = await box(page.locator('[data-slot="ide-template-regions"]'));
  expect(consoleBox.y - above).toBeLessThanOrEqual(24);
  expect(consoleBox.y).toBeGreaterThanOrEqual(above - 1);
});

test("a panel page loads without moving the workspace (BB-E-32, UX-8-3: CLS < 0.05)", async ({ page }) => {
  await page.addInitScript(() => {
    // A load straight into the editor starts on the icon rail (D1); the harness's
    // own URL is not an editor path, so it says so the way a stored choice does.
    localStorage.setItem("fiestaboard_sidebar_collapsed", "true");
    (window as unknown as { __cls: number }).__cls = 0;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as unknown as { value: number; hadRecentInput: boolean }[]) {
        if (!entry.hadRecentInput) (window as unknown as { __cls: number }).__cls += entry.value;
      }
    }).observe({ type: "layout-shift", buffered: true });
  });
  await mockHub(page, { deviceType: "panel" });
  await open(page, 1440);
  await expect(page.locator('[data-slot="page-editor-toolbar"] > *').first()).toBeVisible();
  await expect(page.getByRole("tablist", { name: "Inspector" })).toBeVisible();
  const board = page.locator('[data-slot="editor-preview-board"]');
  const ys: number[] = [];
  for (const wait of [0, 500, 1500]) {
    await page.waitForTimeout(wait);
    ys.push(Math.round((await box(board)).y));
  }
  expect(new Set(ys).size).toBe(1);
  expect(await page.evaluate(() => (window as unknown as { __cls: number }).__cls)).toBeLessThan(0.05);
});

for (const theme of ["light", "dark"] as const) {
  test(`1440px ${theme}: the toolbar hugs its tools, "All shortcuts" sits at the right (UX-2-1)`, async ({
    page,
  }, testInfo) => {
    await mockHub(page);
    await open(page, 1440, { theme });
    const row = page.locator('[data-slot="page-editor-toolbar-row"]');
    const tools = page.locator('[data-slot="page-editor-toolbar"] > *').first();
    await expect(tools).toBeVisible();
    const hint = row.getByRole("button", { name: /all shortcuts/i });
    await expect(hint).toBeVisible();
    const rowBox = await box(row);
    const toolsBox = await box(tools);
    const hintBox = await box(hint);
    // A hug-width group (Figma 53:137378 ~720 px), not a bar across the window.
    expect(toolsBox.width).toBeLessThan(rowBox.width * 0.75);
    expect(hintBox.x + hintBox.width).toBeGreaterThan(rowBox.x + rowBox.width - 4);
    await hint.click();
    await expect(page.getByRole("dialog", { name: /keyboard shortcuts/i })).toBeVisible();
    const shots = process.env.EDITOR_STEADY_SHOTS || testInfo.outputPath("shots");
    await mkdir(shots, { recursive: true });
    await page.keyboard.press("Escape");
    await page.screenshot({ path: path.join(shots, `toolbar-1440-${theme}.png`) });
  });
}

test("the ? key still opens the shortcut list once the header button is gone (UX-1-6, D5)", async ({ page }) => {
  await mockHub(page);
  await open(page, 1440);
  await expect(page.locator('[data-slot="page-editor-toolbar"] > *').first()).toBeVisible();
  await page.locator('[data-slot="page-editor-chrome"]').click({ position: { x: 4, y: 4 } });
  await page.keyboard.press("?");
  await expect(page.getByRole("dialog", { name: /keyboard shortcuts/i })).toBeVisible();
});

for (const width of [1440, 900, 390]) {
  test(`${width}px: "Template" heads its card, above the field (UX-3-3, UX-10-1)`, async ({ page }) => {
    await mockHub(page);
    await open(page, width);
    const header = page.locator('[data-slot="page-editor-template-card-header"]');
    await expect(header).toBeVisible();
    await expect(header).toContainText("Template");
    const field = page.locator('[data-slot="template-card"]');
    await expect(field).toBeVisible();
    const headerBox = await box(header);
    const fieldBox = await box(field);
    // Flush on the field: one card, header then rows.
    expect(Math.abs(headerBox.y + headerBox.height - fieldBox.y)).toBeLessThanOrEqual(1);
    expect(Math.abs(headerBox.x - fieldBox.x)).toBeLessThanOrEqual(1);
    expect(Math.abs(headerBox.width - fieldBox.width)).toBeLessThanOrEqual(1);
  });
}

test("900px: the template and the preview side by side, the Inspector under both (UX-4-5, Figma 61:17544)", async ({
  page,
}) => {
  await mockHub(page);
  await open(page, 900);
  const inspector = page.locator("#ide-inspector");
  await expect(inspector).toBeVisible();
  const template = await box(templateColumn(page));
  const preview = await box(previewColumn(page));
  expect(preview.x).toBeGreaterThanOrEqual(template.x + template.width - 1);
  expect(Math.abs(preview.y - template.y)).toBeLessThanOrEqual(2);
  const inspectorBox = await box(inspector);
  expect(inspectorBox.y).toBeGreaterThanOrEqual(Math.max(template.y + template.height, preview.y + preview.height) - 1);
  // No status row between the pair and the Inspector (M5): it is in the preview card.
  const status = await box(page.locator('[data-slot="preview-status"]'));
  expect(status.y + status.height).toBeLessThanOrEqual(preview.y + preview.height + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("1440px: the status line sits in the preview card's foot (UX-6-2 placement)", async ({ page }) => {
  await mockHub(page);
  await open(page, 1440);
  const status = page.locator('[data-slot="preview-status"]');
  await expect(status).toBeVisible();
  const card = await box(page.locator('[data-slot="editor-preview"]'));
  const statusBox = await box(status);
  expect(statusBox.y).toBeGreaterThanOrEqual(card.y);
  expect(statusBox.y + statusBox.height).toBeLessThanOrEqual(card.y + card.height + 1);
  // Under the board's tiles (the kit's EditorPreview has no slot under Mirror yet: KIT-ASKS).
  const tilesBottom = await page.evaluate(() =>
    Math.max(
      ...[...document.querySelectorAll('[data-slot="editor-preview"] [data-row]')].map(
        (t) => t.getBoundingClientRect().bottom,
      ),
    ),
  );
  expect(statusBox.y).toBeGreaterThanOrEqual(tilesBottom - 1);
});

test("1440px: the toolbar row keeps the Explorer toggle's place at its left end (UX-5-1)", async ({ page }) => {
  await mockHub(page);
  await open(page, 1440);
  const row = page.locator('[data-slot="page-editor-toolbar-row"]');
  await expect(row.locator('[data-slot="page-editor-toolbar-start"]')).toBeAttached();
  const start = await box(row.locator('[data-slot="page-editor-toolbar-start"]'));
  const tools = await box(page.locator('[data-slot="page-editor-toolbar"]'));
  expect(start.x).toBeLessThanOrEqual(tools.x);
});

test.describe("a coarse pointer at desktop width (iPad landscape)", () => {
  test.use({ hasTouch: true });
  // Playwright's touch emulation has no fine pointer at all; the kit hides the
  // hint then (`not-any-pointer-fine:hidden`: no keyboard, no shortcuts). With a
  // trackpad or a keyboard case (any-pointer: fine) it shows.
  test("1280px: the toolbar row still carries the shortcut list's entry, and `?` opens it (D5)", async ({ page }) => {
    await mockHub(page);
    await open(page, 1280);
    expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(true);
    const hint = page.locator('[data-slot="page-editor-toolbar-row"] button', { hasText: "All shortcuts" });
    await expect(hint).toBeAttached();
    await page.locator('[data-slot="page-editor-chrome"]').click({ position: { x: 4, y: 4 } });
    await page.keyboard.press("?");
    await expect(page.getByRole("dialog", { name: /keyboard shortcuts/i })).toBeVisible();
  });
});

test("1440px: the sticky preview stops above the formula workbench while the page scrolls (FABLE-2649)", async ({
  page,
}) => {
  // A tall template (a FiestaPanel) gives the sticky preview room to travel.
  await mockHub(page, { deviceType: "panel" });
  await open(page, 1440);
  await expect(page.getByRole("tablist", { name: "Inspector" })).toBeVisible();
  await templateCard(page).locator('[class*="formula"]').first().click();
  const workbench = page.locator('[data-slot="page-editor-workbench"]');
  await expect(workbench).toBeVisible();
  const scroller = page.locator('[data-slot="page-editor-scroll"]');
  for (const dy of [0, 300, 300, 300]) {
    await scroller.evaluate((el, by) => el.scrollBy(0, by), dy);
    const preview = await box(page.locator('[data-slot="editor-preview"]'));
    const bench = await box(workbench);
    expect(preview.y + preview.height).toBeLessThanOrEqual(bench.y + 1);
  }
});
