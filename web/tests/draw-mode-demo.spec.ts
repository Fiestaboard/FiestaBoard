/**
 * Draw-mode video walkthrough — NOT a regression test.
 *
 * A single deliberately-paced tour of the pencil feature for video capture,
 * showing off the drawing toolbar: inline color swatches (red → yellow →
 * blue), the eraser icon button, character stamping ("HI!") via the
 * character dropdown, undo/redo, exit to the restored editor, save, and
 * board delivery. Run only via playwright-video.config.ts (the main suite
 * ignores this spec).
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

/** Pick a brush from the inline toolbar swatches (color name or "eraser"). */
async function pickBrush(page: Page, brush: string): Promise<void> {
  await page.getByTestId(`draw-color-${brush}`).click();
  await page.waitForTimeout(500);
}

/** Pick a stamp character from the character dropdown, with demo pacing. */
async function pickChar(page: Page, char: string): Promise<void> {
  await page.getByTestId("draw-char-dropdown").click();
  await page.waitForTimeout(500);
  await page.locator(`[data-draw-char="${char}"]`).click();
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

  // --- Enter draw mode: the toolbar swaps to dedicated drawing controls ---
  await page.getByTestId("draw-mode-toggle").click();
  await expect(page.locator('[data-draw-surface="true"]')).toBeVisible();
  await expect(page.getByTestId("draw-color-red")).toBeVisible();
  await expect(page.getByTestId("draw-color-eraser")).toBeVisible();
  await expect(page.getByTestId("draw-char-dropdown")).toBeVisible();
  // Linger so the swatch row, eraser, and character dropdown register.
  await beat(page, 1_200);

  // --- Red swatch: draw a heart, cell by cell ---
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
  await beat(page, 700);

  // --- Yellow swatch: sparkle accents above the heart ---
  await pickBrush(page, "yellow");
  await tile(page, 0, 8).click();
  await page.waitForTimeout(250);
  await tile(page, 0, 12).click();
  await expect(tile(page, 0, 12)).toHaveAttribute("data-cell-value", "yellow");
  await beat(page, 700);

  // --- Blue swatch: accents beside the heart ---
  await pickBrush(page, "blue");
  await tile(page, 2, 6).click();
  await page.waitForTimeout(250);
  await tile(page, 2, 14).click();
  await expect(tile(page, 2, 14)).toHaveAttribute("data-cell-value", "blue");
  await beat(page, 700);

  // --- Eraser icon: remove one blue accent ---
  await pickBrush(page, "eraser");
  await tile(page, 2, 14).click();
  await expect(tile(page, 2, 14)).toHaveAttribute("data-cell-value", " ");
  await beat(page, 700);

  // --- Character dropdown: stamp "HI!" on the bottom row ---
  await pickChar(page, "H");
  await tile(page, 5, 9).click();
  await expect(tile(page, 5, 9)).toHaveAttribute("data-cell-value", "H");
  await pickChar(page, "I");
  await tile(page, 5, 10).click();
  await expect(tile(page, 5, 10)).toHaveAttribute("data-cell-value", "I");
  await pickChar(page, "!");
  await tile(page, 5, 11).click();
  await expect(tile(page, 5, 11)).toHaveAttribute("data-cell-value", "!");
  await beat(page, 800);

  // --- Undo removes the last stamp... ---
  await page.keyboard.press("Control+z");
  await expect(tile(page, 5, 11)).toHaveAttribute("data-cell-value", " ");
  await beat(page, 700);

  // --- ...and redo brings it back ---
  await page.keyboard.press("Control+y");
  await expect(tile(page, 5, 11)).toHaveAttribute("data-cell-value", "!");
  await beat(page, 700);

  // --- Escape restores the editor, now full of color chips and characters ---
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
