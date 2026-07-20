/**
 * Mixed-device multi-board E2E: a Flagship board (6×22) and a Note board
 * (3×15) running side by side.
 *
 * The other multi-board specs run flagship+flagship; this one asserts the
 * fleet works when the boards are DIFFERENT shapes — at the hardware layer
 * (each board receives content sized for ITS device from one refresh) and
 * in the UI (the board selector switches cleanly between device types).
 *
 * Board 1 → mock port 7000 (flagship) · Board 2 → mock port 7001 (note).
 */
import {
  API_URL,
  authHeaders,
  configureBoard,
  createPage,
  createSchedule,
  deleteAllPages,
  deleteAllSchedules,
  deletePagesByDevice,
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

/** Unique single-word token so content-unchanged caches never skip a send. */
function uniq(prefix: string): string {
  return `${prefix}${Date.now() % 1_000_000}`;
}

async function forceRefresh(): Promise<void> {
  const res = await fetch(`${API_URL}/force-refresh`, { method: "POST", headers: authHeaders() });
  if (!res.ok) throw new Error(`force-refresh failed: ${res.status} ${await res.text()}`);
}

async function setScheduleEnabled(enabled: boolean, boardId: string): Promise<void> {
  const res = await fetch(`${API_URL}/schedules/enabled`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ enabled, board_id: boardId }),
  });
  if (!res.ok) throw new Error(`setScheduleEnabled failed: ${res.status}`);
}

function boardText(state: { current_message?: number[][] }): string {
  return gridToText(state.current_message).join("\n");
}

function allHistoryText(state: { history?: Array<{ characters?: number[][] }> }): string {
  return (state.history ?? []).map((h) => gridToText(h.characters).join("\n")).join("\n---\n");
}

test.describe("Mixed-device fleet: flagship + note", () => {
  let flagshipId: string;
  let noteId: string;

  test.beforeEach(async ({ page }) => {
    await ensureAuthForFetch();
    await configureBoard();
    await suppressWizard(page);
    await page.addInitScript(() => localStorage.removeItem("fiestaboard_current_board"));
    await deleteAllSchedules();
    await deleteAllPages();
    ({ board1Id: flagshipId, board2Id: noteId } = await ensureTwoBoardsWithConnections({
      board2DeviceType: "note",
      board1Name: "Living Room",
      board2Name: "Desk Note",
    }));
    await setScheduleEnabled(true, flagshipId);
    await setScheduleEnabled(true, noteId);
  });

  test.afterAll(async () => {
    await deleteAllSchedules();
    // Note pages first: deleting the last page auto-creates a Welcome typed
    // to the deleted page's device, and a note-typed Welcome would leak the
    // Note tab into later suites.
    await deletePagesByDevice("note");
    await deleteAllPages();
    await resetToSingleBoard();
  });

  test("one refresh delivers correctly-sized content to each device type", async () => {
    const tokenF = uniq("BIG");
    const tokenN = uniq("SMALL");
    const pageF = await createPage("Flagship Mixed", [tokenF, "", "SIX BY TWENTYTWO", "", "", ""], "flagship");
    const pageN = await createPage("Note Mixed", [tokenN, "THREE BY 15", ""], "note");
    await createSchedule(pageF, "00:00", "23:59", "all", flagshipId);
    await createSchedule(pageN, "00:00", "23:59", "all", noteId);

    await forceRefresh();

    // Flagship board received ITS page at flagship dimensions…
    await expect.poll(async () => boardText(await getMockBoardState()), { timeout: 15_000 }).toContain(tokenF);
    const state1 = await getMockBoardState();
    expect(state1.current_message).toHaveLength(6);
    expect(state1.current_message?.[0]).toHaveLength(22);

    // …and the note board received ITS page at note dimensions.
    await expect.poll(async () => boardText(await getMockBoardState2()), { timeout: 15_000 }).toContain(tokenN);
    const state2 = await getMockBoardState2();
    expect(state2.current_message).toHaveLength(3);
    expect(state2.current_message?.[0]).toHaveLength(15);

    // No cross-device leakage in either direction, ever.
    expect(allHistoryText(state1)).not.toContain(tokenN);
    expect(allHistoryText(state2)).not.toContain(tokenF);
  });

  test("board selector switches cleanly between a flagship and a note board", async ({ page }) => {
    const pageF = await createPage("Flagship Sched", [uniq("F"), "", "", "", "", ""], "flagship");
    const pageN = await createPage("Note Sched", [uniq("N"), "", ""], "note");
    await createSchedule(pageF, "07:00", "09:00", "all", flagshipId);
    await createSchedule(pageN, "20:00", "22:00", "all", noteId);

    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    const boardSelector = page
      .getByTestId("board-selector")
      .or(page.getByRole("combobox", { name: "Select board to manage" }))
      .filter({ visible: true })
      .first();
    await expect(boardSelector).toBeVisible({ timeout: 15_000 });
    await expect(boardSelector).toContainText("Living Room");
    await expect(page.getByText("07:00").first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("20:00")).toHaveCount(0);

    // Switch to the NOTE board — the view must swap completely, exactly as it
    // does between two flagship boards.
    await boardSelector.click();
    await page.getByRole("option", { name: "Desk Note" }).click();
    await expect(boardSelector).toContainText("Desk Note");
    await expect(page.getByText("20:00").first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("07:00")).toHaveCount(0);

    // And back.
    await boardSelector.click();
    await page.getByRole("option", { name: "Living Room" }).click();
    await expect(boardSelector).toContainText("Living Room");
    await expect(page.getByText("07:00").first()).toBeVisible({ timeout: 10_000 });
  });
});
