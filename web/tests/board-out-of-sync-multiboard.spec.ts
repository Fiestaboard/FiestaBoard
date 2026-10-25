/**
 * Another app wrote to a SECONDARY board (issue #1945, PR C).
 *
 * Board-state polling used to read the primary board only, so board 2 never
 * showed the out-of-sync banner. The one poll thread now reads every readable
 * hardware board, so an external write to board 2 surfaces on Home (with
 * board 2 selected) and on board 2's own display page — and only there.
 *
 * Restore is per board (#2354): restoring board 2 writes board 2 only.
 * Board 2's "Restore automatically" is turned off here so the other app's
 * content stays up until the test restores it by hand.
 */
import type { Page } from "@playwright/test";

import {
  API_URL,
  authHeaders,
  createPage,
  deleteAllPages,
  ensureTwoBoardsWithConnections,
  expect,
  getMockBoardState,
  getMockBoardState2,
  gridToText,
  MOCK_BOARD_URL_2,
  mockBoardGrid,
  resetMockBoard,
  resetToSingleBoard,
  setAutoRestore,
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
  // A spec earlier on this backend may have stopped the display loop, which
  // also stops the board-state poll.
  await fetch(`${API_URL}/start`, { method: "POST", headers: authHeaders() });
  await deleteAllPages();
});

test.afterEach(async () => {
  await setLocalReadInterval(30);
  await deleteAllPages();
  await resetToSingleBoard();
  await resetMockBoard();
});

test("another app writes board 2 → its banner, its geometry, and a Restore of board 2 only", async ({ page }) => {
  test.setTimeout(120_000);
  const { board1Id, board2Id } = await ensureTwoBoardsWithConnections({
    board1Name: "Living Room",
    board2Name: "Kitchen",
  });
  // Keep the other app's content on board 2 until Restore (resetToSingleBoard
  // in afterEach replaces both boards, so nothing to undo).
  await setAutoRestore(board2Id, false);
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
  await expect(banner(page)).toHaveAttribute("data-face", "out-of-sync");
  // The old install-wide hold line is gone: Restore no longer touches board 1.
  await expect(banner(page)).not.toContainText("every display");

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

  // Restore from board 2: board 2's own restore, and board 1 is not written.
  await selectBoard(page, "Kitchen");
  await expect(banner(page)).toBeVisible({ timeout: 15_000 });
  const board1Writes = (await getMockBoardState()).message_count ?? 0;
  const restoreRequests: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && /\/api\/(force-refresh|v1\/boards\/[^/]+\/restore)/.test(r.url())) {
      restoreRequests.push(new URL(r.url()).pathname);
    }
  });
  const restored = page.waitForResponse(
    (r) => r.url().includes(`/api/v1/boards/${board2Id}/restore`) && r.request().method() === "POST",
  );
  await banner(page).getByRole("button", { name: "Restore" }).click();
  const response = await restored;
  expect(response.status()).toBe(200);
  expect(await response.json()).toMatchObject({ board_id: board2Id, sent: true });
  await expect(page.getByText("Board restored")).toBeVisible({ timeout: 10_000 });
  await expect.poll(async () => mockBoardGrid(await getMockBoardState2()), { timeout: 10_000 }).toEqual(board2Page);
  // Past the banner's confirming refetch: still only board 2's restore, and
  // board 1's listener received nothing.
  await page.waitForTimeout(5_000);
  expect(restoreRequests).toEqual([`/api/v1/boards/${board2Id}/restore`]);
  expect((await getMockBoardState()).message_count ?? 0).toBe(board1Writes);
});
