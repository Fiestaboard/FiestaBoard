/**
 * Multi-board output & consistency E2E.
 *
 * These tests configure TWO boards with real (mock) Local-API connections —
 * board 1 → mock port 7000, board 2 → mock port 7001 — and assert at the
 * hardware layer: what each physical board actually received. This is the
 * layer the older multi-board specs (multi-board.spec.ts,
 * multi-board-schedule.spec.ts) never reach; they verify settings/schedule
 * CRUD and UI filtering only.
 *
 * Requires the mock board server to listen on both ports (PORTS=7000,7001 —
 * docker-compose.dev.yml already does; CI mock containers are configured in
 * ci.yml / integration-tests.yml).
 *
 * Known product gaps are encoded as test.fixme so they flip to failures the
 * moment the behavior lands and the assertions can be activated:
 *  - The display engine only drives boards[0] (src/main.py) — per-board
 *    driving is epic #1241.
 *  - /settings/board mutations (add/remove/update) never reinitialize the
 *    board client, so output keeps targeting a removed board until restart.
 */
import type { Locator, Page } from "@playwright/test";

import {
  API_URL,
  authHeaders,
  configureBoard,
  createPage,
  createSchedule,
  deleteAllPages,
  deleteAllSchedules,
  ensureAuthForFetch,
  ensureTwoBoardsWithConnections,
  expect,
  getMockBoardState,
  getMockBoardState2,
  gridToText,
  resetToSingleBoard,
  suppressWizard,
  test,
} from "./helpers";

/** Unique single-word token so the content-unchanged cache never skips a send. */
function uniq(prefix: string): string {
  return `${prefix}${Date.now() % 1_000_000}`;
}

/** Trigger the schedule-resolution-and-send path synchronously (no cache skip at the board layer). */
async function forceRefresh(): Promise<void> {
  const res = await fetch(`${API_URL}/force-refresh`, { method: "POST", headers: authHeaders() });
  if (!res.ok) throw new Error(`force-refresh failed: ${res.status} ${await res.text()}`);
}

/** Send a page straight to the board (manual posting path). */
async function sendPageToBoard(pageId: string): Promise<{ sent_to_board?: boolean; paused?: boolean }> {
  const res = await fetch(`${API_URL}/pages/${pageId}/send?target=board`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`send page failed: ${res.status} ${await res.text()}`);
  return res.json();
}

/**
 * The board switcher control, wherever the current UI puts it: the schedule
 * toolbar Select (data-testid="board-selector") or the global sidebar
 * selector on the multi-board branch (combobox "Select board to manage").
 * Both render only when more than one board exists.
 */
function boardSwitcher(page: Page): Locator {
  return page
    .getByTestId("board-selector")
    .or(page.getByRole("combobox", { name: "Select board to manage" }))
    .filter({ visible: true })
    .first();
}

/** All rows of the mock board's current message as decoded text. */
function boardText(state: { current_message?: number[][] }): string {
  return gridToText(state.current_message).join("\n");
}

/** Decoded text of every message the mock board ever received. */
function allHistoryText(state: { history?: Array<{ characters?: number[][] }> }): string {
  return (state.history ?? []).map((h) => gridToText(h.characters).join("\n")).join("\n---\n");
}

async function setBoardPaused(boardId: string, paused: boolean): Promise<void> {
  const res = await fetch(`${API_URL}/settings/board/${boardId}/pause`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ paused }),
  });
  if (!res.ok) throw new Error(`setBoardPaused failed: ${res.status}`);
}

async function setScheduleEnabled(enabled: boolean, boardId?: string): Promise<void> {
  const body: Record<string, unknown> = { enabled };
  if (boardId) body.board_id = boardId;
  const res = await fetch(`${API_URL}/schedules/enabled`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`setScheduleEnabled failed: ${res.status}`);
}

test.describe("Multi-board output isolation", () => {
  let board1Id: string;
  let board2Id: string;

  test.beforeEach(async () => {
    await ensureAuthForFetch();
    await configureBoard();
    await deleteAllSchedules();
    await deleteAllPages();
    ({ board1Id, board2Id } = await ensureTwoBoardsWithConnections());
    // Schedule mode on for the primary board so /force-refresh resolves schedules.
    await setScheduleEnabled(true, board1Id);
  });

  test.afterAll(async () => {
    await deleteAllSchedules();
    await deleteAllPages();
    await resetToSingleBoard();
  });

  test("manual page send reaches board 1's hardware and never board 2's", async () => {
    const token = uniq("ALPHA");
    const pageId = await createPage("Manual Send Target", [token, "", "", "", "", ""]);

    const before1 = (await getMockBoardState()).message_count ?? 0;
    const before2 = (await getMockBoardState2()).message_count ?? 0;

    await sendPageToBoard(pageId);

    await expect
      .poll(async () => (await getMockBoardState()).message_count, { timeout: 10_000 })
      .toBeGreaterThan(before1);
    const state1 = await getMockBoardState();
    expect(boardText(state1)).toContain(token);

    // Board 2 must not have received anything.
    const state2 = await getMockBoardState2();
    expect(state2.message_count ?? 0).toBe(before2);
  });

  test("board 1's scheduled page is delivered to board 1's hardware", async () => {
    const token = uniq("KITCHEN");
    const pageId = await createPage("B1 Scheduled", [token, "", "", "", "", ""]);
    await createSchedule(pageId, "00:00", "23:59", "all", board1Id);

    await forceRefresh();

    await expect.poll(async () => boardText(await getMockBoardState()), { timeout: 10_000 }).toContain(token);

    // Nothing leaked to board 2.
    const state2 = await getMockBoardState2();
    expect(state2.message_count ?? 0).toBe(0);
  });

  test("a schedule scoped to board 2 never leaks onto board 1", async () => {
    const token1 = uniq("HOME");
    const token2 = uniq("OFFICE");
    const page1 = await createPage("B1 Page", [token1, "", "", "", "", ""]);
    const page2 = await createPage("B2 Page", [token2, "", "", "", "", ""]);
    await createSchedule(page1, "00:00", "23:59", "all", board1Id);
    await createSchedule(page2, "00:00", "23:59", "all", board2Id);

    await forceRefresh();

    // Board 1 shows ITS schedule's page…
    await expect.poll(async () => boardText(await getMockBoardState()), { timeout: 10_000 }).toContain(token1);
    // …and board 2's content never appeared anywhere in board 1's history.
    const state1 = await getMockBoardState();
    expect(allHistoryText(state1)).not.toContain(token2);
  });

  // KNOWN GAP (epic #1241): the display engine builds a client for boards[0]
  // only (src/main.py _build_board_clients), so board 2 never receives its
  // scheduled content. Activate this test when per-board driving lands.
  test.fixme("board 2 receives its scheduled content on its own hardware", async () => {
    const token2 = uniq("SECOND");
    const page2 = await createPage("B2 Own Page", [token2, "", "", "", "", ""]);
    await createSchedule(page2, "00:00", "23:59", "all", board2Id);
    await setScheduleEnabled(true, board2Id);

    await forceRefresh();

    await expect.poll(async () => boardText(await getMockBoardState2()), { timeout: 15_000 }).toContain(token2);
  });

  // KNOWN GAP: /settings/board mutations never call reinitialize_board_client
  // (only legacy /config/board does — see src/api_server.py), so after the
  // primary board is removed, output still targets the REMOVED board's
  // connection until the backend restarts. Activate when fixed.
  test.fixme("removing the primary board redirects output to the promoted board", async () => {
    const token2 = uniq("PROMOTED");
    const page2 = await createPage("B2 Promoted Page", [token2, "", "", "", "", ""]);
    await createSchedule(page2, "00:00", "23:59", "all", board2Id);
    await setScheduleEnabled(true, board2Id);
    const before1 = (await getMockBoardState()).message_count ?? 0;

    const res = await fetch(`${API_URL}/settings/board/${board1Id}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    expect(res.ok).toBe(true);

    await forceRefresh();

    // Output must land on the promoted board (now the only board)…
    await expect.poll(async () => boardText(await getMockBoardState2()), { timeout: 15_000 }).toContain(token2);
    // …not on the removed board's old connection.
    expect((await getMockBoardState()).message_count ?? 0).toBe(before1);
  });

  test("pausing board 1 blocks its output without disturbing board 2 state", async () => {
    const token = uniq("PAUSED");
    const pageId = await createPage("Pause Test Page", [token, "", "", "", "", ""]);
    await createSchedule(pageId, "00:00", "23:59", "all", board1Id);

    await setBoardPaused(board1Id, true);
    const before1 = (await getMockBoardState()).message_count ?? 0;

    // Neither the schedule path nor the manual path may reach the board.
    await forceRefresh();
    const sendResult = await sendPageToBoard(pageId);
    expect(sendResult.sent_to_board ?? false).toBe(false);
    expect((await getMockBoardState()).message_count ?? 0).toBe(before1);

    // Board 2's per-board config is untouched by board 1's pause.
    const settingsRes = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
    const settings = await settingsRes.json();
    const b2 = (settings.boards ?? []).find((b: { id: string }) => b.id === board2Id);
    expect(b2?.paused ?? false).toBe(false);

    // Unpause → output flows again.
    await setBoardPaused(board1Id, false);
    await forceRefresh();
    await expect.poll(async () => boardText(await getMockBoardState()), { timeout: 10_000 }).toContain(token);
  });

  test("per-board schedule lists are disjoint, complete, and independently configured", async () => {
    const pageA = await createPage("Sched A", [uniq("A"), "", "", "", "", ""]);
    const pageB = await createPage("Sched B", [uniq("B"), "", "", "", "", ""]);
    const pageC = await createPage("Sched C", [uniq("C"), "", "", "", "", ""]);
    const s1 = await createSchedule(pageA, "06:00", "12:00", "all", board1Id);
    const s2 = await createSchedule(pageB, "12:00", "18:00", "all", board1Id);
    const s3 = await createSchedule(pageC, "06:00", "18:00", "all", board2Id);

    const list = async (boardId: string) => {
      const res = await fetch(`${API_URL}/schedules?board_id=${boardId}`, { headers: authHeaders() });
      return res.json();
    };

    const b1 = await list(board1Id);
    const b2 = await list(board2Id);
    const all = await list("*");

    const b1Ids = b1.schedules.map((s: { id: string }) => s.id).sort();
    const b2Ids = b2.schedules.map((s: { id: string }) => s.id).sort();
    const allIds = all.schedules.map((s: { id: string }) => s.id).sort();

    // Disjoint and complete: each schedule belongs to exactly one board.
    expect(b1Ids).toEqual([s1, s2].sort());
    expect(b2Ids).toEqual([s3]);
    expect(allIds).toEqual([s1, s2, s3].sort());
    expect(b1Ids.filter((id: string) => b2Ids.includes(id))).toEqual([]);

    const setDefaultPage = async (pageId: string | null, boardId: string) => {
      await fetch(`${API_URL}/schedules/default-page`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ page_id: pageId, board_id: boardId }),
      });
    };

    // Per-board default page and enabled flag are independent. Set both
    // explicitly rather than assuming a clean slate — earlier tests on this
    // container may have left a default page behind.
    // (schedule_enabled defaults to false for a new board — see src/devices.py —
    // so enable board 2 explicitly before asserting flag independence.)
    await setDefaultPage(pageA, board1Id);
    await setDefaultPage(pageC, board2Id);
    await setScheduleEnabled(true, board2Id);
    await setScheduleEnabled(false, board1Id);

    const b1After = await list(board1Id);
    const b2After = await list(board2Id);
    expect(b1After.default_page_id).toBe(pageA);
    expect(b2After.default_page_id).toBe(pageC);
    expect(b1After.enabled).toBe(false);
    expect(b2After.enabled).toBe(true);

    // Clearing board 1's default leaves board 2's untouched. (A cleared
    // per-board default falls back to the legacy global default — see
    // src/schedules/storage.py — so board 1's own value isn't asserted here.)
    await setDefaultPage(null, board1Id);
    expect((await list(board2Id)).default_page_id).toBe(pageC);

    await setDefaultPage(null, board2Id);
    await setScheduleEnabled(true, board1Id);
  });

  test("deleting a board leaves no schedules that activate on the surviving board", async () => {
    const token1 = uniq("SURVIVOR");
    const token2 = uniq("GHOST");
    const page1 = await createPage("Survivor Page", [token1, "", "", "", "", ""]);
    const page2 = await createPage("Ghost Page", [token2, "", "", "", "", ""]);
    await createSchedule(page1, "00:00", "23:59", "all", board1Id);
    await createSchedule(page2, "00:00", "23:59", "all", board2Id);

    const res = await fetch(`${API_URL}/settings/board/${board2Id}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    expect(res.ok).toBe(true);

    // The surviving board's schedule list must not contain the ghost.
    const listRes = await fetch(`${API_URL}/schedules?board_id=${board1Id}`, { headers: authHeaders() });
    const list = await listRes.json();
    const pageIds = list.schedules.map((s: { page_id: string }) => s.page_id);
    expect(pageIds).toContain(page1);
    expect(pageIds).not.toContain(page2);

    // And the deleted board's schedule never activates on board 1's hardware.
    await forceRefresh();
    await expect.poll(async () => boardText(await getMockBoardState()), { timeout: 10_000 }).toContain(token1);
    expect(allHistoryText(await getMockBoardState())).not.toContain(token2);
  });
});

test.describe("Multi-board UI clarity when switching boards", () => {
  let board1Id: string;
  let board2Id: string;

  test.beforeEach(async ({ page }) => {
    await ensureAuthForFetch();
    await configureBoard();
    await suppressWizard(page);
    // Boards are recreated with fresh ids each test — drop any persisted
    // current-board selection so the app falls back to the first board.
    await page.addInitScript(() => localStorage.removeItem("fiestaboard_current_board"));
    await deleteAllSchedules();
    await deleteAllPages();
    ({ board1Id, board2Id } = await ensureTwoBoardsWithConnections({
      board1Name: "Kitchen",
      board2Name: "Office",
    }));
    await setScheduleEnabled(true, board1Id);
    await setScheduleEnabled(true, board2Id);
  });

  test.afterAll(async () => {
    await deleteAllSchedules();
    await deleteAllPages();
    await resetToSingleBoard();
  });

  test("board selector names the selected board and fully swaps the schedule view", async ({ page }) => {
    const pageK = await createPage("Kitchen Page");
    const pageO = await createPage("Office Page");
    await createSchedule(pageK, "07:00", "09:00", "all", board1Id);
    await createSchedule(pageO, "20:00", "22:00", "all", board2Id);

    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    // The selector must make the current board unambiguous by NAME.
    const boardSelector = boardSwitcher(page);
    await expect(boardSelector).toBeVisible({ timeout: 15_000 });
    await expect(boardSelector).toContainText("Kitchen");

    // Kitchen's schedule is shown; Office's is NOT mixed in.
    await expect(page.getByText("07:00").first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("20:00")).toHaveCount(0);

    // Switch to Office.
    await boardSelector.click();
    await page.getByRole("option", { name: "Office" }).click();

    // Selector reflects the switch and the view swaps completely.
    await expect(boardSelector).toContainText("Office");
    await expect(page.getByText("20:00").first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("07:00")).toHaveCount(0);
  });

  test("per-board schedule-enabled toggle follows the selected board", async ({ page }) => {
    // Kitchen enabled, Office disabled — the toggle must track the selection.
    await setScheduleEnabled(true, board1Id);
    await setScheduleEnabled(false, board2Id);

    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    const toggle = page.getByTestId("schedule-enabled-toggle");
    await expect(toggle).toBeVisible({ timeout: 10_000 });
    await expect(toggle).toHaveAttribute("aria-checked", "true");

    const boardSelector = boardSwitcher(page);
    await boardSelector.click();
    await page.getByRole("option", { name: "Office" }).click();

    await expect(toggle).toHaveAttribute("aria-checked", "false", { timeout: 10_000 });

    // Switching back restores Kitchen's state — no cross-board bleed.
    await boardSelector.click();
    await page.getByRole("option", { name: "Kitchen" }).click();
    await expect(toggle).toHaveAttribute("aria-checked", "true", { timeout: 10_000 });
  });
});
