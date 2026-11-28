import { expect, type Locator, type Page, test } from "@playwright/test";

import { mockHub } from "./creator-ide-hub";

// FABLE-2653 §3.1 (editor UX W2-A): the shortcut list hangs under the template
// header at 1024×768 and scrolls inside instead of flipping over the preview.

async function open(page: Page, width: number, height: number) {
  await mockHub(page);
  await page.setViewportSize({ width, height });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(`/tests/layout/editor-window.html?${new URLSearchParams({ path: "/pages/edit/kitchen-morning" })}`);
  await expect(page.getByRole("textbox", { name: /page name/i })).toHaveValue("Kitchen morning");
  await expect(page.getByRole("tablist", { name: "Inspector" })).toBeVisible();
}

const box = async (locator: Locator) => (await locator.boundingBox())!;

test("1024×768: the shortcut list hangs under the template header and scrolls inside (FABLE-2653 §3.1)", async ({
  page,
}) => {
  await open(page, 1024, 768);
  await page.getByRole("button", { name: /all shortcuts/i }).click();
  const list = page.locator('[data-slot="shortcut-list-popover"]');
  await expect(list).toBeVisible();
  const card = await box(page.locator('[data-slot="template-card"]'));
  const header = await box(page.locator('[data-slot="template-card-header"]'));
  const popup = await box(list);
  // Under the header row, inside the template column's left edge: not flipped beside the card.
  expect(popup.y).toBeGreaterThanOrEqual(header.y + header.height - 1);
  expect(Math.abs(popup.x - card.x)).toBeLessThanOrEqual(2);
  expect(popup.y + popup.height).toBeLessThanOrEqual(768);
  // Its rows scroll inside it.
  expect(await list.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
});
