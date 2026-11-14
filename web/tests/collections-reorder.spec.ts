/**
 * Collection reorder (WEB-06, slice 2.6): the page list is a FiestaUI
 * SortableList. A row is lifted with Space, moved with the arrow keys and
 * dropped with Space; a pointer drags the grip. Either way the new order is
 * saved through `PUT /v1/collections/{id}` and survives a reload.
 *
 * Figma: 07 `57:66920` (touch drag), 07c `312:74870` (keyboard reorder).
 */
import type { Locator, Page } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

import {
  API_URL,
  authHeaders,
  configureBoard,
  createCollection,
  createPage,
  deleteAllCollections,
  deleteAllPages,
  ensureAuthForFetch,
  expect,
  loginIfNeeded,
  suppressWizard,
  test,
} from "./helpers";

const NAMES = ["Morning commute", "Market open", "Weather and surf"];

function rows(page: Page): Locator {
  return page.locator('[data-slot="sortable-list-item"]');
}

function rowOf(page: Page, name: string): Locator {
  return rows(page).filter({ hasText: name });
}

function status(page: Page): Locator {
  return page.locator('[data-slot="sortable-list-status"]');
}

async function order(page: Page): Promise<string[]> {
  return rows(page).locator('[data-slot="list-row-title"]').allTextContents();
}

async function savedOrder(collectionId: string): Promise<string[]> {
  const res = await fetch(`${API_URL}/v1/collections/${encodeURIComponent(collectionId)}`, {
    headers: authHeaders(),
  });
  expect(res.ok).toBe(true);
  return ((await res.json()) as { page_ids: string[] }).page_ids;
}

/** Seed three pages and a time-based Collection, then open its editor. */
async function openSeededCollection(page: Page): Promise<{ id: string; pageIds: string[] }> {
  const pageIds: string[] = [];
  for (const name of NAMES) pageIds.push(await createPage(name));
  const collection = await createCollection(`Weekday mornings ${Date.now()}`, pageIds, 60);
  await page.goto(`/collections/${encodeURIComponent(collection.id)}`);
  await expect(rows(page)).toHaveCount(3, { timeout: 15_000 });
  expect(await order(page)).toEqual(NAMES);
  return { id: collection.id, pageIds };
}

async function saveAndReopen(page: Page, collectionId: string) {
  await page.getByRole("button", { name: "Update Collection" }).click();
  await expect(page).toHaveURL(/\/collections\/?$/, { timeout: 15_000 });
  await page.goto(`/collections/${encodeURIComponent(collectionId)}`);
  await page.reload();
  await expect(rows(page)).toHaveCount(3, { timeout: 15_000 });
}

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await suppressWizard(page);
  await deleteAllCollections();
});

test.afterEach(async () => {
  await deleteAllCollections();
  await deleteAllPages();
});

test.describe("Collection reorder", () => {
  test("reorders by keyboard, announces each step and keeps the order after a reload", async ({ page }) => {
    const { id, pageIds } = await openSeededCollection(page);

    const first = rowOf(page, "Morning commute");
    await first.focus();
    await page.keyboard.press("Space");
    await expect(status(page)).toHaveText(
      "Morning commute lifted · position 1 of 3 · ↑ ↓ to move, Space to drop, Esc to cancel",
    );
    await expect(first).toHaveAttribute("data-lifted", "true");
    await page.keyboard.press("ArrowDown");
    await expect(status(page)).toHaveText("Morning commute · moving to position 2 of 3");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Space");
    await expect(status(page)).toHaveText("Morning commute dropped · position 3 of 3");
    await expect(rowOf(page, "Morning commute")).toBeFocused();
    expect(await order(page)).toEqual(["Market open", "Weather and surf", "Morning commute"]);

    await saveAndReopen(page, id);
    expect(await order(page)).toEqual(["Market open", "Weather and surf", "Morning commute"]);
    expect(await savedOrder(id)).toEqual([pageIds[1], pageIds[2], pageIds[0]]);
  });

  test("Escape puts a lifted row back without changing the saved order", async ({ page }) => {
    const { id, pageIds } = await openSeededCollection(page);
    await rowOf(page, "Market open").focus();
    await page.keyboard.press("Space");
    await page.keyboard.press("ArrowUp");
    expect(await order(page)).toEqual(["Market open", "Morning commute", "Weather and surf"]);
    await page.keyboard.press("Escape");
    await expect(status(page)).toHaveText("Market open returned to position 2 of 3");
    expect(await order(page)).toEqual(NAMES);
    // Escape stayed inside the list: the editor is still open.
    await expect(page).toHaveURL(new RegExp(`/collections/${encodeURIComponent(id)}`));
    expect(await savedOrder(id)).toEqual(pageIds);
  });

  test("reorders by dragging the grip and keeps the order after a reload", async ({ page }) => {
    const { id, pageIds } = await openSeededCollection(page);

    const handle = rowOf(page, "Weather and surf").locator('[data-slot="sortable-list-handle"]');
    await page.locator('[data-slot="sortable-list"]').scrollIntoViewIfNeeded();
    const from = await handle.boundingBox();
    const target = await rowOf(page, "Morning commute").boundingBox();
    if (!from || !target) throw new Error("rows are not laid out");

    await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
    await page.mouse.down();
    // Past the first row's centre, in steps, as a hand would.
    await page.mouse.move(from.x + from.width / 2, target.y + 4, { steps: 12 });
    await expect(status(page)).toHaveText("Weather and surf · moving to position 1 of 3");
    await expect(page.locator('[data-slot="sortable-list-indicator"]')).toBeVisible();
    await page.mouse.up();

    await expect(status(page)).toHaveText("Weather and surf dropped · position 1 of 3");
    expect(await order(page)).toEqual(["Weather and surf", "Morning commute", "Market open"]);

    await saveAndReopen(page, id);
    expect(await order(page)).toEqual(["Weather and surf", "Morning commute", "Market open"]);
    expect(await savedOrder(id)).toEqual([pageIds[2], pageIds[0], pageIds[1]]);
  });

  test("Move down in the row menu reorders and saves", async ({ page }) => {
    const { id, pageIds } = await openSeededCollection(page);
    await page.getByRole("button", { name: "More actions for Morning commute" }).click();
    await page.getByRole("menuitem", { name: "Move down" }).click();
    await expect(status(page)).toHaveText("Morning commute moved to position 2 of 3");
    expect(await order(page)).toEqual(["Market open", "Morning commute", "Weather and surf"]);
    await saveAndReopen(page, id);
    expect(await savedOrder(id)).toEqual([pageIds[1], pageIds[0], pageIds[2]]);
  });

  test("the editor with a lifted row has no critical or serious axe violations", async ({ page }) => {
    await openSeededCollection(page);
    await rowOf(page, "Market open").focus();
    await page.keyboard.press("Space");
    await expect(rowOf(page, "Market open")).toHaveAttribute("data-lifted", "true");
    // Measure settled colours, not a frame of the route's fade-in.
    await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))));
    await injectAxe(page);
    const violations = await getViolations(page, '[data-slot="sortable-list"]', {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] },
    });
    const failing = violations.filter((v) => v.impact === "critical" || v.impact === "serious");
    expect(failing.map((v) => `${v.id}: ${v.help} ${JSON.stringify(v.nodes.map((n) => [n.target, n.failureSummary]))}`)).toEqual([]);
  });
});
