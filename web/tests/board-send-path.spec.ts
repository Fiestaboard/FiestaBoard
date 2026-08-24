/**
 * Board send-path integration E2E.
 *
 * Every other refresh-based E2E uses `POST /force-refresh`, which calls
 * `clear_cache()` on all board clients first — structurally bypassing the
 * unchanged-message dedup that a board-client refactor is most likely to
 * break (issue #1732). These tests deliberately drive the *non-force* send
 * path (`POST /pages/{id}/send`, which routes straight through
 * `BoardClient.render()` → `send_characters()` and honors the client-side
 * cache) so the hardware-layer behavior is actually observed on the mock
 * board rather than trusted from a settings echo.
 *
 * Three behaviors are pinned, each asserted against `getMockBoardState()`:
 *   1. skip-unchanged — an identical repeat send never reaches the board.
 *   2. output target UI — a plain send with target=ui never reaches the board.
 *   3. stepped transition — a plugin transition sends >1 frame and lands on
 *      the exact target grid.
 *
 * Requires the mock board server on port 7000 (docker-compose.dev.yml maps
 * host 17000 → container 7000; CI mock containers do the same).
 */
import {
  API_URL,
  authHeaders,
  configureBoard,
  createPage,
  deleteAllPages,
  ensureAuthForFetch,
  expect,
  getMockBoardState,
  gridToText,
  resetMockBoard,
  resetToSingleBoard,
  setActivePage,
  test,
  updatePluginConfig,
} from "./helpers";

/** A single-word token unique per invocation so content never collides with the cache. */
function uniq(prefix: string): string {
  return `${prefix}${Date.now() % 1_000_000}`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

/**
 * Send a page via the manual send path. Omit `target` to honor the configured
 * output-target setting; pass "board" to force a board attempt regardless.
 */
async function sendPage(pageId: string, target?: "board" | "ui" | "both"): Promise<{ sent_to_board?: boolean }> {
  const suffix = target ? `?target=${target}` : "";
  const res = await fetch(`${API_URL}/pages/${pageId}/send${suffix}`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(`send page failed: ${res.status} ${await res.text()}`);
  return res.json();
}

async function getOutputTarget(): Promise<string> {
  const res = await fetch(`${API_URL}/settings/output`, { headers: authHeaders() });
  return (await res.json()).target;
}

async function setOutputTarget(target: string): Promise<void> {
  const res = await fetch(`${API_URL}/settings/output`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ target }),
  });
  if (!res.ok) throw new Error(`setOutputTarget failed: ${res.status} ${await res.text()}`);
}

async function getGlobalStrategy(): Promise<string | null> {
  const res = await fetch(`${API_URL}/settings/transitions`, { headers: authHeaders() });
  return (await res.json()).strategy ?? null;
}

async function setGlobalStrategy(strategy: string | null): Promise<void> {
  const res = await fetch(`${API_URL}/settings/transitions`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ strategy }),
  });
  if (!res.ok) throw new Error(`setGlobalStrategy failed: ${res.status} ${await res.text()}`);
}

async function setBeta(transitionPluginsEnabled: boolean): Promise<void> {
  const res = await fetch(`${API_URL}/settings/beta`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ transition_plugins_enabled: transitionPluginsEnabled }),
  });
  if (!res.ok) throw new Error(`setBeta failed: ${res.status} ${await res.text()}`);
}

async function setScheduleEnabled(enabled: boolean): Promise<void> {
  const res = await fetch(`${API_URL}/schedules/enabled`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ enabled }),
  });
  if (!res.ok) throw new Error(`setScheduleEnabled failed: ${res.status} ${await res.text()}`);
}

async function clearBoardCache(): Promise<void> {
  const res = await fetch(`${API_URL}/clear-cache`, { method: "POST", headers: authHeaders() });
  if (!res.ok) throw new Error(`clear-cache failed: ${res.status} ${await res.text()}`);
}

async function messageCount(): Promise<number> {
  return (await getMockBoardState()).message_count ?? 0;
}

/** A bundled transition plugin present in every install; steps frame-by-frame. */
const TRANSITION_PLUGIN = "plugin:typewriter";

test.describe("Board send-path integration", () => {
  let priorTarget = "both";
  let priorStrategy: string | null = null;

  test.beforeEach(async () => {
    await ensureAuthForFetch();
    await configureBoard();
    await setScheduleEnabled(false); // manual mode: the poll loop only ever sends the active page
    await deleteAllPages();
    priorTarget = await getOutputTarget();
    priorStrategy = await getGlobalStrategy();
  });

  test.afterEach(async () => {
    // Restore anything the tests mutated so sibling specs on this backend
    // see a clean slate.
    await setOutputTarget(priorTarget).catch(() => {});
    await setGlobalStrategy(priorStrategy).catch(() => {});
    await setBeta(false).catch(() => {});
    await deleteAllPages().catch(() => {});
    await resetToSingleBoard().catch(() => {});
  });

  test("identical content sent twice via the non-force path reaches the board only once", async () => {
    const token = uniq("SKIP");
    const pageId = await createPage(`Skip Unchanged ${token}`, [token, "", "", "", "", ""]);
    // Make it the active page too, so the background poll loop can only ever
    // (re-)send THIS content — which, once cached, is itself deduped. That
    // keeps the message count frozen except for the sends we make explicitly.
    await setActivePage(pageId);

    // First send lands the content on the board.
    await sendPage(pageId, "board");
    await expect
      .poll(messageCount, { timeout: 15_000, message: "first send should reach the board" })
      .toBeGreaterThanOrEqual(1);

    const before = await messageCount();

    // A second, byte-identical send must be dropped by the unchanged-message
    // cache — the board must NOT receive it again. Give any erroneous send a
    // beat to land before asserting the count never moved.
    const second = await sendPage(pageId, "board");
    expect(second.sent_to_board, "an unchanged repeat send must report was_sent=false").toBe(false);
    await sleep(1_500);

    expect(await messageCount(), "an unchanged repeat send must not reach the board").toBe(before);
  });

  test("output target UI keeps a plain send off the board", async () => {
    // Pin an active page and let it land, so the poll loop's steady-state
    // send is deduped and cannot inflate the count during the assertion.
    const activeToken = uniq("UIACTIVE");
    const activeId = await createPage(`UI Active ${activeToken}`, [activeToken, "", "", "", "", ""]);
    await setActivePage(activeId);
    await sendPage(activeId, "board");
    await expect.poll(messageCount, { timeout: 15_000 }).toBeGreaterThanOrEqual(1);

    // Now switch to UI-only output and try to send a DIFFERENT (uncached)
    // page with no explicit target, so the output-target setting governs.
    await setOutputTarget("ui");
    const uiToken = uniq("UIONLY");
    const uiPageId = await createPage(`UI Only ${uiToken}`, [uiToken, "", "", "", "", ""]);

    await resetMockBoard();
    const before = await messageCount(); // 0 after reset; poll loop only re-sends the (cached) active page

    const result = await sendPage(uiPageId); // no target → honors output settings
    expect(result.sent_to_board, "a UI-only send must not reach the board").toBe(false);
    await sleep(1_500);

    expect(await messageCount(), "nothing should reach the board while output target is UI").toBe(before);
  });

  test("a stepped transition sends multiple frames and lands on the target grid", async () => {
    test.setTimeout(90_000);
    await setBeta(true); // plugin transitions are gated behind the beta flag
    await setGlobalStrategy(TRANSITION_PLUGIN);
    // Sweep a whole row per frame so the transition still steps (>1 frame) but
    // finishes quickly instead of ticking through all 132 tiles one at a time.
    // If the config isn't picked up the test still holds (just slower), since
    // the default sweep also yields many frames.
    await updatePluginConfig("typewriter", { chars_per_frame: 22, frame_interval_ms: 0 }).catch(() => {});

    const token = uniq("STEP");
    const pageId = await createPage(`Stepped ${token}`, [token, "", "", "", "", ""]);

    // Start from a blank board so the typewriter genuinely reveals the target
    // over several frames rather than snapping.
    await clearBoardCache();
    await resetMockBoard();

    await sendPage(pageId, "board");

    const state = await getMockBoardState();
    const history = state.history ?? [];

    // A stepped transition pushes more than one frame to the board...
    expect(history.length, "a stepped transition should send more than one frame").toBeGreaterThan(1);

    // ...and the final frame must be the exact target grid the board settles on.
    const lastFrame = history.at(-1)?.characters;
    expect(lastFrame, "the last history frame should have characters").toBeTruthy();
    expect(lastFrame).toEqual(state.current_message);

    // Sanity-check the target actually rendered our content (not a stray blank frame).
    expect(gridToText(state.current_message).join("")).toContain(token);
  });
});
