import { mkdir } from "node:fs/promises";
import path from "node:path";

import { expect, type Locator, type Page, test } from "@playwright/test";

import { mockHub } from "./creator-ide-hub";

// BB-E-7, BB-E-11, BB-E-22: one three-column workspace (Figma 184:159319;
// supersedes ide-columns.test.ts, BB-B-19: the Console and Inspector now sit
// inside the template and preview columns, measured below):
// Explorer | Template + Console + Timeline | Preview + Inspector, under one
// sticky header and toolbar; the same frame for a new page and a saved one;
// Tab order that follows the columns. 1024–1279 has no Figma frame (D8): the
// same grid, narrower (Jev same_three_column, DESIGN-DELTAS).

async function open(page: Page, width: number, pathname = "/pages/edit/kitchen-morning") {
  await page.setViewportSize({ width, height: width >= 1440 ? 900 : width >= 1280 ? 800 : 768 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/tests/layout/editor-window.html?${new URLSearchParams({ theme: "light", path: pathname })}`);
}

const column = (page: Page, name: "explorer" | "template" | "preview") =>
  page.locator(`[data-slot="page-editor-${name}-column"]`);
const box = async (locator: Locator) => (await locator.boundingBox())!;

for (const width of [1440, 1280, 1024]) {
  test(`${width}px: one workspace, the IDE regions in their columns (BB-E-7)`, async ({ page }, testInfo) => {
    await mockHub(page);
    await open(page, width);
    await page.getByRole("button", { name: "Show Explorer" }).click();
    await expect(page.getByRole("navigation", { name: "Explorer" })).toBeVisible();
    const consoleRegion = page.getByRole("region", { name: "Console" });
    const inspector = page.getByRole("tablist", { name: "Inspector" });
    await expect(consoleRegion).toBeVisible();
    await expect(inspector).toBeVisible();

    // Three columns side by side, left to right.
    const explorer = await box(column(page, "explorer"));
    const template = await box(column(page, "template"));
    const preview = await box(column(page, "preview"));
    expect(explorer.x + explorer.width).toBeLessThanOrEqual(template.x);
    expect(template.x + template.width).toBeLessThanOrEqual(preview.x);
    // The Explorer sits under the header and toolbar, as drawn (not beside them).
    const chrome = await box(page.locator('[data-slot="page-editor-chrome"]'));
    expect(explorer.y).toBeGreaterThanOrEqual(chrome.y + chrome.height - 1);

    // The Console and Timeline are in the template column; the status row and Inspector in the preview column.
    const consoleBox = await box(consoleRegion);
    const week = await box(page.locator('[data-slot="ide-timeline"]'));
    // The card, not the tablist: the kit's tab strip scrolls inside it when narrow.
    const inspectorBox = await box(page.locator("#ide-inspector"));
    for (const b of [consoleBox, week]) {
      expect(b.x).toBeGreaterThanOrEqual(template.x - 1);
      expect(b.x + b.width).toBeLessThanOrEqual(template.x + template.width + 1);
    }
    expect(inspectorBox.x).toBeGreaterThanOrEqual(preview.x - 1);
    expect(inspectorBox.x + inspectorBox.width).toBeLessThanOrEqual(preview.x + preview.width + 1);
    // Figma fits it all at 1440 × 900: the Console and the Inspector start above the fold.
    if (width === 1440) {
      expect(consoleBox.y).toBeLessThan(900);
      expect(inspectorBox.y).toBeLessThan(900);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

    const shots = process.env.EDITOR_WORKSPACE_SHOTS || testInfo.outputPath("editor-workspace-shots");
    await mkdir(shots, { recursive: true });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join(shots, `workspace-${width}.png`) });
  });

  test(`${width}px: the header and the toolbar stay put while the workspace scrolls (BB-E-7)`, async ({ page }) => {
    await mockHub(page, { deviceType: "panel" });
    await open(page, width);
    await expect(page.getByRole("region", { name: "Console" })).toBeVisible();
    const toolbarHost = page.locator('[data-slot="page-editor-chrome"] [data-slot="page-editor-toolbar"]');
    await expect(toolbarHost).toBeVisible();
    const before = await box(toolbarHost);
    await page.locator('[data-slot="page-editor-scroll"]').evaluate((el) => el.scrollBy(0, 600));
    await expect
      .poll(() => page.locator('[data-slot="page-editor-scroll"]').evaluate((el) => el.scrollTop))
      .toBeGreaterThan(100);
    const after = await box(toolbarHost);
    expect(after.y).toBe(before.y);
    await expect(page.getByRole("textbox", { name: /page name/i })).toBeInViewport();
  });
}

test("a new page has the saved page's frame; the first save moves nothing (BB-E-11)", async ({ page }) => {
  await mockHub(page);
  await open(page, 1440, "/pages/new");
  const name = page.getByRole("textbox", { name: /page name/i });
  await expect(name).toBeVisible();
  await expect(column(page, "explorer")).toBeVisible();
  await name.fill("Kitchen morning");
  const editor = page.locator(".ProseMirror").first();
  await editor.click();
  await page.keyboard.type("HELLO");
  const frame = async () => ({
    explorer: await box(column(page, "explorer")),
    template: await box(column(page, "template")),
    preview: await box(page.locator('[data-slot="editor-preview"]')),
    editor: await box(editor),
  });
  const before = await frame();
  await page.getByRole("button", { name: /save page/i }).click();
  await expect(page.getByRole("region", { name: "Console" })).toBeVisible();
  const after = await frame();
  for (const key of ["explorer", "template", "preview", "editor"] as const) {
    expect({ key, x: after[key].x, y: after[key].y, width: after[key].width }).toEqual({
      key,
      x: before[key].x,
      y: before[key].y,
      width: before[key].width,
    });
  }
});

test("Tab goes column by column: Explorer, template column, preview column (BB-E-22)", async ({ page }) => {
  await mockHub(page);
  await open(page, 1440);
  await page.getByRole("button", { name: "Show Explorer" }).click();
  await expect(page.getByRole("tablist", { name: "Inspector" })).toBeVisible();
  await page.getByRole("button", { name: "Hide Explorer" }).focus();
  const order = ["explorer", "template", "preview"];
  const seen: string[] = [];
  for (let i = 0; i < 80; i += 1) {
    const where = await page.evaluate((names) => {
      const el = document.activeElement;
      return names.find((n) => el?.closest(`[data-slot="page-editor-${n}-column"]`)) ?? "outside";
    }, order);
    // Past the last column Tab leaves the editor (and wraps round the page): one pass is enough.
    if (where === "outside" && seen.at(-1) === "preview") break;
    if (where !== "outside" && seen.at(-1) !== where) seen.push(where);
    await page.keyboard.press("Tab");
  }
  // Each column is visited once, in the order the reader sees them left to right: no zig-zag back.
  const visual = await Promise.all(
    order.map(async (name) => ({ name, x: (await box(column(page, name as never))).x })),
  );
  expect(seen).toEqual(visual.sort((a, b) => a.x - b.x).map((c) => c.name));
  expect(seen).toEqual(order);
});

test("Page duration is one Tab stop: the Page panel itself is not a second one (BB-E-22)", async ({ page }) => {
  await mockHub(page);
  await open(page, 1440);
  await page.getByRole("tab", { name: "Page" }).focus();
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toHaveAttribute("data-slot", "list-row");
  await expect(page.locator(":focus")).toContainText("Page duration");
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toContainText("Transition");
});
