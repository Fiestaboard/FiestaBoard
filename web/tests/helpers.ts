/**
 * Integration test helpers for FiestaBoard.
 *
 * Provides utilities to interact with the mock Vestaboard API
 * and reset state between tests.
 *
 * Supports per-worker backend isolation for parallel execution.
 * In CI, set WORKER_URLS / WORKER_MOCK_URLS / WORKER_MOCK_HOSTS as
 * comma-separated lists (one entry per Playwright worker). Each worker
 * gets its own FiestaBoard + mock board container so tests in different
 * files can run in parallel without state interference.
 */
import type { BrowserContext, Locator, Page } from "@playwright/test";
import { expect, test as base } from "@playwright/test";

const _workerUrls = (process.env.WORKER_URLS || "").split(",").filter(Boolean);
const _workerMockUrls = (process.env.WORKER_MOCK_URLS || "").split(",").filter(Boolean);
const _workerMockHosts = (process.env.WORKER_MOCK_HOSTS || "").split(",").filter(Boolean);

const DEFAULT_API_URL = process.env.BASE_URL
  ? `${process.env.BASE_URL}/api`
  : `http://localhost:${process.env.API_PORT || "4420"}/api`;
// Default host ports match docker-compose.dev.yml (17000:7000) so local Playwright
// can reach the mock from the host. Use MOCK_BOARD_PORT=7000 if you run server.py on the host.
const DEFAULT_MOCK_BOARD_PORT = parseInt(process.env.MOCK_BOARD_PORT || "17000", 10);
const DEFAULT_MOCK_BOARD_URL = process.env.MOCK_BOARD_URL || `http://localhost:${DEFAULT_MOCK_BOARD_PORT}`;
const DEFAULT_BOARD_HOST = process.env.MOCK_BOARD_HOST || "localhost";

export let API_URL = DEFAULT_API_URL;

export let MOCK_BOARD_URL = DEFAULT_MOCK_BOARD_URL;

export let BOARD_HOST = DEFAULT_BOARD_HOST;
export const MOCK_BOARD_PORT = DEFAULT_MOCK_BOARD_PORT;
/** Second mock board host port (docker-compose.dev.yml maps 17001:7001). */
export const MOCK_BOARD_PORT_2 = parseInt(process.env.MOCK_BOARD_PORT_2 || "17001", 10);
export const MOCK_BOARD_URL_2 = `http://localhost:${MOCK_BOARD_PORT_2}`;

function _configureWorker(workerIndex: number) {
  if (_workerUrls.length > 0) {
    const idx = workerIndex % _workerUrls.length;
    API_URL = `${_workerUrls[idx]}/api`;
    MOCK_BOARD_URL = _workerMockUrls[idx] || DEFAULT_MOCK_BOARD_URL;
    BOARD_HOST = _workerMockHosts[idx] || DEFAULT_BOARD_HOST;
  }
}

/** Extend Playwright's base test with per-worker isolation and per-test cleanup. */
export const test = base.extend<{ resetBackend: void }, { workerBackend: void }>({
  workerBackend: [
    async ({}, use, workerInfo) => {
      _configureWorker(workerInfo.workerIndex);
      await use();
    },
    { scope: "worker", auto: true },
  ],

  baseURL: async ({}, use, workerInfo) => {
    if (_workerUrls.length > 0) {
      const idx = workerInfo.workerIndex % _workerUrls.length;
      // eslint-disable-next-line react-hooks/rules-of-hooks -- Playwright fixture `use` callback, not a React hook
      await use(_workerUrls[idx]);
    } else {
      // eslint-disable-next-line react-hooks/rules-of-hooks -- Playwright fixture `use` callback, not a React hook
      await use(process.env.BASE_URL || "http://localhost:4420");
    }
  },

  resetBackend: [
    async ({}, use) => {
      await resetMockBoard();
      await use();
    },
    { auto: true },
  ],
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
 *
 * Also pins the multi-board settings to a single "flagship" device. Without
 * this, the inferred device list can flip to ["note"] between tests (depending
 * on which test reset state last), which hides flagship pages from the /pages
 * UI because PagesPage filters by the currently-active device tab. See
 * `web/src/app/pages/page.tsx` — `useBoardSettings().devices` drives the
 * tab list, and pages whose `device_type` doesn't match the active tab are
 * filtered out by `<PageGridSelector deviceTypeFilter={...} />`.
 */
export async function configureBoard() {
  await ensureAuthForFetch();
  await fetch(`${API_URL}/config/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      api_mode: "local",
      local_api_key: "test-key",
      host: BOARD_HOST,
    }),
  });
  // Pin the device list so tests that create flagship-default pages can
  // actually see them in /pages — see comment above.
  await fetch(`${API_URL}/settings/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ devices: ["flagship"] }),
  });
}

/**
 * Clear the board configuration so the backend returns to first-run mode.
 * Use this before tests that need the setup wizard to appear.
 *
 * Uses DELETE /api/config/board which resets to defaults without re-applying
 * environment-variable overrides (BOARD_HOST, BOARD_LOCAL_API_KEY, etc.).
 * This is important in CI where those env vars are always set; a plain PUT
 * with empty strings would be immediately overwritten by Config.reload().
 */
export async function clearBoardConfig() {
  const res = await fetch(`${API_URL}/config/board`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(`clearBoardConfig failed: ${res.status} ${await res.text()}`);
  }
}

/**
 * If the running container has auth enabled, mint a session cookie for the
 * existing admin via the in-container auth service and attach it to the
 * Playwright context. No-op when auth is disabled (the standard CI path).
 *
 * We mint via `docker compose exec` rather than POST /auth/login because the
 * admin password isn't available to the test runner.
 */
let _cachedSessionCookie: string | null = null;

/**
 * Stall a route until a release function is called, then continue. Used to
 * observe `*.pending` / `*.saving` / `*.loading` UI states deterministically.
 *
 * Returns a `release` function. Call it once the assertion has captured the
 * pending state to let the real request finish.
 *
 * @example
 *   const release = await slowRoute(page, "**\/api\/pages", ["GET"]);
 *   await page.goto("/pages");
 *   await expect(skeleton).toBeVisible();
 *   release();
 */
export async function slowRoute(
  page: Page,
  urlPattern: string | RegExp,
  methods: ReadonlyArray<"GET" | "POST" | "PUT" | "DELETE" | "PATCH"> = ["GET"],
): Promise<() => void> {
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(urlPattern, async (route) => {
    if (methods.includes(route.request().method() as (typeof methods)[number])) {
      await gate;
    }
    await route.continue();
  });
  return release;
}

/**
 * Scope a locator to the Sonner toast region. Avoids strict-mode collisions with
 * the Next.js dev runtime-error overlay, which also surfaces via role="alert".
 */
export function getToastsRegion(page: Page): Locator {
  return page.locator("[data-sonner-toast]").first();
}

/** Auth header pair to attach to fetch() calls when auth is on. Empty when off. */
export function authHeaders(): Record<string, string> {
  return _cachedSessionCookie ? { Cookie: `fiestaboard_session=${_cachedSessionCookie}` } : {};
}

/**
 * Ensure the in-process fetch helpers can authenticate. Mints and caches a
 * session cookie if auth is enabled; no-op otherwise. Safe to call repeatedly.
 */
export async function ensureAuthForFetch(): Promise<void> {
  const baseUrl = (process.env.BASE_URL || "http://localhost:4420").replace(/\/$/, "");
  const status = await fetch(`${baseUrl}/api/auth/status`)
    .then((r) => r.json() as Promise<{ enabled: boolean }>)
    .catch(() => ({ enabled: false }));
  if (!status.enabled || _cachedSessionCookie) return;
  await _mintSessionCookie();
}

async function _mintSessionCookie(): Promise<void> {
  const { execSync } = await import("node:child_process");
  const composeFile = process.env.COMPOSE_FILE || "/Users/jeffrey/workspace/FiestaBoard/docker-compose.dev.yml";
  const script = `
import time
from src.auth.service import get_auth_service, SessionToken, _remember_me_ttl_seconds
svc = get_auth_service()
user = svc._data["users"][0]
now_ms = int(time.time() * 1000)
tok = SessionToken(
    username=user["username"],
    issued_at=now_ms,
    expires_at=now_ms + _remember_me_ttl_seconds() * 1000,
)
print(svc._sign(tok.encode()))
`;
  const out = execSync(`docker compose -f ${composeFile} exec -T fiestaboard python -`, {
    encoding: "utf8",
    input: script,
  });
  _cachedSessionCookie = out.trim().split("\n").pop()!.trim();
}

export async function loginIfNeeded(context: BrowserContext): Promise<void> {
  const baseUrl = (process.env.BASE_URL || "http://localhost:4420").replace(/\/$/, "");
  const status = await fetch(`${baseUrl}/api/auth/status`)
    .then((r) => r.json() as Promise<{ enabled: boolean; authenticated: boolean }>)
    .catch(() => ({ enabled: false, authenticated: true }));
  if (!status.enabled) return;
  if (!_cachedSessionCookie) await _mintSessionCookie();
  if (!_cachedSessionCookie) return;

  const url = new URL(baseUrl);
  await context.addCookies([
    {
      name: "fiestaboard_session",
      value: _cachedSessionCookie,
      domain: url.hostname,
      path: "/",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
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
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`createPage failed: ${res.status}`);
  const data = await res.json();
  return data.page.id;
}

/** Create a Note page (3 lines, 15 cols) and return its ID. */
export async function createNotePage(name: string, template: string[] = ["NOTE TEST", "", ""]): Promise<string> {
  return createPage(name, template, "note");
}

/** Delete a page via the API. */
export async function deletePage(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/pages/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`deletePage failed: ${res.status}`);
}

/** Create a collection via the API and return its full record. */
export async function createCollection(
  name: string,
  pageIds: string[],
  intervalSeconds = 30,
): Promise<{ id: string; name: string; page_ids: string[]; time: { interval_seconds: number } }> {
  const res = await fetch(`${API_URL}/collections`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      name,
      page_ids: pageIds,
      selection_mode: "time",
      time: { interval_seconds: intervalSeconds },
    }),
  });
  if (!res.ok) {
    throw new Error(`createCollection failed: ${res.status} ${await res.text()}`);
  }
  const data = await res.json();
  return data.collection;
}

/** Delete every collection via the API. */
export async function deleteAllCollections(): Promise<void> {
  const res = await fetch(`${API_URL}/collections`, { headers: authHeaders() });
  if (!res.ok) return;
  const data = await res.json();
  for (const c of data.collections || []) {
    await fetch(`${API_URL}/collections/${c.id}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
  }
}

/** Delete every page via the API. */
export async function deleteAllPages(): Promise<void> {
  const res = await fetch(`${API_URL}/pages`, { headers: authHeaders() });
  if (!res.ok) return;
  const data = await res.json();
  for (const p of data.pages) {
    await fetch(`${API_URL}/pages/${p.id}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
  }
}

/** Create a schedule via the API and return its ID. Optional boardId for per-board schedules. */
export async function createSchedule(
  pageId: string,
  startTime: string | null = "08:00",
  endTime: string | null = "12:00",
  dayPattern = "weekdays",
  boardId?: string,
  opts: { enabled?: boolean } = {},
): Promise<string> {
  const body: Record<string, unknown> = {
    page_id: pageId,
    start_time: startTime,
    end_time: endTime,
    day_pattern: dayPattern,
  };
  if (boardId != null && boardId !== "") body.board_id = boardId;
  if (opts.enabled === false) body.enabled = false;
  const res = await fetch(`${API_URL}/schedules`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`createSchedule failed: ${res.status}`);
  const data = await res.json();
  return data.id;
}

/** Delete a schedule via the API. */
export async function deleteSchedule(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/schedules/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`deleteSchedule failed: ${res.status}`);
}

/** Delete every schedule via the API (across all boards). */
export async function deleteAllSchedules(): Promise<void> {
  const res = await fetch(`${API_URL}/schedules?board_id=*`, { headers: authHeaders() });
  if (!res.ok) return;
  const data = await res.json();
  for (const s of data.schedules) {
    await fetch(`${API_URL}/schedules/${s.id}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
  }
}

/** Enable a plugin via the API. */
export async function enablePlugin(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/plugins/${id}/enable`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`enablePlugin failed: ${res.status}`);
}

/** Disable a plugin via the API. */
export async function disablePlugin(id: string): Promise<void> {
  const res = await fetch(`${API_URL}/plugins/${id}/disable`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`disablePlugin failed: ${res.status}`);
}

/** Update plugin configuration via the API. */
export async function updatePluginConfig(id: string, config: Record<string, unknown>): Promise<void> {
  const res = await fetch(`${API_URL}/plugins/${id}/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ config }),
  });
  if (!res.ok) throw new Error(`updatePluginConfig failed: ${res.status}`);
}

/** Set the currently active page. */
export async function setActivePage(id: string | null): Promise<void> {
  const res = await fetch(`${API_URL}/settings/active-page`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ page_id: id }),
  });
  if (!res.ok) throw new Error(`setActivePage failed: ${res.status}`);
}

/**
 * Ensure at least two boards exist (add a Note board if only one).
 * Returns the two board ids for use in tests.
 */
export async function ensureTwoBoards(): Promise<{ board1Id: string; board2Id: string }> {
  const res = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`ensureTwoBoards: failed to get board settings: ${res.status}`);
  const data = await res.json();
  const boards = data.boards ?? [];
  if (boards.length >= 2) {
    return { board1Id: boards[0].id, board2Id: boards[1].id };
  }
  if (boards.length === 0) {
    await resetToSingleBoard();
    const r2 = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
    const d2 = await r2.json();
    const b = d2.boards?.[0];
    if (!b) throw new Error("ensureTwoBoards: no board after reset");
    await fetch(`${API_URL}/settings/board/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ device_type: "note" }),
    });
    const r3 = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
    const d3 = await r3.json();
    const bs = d3.boards ?? [];
    return { board1Id: bs[0].id, board2Id: bs[1].id };
  }
  await fetch(`${API_URL}/settings/board/add`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ device_type: "note" }),
  });
  const r2 = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
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
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      boards: [
        {
          name: "My Board",
          device_type: "flagship",
          board_color: "black",
          enabled: true,
          api_mode: "local",
          host: BOARD_HOST,
          local_api_key: "test-key",
        },
      ],
    }),
  });
}

/** Suppress the setup wizard by injecting localStorage before navigation. */
export function suppressWizard(page: Page) {
  return page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
}

/**
 * Open a tab on the redesigned Settings page. The page splits its content
 * across tabs (General, Hardware, Behavior, Integrations, System, Advanced),
 * so tests that look for tab-scoped content must click the right tab first.
 */
export async function openSettingsTab(
  page: Page,
  tab: "General" | "Account" | "Hardware" | "Network" | "Behavior" | "Integrations" | "System" | "Advanced",
) {
  const trigger = page.getByRole("tab", { name: tab, exact: true });
  await trigger.waitFor({ state: "visible", timeout: 15_000 });
  await trigger.click();
}

/**
 * Wait until the backend reports first-run mode (no board configured).
 * `clearBoardConfig()` returns 200 as soon as the DELETE handler runs, but the
 * validate endpoint that drives the setup wizard reads from a separate cache.
 * Without this poll, navigating to `/` immediately after a clear can race and
 * see a stale "configured" state — and the wizard won't render.
 */
export async function waitForFirstRun(timeoutMs = 10_000): Promise<void> {
  const start = Date.now();
  let lastStatus = 0;
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`${API_URL}/config/validate`);
      lastStatus = res.status;
      if (res.ok) {
        const data = (await res.json()) as { is_first_run?: boolean };
        if (data.is_first_run === true) return;
      }
    } catch {
      // ignore; the API may still be coming up
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(`waitForFirstRun: backend never reported is_first_run=true (last status ${lastStatus})`);
}

/**
 * Wait until there is no active board display — i.e. GET /api/pages/current-display
 * returns 404. `setActivePage(null)` flips the stored ID, but a polling loop on
 * the backend can re-promote the auto-created "Welcome" page before the next
 * client action lands. Polling here closes that window.
 */
export async function waitForNoActiveDisplay(timeoutMs = 5_000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const res = await fetch(`${API_URL}/pages/current-display`);
    if (res.status === 404) return;
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error("waitForNoActiveDisplay: an active display kept getting promoted");
}
