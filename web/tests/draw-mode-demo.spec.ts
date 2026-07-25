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
  configureMockCloud,
  deleteAllPages,
  expect,
  getMockBoardState,
  resetMockCloud,
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

test("pencil draw mode on an 8x8 note array", async ({ page }) => {
  // 24 rows × 120 cols — the biggest board the product supports (2,880 tiles).
  // 1600×1000 keeps the exact 1.6 aspect of the 1280×800 video frame, so the
  // recording downscales without letterboxing while the preview gets more
  // pixels per tile.
  await page.setViewportSize({ width: 1600, height: 1000 });

  // Cloud-mode 8×8 array board + a blank 24-line page to draw on.
  await configureMockCloud(8, 8);
  await resetMockCloud();
  const boardRes = await fetch(`${API_URL}/settings/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      boards: [
        {
          name: "Big Array",
          device_type: "note_array",
          board_color: "black",
          enabled: true,
          api_mode: "cloud",
          notes_wide: 8,
          notes_tall: 8,
          note_array_token: `test-array-token-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        },
      ],
    }),
  });
  expect(boardRes.ok).toBe(true);
  const pageRes = await fetch(`${API_URL}/pages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      name: "Big Array Demo",
      type: "template",
      template: Array.from({ length: 24 }, () => ""),
      device_type: "note_array",
      notes_wide: 8,
      notes_tall: 8,
    }),
  });
  expect(pageRes.ok).toBe(true);
  const pageId = (await pageRes.json()).page.id;

  // --- Open the editor: the 24×120 preview fills the card ---
  await page.goto(`/pages/edit/${pageId}`);
  await expect(page.getByText("Edit Page").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("draw-mode-toggle")).toBeVisible({ timeout: 10_000 });
  await beat(page, 1_000);

  // --- Pencil on ---
  await page.getByTestId("draw-mode-toggle").click();
  await expect(page.locator('[data-draw-surface="true"]')).toBeVisible();
  await beat(page, 1_000);

  /** Drag one continuous stroke through per-row waypoints of a diagonal. */
  async function dragDiagonal(colForRow: (row: number) => number): Promise<void> {
    const first = await tile(page, 0, colForRow(0)).boundingBox();
    expect(first).toBeTruthy();
    await page.mouse.move(first!.x + first!.width / 2, first!.y + first!.height / 2);
    await page.mouse.down();
    for (let row = 1; row < 24; row++) {
      const box = await tile(page, row, colForRow(row)).boundingBox();
      expect(box).toBeTruthy();
      await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2, { steps: 3 });
      await page.waitForTimeout(40);
    }
    await page.mouse.up();
  }

  // --- Red: drag the main diagonal corner to corner, crossing every note ---
  await pickBrush(page, "red");
  await dragDiagonal((row) => Math.round((row * 119) / 23));
  await expect(tile(page, 23, 119)).toHaveAttribute("data-cell-value", "red");
  await beat(page, 800);

  // --- Yellow: the anti-diagonal completes a big X across the array ---
  await pickBrush(page, "yellow");
  await dragDiagonal((row) => 119 - Math.round((row * 119) / 23));
  await expect(tile(page, 23, 0)).toHaveAttribute("data-cell-value", "yellow");
  await beat(page, 800);

  // --- Eraser: nip two cells out of the diagonals ---
  await pickBrush(page, "eraser");
  await tile(page, 11, Math.round((11 * 119) / 23)).click();
  await page.waitForTimeout(300);
  await tile(page, 12, Math.round((12 * 119) / 23)).click();
  await beat(page, 800);

  // --- Stamp a character on the big grid ---
  await pickChar(page, "X");
  await tile(page, 0, 3).click();
  await expect(tile(page, 0, 3)).toHaveAttribute("data-cell-value", "X");
  await beat(page, 800);

  // --- Save the page and end on the pages list ---
  // NOTE: the saved card itself is not asserted here — pages._index.tsx's
  // DEVICE_ORDER omits "note_array", so note-array pages don't (yet) appear
  // on the Pages list. Pre-existing platform gap, tracked outside this spec.
  const saveButton = page.getByRole("button", { name: "Save Page" }).or(page.getByRole("button", { name: /save/i }));
  await saveButton.first().click();
  await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });
  await beat(page, 1_200);
});
