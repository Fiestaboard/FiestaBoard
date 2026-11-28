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
  test(`${width}px: "Template" heads its card in one row with the count, above the rows (UX-3-3, UX-10-1, FABLE-2648)`, async ({
    page,
  }) => {
    await mockHub(page);
    await open(page, width);
    const card = page.locator('[data-slot="template-card"]');
    await expect(card).toBeVisible();
    // One header row, the editor's own: no second strip above the card.
    await expect(page.locator('[data-slot="page-editor-template-card-header"]')).toHaveCount(0);
    const header = card.locator('[data-slot="template-card-header"]');
    await expect(header).toContainText("Template");
    await expect(header.getByRole("group", { name: /editor mode/i })).toBeVisible();
    const title = await box(header.locator('[data-slot="page-editor-template-title"]'));
    const meta = await box(header.getByTestId("template-card-meta"));
    expect(Math.abs(title.y + title.height / 2 - (meta.y + meta.height / 2))).toBeLessThanOrEqual(2);
    expect(meta.x).toBeGreaterThan(title.x + title.width);
    const cardBox = await box(card);
    const rows = await box(card.locator('[data-slot="template-rows"]'));
    expect(title.y).toBeGreaterThanOrEqual(cardBox.y);
    expect(title.y + title.height).toBeLessThanOrEqual(rows.y);
  });
}

test("a narrow template column: the card title keeps Rich | Plain whole, the count truncates first", async ({
  page,
}) => {
  await mockHub(page);
  await open(page, 1024);
  const show = page.getByRole("button", { name: "Explorer", exact: true, pressed: false });
  if (await show.count()) await show.click();
  const header = page.locator('[data-slot="template-card"] [data-slot="template-card-header"]');
  const title = header.locator('[data-slot="page-editor-template-title"]');
  await expect(title).toBeVisible();
  expect(await title.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
  const plain = await box(title.getByRole("button", { name: /plain/i }));
  const meta = await box(header.getByTestId("template-card-meta"));
  expect(plain.x + plain.width).toBeLessThanOrEqual(meta.x);
});

for (const [name, deviceType] of [
  ["Flagship", undefined],
  ["band (panel)", "panel"],
] as const) {
  test(`${name}: the shortcut list hangs at the template card's left edge, under its header (DD-W30)`, async ({
    page,
  }) => {
    await mockHub(page, deviceType ? { deviceType } : {});
    await open(page, 1440);
    const card = page.locator('[data-slot="template-card"]');
    await expect(card).toBeVisible();
    await page.locator('[data-slot="page-editor-chrome"]').click({ position: { x: 4, y: 4 } });
    await page.keyboard.press("?");
    const list = page.getByRole("dialog", { name: /keyboard shortcuts/i });
    await expect(list).toBeVisible();
    await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== "running"));
    const [listBox, cardBox, column] = await Promise.all([box(list), box(card), box(templateColumn(page))]);
    expect(Math.abs(listBox.x - cardBox.x)).toBeLessThanOrEqual(2);
    // Under the card's header row (not under the whole card, not beside the column), on screen.
    expect(listBox.y).toBeLessThan(cardBox.y + 64);
    expect(listBox.x).toBeGreaterThanOrEqual(column.x);
    expect(listBox.x + listBox.width).toBeLessThanOrEqual(1440);
  });
}

test("draw mode: the template title stays on screen and anchors the shortcut list (OPUS-2653)", async ({ page }) => {
  await mockHub(page);
  await open(page, 1440);
  await page.getByRole("button", { name: "Draw on board", exact: true }).click();
  await expect(page.locator('[data-slot="template-card"]')).toBeHidden();
  const title = page.locator('[data-slot="page-editor-template-title"]');
  await expect(title).toBeVisible();
  await page.locator('[data-slot="page-editor-chrome"]').click({ position: { x: 4, y: 4 } });
  await page.keyboard.press("?");
  const list = page.getByRole("dialog", { name: /keyboard shortcuts/i });
  await expect(list).toBeVisible();
  const titleBox = await box(title);
  const listBox = await box(list);
  expect(listBox.x).toBeGreaterThanOrEqual(titleBox.x - 1);
  expect(listBox.y).toBeGreaterThanOrEqual(titleBox.y);
});

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

test("1440px: the toolbar row holds the Explorer toggle at its left end (UX-5-1)", async ({ page }) => {
  await mockHub(page);
  await open(page, 1440);
  const row = page.locator('[data-slot="page-editor-toolbar-row"]');
  const start = row.locator('[data-slot="page-editor-toolbar-start"]');
  expect(await start.evaluate((el) => el.previousElementSibling === null)).toBe(true);
  const toggle = start.getByRole("button", { name: "Explorer", exact: true });
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  // The toggle starts the row; the tools follow it.
  expect(Math.round((await box(toggle)).x)).toBe(Math.round((await box(row)).x));
  const tools = await box(page.locator('[data-slot="page-editor-toolbar"]'));
  expect(tools.x).toBeGreaterThan((await box(toggle)).x);
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
