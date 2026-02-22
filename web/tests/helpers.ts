/**
 * Integration test helpers for FiestaBoard.
 *
 * Provides utilities to interact with the mock Vestaboard API
 * and reset state between tests.
 *
 * When running against Docker dev containers, set MOCK_BOARD_HOST to the
 * Docker service name (e.g. "fiestaboard-mock-board") so the API container
 * can reach the mock board.  In CI everything runs on localhost so the
 * default works as-is.
 */
import { test as base, expect } from "@playwright/test";

export const API_URL = `http://localhost:${process.env.API_PORT || "8000"}`;
export const MOCK_BOARD_PORT = parseInt(process.env.MOCK_BOARD_PORT || "7000", 10);
export const MOCK_BOARD_URL = `http://localhost:${MOCK_BOARD_PORT}`;
/** Second mock board port for multi-board e2e (when mock started with PORTS=7000,7001). */
export const MOCK_BOARD_PORT_2 = 7001;
export const MOCK_BOARD_URL_2 = `http://localhost:${MOCK_BOARD_PORT_2}`;
export const BOARD_HOST = process.env.MOCK_BOARD_HOST || "localhost";

/** Extend Playwright's base test with per-test backend state cleanup. */
export const test = base.extend<{ resetBackend: void }>({
  // eslint-disable-next-line no-empty-pattern
  resetBackend: [async ({}, use) => {
    await resetMockBoard(); // resets all ports when mock is multi-port
    await use();
  }, { auto: true }],
});

export { expect };

/** Read the mock board's internal state (message history, etc.). Optional port for multi-board. */
export async function getMockBoardState(port?: number): Promise<{
  current_message?: number[][];
  device_dimensions?: number[];
  message_count?: number;
  request_count?: number;
  history?: unknown[];
  port?: number;
}> {
  const base = port != null ? `http://localhost:${port}` : MOCK_BOARD_URL;
  const url = port != null ? `${base}/mock/state?port=${port}` : `${base}/mock/state`;
  const res = await fetch(url);
  return res.json();
}

/** Reset the mock board. Optional port to reset one board; omit to reset all (multi-board). */
export async function resetMockBoard(port?: number): Promise<void> {
  const base = port != null ? `http://localhost:${port}` : MOCK_BOARD_URL;
  const res = await fetch(`${base}/mock/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: port != null ? JSON.stringify({ port }) : "{}",
  });
  if (!res.ok) throw new Error(`resetMockBoard failed: ${res.status}`);
}

/**
 * Configure the board via the API so the app is no longer in first-run mode.
 * Call this in tests that need a working backend without running the wizard.
 */
export async function configureBoard() {
  await fetch(`${API_URL}/config/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      api_mode: "local",
      local_api_key: "test-key",
      host: BOARD_HOST,
    }),
  });
}

/**
 * Clear the board configuration so the backend returns to first-run mode.
 * Use this before tests that need the setup wizard to appear.
 */
export async function clearBoardConfig() {
  await fetch(`${API_URL}/config/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      api_mode: "local",
      local_api_key: "",
      host: "",
    }),
  });
}

/** Wait until the API server is ready. */
export async function waitForApi(timeoutMs = 15_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`${API_URL}/health`);
      if (res.ok) return;
    } catch {
      // not ready yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("API server did not become ready");
}

// ---------------------------------------------------------------------------
// CRUD helpers – keep tests focused on assertions, not setup boilerplate
// ---------------------------------------------------------------------------

/** Create a page via the API and return its ID. */
export async function createPage(
  name: string,
  template: string[] = ["TEST PAGE", "", "", "", "", ""],
  deviceType: "flagship" | "note" = "flagship",
): Promise<string> {
  const body: Record<string, unknown> = { name, type: "template", template };
  if (deviceType !== "flagship") {
    body.device_type = deviceType;
  }
  const res = await fetch(`${API_URL}/pages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`createPage failed: ${res.status}`);
  const data = await res.json();
  return data.page.id;
}

/** Create a Note page (3 lines, 15 cols) and return its ID. */
export async function createNotePage(
  name: string,
  template: string[] = ["NOTE TEST", "", ""],
): Promise<string> {
  return createPage(name, template, "note");
}


/** Delete a page via the API. */
export async function deletePage(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/pages/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`deletePage failed: ${res.status}`);
}

/** Delete every page via the API. */
export async function deleteAllPages(): Promise<void> {
  const res = await fetch(`${API_URL}/pages`);
  if (!res.ok) return;
  const data = await res.json();
  for (const p of data.pages) {
    await fetch(`${API_URL}/pages/${p.id}`, { method: "DELETE" });
  }
}

/** Create a schedule via the API and return its ID. */
export async function createSchedule(
  pageId: string,
  startTime = "08:00",
  endTime = "12:00",
  dayPattern = "weekdays",
): Promise<string> {
  const res = await fetch(`${API_URL}/schedules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      page_id: pageId,
      start_time: startTime,
      end_time: endTime,
      day_pattern: dayPattern,
    }),
  });
  if (!res.ok) throw new Error(`createSchedule failed: ${res.status}`);
  const data = await res.json();
  return data.id;
}

/** Delete a schedule via the API. */
export async function deleteSchedule(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/schedules/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`deleteSchedule failed: ${res.status}`);
}

/** Delete every schedule via the API. */
export async function deleteAllSchedules(): Promise<void> {
  const res = await fetch(`${API_URL}/schedules`);
  if (!res.ok) return;
  const data = await res.json();
  for (const s of data.schedules) {
    await fetch(`${API_URL}/schedules/${s.id}`, { method: "DELETE" });
  }
}

/** Enable a plugin via the API. */
export async function enablePlugin(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/plugins/${id}/enable`, { method: "POST" });
  if (!res.ok) throw new Error(`enablePlugin failed: ${res.status}`);
}

/** Disable a plugin via the API. */
export async function disablePlugin(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/plugins/${id}/disable`, { method: "POST" });
  if (!res.ok) throw new Error(`disablePlugin failed: ${res.status}`);
}

/** Update plugin configuration via the API. */
export async function updatePluginConfig(
  id: string,
  config: Record<string, unknown>,
): Promise<void> {
  const res = await fetch(`${API_URL}/plugins/${id}/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config }),
  });
  if (!res.ok) throw new Error(`updatePluginConfig failed: ${res.status}`);
}

/** Set the currently active page. */
export async function setActivePage(id: string | null): Promise<void> {
  const res = await fetch(`${API_URL}/settings/active-page`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page_id: id }),
  });
  if (!res.ok) throw new Error(`setActivePage failed: ${res.status}`);
}

/**
 * Ensure at least two boards exist (add a Note board if only one).
 * Returns the two board ids for use in tests.
 */
export async function ensureTwoBoards(): Promise<{ board1Id: string; board2Id: string }> {
  const res = await fetch(`${API_URL}/settings/board`);
  if (!res.ok) throw new Error(`ensureTwoBoards: failed to get board settings: ${res.status}`);
  const data = await res.json();
  const boards = data.boards ?? [];
  if (boards.length >= 2) {
    return { board1Id: boards[0].id, board2Id: boards[1].id };
  }
  if (boards.length === 0) {
    await resetToSingleBoard();
    const r2 = await fetch(`${API_URL}/settings/board`);
    const d2 = await r2.json();
    const b = d2.boards?.[0];
    if (!b) throw new Error("ensureTwoBoards: no board after reset");
    await fetch(`${API_URL}/settings/board/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_type: "note" }),
    });
    const r3 = await fetch(`${API_URL}/settings/board`);
    const d3 = await r3.json();
    const bs = d3.boards ?? [];
    return { board1Id: bs[0].id, board2Id: bs[1].id };
  }
  await fetch(`${API_URL}/settings/board/add`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device_type: "note" }),
  });
  const r2 = await fetch(`${API_URL}/settings/board`);
  const d2 = await r2.json();
  const bs = d2.boards ?? [];
  return { board1Id: bs[0].id, board2Id: bs[1].id };
}

/**
 * Reset to a single configured Flagship board.
 * Useful in afterEach to ensure clean multi-board state.
 */
export async function resetToSingleBoard() {
  await fetch(`${API_URL}/settings/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      boards: [{
        name: "My Board",
        device_type: "flagship",
        board_color: "black",
        enabled: true,
        api_mode: "local",
        host: BOARD_HOST,
        local_api_key: "test-key",
      }],
    }),
  });
}

/** Suppress the setup wizard by injecting localStorage before navigation. */
export function suppressWizard(page: import("@playwright/test").Page) {
  return page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
}
