/**
 * Pencil draw-mode E2E tests.
 *
 * Covers the draw-on-board feature in the page builder: painting cells,
 * drag strokes with single-step undo, the eraser brush, variable stripping,
 * toolbar lockout while drawing, and small-board / note-array grids.
 *
 * In draw mode the preview renders via the static tile path, so each tile
 * carries data-row / data-col / data-cell-value (color cells hold the color
 * NAME, e.g. "blue"; blank cells hold a single space).
 */
import type { Page } from "@playwright/test";

import {
  API_URL,
  authHeaders,
  BOARD_2_LOCAL_API_PORT,
  BOARD_HOST,
  configureBoard,
  configureMockCloud,
  createPage,
  deleteAllPages,
  disablePlugin,
  enablePlugin,
  expect,
  getMockBoardState,
  resetToSingleBoard,
  setActivePage,
  suppressWizard,
  test,
} from "./helpers";

// Vestaboard character codes on the physical board.
const BLUE_CODE = 67;
const LETTER_A_CODE = 1;
const BLANK_CODE = 0;

/** Trigger an immediate main-loop refresh so active-page content reaches the board. */
async function forceRefresh(): Promise<void> {
  const res = await fetch(`${API_URL}/force-refresh`, { method: "POST", headers: authHeaders() });
  if (!res.ok) throw new Error(`force-refresh failed: ${res.status} ${await res.text()}`);
}

/** A tile locator scoped to the active draw surface. */
function tile(page: Page, row: number, col: number) {
  return page.locator(`[data-draw-surface="true"] [data-row="${row}"][data-col="${col}"]`);
}

/** Enter draw mode from the editor toolbar and wait for the draw surface. */
async function enterDrawMode(page: Page): Promise<void> {
  await page.getByTestId("draw-mode-toggle").click();
  await expect(page.locator('[data-draw-surface="true"]')).toBeVisible();
}

/** Pick a brush (color name or "eraser") from the inline toolbar swatches. */
async function pickBrush(page: Page, brush: string): Promise<void> {
  await page.getByTestId(`draw-color-${brush}`).click();
}

/** Pick a stamp character from the character dropdown. */
async function pickChar(page: Page, char: string): Promise<void> {
  await page.getByTestId("draw-char-dropdown").click();
  await page.locator(`[data-draw-char="${char}"]`).click();
}

/** Open the builder for a new page and wait for it to be interactive. */
async function gotoNewPage(page: Page): Promise<void> {
  await page.goto("/pages/new");
  await expect(page.getByText("Create Page").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("draw-mode-toggle")).toBeVisible({ timeout: 10_000 });
}

/** Open the builder for an existing page and wait for it to be interactive. */
async function gotoEditPage(page: Page, pageId: string): Promise<void> {
  await page.goto(`/pages/edit/${pageId}`);
  await expect(page.getByText("Edit Page").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("draw-mode-toggle")).toBeVisible({ timeout: 10_000 });
}

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
});

test.afterEach(async () => {
  await deleteAllPages();
  await resetToSingleBoard();
  // Some tests enable date_time to get template variables — leave it off.
  await disablePlugin("date_time").catch(() => {});
});

test.describe("Draw mode", () => {
  test("paint cells, save, and the painted colors reach the board", async ({ page }) => {
    test.setTimeout(60_000);
    await gotoNewPage(page);

    await enterDrawMode(page);
    // The text editor collapses while drawing (but stays mounted).
    await expect(page.locator('[contenteditable="true"]').first()).toBeHidden();

    await pickBrush(page, "blue");
    await tile(page, 1, 3).click();
    await tile(page, 4, 0).click();
    await expect(tile(page, 1, 3)).toHaveAttribute("data-cell-value", "blue");
    await expect(tile(page, 4, 0)).toHaveAttribute("data-cell-value", "blue");

    // Escape exits draw mode and restores the editor.
    await page.keyboard.press("Escape");
    await expect(page.locator('[data-draw-surface="true"]')).toHaveCount(0);
    await expect(page.locator('[contenteditable="true"]').first()).toBeVisible();

    const pageName = `Draw E2E ${Date.now()}`;
    await page.getByPlaceholder("My Custom Page").fill(pageName);
    const saveButton = page.getByRole("button", { name: "Save Page" }).or(page.getByRole("button", { name: /save/i }));
    await saveButton.first().click();
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });

    const res = await fetch(`${API_URL}/pages`, { headers: authHeaders() });
    const data = await res.json();
    const saved = data.pages.find((p: { name: string }) => p.name === pageName);
    expect(saved).toBeTruthy();

    await setActivePage(saved.id);
    await forceRefresh();
    await expect
      .poll(async () => (await getMockBoardState()).current_message?.[1]?.[3], { timeout: 20_000 })
      .toBe(BLUE_CODE);
    expect((await getMockBoardState()).current_message?.[4]?.[0]).toBe(BLUE_CODE);
  });

  test("drag stroke paints a row segment and one undo reverts it all", async ({ page }) => {
    await gotoNewPage(page);
    await enterDrawMode(page);
    await pickBrush(page, "red");

    const start = await tile(page, 2, 2).boundingBox();
    expect(start).toBeTruthy();
    await page.mouse.move(start!.x + start!.width / 2, start!.y + start!.height / 2);
    await page.mouse.down();
    for (const col of [3, 4, 5, 6]) {
      const box = await tile(page, 2, col).boundingBox();
      expect(box).toBeTruthy();
      await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2, { steps: 3 });
    }
    await page.mouse.up();

    for (const col of [2, 3, 4, 5, 6]) {
      await expect(tile(page, 2, col)).toHaveAttribute("data-cell-value", "red");
    }

    // The whole stroke is ONE undo step.
    await page.keyboard.press("Control+z");
    for (const col of [2, 3, 4, 5, 6]) {
      await expect(tile(page, 2, col)).toHaveAttribute("data-cell-value", " ");
    }
  });

  test("eraser clears a painted cell without touching its neighbor", async ({ page }) => {
    await gotoNewPage(page);
    await enterDrawMode(page);
    await pickBrush(page, "blue");

    await tile(page, 0, 5).click();
    await tile(page, 0, 7).click();
    await expect(tile(page, 0, 5)).toHaveAttribute("data-cell-value", "blue");
    await expect(tile(page, 0, 7)).toHaveAttribute("data-cell-value", "blue");

    await pickBrush(page, "eraser");
    await tile(page, 0, 5).click();

    await expect(tile(page, 0, 5)).toHaveAttribute("data-cell-value", " ");
    await expect(tile(page, 0, 7)).toHaveAttribute("data-cell-value", "blue");
  });

  test("painting a variable line strips the variable; undo restores it", async ({ page }) => {
    // Without an enabled plugin there are no known variables, and the editor
    // won't parse {{date_time.time}} into a variable node.
    await enablePlugin("date_time");
    const pageId = await createPage("Draw Var", ["HI {{date_time.time}}", "", "", "", "", ""]);
    await gotoEditPage(page, pageId);

    // The template's variable renders as one variable node in the editor.
    // (The React node view drops the serialized data-type="variable" attr,
    // but TipTap tags its wrapper with the node-variable class.)
    const variableNodes = page.locator('[contenteditable="true"] .node-variable');
    await expect(variableNodes).toHaveCount(1);

    await enterDrawMode(page);
    // The editor is hidden but stays mounted — the variable node is still in the DOM.
    await expect(variableNodes).toHaveCount(1);

    await pickBrush(page, "blue");
    await tile(page, 0, 0).click();
    await expect(tile(page, 0, 0)).toHaveAttribute("data-cell-value", "blue");
    // Painting a row converts it to a positional line: the variable is stripped.
    await expect(variableNodes).toHaveCount(0);

    await page.keyboard.press("Control+z");
    await expect(variableNodes).toHaveCount(1);
    await expect(tile(page, 0, 0)).toHaveAttribute("data-cell-value", "H", { timeout: 10_000 });
  });

  test("toolbar swaps to drawing controls while drawing and back on exit", async ({ page }) => {
    // The Variables dropdown only renders when variables exist.
    await enablePlugin("date_time");
    await gotoNewPage(page);

    const cutButton = page.getByRole("button", { name: "Cut", exact: true });
    const pasteButton = page.getByRole("button", { name: "Paste", exact: true });
    const alignButtons = [
      page.getByRole("button", { name: "Align left", exact: true }),
      page.getByRole("button", { name: "Align center", exact: true }),
      page.getByRole("button", { name: "Align right", exact: true }),
    ];
    const variablesTrigger = page.getByRole("button", { name: "Variables", exact: true });
    await expect(variablesTrigger).toBeVisible({ timeout: 10_000 });

    await enterDrawMode(page);
    // Content-editing controls are removed from the toolbar entirely...
    await expect(cutButton).toHaveCount(0);
    await expect(pasteButton).toHaveCount(0);
    for (const btn of alignButtons) {
      await expect(btn).toHaveCount(0);
    }
    await expect(variablesTrigger).toHaveCount(0);
    // ...replaced by the 8 inline color swatches, eraser, and char dropdown.
    for (const name of ["red", "orange", "yellow", "green", "blue", "violet", "white", "black"]) {
      await expect(page.getByTestId(`draw-color-${name}`)).toBeVisible();
    }
    await expect(page.getByTestId("draw-color-eraser")).toBeVisible();
    await expect(page.getByTestId("draw-char-dropdown")).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.locator('[data-draw-surface="true"]')).toHaveCount(0);
    // The editing toolbar returns; the drawing controls leave.
    await expect(cutButton).toBeVisible();
    await expect(pasteButton).toBeVisible();
    for (const btn of alignButtons) {
      await expect(btn).toBeVisible();
    }
    await expect(variablesTrigger).toBeVisible();
    await expect(page.getByTestId("draw-color-red")).toHaveCount(0);
    await expect(page.getByTestId("draw-color-eraser")).toHaveCount(0);
    await expect(page.getByTestId("draw-char-dropdown")).toHaveCount(0);
  });

  test("painting works to the bottom-right corner of a 3×15 Note board", async ({ page }) => {
    // Enable the Note device tab alongside flagship (mirrors note-pages.spec.ts).
    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ devices: ["flagship", "note"] }),
    });
    const pageId = await createPage("Note Draw", ["", "", ""], "note");
    await gotoEditPage(page, pageId);

    await enterDrawMode(page);
    await pickBrush(page, "blue");
    await tile(page, 2, 14).click();
    await expect(tile(page, 2, 14)).toHaveAttribute("data-cell-value", "blue");
  });

  test("painting works beyond single-note bounds on a 2×1 note array", async ({ page }) => {
    // Mirror the note-array setup: size the cloud mock and configure a 2×1
    // local note-array board whose tiles point at the mock's two listeners.
    await configureMockCloud(2, 1);
    const board = {
      name: "Local Array",
      device_type: "note_array",
      board_color: "black",
      enabled: true,
      api_mode: "local",
      notes_wide: 2,
      notes_tall: 1,
      tiles: [
        { row: 0, col: 0, host: BOARD_HOST, port: 7000, local_api_key: "test-key", enabled: true },
        { row: 0, col: 1, host: BOARD_HOST, port: BOARD_2_LOCAL_API_PORT, local_api_key: "test-key", enabled: true },
      ],
    };
    const boardRes = await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ boards: [board] }),
    });
    expect(boardRes.ok).toBe(true);

    const pageRes = await fetch(`${API_URL}/pages`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        name: "Array Draw",
        type: "template",
        template: ["", "", ""],
        device_type: "note_array",
        notes_wide: 2,
        notes_tall: 1,
      }),
    });
    expect(pageRes.ok).toBe(true);
    const pageId = (await pageRes.json()).page.id;

    await gotoEditPage(page, pageId);
    await enterDrawMode(page);
    await pickBrush(page, "blue");
    // Column 20 lives in the SECOND note of the 3×30 composite grid.
    await tile(page, 1, 20).click();
    await expect(tile(page, 1, 20)).toHaveAttribute("data-cell-value", "blue");
  });

  test("character stamping reaches the board; eraser removes a stamp", async ({ page }) => {
    test.setTimeout(60_000);
    await gotoNewPage(page);
    await enterDrawMode(page);

    // Pick "A" from the character dropdown and stamp two tiles.
    await pickChar(page, "A");
    await tile(page, 0, 2).click();
    await tile(page, 0, 4).click();
    await expect(tile(page, 0, 2)).toHaveAttribute("data-cell-value", "A");
    await expect(tile(page, 0, 4)).toHaveAttribute("data-cell-value", "A");

    // The eraser button clears one of the stamps.
    await pickBrush(page, "eraser");
    await tile(page, 0, 4).click();
    await expect(tile(page, 0, 4)).toHaveAttribute("data-cell-value", " ");
    await expect(tile(page, 0, 2)).toHaveAttribute("data-cell-value", "A");

    await page.keyboard.press("Escape");
    const pageName = `Stamp E2E ${Date.now()}`;
    await page.getByPlaceholder("My Custom Page").fill(pageName);
    const saveButton = page.getByRole("button", { name: "Save Page" }).or(page.getByRole("button", { name: /save/i }));
    await saveButton.first().click();
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });

    const res = await fetch(`${API_URL}/pages`, { headers: authHeaders() });
    const data = await res.json();
    const saved = data.pages.find((p: { name: string }) => p.name === pageName);
    expect(saved).toBeTruthy();

    await setActivePage(saved.id);
    await forceRefresh();
    await expect
      .poll(async () => (await getMockBoardState()).current_message?.[0]?.[2], { timeout: 20_000 })
      .toBe(LETTER_A_CODE);
    expect((await getMockBoardState()).current_message?.[0]?.[4]).toBe(BLANK_CODE);
  });
});
