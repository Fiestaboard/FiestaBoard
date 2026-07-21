/**
 * Local note-array output E2E — hardware layer.
 *
 * Configures ONE board as a 2×1 note array in LOCAL mode whose two tiles
 * point at the mock board's two Local-API ports (7000 / 7001), then asserts
 * at the mock layer that each physical Note received exactly its 3×15 slice
 * of the rendered 3×30 virtual frame, and that the identify endpoint flashes
 * a slot label onto only the targeted tile.
 *
 * Requires the mock board server to listen on both ports (PORTS=7000,7001 —
 * docker-compose.dev.yml already does; CI mock containers are configured in
 * ci.yml / integration-tests.yml).
 */
import {
  API_URL,
  authHeaders,
  BOARD_2_LOCAL_API_PORT,
  BOARD_HOST,
  configureBoard,
  deleteAllPages,
  ensureAuthForFetch,
  expect,
  getMockBoardState,
  getMockBoardState2,
  gridToText,
  MOCK_BOARD_PORT,
  resetToSingleBoard,
  test,
} from "./helpers";

/** Unique single-word token so the content-unchanged cache never skips a send. */
function uniq(prefix: string): string {
  return `${prefix}${Date.now() % 1_000_000}`;
}

/** Configure a single 2×1 local-mode note array: tile 1 → mock :7000, tile 2 → mock :7001. */
async function ensureLocalArrayBoard(): Promise<string> {
  await ensureAuthForFetch();
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
  const res = await fetch(`${API_URL}/settings/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ boards: [board] }),
  });
  if (!res.ok) throw new Error(`ensureLocalArrayBoard failed: ${res.status} ${await res.text()}`);
  const data = await res.json();
  const id = data.settings?.boards?.[0]?.id;
  if (!id) throw new Error("ensureLocalArrayBoard: no board id returned");
  return id;
}

/** Create a 3×30 note-array page and return its ID. */
async function createArrayPage(name: string, template: string[]): Promise<string> {
  const res = await fetch(`${API_URL}/pages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, type: "template", template, device_type: "note_array", notes_wide: 2, notes_tall: 1 }),
  });
  if (!res.ok) throw new Error(`createArrayPage failed: ${res.status} ${await res.text()}`);
  const data = await res.json();
  return data.page.id;
}

async function sendPageToBoard(pageId: string): Promise<void> {
  const res = await fetch(`${API_URL}/pages/${pageId}/send?target=board`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`send page failed: ${res.status} ${await res.text()}`);
}

test.describe("Local note array — per-tile fan-out", () => {
  test.beforeEach(async () => {
    await configureBoard();
    await deleteAllPages();
  });

  test.afterEach(async () => {
    await deleteAllPages();
    await resetToSingleBoard();
  });

  test("each tile receives its 3×15 slice of the virtual frame", async () => {
    await ensureLocalArrayBoard();

    // 30-column line: cols 0-14 spell LEFT<token>, cols 15-29 spell RIGHT<token>.
    const left = uniq("LEFT");
    const right = uniq("RIGHT");
    const line = left.padEnd(15, " ") + right.padEnd(15, " ");
    const pageId = await createArrayPage(uniq("ARRAYPAGE"), [line, "", ""]);

    await sendPageToBoard(pageId);

    await expect
      .poll(async () => gridToText((await getMockBoardState(MOCK_BOARD_PORT)).current_message)[0] ?? "", {
        timeout: 15_000,
      })
      .toContain(left);
    const tile1 = await getMockBoardState(MOCK_BOARD_PORT);
    const tile2 = await getMockBoardState2();

    // Every tile got a Note-sized grid — the mock validates 3×15 on POST.
    expect(tile1.current_message).toHaveLength(3);
    expect(tile1.current_message?.[0]).toHaveLength(15);
    expect(tile2.current_message).toHaveLength(3);
    expect(tile2.current_message?.[0]).toHaveLength(15);

    // Left tile shows only the left half; right tile only the right half.
    const tile1Text = gridToText(tile1.current_message).join("\n");
    const tile2Text = gridToText(tile2.current_message).join("\n");
    expect(tile1Text).toContain(left);
    expect(tile1Text).not.toContain(right);
    expect(tile2Text).toContain(right);
    expect(tile2Text).not.toContain(left);
  });

  test("identify flashes the slot label onto only the targeted tile", async () => {
    const boardId = await ensureLocalArrayBoard();

    const res = await fetch(`${API_URL}/settings/board/${boardId}/identify`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ target: "tile", row: 0, col: 1 }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.results).toEqual([{ row: 0, col: 1, success: true }]);

    // Tile 2 (mock :7001) shows its reading-order position + coordinates.
    await expect
      .poll(async () => gridToText((await getMockBoardState2()).current_message).join("\n"), { timeout: 10_000 })
      .toContain("POSITION 2");
    const tile2Text = gridToText((await getMockBoardState2()).current_message).join("\n");
    expect(tile2Text).toContain("R1 C2");

    // The untargeted tile did not receive the identify pattern.
    const tile1Text = gridToText((await getMockBoardState(MOCK_BOARD_PORT)).current_message).join("\n");
    expect(tile1Text).not.toContain("POSITION 2");
  });
});
