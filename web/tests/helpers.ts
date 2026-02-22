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
export const MOCK_BOARD_URL = `http://localhost:${process.env.MOCK_BOARD_PORT || "7000"}`;
export const BOARD_HOST = process.env.MOCK_BOARD_HOST || "localhost";

/** Extend Playwright's base test with per-test backend state cleanup. */
export const test = base.extend<{ resetBackend: void }>({
  // eslint-disable-next-line no-empty-pattern
  resetBackend: [async ({}, use) => {
    await fetch(`${MOCK_BOARD_URL}/mock/reset`, { method: "POST" });
    await use();
  }, { auto: true }],
});

export { expect };

/** Read the mock board's internal state (message history, etc.). */
export async function getMockBoardState() {
  const res = await fetch(`${MOCK_BOARD_URL}/mock/state`);
  return res.json();
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
