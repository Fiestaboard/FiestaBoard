import {
  API_URL,
  authHeaders,
  configureBoard,
  createPage,
  createSchedule,
  deleteAllPages,
  ensureTwoBoardsWithConnections,
  expect,
  resetToSingleBoard,
  setActivePage,
  setScheduleEnabled,
  test,
  waitForNoActiveDisplay,
} from "./helpers";

test("page cleanup unlinks schedule defaults on every board and leaves no scheduled display", async () => {
  await configureBoard();
  const { board1Id, board2Id } = await ensureTwoBoardsWithConnections();
  const pageIds = [];
  try {
    for (const boardId of [board1Id, board2Id]) {
      const pageId = await createPage(`Default for ${boardId}`, ["DEFAULT", "", "", "", "", ""]);
      pageIds.push(pageId);
      const response = await fetch(`${API_URL}/v1/boards/${boardId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ default_page_id: pageId, schedule_enabled: true }),
      });
      expect(response.ok, await response.text()).toBe(true);
      await createSchedule(pageId, "00:00", "23:59", "all", boardId);
    }

    await deleteAllPages({ strict: true, deleteSchedules: true });

    for (const boardId of [board1Id, board2Id]) {
      const response = await fetch(`${API_URL}/v1/boards/${boardId}`, { headers: authHeaders() });
      expect(response.ok).toBe(true);
      const board = await response.json();
      expect(board.default_page_id).toBeNull();
      expect(board.schedule_enabled).toBe(true);
    }
    for (const pageId of pageIds) {
      const response = await fetch(`${API_URL}/v1/pages/${pageId}`, { headers: authHeaders() });
      expect(response.status).toBe(404);
    }
    const schedules = await fetch(`${API_URL}/v1/schedules?board_id=*`, { headers: authHeaders() });
    expect(schedules.ok).toBe(true);
    expect((await schedules.json()).schedules).toEqual([]);
    await setActivePage(null);
    await waitForNoActiveDisplay();
  } finally {
    await setScheduleEnabled(false);
    await resetToSingleBoard();
    await deleteAllPages({ strict: true, deleteSchedules: true });
  }
});
