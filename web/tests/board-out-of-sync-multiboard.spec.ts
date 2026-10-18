/**
 * Another app wrote to a SECONDARY board (issue #1945, PR C).
 *
 * Board-state polling used to read the primary board only, so board 2 never
 * showed the out-of-sync banner. The one poll thread now reads every readable
 * hardware board, so an external write to board 2 surfaces on Home (with
 * board 2 selected) and on board 2's own display page — and only there.
 */
import type { Page } from "@playwright/test";

import {
  API_URL,
  authHeaders,
  createPage,
  deleteAllPages,
  ensureTwoBoardsWithConnections,
  expect,
  getMockBoardState2,
  gridToText,
  MOCK_BOARD_URL_2,
  mockBoardGrid,
  resetMockBoard,
  resetToSingleBoard,
  setScheduleEnabled,
  suppressWizard,
  test,
} from "./helpers";

function hiRed(): number[][] {
  const grid = Array.from({ length: 6 }, () => Array(22).fill(0));
  grid[0][0] = 8;
  grid[0][1] = 9;
  grid[0][2] = 63;
  return grid;
}

function uniqueWord(): string {
  return Array.from({ length: 6 }, () => String.fromCharCode(65 + Math.floor(Math.random() * 26))).join("");
}

async function setActivePageFor(boardId: string, pageId: string) {
  const res = await fetch(`${API_URL}/settings/active-page`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ page_id: pageId, board_id: boardId }),
  });
  if (!res.ok) throw new Error(`setActivePage(${boardId}) failed: ${res.status} ${await res.text()}`);
}

async function setLocalReadInterval(seconds: number) {
  const res = await fetch(`${API_URL}/settings/polling`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ board_read_interval_local: seconds }),
  });
  if (!res.ok) throw new Error(`polling failed: ${res.status}`);
}

async function boardState(boardId: string) {
  const res = await fetch(`${API_URL}/board/current-message?board_id=${boardId}`, { headers: authHeaders() });
  return res.json();
}

async function selectBoard(page: Page, name: string) {
  const switcher = page
    .getByTestId("board-selector")
    .or(page.getByRole("combobox", { name: "Select board to manage" }))
    .filter({ visible: true })
    .first();
  await expect(switcher).toBeVisible({ timeout: 15_000 });
  await switcher.click();
  await page.getByRole("option", { name }).click();
  await expect(switcher).toContainText(name);
}

const banner = (page: Page) => page.getByTestId("board-out-of-sync");

test.beforeEach(async ({ page }) => {
  await suppressWizard(page);
  // Manual mode: a schedule left on by another spec would repaint the board.
  await setScheduleEnabled(false);
  await deleteAllPages();
});

test.afterEach(async () => {
  await setLocalReadInterval(30);
  await deleteAllPages();
  await resetToSingleBoard();
  await resetMockBoard();
});

test("another app writes board 2 → its banner, its geometry, and an install-wide Restore", async ({ page }) => {
  test.setTimeout(120_000);
  const { board1Id, board2Id } = await ensureTwoBoardsWithConnections({
    board1Name: "Living Room",
    board2Name: "Kitchen",
  });
  await setLocalReadInterval(20);

  const text1 = `ONE ${uniqueWord()}`;
  const text2 = `TWO ${uniqueWord()}`;
  await setActivePageFor(board1Id, await createPage(`One ${Date.now()}`, [text1, "", "", "", "", ""]));
  await setActivePageFor(board2Id, await createPage(`Two ${Date.now()}`, [text2, "", "", "", "", ""]));
  await expect
    .poll(async () => gridToText(mockBoardGrid(await getMockBoardState2()))[0], { timeout: 15_000 })
    .toContain(text2);
  const board2Page = mockBoardGrid(await getMockBoardState2());

  // Another app writes board 2 only.
  const res = await fetch(`${MOCK_BOARD_URL_2}/local-api/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Vestaboard-Local-Api-Key": "test-key" },
    body: JSON.stringify({ characters: hiRed() }),
  });
  expect(res.ok).toBe(true);

  // The poll reads board 2 on its own; no forced read.
  await expect
    .poll(
      async () => {
        const state = await boardState(board2Id);
        return JSON.stringify(state.characters) !== JSON.stringify(state.expected_characters);
      },
      { timeout: 45_000, intervals: [2_000] },
    )
    .toBe(true);

  // Home, board 2 selected.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });
  await selectBoard(page, "Kitchen");
  await expect(banner(page)).toBeVisible({ timeout: 15_000 });
  await expect(banner(page)).toContainText("Restore resends pages to every display.");

  // Board 2's own display page: the banner sits under "Now showing".
  await page.goto(`/displays/${board2Id}`);
  const onDisplay = banner(page);
  await expect(onDisplay).toBeVisible({ timeout: 15_000 });
  const created = page.waitForRequest((r) => r.url().includes("/api/v1/pages") && r.method() === "POST");
  await onDisplay.getByRole("button", { name: "Save as page" }).click();
  const body = (await created).postDataJSON() as { device_type: string; template: string[] };
  expect(body.device_type).toBe("flagship");
  expect(body.template[0]).toBe("HI{{red}}");

  // Board 1 (the primary) shows nothing, on Home or on its display page.
  await page.goto(`/displays/${board1Id}`);
  await expect(page.getByText("Now showing")).toBeVisible({ timeout: 15_000 });
  await page.waitForTimeout(2_000);
  await expect(banner(page)).toHaveCount(0);
  await page.goto("/");
  await selectBoard(page, "Living Room");
  await page.waitForTimeout(2_000);
  await expect(banner(page)).toHaveCount(0);

  // Restore from board 2: install-wide, and the toast says so.
  await selectBoard(page, "Kitchen");
  await expect(banner(page)).toBeVisible({ timeout: 15_000 });
  await banner(page).getByRole("button", { name: "Restore" }).click();
  await expect(page.getByText("Pages resent to every display")).toBeVisible({ timeout: 10_000 });
  await expect.poll(async () => mockBoardGrid(await getMockBoardState2()), { timeout: 10_000 }).toEqual(board2Page);
});
