/**
 * Note-array output E2E: the multi-board feature set, proven for Vestaboard
 * Note ARRAYS at the hardware layer.
 *
 * Arrays speak the Cloud API (X-Vestaboard-Token), mocked by
 * integration-tests/mock-cloud/server.py — the backend reaches it via
 * VESTABOARD_CLOUD_API_URL; tests read its state via MOCK_CLOUD_URL. The
 * mock validates incoming grids against its configured size, so a
 * wrong-sized send FAILS, not just looks odd.
 *
 * Covered here:
 *  - solo array installs: an array as the ONLY board receives manual sends
 *    and scheduled content at its exact W×H geometry
 *  - every array geometry class: all five named presets, 1×1, the 8-wide /
 *    8-tall / 8×8 extremes, and a non-preset size
 *  - mixed fleet: flagship + array driven independently in one refresh,
 *    with pause isolation — mirroring multi-board-output.spec.ts
 */
import {
  API_URL,
  authHeaders,
  BOARD_HOST,
  configureBoard,
  configureMockCloud,
  createPage,
  deleteAllPages,
  deleteAllSchedules,
  deletePagesByDevice,
  ensureAuthForFetch,
  expect,
  getMockBoardState,
  getMockCloudState,
  gridToText,
  resetMockBoard,
  resetMockCloud,
  resetToSingleBoard,
  test,
} from "./helpers";

const NOTE_ROWS = 3;
const NOTE_COLS = 15;

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

async function createSchedule(pageId: string, boardId: string): Promise<void> {
  const res = await fetch(`${API_URL}/schedules`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      page_id: pageId,
      start_time: "00:00",
      end_time: "23:59",
      day_pattern: "all",
      board_id: boardId,
    }),
  });
  if (!res.ok) throw new Error(`createSchedule failed: ${res.status}`);
}

/** Create a note_array page sized W×H with `token` on its first line. */
async function createArrayPage(name: string, token: string, notesWide: number, notesTall: number): Promise<string> {
  const rows = notesTall * NOTE_ROWS;
  const template = Array.from({ length: rows }, (_, i) => (i === 0 ? token : ""));
  const res = await fetch(`${API_URL}/pages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      name,
      type: "template",
      template,
      device_type: "note_array",
      notes_wide: notesWide,
      notes_tall: notesTall,
    }),
  });
  if (!res.ok) throw new Error(`createArrayPage failed: ${res.status} ${await res.text()}`);
  const data = await res.json();
  return data.page.id;
}

/** Configure the fleet: optionally a flagship (mock port 7000) + one array. */
async function configureBoards(opts: {
  flagship: boolean;
  notesWide: number;
  notesTall: number;
}): Promise<{ flagshipId?: string; arrayId: string }> {
  const boards: Record<string, unknown>[] = [];
  if (opts.flagship) {
    boards.push({
      name: "Flagship",
      device_type: "flagship",
      board_color: "black",
      enabled: true,
      api_mode: "local",
      host: BOARD_HOST,
      port: 7000,
      local_api_key: "test-key",
    });
  }
  boards.push({
    name: "Array",
    device_type: "note_array",
    board_color: "white",
    enabled: true,
    api_mode: "cloud",
    notes_wide: opts.notesWide,
    notes_tall: opts.notesTall,
    // Unique per call: the backend's ≥15s note-array send throttle is keyed
    // by token at module level, so a shared token would suppress every
    // test's send after the first one.
    note_array_token: `test-array-token-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
  });
  const res = await fetch(`${API_URL}/settings/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ boards }),
  });
  if (!res.ok) throw new Error(`configureBoards failed: ${res.status} ${await res.text()}`);
  const data = await res.json();
  const saved = data.settings?.boards ?? [];
  return opts.flagship ? { flagshipId: saved[0].id, arrayId: saved[1].id } : { arrayId: saved[0].id };
}

function cloudText(state: { current_grid?: number[][] }): string {
  return gridToText(state.current_grid).join("\n");
}

test.describe("Note-array output", () => {
  test.beforeEach(async () => {
    await ensureAuthForFetch();
    await configureBoard();
    await deleteAllSchedules();
    await deleteAllPages();
    await resetMockCloud();
    await resetMockBoard();
  });

  test.afterAll(async () => {
    await deleteAllSchedules();
    await deletePagesByDevice("note_array");
    await deleteAllPages();
    await resetToSingleBoard();
  });

  test("solo array install: scheduled content reaches the array at its exact size", async () => {
    await configureMockCloud(2, 2); // 6 × 30
    const { arrayId } = await configureBoards({ flagship: false, notesWide: 2, notesTall: 2 });
    await setScheduleEnabled(true, arrayId);

    const token = uniq("SOLOARRAY");
    const pageId = await createArrayPage("Solo Array Page", token, 2, 2);
    await createSchedule(pageId, arrayId);

    await forceRefresh();

    await expect.poll(async () => cloudText(await getMockCloudState()), { timeout: 15_000 }).toContain(token);
    const state = await getMockCloudState();
    expect(state.current_grid).toHaveLength(6);
    expect(state.current_grid?.[0]).toHaveLength(30);
  });

  test("solo array install: manual page send reaches the array hardware", async () => {
    await configureMockCloud(2, 1); // 3 × 30
    const { arrayId } = await configureBoards({ flagship: false, notesWide: 2, notesTall: 1 });
    await setScheduleEnabled(false, arrayId);

    const token = uniq("MANUAL");
    const pageId = await createArrayPage("Manual Array Page", token, 2, 1);
    const res = await fetch(`${API_URL}/pages/${pageId}/send?target=board`, { method: "POST", headers: authHeaders() });
    if (!res.ok) throw new Error(`send failed: ${res.status} ${await res.text()}`);

    await expect.poll(async () => cloudText(await getMockCloudState()), { timeout: 15_000 }).toContain(token);
    const state = await getMockCloudState();
    expect(state.current_grid).toHaveLength(3);
    expect(state.current_grid?.[0]).toHaveLength(30);
  });

  // Every geometry class the product supports: the five named presets, the
  // 1×1 minimum, the MAX_NOTES_PER_AXIS extremes, and a non-preset size.
  // The mock VALIDATES incoming grids against the configured size, so a
  // mis-sized send is a hard failure, not a silent mismatch.
  const SIZES: Array<{ label: string; wide: number; tall: number }> = [
    { label: "1x1 single note", wide: 1, tall: 1 },
    { label: "2 side-by-side", wide: 2, tall: 1 },
    { label: "4 side-by-side", wide: 4, tall: 1 },
    { label: "2 stacked", wide: 1, tall: 2 },
    { label: "4 stacked", wide: 1, tall: 4 },
    { label: "2x2 grid", wide: 2, tall: 2 },
    { label: "3x2 non-preset", wide: 3, tall: 2 },
    { label: "8 wide max", wide: 8, tall: 1 },
    { label: "8 tall max", wide: 1, tall: 8 },
    { label: "8x8 maximum", wide: 8, tall: 8 },
  ];

  for (const size of SIZES) {
    test(`array size ${size.label}: delivers a ${size.tall * NOTE_ROWS}×${size.wide * NOTE_COLS} grid`, async () => {
      await configureMockCloud(size.wide, size.tall);
      const { arrayId } = await configureBoards({ flagship: false, notesWide: size.wide, notesTall: size.tall });
      await setScheduleEnabled(true, arrayId);

      const token = uniq("SZ");
      const pageId = await createArrayPage(`Size ${size.label}`, token, size.wide, size.tall);
      await createSchedule(pageId, arrayId);

      await forceRefresh();

      await expect.poll(async () => cloudText(await getMockCloudState()), { timeout: 15_000 }).toContain(token);
      const state = await getMockCloudState();
      expect(state.current_grid).toHaveLength(size.tall * NOTE_ROWS);
      expect(state.current_grid?.[0]).toHaveLength(size.wide * NOTE_COLS);
    });
  }

  test("mixed fleet: flagship and array each receive their own content in one refresh", async () => {
    await configureMockCloud(2, 2);
    const { flagshipId, arrayId } = await configureBoards({ flagship: true, notesWide: 2, notesTall: 2 });
    await setScheduleEnabled(true, flagshipId!);
    await setScheduleEnabled(true, arrayId);

    const tokenF = uniq("FLAG");
    const tokenA = uniq("ARRAY");
    const pageF = await createPage("Flagship vs Array", [tokenF, "", "", "", "", ""], "flagship");
    const pageA = await createArrayPage("Array vs Flagship", tokenA, 2, 2);
    await createSchedule(pageF, flagshipId!);
    await createSchedule(pageA, arrayId);

    await forceRefresh();

    // Flagship got its 6×22 content on the Local-API mock…
    await expect
      .poll(async () => gridToText((await getMockBoardState()).current_message).join("\n"), { timeout: 15_000 })
      .toContain(tokenF);
    // …the array got its 6×30 content on the Cloud mock…
    await expect.poll(async () => cloudText(await getMockCloudState()), { timeout: 15_000 }).toContain(tokenA);
    const cloud = await getMockCloudState();
    expect(cloud.current_grid).toHaveLength(6);
    expect(cloud.current_grid?.[0]).toHaveLength(30);
    // …and neither leaked into the other.
    expect(cloudText(cloud)).not.toContain(tokenF);
    const board = await getMockBoardState();
    expect(gridToText(board.current_message).join("\n")).not.toContain(tokenA);
  });

  test("pausing the array blocks its output while the flagship keeps running", async () => {
    await configureMockCloud(2, 1);
    const { flagshipId, arrayId } = await configureBoards({ flagship: true, notesWide: 2, notesTall: 1 });
    await setScheduleEnabled(true, flagshipId!);
    await setScheduleEnabled(true, arrayId);

    const tokenF = uniq("STILLON");
    const tokenA = uniq("PAUSEDARR");
    const pageF = await createPage("Flagship While Paused", [tokenF, "", "", "", "", ""], "flagship");
    const pageA = await createArrayPage("Paused Array Page", tokenA, 2, 1);
    await createSchedule(pageF, flagshipId!);
    await createSchedule(pageA, arrayId);

    const pauseRes = await fetch(`${API_URL}/settings/board/${arrayId}/pause`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ paused: true }),
    });
    expect(pauseRes.ok).toBe(true);
    const before = (await getMockCloudState()).request_count ?? 0;

    await forceRefresh();

    // Flagship delivered; the paused array's cloud mock saw NO new sends.
    await expect
      .poll(async () => gridToText((await getMockBoardState()).current_message).join("\n"), { timeout: 15_000 })
      .toContain(tokenF);
    expect((await getMockCloudState()).request_count ?? 0).toBe(before);

    // Unpause → the array catches up.
    await fetch(`${API_URL}/settings/board/${arrayId}/pause`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ paused: false }),
    });
    await forceRefresh();
    await expect.poll(async () => cloudText(await getMockCloudState()), { timeout: 15_000 }).toContain(tokenA);
  });
});
