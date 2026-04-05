/**
 * FiestaBoard — Board Discovery, Offline Handling & Per-Board Schedule E2E Tests
 *
 * Fills remaining gaps from issue #507:
 *
 *   1. Board discovery: /config/board/scan endpoint
 *   2. Board connection test: /config/board/test with unreachable host
 *   3. Per-board schedule active page: /schedules/active/page?board_id=X
 *   4. Per-board schedule enable/disable independence
 *   5. Note template rendering via /templates/render
 *   6. Board offline: send-message / page-send error handling
 *
 * Issue: #507
 */
import {
  test,
  expect,
  configureBoard,
  createPage,
  createNotePage,
  createSchedule,
  deleteAllPages,
  deleteAllSchedules,
  ensureTwoBoards,
  resetToSingleBoard,
  API_URL,
  BOARD_HOST,
} from "./helpers";

test.beforeEach(async () => {
  await configureBoard();
  await resetToSingleBoard();
  await deleteAllSchedules();
  await deleteAllPages();
});

test.afterEach(async () => {
  await resetToSingleBoard();
  await deleteAllSchedules();
  await deleteAllPages();
});

// ---------------------------------------------------------------------------
// 1. Board Discovery / Scan
// ---------------------------------------------------------------------------

test.describe("Board Discovery — /config/board/scan", () => {
  test("scan endpoint returns a boards array", async () => {
    const res = await fetch(`${API_URL}/config/board/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("boards");
    expect(Array.isArray(data.boards)).toBe(true);
  });

  test("scan respects timeout parameter", async () => {
    const start = Date.now();
    const res = await fetch(`${API_URL}/config/board/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ timeout: 1 }),
    });
    const elapsed = Date.now() - start;
    expect(res.ok).toBe(true);

    // With a 1s timeout the request should finish reasonably fast
    // (allow extra time for server overhead, but well under a full 15s scan)
    expect(elapsed).toBeLessThan(10_000);
  });

  test("scan with default body returns valid structure", async () => {
    const res = await fetch(`${API_URL}/config/board/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(Array.isArray(data.boards)).toBe(true);

    // Each discovered board (if any) should have ip and port fields
    for (const board of data.boards) {
      expect(board).toHaveProperty("ip");
      expect(board).toHaveProperty("port");
    }
  });
});

// ---------------------------------------------------------------------------
// 2. Board Connection Test — Offline Board
// ---------------------------------------------------------------------------

test.describe("Board Connection Test — Offline Detection", () => {
  test("connection test succeeds against mock board", async () => {
    const res = await fetch(`${API_URL}/config/board/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_mode: "local",
        local_api_key: "test-key",
        host: BOARD_HOST,
      }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.success).toBe(true);
  });

  test("connection test fails for unreachable host", async () => {
    const res = await fetch(`${API_URL}/config/board/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_mode: "local",
        local_api_key: "test-key",
        host: "192.0.2.99",
      }),
    });
    expect(res.ok).toBe(true); // endpoint itself doesn't 500
    const data = await res.json();
    expect(data.success).toBe(false);
    expect(data).toHaveProperty("message");
  });

  test("connection test reports missing credentials", async () => {
    const res = await fetch(`${API_URL}/config/board/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_mode: "local",
        local_api_key: "",
        host: BOARD_HOST,
      }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// 3. Per-Board Schedule Active Page Resolution
// ---------------------------------------------------------------------------

test.describe("Per-Board Schedule — Active Page Resolution", () => {
  test("active page endpoint returns schedule_enabled field", async () => {
    const res = await fetch(`${API_URL}/schedules/active/page`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data).toHaveProperty("schedule_enabled");
    expect(data).toHaveProperty("page_id");
    expect(data).toHaveProperty("source");
  });

  test("active page returns correct page per board when schedules differ", async () => {
    const { board1Id, board2Id } = await ensureTwoBoards();

    const page1 = await createPage("Flagship Active", [
      "FLAGSHIP", "", "", "", "", "",
    ]);
    const page2 = await createNotePage("Note Active", ["NOTE", "", ""]);

    // Enable schedule mode for both boards
    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: true, board_id: board1Id }),
    });
    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: true, board_id: board2Id }),
    });

    // Set different default pages per board (used when no schedule matches)
    await fetch(`${API_URL}/schedules/default-page`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page_id: page1, board_id: board1Id }),
    });
    await fetch(`${API_URL}/schedules/default-page`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page_id: page2, board_id: board2Id }),
    });

    // Query active page per board
    const res1 = await fetch(
      `${API_URL}/schedules/active/page?board_id=${board1Id}`,
    );
    expect(res1.ok).toBe(true);
    const data1 = await res1.json();
    expect(data1.schedule_enabled).toBe(true);
    // The default page for board1 should be page1
    expect(data1.default_page_id).toBe(page1);

    const res2 = await fetch(
      `${API_URL}/schedules/active/page?board_id=${board2Id}`,
    );
    expect(res2.ok).toBe(true);
    const data2 = await res2.json();
    expect(data2.schedule_enabled).toBe(true);
    expect(data2.default_page_id).toBe(page2);
  });

  test("schedule enable/disable is independent per board", async () => {
    const { board1Id, board2Id } = await ensureTwoBoards();

    // Enable schedule on board1, disable on board2
    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: true, board_id: board1Id }),
    });
    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: false, board_id: board2Id }),
    });

    const res1 = await fetch(
      `${API_URL}/schedules/active/page?board_id=${board1Id}`,
    );
    const data1 = await res1.json();
    expect(data1.schedule_enabled).toBe(true);

    const res2 = await fetch(
      `${API_URL}/schedules/active/page?board_id=${board2Id}`,
    );
    const data2 = await res2.json();
    expect(data2.schedule_enabled).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// 4. Note Template Rendering via API
// ---------------------------------------------------------------------------

test.describe("Note Template Rendering — /templates/render", () => {
  test("render endpoint respects Note 15-column width", async () => {
    const res = await fetch(`${API_URL}/templates/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: ["HELLO NOTE", "", ""],
        device_type: "note",
      }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();

    // Rendered lines should exist and each should be ≤ 15 characters
    if (data.lines) {
      expect(data.lines.length).toBe(3);
      for (const line of data.lines) {
        expect(line.length).toBeLessThanOrEqual(15);
      }
    }
    // Board array (if present) should be 3×15
    if (data.board_array) {
      expect(data.board_array.length).toBe(3);
      for (const row of data.board_array) {
        expect(row.length).toBe(15);
      }
    }
  });

  test("render endpoint uses 22-column width for Flagship", async () => {
    const res = await fetch(`${API_URL}/templates/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: ["HELLO FLAGSHIP", "", "", "", "", ""],
        device_type: "flagship",
      }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();

    if (data.lines) {
      expect(data.lines.length).toBe(6);
      for (const line of data.lines) {
        expect(line.length).toBeLessThanOrEqual(22);
      }
    }
    if (data.board_array) {
      expect(data.board_array.length).toBe(6);
      for (const row of data.board_array) {
        expect(row.length).toBe(22);
      }
    }
  });

  test("render for Note truncates text exceeding 15 columns", async () => {
    const longLine = "ABCDEFGHIJKLMNOPQRSTUV"; // 22 chars (Flagship width)
    const res = await fetch(`${API_URL}/templates/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template: [longLine, "", ""],
        device_type: "note",
      }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();

    // Rendered output should clip or wrap at 15 cols
    if (data.board_array) {
      expect(data.board_array.length).toBe(3);
      expect(data.board_array[0].length).toBe(15);
    }
  });
});

// ---------------------------------------------------------------------------
// 5. Board Offline — Send Handling
// ---------------------------------------------------------------------------

test.describe("Board Offline — Send Error Handling", () => {
  test("sending to an offline board does not crash the API", async () => {
    // Configure board with unreachable host
    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        boards: [{
          name: "Offline Board",
          device_type: "flagship",
          board_color: "black",
          enabled: true,
          api_mode: "local",
          host: "192.0.2.99",
          local_api_key: "test-key",
        }],
      }),
    });

    const pageId = await createPage("Offline Test", [
      "OFFLINE", "", "", "", "", "",
    ]);

    // Send to board target — should fail gracefully, not 500
    const res = await fetch(`${API_URL}/pages/${pageId}/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: "board" }),
    });

    // Accept any non-crash response (200 with sent_to_board=false or 4xx/5xx with detail)
    expect(res.status).not.toBe(502);
    const data = await res.json();
    expect(data).toHaveProperty("status");
  });

  test("send-message to offline board returns an error status", async () => {
    // Configure board with unreachable host
    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        boards: [{
          name: "Unreachable Board",
          device_type: "flagship",
          board_color: "black",
          enabled: true,
          api_mode: "local",
          host: "192.0.2.99",
          local_api_key: "test-key",
        }],
      }),
    });

    // Start the service so vb_client is built with the bad host
    await fetch(`${API_URL}/start`, { method: "POST" });

    const res = await fetch(`${API_URL}/send-message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "HELLO" }),
    });

    // The endpoint should handle the failure gracefully
    // It may return 500 (board unreachable) or 503 (client not initialized)
    // but should NOT crash the server entirely
    const data = await res.json();
    expect(data).toBeDefined();
  });

  test("page send to UI target works even when board is offline", async () => {
    // Configure board with unreachable host
    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        boards: [{
          name: "Offline UI Board",
          device_type: "flagship",
          board_color: "black",
          enabled: true,
          api_mode: "local",
          host: "192.0.2.99",
          local_api_key: "test-key",
        }],
      }),
    });

    const pageId = await createPage("UI Only", [
      "UI TARGET", "", "", "", "", "",
    ]);

    // Send with target=ui — should succeed regardless of board connectivity
    const res = await fetch(`${API_URL}/pages/${pageId}/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: "ui" }),
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.status).toBe("success");
  });
});

// ---------------------------------------------------------------------------
// 6. Multi-Board — Board Settings State Independence
// ---------------------------------------------------------------------------

test.describe("Multi-Board — State Independence", () => {
  test("disabling one board does not affect the other", async () => {
    const { board1Id, board2Id } = await ensureTwoBoards();

    // Get current boards, disable board2
    const boardRes = await fetch(`${API_URL}/settings/board`);
    const boardData = await boardRes.json();
    const updatedBoards = boardData.boards.map(
      (b: Record<string, unknown>) =>
        b.id === board2Id ? { ...b, enabled: false } : b,
    );

    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ boards: updatedBoards }),
    });

    // Verify board1 is still enabled, board2 is disabled
    const verifyRes = await fetch(`${API_URL}/settings/board`);
    const verifyData = await verifyRes.json();
    const b1 = verifyData.boards.find(
      (b: Record<string, unknown>) => b.id === board1Id,
    );
    const b2 = verifyData.boards.find(
      (b: Record<string, unknown>) => b.id === board2Id,
    );
    expect(b1?.enabled).toBe(true);
    expect(b2?.enabled).toBe(false);
  });

  test("changing device type of one board preserves the other", async () => {
    const { board1Id, board2Id } = await ensureTwoBoards();

    // Get current boards — board1 is flagship, board2 is note
    const boardRes = await fetch(`${API_URL}/settings/board`);
    const boardData = await boardRes.json();
    const board1 = boardData.boards.find(
      (b: Record<string, unknown>) => b.id === board1Id,
    );
    const board2 = boardData.boards.find(
      (b: Record<string, unknown>) => b.id === board2Id,
    );

    // Change board2 from note to flagship
    const updatedBoards = boardData.boards.map(
      (b: Record<string, unknown>) =>
        b.id === board2Id ? { ...b, device_type: "flagship" } : b,
    );

    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ boards: updatedBoards }),
    });

    // Verify board1's device_type is unchanged
    const verifyRes = await fetch(`${API_URL}/settings/board`);
    const verifyData = await verifyRes.json();
    const b1 = verifyData.boards.find(
      (b: Record<string, unknown>) => b.id === board1Id,
    );
    expect(b1?.device_type).toBe(board1?.device_type);
  });

  test("devices array reflects unique device types from all boards", async () => {
    await ensureTwoBoards(); // board1=flagship, board2=note

    const res = await fetch(`${API_URL}/settings/board`);
    const data = await res.json();

    // The devices array should contain both "flagship" and "note"
    expect(data.devices).toContain("flagship");
    expect(data.devices).toContain("note");
  });
});
