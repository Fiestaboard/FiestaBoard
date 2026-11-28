import { expect, type Locator, type Page, test } from "@playwright/test";

import { mockHub } from "./creator-ide-hub";

// Editor UX wave 2, pack W2-A. UX-5-1 (DD-W168): one Explorer toggle at the
// toolbar row's left end, `aria-pressed`, in the same place open or closed.
// FABLE-2652 §3.6: below 1280 the open Explorer is an overlay (D8) and Esc or
// a press outside closes it, Esc returning focus to the toggle. FP-5 (UX-9-2):
// Tab runs nav → header → toolbar → template column → preview column.

async function open(page: Page, width: number, height = width >= 1440 ? 900 : width >= 1280 ? 800 : 768) {
  await mockHub(page);
  await page.setViewportSize({ width, height });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/tests/layout/editor-window.html?${new URLSearchParams({ path: "/pages/edit/kitchen-morning" })}`);
  await expect(page.getByRole("textbox", { name: /page name/i })).toHaveValue("Kitchen morning");
  await expect(page.getByRole("tablist", { name: "Inspector" })).toBeVisible();
}

const toggle = (page: Page) => page.getByRole("button", { name: "Explorer", exact: true });
const explorer = (page: Page) => page.getByRole("navigation", { name: "Explorer" });
const box = async (locator: Locator) => (await locator.boundingBox())!;

for (const width of [1440, 1024]) {
  test(`${width}px: one Explorer toggle in the toolbar row, same place open and closed (UX-5-1)`, async ({ page }) => {
    await open(page, width);
    await expect(toggle(page)).toHaveCount(1);
    await expect(toggle(page)).toHaveAttribute("aria-pressed", "false");
    // It heads the toolbar row, before the tools.
    const row = page.locator('[data-slot="page-editor-toolbar-row"]');
    await expect(row.locator('[data-slot="page-editor-toolbar-start"]').getByRole("button")).toHaveCount(1);
    const closed = await box(toggle(page));
    const tools = await box(page.locator('[data-slot="page-editor-toolbar"]'));
    expect(closed.x + closed.width).toBeLessThanOrEqual(tools.x);
    // Closed, the Explorer takes no column: the template starts where the toolbar does.
    const template = await box(page.locator('[data-slot="page-editor-template-column"]'));
    expect(Math.abs(template.x - closed.x)).toBeLessThanOrEqual(1);

    await toggle(page).click();
    await expect(explorer(page)).toBeVisible();
    await expect(toggle(page)).toHaveAttribute("aria-pressed", "true");
    await expect(toggle(page)).toBeFocused();
    const opened = await box(toggle(page));
    expect(opened).toEqual(closed);
    // No second open/close control anywhere (the card's Hide and the column's Show are gone).
    await expect(page.getByRole("button", { name: /explorer/i })).toHaveCount(1);

    await toggle(page).click();
    await expect(explorer(page)).toHaveCount(0);
    await expect(toggle(page)).toBeFocused();
    expect(await box(toggle(page))).toEqual(closed);
  });
}

test("1024px: the Explorer overlay closes on Esc (focus back on the toggle) and on a press outside (D8)", async ({
  page,
}) => {
  await open(page, 1024);
  const template = page.locator('[data-slot="page-editor-template-column"]');
  const before = await box(template);
  await toggle(page).click();
  await expect(explorer(page)).toBeVisible();
  // It lies over the template, which neither moves nor narrows.
  expect(await box(template)).toEqual(before);

  await page.keyboard.press("Escape");
  await expect(explorer(page)).toHaveCount(0);
  await expect(toggle(page)).toBeFocused();

  await toggle(page).click();
  await expect(explorer(page)).toBeVisible();
  // A press inside the panel keeps it open.
  await explorer(page).click({ position: { x: 20, y: 60 } });
  await expect(explorer(page)).toBeVisible();
  // A press on the preview, outside the panel and its toggle, closes it.
  const preview = await box(page.locator('[data-slot="page-editor-preview-column"]'));
  await page.mouse.click(preview.x + preview.width / 2, preview.y + 20);
  await expect(explorer(page)).toHaveCount(0);
  await expect(toggle(page)).toHaveAttribute("aria-pressed", "false");
});

test("1440px: the open Explorer is a column there, so Esc and a press outside leave it open", async ({ page }) => {
  await open(page, 1440);
  await toggle(page).click();
  await expect(explorer(page)).toBeVisible();
  await page.keyboard.press("Escape");
  const preview = await box(page.locator('[data-slot="page-editor-preview-column"]'));
  await page.mouse.click(preview.x + preview.width / 2, preview.y + 20);
  await expect(explorer(page)).toBeVisible();
});

test("1440px: Tab runs nav → header → toolbar → template column → preview column (FP-5)", async ({ page }) => {
  await open(page, 1440);
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  const regions = [
    ["nav", '[data-slot="sidebar"], nav[aria-label]:not([aria-label="Explorer"])'],
    ["header", '[data-slot="card-header"]'],
    ["toolbar", '[data-slot="page-editor-toolbar-row"]'],
    ["template", '[data-slot="page-editor-template-column"]'],
    ["preview", '[data-slot="page-editor-preview-column"]'],
  ] as const;
  const seen: string[] = [];
  for (let i = 0; i < 120; i += 1) {
    await page.keyboard.press("Tab");
    const stop = await page.evaluate(
      (list) => {
        const el = document.activeElement;
        if (!el || el === document.body) return { where: "end", ring: true, name: "" };
        const where = list.find(([, selector]) => el.closest(selector))?.[0] ?? "other";
        const style = getComputedStyle(el);
        // A visible ring: an outline, a ring shadow, or the kit board bezel's :has() ring.
        const ring =
          (style.outlineStyle !== "none" && parseFloat(style.outlineWidth) > 0) ||
          style.boxShadow !== "none" ||
          !!el.parentElement?.matches(":has(> :focus-visible)");
        const name = (el.getAttribute("aria-label") || el.textContent || el.tagName).trim().slice(0, 40);
        return {
          where,
          ring,
          name,
          tabStopOnly: el.tagName === "DIV" && !el.getAttribute("role")?.match(/textbox|tab|button/),
        };
      },
      regions as unknown as [string, string][],
    );
    if (stop.where === "end") break;
    expect(stop.ring, `${stop.name} shows a focus ring`).toBe(true);
    if (seen.at(-1) !== stop.where && stop.where !== "other") seen.push(stop.where);
  }
  expect(seen).toEqual(["nav", "header", "toolbar", "template", "preview"]);
});
