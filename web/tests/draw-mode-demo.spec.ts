/**
 * Draw-mode video walkthrough — NOT a regression test.
 *
 * A single deliberately-paced tour of the pencil feature for video capture:
 * paint a red heart, drag a yellow underline, erase, undo/redo, exit to the
 * restored editor with its color chips, save, send to the board, and finish
 * on the pages list. Run only via playwright-video.config.ts (the main
 * suite ignores this spec).
 */
import type { Page } from "@playwright/test";

import {
  API_URL,
  authHeaders,
  configureBoard,
  deleteAllPages,
  expect,
  getMockBoardState,
  resetToSingleBoard,
  setActivePage,
  suppressWizard,
  test,
} from "./helpers";

const RED_CODE = 63;

/** A tile locator scoped to the active draw surface. */
function tile(page: Page, row: number, col: number) {
  return page.locator(`[data-draw-surface="true"] [data-row="${row}"][data-col="${col}"]`);
}

async function pickBrush(page: Page, brush: string): Promise<void> {
  await page.getByTestId("draw-brush-dropdown").click();
  await page.waitForTimeout(400);
  await page.getByTestId(`draw-color-${brush}`).click();
  await page.waitForTimeout(400);
}

async function forceRefresh(): Promise<void> {
  const res = await fetch(`${API_URL}/force-refresh`, { method: "POST", headers: authHeaders() });
  if (!res.ok) throw new Error(`force-refresh failed: ${res.status} ${await res.text()}`);
}

/** Beat pause — long enough to read, short enough to keep the video tight. */
async function beat(page: Page, ms = 600): Promise<void> {
  await page.waitForTimeout(ms);
}

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await deleteAllPages();
  await suppressWizard(page);
});

test.afterEach(async () => {
  await deleteAllPages();
  await resetToSingleBoard();
});

test("pencil draw mode walkthrough", async ({ page }) => {
  // --- Open the page builder ---
  await page.goto("/pages/new");
  await expect(page.getByText("Create Page").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("draw-mode-toggle")).toBeVisible({ timeout: 10_000 });
  await beat(page, 800);

  // --- Enter draw mode ---
  await page.getByTestId("draw-mode-toggle").click();
  await expect(page.locator('[data-draw-surface="true"]')).toBeVisible();
  await beat(page, 800);

  // --- Draw a red heart, cell by cell ---
  await pickBrush(page, "red");
  const heart: Array<[number, number]> = [
    [1, 9],
    [1, 11],
    [2, 8],
    [2, 9],
    [2, 10],
    [2, 11],
    [2, 12],
    [3, 9],
    [3, 10],
    [3, 11],
    [4, 10],
  ];
  for (const [row, col] of heart) {
    await tile(page, row, col).click();
    await page.waitForTimeout(180);
  }
  await expect(tile(page, 4, 10)).toHaveAttribute("data-cell-value", "red");
  await beat(page, 800);

  // --- Drag a yellow underline across the bottom row ---
  await pickBrush(page, "yellow");
  const start = await tile(page, 5, 6).boundingBox();
  expect(start).toBeTruthy();
  await page.mouse.move(start!.x + start!.width / 2, start!.y + start!.height / 2);
  await page.mouse.down();
  for (let col = 7; col <= 15; col++) {
    const box = await tile(page, 5, col).boundingBox();
    expect(box).toBeTruthy();
    await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2, { steps: 4 });
    await page.waitForTimeout(60);
  }
  await page.mouse.up();
  await expect(tile(page, 5, 15)).toHaveAttribute("data-cell-value", "yellow");
  await beat(page, 800);

  // --- Erase two cells from the heart's shoulders ---
  await pickBrush(page, "eraser");
  await tile(page, 2, 8).click();
  await beat(page, 500);
  await tile(page, 2, 12).click();
  await expect(tile(page, 2, 12)).toHaveAttribute("data-cell-value", " ");
  await beat(page, 700);

  // --- Undo brings the last erased cell back... ---
  await page.keyboard.press("Control+z");
  await expect(tile(page, 2, 12)).toHaveAttribute("data-cell-value", "red");
  await beat(page, 700);

  // --- ...and redo erases it again ---
  await page.keyboard.press("Control+y");
  await expect(tile(page, 2, 12)).toHaveAttribute("data-cell-value", " ");
  await beat(page, 700);

  // --- Escape restores the editor, now full of color chips ---
  await page.keyboard.press("Escape");
  await expect(page.locator('[data-draw-surface="true"]')).toHaveCount(0);
  await expect(page.locator('[contenteditable="true"]').first()).toBeVisible();
  await beat(page, 1_000);

  // --- Name and save the page ---
  const pageName = "Pencil Demo";
  await page.getByPlaceholder("My Custom Page").click();
  await page.getByPlaceholder("My Custom Page").pressSequentially(pageName, { delay: 60 });
  await beat(page, 500);
  const saveButton = page.getByRole("button", { name: "Save Page" }).or(page.getByRole("button", { name: /save/i }));
  await saveButton.first().click();
  await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });
  await beat(page, 800);

  // --- Send it to the board and confirm the red heart arrived ---
  const res = await fetch(`${API_URL}/pages`, { headers: authHeaders() });
  const data = await res.json();
  const saved = data.pages.find((p: { name: string }) => p.name === pageName);
  expect(saved).toBeTruthy();
  await setActivePage(saved.id);
  await forceRefresh();
  await expect
    .poll(async () => (await getMockBoardState()).current_message?.[1]?.[9], { timeout: 20_000 })
    .toBe(RED_CODE);

  // --- End on the pages list showing the saved demo page ---
  await expect(page.getByText(pageName).first()).toBeVisible({ timeout: 10_000 });
  await beat(page, 1_200);
});
