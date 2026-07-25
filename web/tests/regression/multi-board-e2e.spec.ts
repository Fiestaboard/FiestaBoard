/**
 * Multi-board E2E regression. [#1251, final issue of the per-board epic #1241]
 *
 * Exercises the per-board model through the actual UI with a MIXED fleet —
 * a Flagship board (Local API, mocked by integration-tests/mock-board) and a
 * Vestaboard Note Array board (Cloud API, mocked by integration-tests/mock-cloud)
 * — which no earlier spec drives through the sidebar/Dashboard/Schedule/page-picker
 * UI together:
 *
 *  - multi-board-output.spec.ts and note-array-output.spec.ts assert at the
 *    API/hardware layer (fetch calls straight to /pages/{id}/send etc.), and
 *    note-array-output.spec.ts's "mixed fleet" test already covers the
 *    backend send->read assertion per board against both stdlib mocks.
 *  - board-switch-ux.spec.ts and multi-board-output.spec.ts drive the sidebar
 *    selector UI, but only ever with two Flagship boards.
 *
 * This spec is the missing combination: sidebar board selector -> Dashboard
 * + Schedule -> page-picker size filtering -> editor retarget warning, all
 * with one Flagship + one Note Array board.
 */
import {
  API_URL,
  authHeaders,
  BOARD_HOST,
  configureBoard,
  configureMockCloud,
  deleteAllPages,
  deleteAllSchedules,
  deletePagesByDevice,
  ensureAuthForFetch,
  expect,
  getMockBoardState,
  getMockCloudState,
  getToastsRegion,
  gridToText,
  loginIfNeeded,
  resetMockBoard,
  resetMockCloud,
  resetToSingleBoard,
  suppressWizard,
  test,
} from "../helpers";

const ARRAY_NOTES_WIDE = 2;
const ARRAY_NOTES_TALL = 1;
const ARRAY_ROWS = ARRAY_NOTES_TALL * 3; // 3
const ARRAY_COLS = ARRAY_NOTES_WIDE * 15; // 30

function uniq(prefix: string): string {
  return `${prefix}${Date.now() % 1_000_000}`;
}

/** Create a Flagship (6x22) page and return its id. */
async function createFlagshipPage(name: string, token: string): Promise<string> {
  const template = ["", token, "", "", "", ""];
  const res = await fetch(`${API_URL}/pages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, type: "template", template }),
  });
  if (!res.ok) throw new Error(`createFlagshipPage failed: ${res.status} ${await res.text()}`);
  const data = await res.json();
  return data.page.id;
}

/** Create a note_array page sized to ARRAY_NOTES_WIDE x ARRAY_NOTES_TALL and return its id. */
async function createArrayPage(name: string, token: string): Promise<string> {
  const template = Array.from({ length: ARRAY_ROWS }, (_, i) => (i === 0 ? token : ""));
  const res = await fetch(`${API_URL}/pages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      name,
      type: "template",
      template,
      device_type: "note_array",
      notes_wide: ARRAY_NOTES_WIDE,
      notes_tall: ARRAY_NOTES_TALL,
    }),
  });
  if (!res.ok) throw new Error(`createArrayPage failed: ${res.status} ${await res.text()}`);
  const data = await res.json();
  return data.page.id;
}

/** Configure a Flagship board ("Kitchen") + a Note Array board ("Office"), both manual mode. */
async function configureMixedFleet(): Promise<{ kitchenId: string; officeId: string }> {
  const res = await fetch(`${API_URL}/settings/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      boards: [
        {
          name: "Kitchen",
          device_type: "flagship",
          board_color: "black",
          enabled: true,
          api_mode: "local",
          host: BOARD_HOST,
          port: 7000,
          local_api_key: "test-key",
        },
        {
          name: "Office",
          device_type: "note_array",
          board_color: "white",
          enabled: true,
          api_mode: "cloud",
          notes_wide: ARRAY_NOTES_WIDE,
          notes_tall: ARRAY_NOTES_TALL,
          // Unique per run: the backend throttles note-array sends per token.
          note_array_token: `test-array-token-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        },
      ],
    }),
  });
  if (!res.ok) throw new Error(`configureMixedFleet failed: ${res.status} ${await res.text()}`);
  const data = await res.json();
  const boards = data.settings?.boards ?? [];
  if (boards.length < 2) throw new Error("configureMixedFleet: expected 2 boards");
  return { kitchenId: boards[0].id, officeId: boards[1].id };
}

async function setActivePage(pageId: string, boardId: string): Promise<void> {
  const res = await fetch(`${API_URL}/settings/active-page`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ page_id: pageId, board_id: boardId }),
  });
  if (!res.ok) throw new Error(`setActivePage failed: ${res.status} ${await res.text()}`);
}

function boardText(state: { current_message?: number[][] }): string {
  return gridToText(state.current_message).join("\n");
}

function cloudText(state: { current_grid?: number[][] }): string {
  return gridToText(state.current_grid).join("\n");
}

test.describe("regression: multi-board — mixed fleet through the real UI", () => {
  let kitchenId: string;
  let officeId: string;

  test.beforeEach(async ({ context, page }) => {
    await ensureAuthForFetch();
    await loginIfNeeded(context);
    await configureBoard();
    await deleteAllSchedules();
    await deleteAllPages();
    await resetMockBoard();
    await resetMockCloud();
    await configureMockCloud(ARRAY_NOTES_WIDE, ARRAY_NOTES_TALL);
    ({ kitchenId, officeId } = await configureMixedFleet());
    // No need to clear a stale `fiestaboard_current_board`: each test creates
    // fresh boards with new ids, and CurrentBoardProvider falls back to the
    // primary board whenever the stored id doesn't match a live board.
    await suppressWizard(page);
  });

  test.afterAll(async () => {
    await deleteAllSchedules();
    await deletePagesByDevice("note_array");
    await deleteAllPages();
    await resetToSingleBoard();
  });

  test("sidebar board selector switches the Dashboard and Schedule to the selected board's own state", async ({
    page,
  }) => {
    const kitchenPage = await createFlagshipPage("Kitchen Active", uniq("KIT"));
    const officePage = await createArrayPage("Office Active", uniq("OFF"));
    await setActivePage(kitchenPage, kitchenId);
    await setActivePage(officePage, officeId);

    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("active-display-board-name")).toContainText("Kitchen", { timeout: 10_000 });

    await page.locator("aside").getByLabel("Select board to manage").click();
    await page.getByRole("option", { name: "Office" }).click();
    await expect(page.getByTestId("active-display-board-name")).toContainText("Office", { timeout: 10_000 });

    // The current-board selection is shared context: Schedule reflects it too.
    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("active-board-indicator")).toContainText("Office", { timeout: 10_000 });

    await page.locator("aside").getByLabel("Select board to manage").click();
    await page.getByRole("option", { name: "Kitchen" }).click();
    await expect(page.getByTestId("active-board-indicator")).toContainText("Kitchen", { timeout: 10_000 });
  });

  test("Change Page on the selected board sends to that board's own mock, at that board's own size", async ({
    page,
  }) => {
    // Note-array sends are throttled >=15s per board token (src/board_client.py
    // NOTE_ARRAY_MIN_SEND_INTERVAL); this test sends to Office twice.
    test.setTimeout(45_000);
    const kitchenToken = uniq("KIT");
    const officeToken = uniq("OFF");
    await createFlagshipPage("Kitchen Send", kitchenToken);
    await createArrayPage("Office Send", officeToken);
    // Seed Office with a placeholder active page before switching to it: a
    // board with no active page yet triggers a (separate, transient)
    // auto-assign-default attempt that can race with an immediate UI click.
    const officePlaceholder = await createArrayPage("Office Placeholder", uniq("PLC"));
    await setActivePage(officePlaceholder, officeId);

    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible({ timeout: 15_000 });

    // Kitchen (default board) -> Change Page -> pick the Kitchen page.
    await page.getByRole("button", { name: /Change Page/i }).click();
    await page.getByText("Kitchen Send", { exact: true }).click();

    await expect.poll(async () => boardText(await getMockBoardState()), { timeout: 10_000 }).toContain(kitchenToken);
    const boardStateAfterKitchen = await getMockBoardState();
    expect(boardStateAfterKitchen.current_message?.length).toBe(6);

    // Switch to Office -> Change Page -> pick the Office (array) page.
    await page.locator("aside").getByLabel("Select board to manage").click();
    await page.getByRole("option", { name: "Office" }).click();
    await expect(page.getByTestId("active-display-board-name")).toContainText("Office", { timeout: 10_000 });

    // Clear the throttle window opened by the placeholder's send above.
    await page.waitForTimeout(16_000);

    await page.getByRole("button", { name: /Change Page/i }).click();
    await page.getByText("Office Send", { exact: true }).click();

    await expect.poll(async () => cloudText(await getMockCloudState()), { timeout: 10_000 }).toContain(officeToken);
    const cloudState = await getMockCloudState();
    expect(cloudState.current_grid?.length).toBe(ARRAY_ROWS);
    expect(cloudState.current_grid?.[0]?.length).toBe(ARRAY_COLS);

    // The array's content never reached the flagship's hardware.
    const finalBoardState = await getMockBoardState();
    expect(boardText(finalBoardState)).not.toContain(officeToken);
  });

  test("the page picker filters out pages that don't match the selected board's size", async ({ page }) => {
    const kitchenPage = await createFlagshipPage("Kitchen Only", uniq("KIT"));
    const officePage = await createArrayPage("Office Only", uniq("OFF"));
    // Give each board an active page so switching boards doesn't also trigger
    // the (unrelated) "no active page yet" auto-assign path.
    await setActivePage(kitchenPage, kitchenId);
    await setActivePage(officePage, officeId);

    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible({ timeout: 15_000 });

    // Kitchen (Flagship) selected: only the Flagship-sized page is offered.
    await page.getByRole("button", { name: /Change Page/i }).click();
    const kitchenDialog = page.getByRole("dialog");
    await expect(kitchenDialog.getByText("Kitchen Only", { exact: true })).toBeVisible({ timeout: 10_000 });
    await expect(kitchenDialog.getByText("Office Only", { exact: true })).toHaveCount(0);
    await page.keyboard.press("Escape");

    // Switch to Office (Note Array): only the array-sized page is offered.
    await page.locator("aside").getByLabel("Select board to manage").click();
    await page.getByRole("option", { name: "Office" }).click();
    await expect(page.getByTestId("active-display-board-name")).toContainText("Office", { timeout: 10_000 });

    await page.getByRole("button", { name: /Change Page/i }).click();
    const officeDialog = page.getByRole("dialog");
    await expect(officeDialog.getByText("Office Only", { exact: true })).toBeVisible({ timeout: 10_000 });
    await expect(officeDialog.getByText("Kitchen Only", { exact: true })).toHaveCount(0);
  });

  test("retargeting a board's active page to an incompatible size surfaces the stale-reference warning", async ({
    page,
  }) => {
    const pageId = await createFlagshipPage("Retarget Active Page", uniq("KIT"));
    await setActivePage(pageId, kitchenId);

    await page.goto(`/pages/edit/${pageId}`);
    await expect(page.getByText("6 × 22").first()).toBeVisible({ timeout: 15_000 });

    // Flagship (6x22) -> Note (3x15): a shrinking retarget confirms first.
    await page.getByLabel("Change board size").click();
    await page.getByRole("option", { name: "Note", exact: true }).click();
    await expect(page.getByText("3 × 15").first()).toBeVisible({ timeout: 10_000 });

    await page.getByRole("button", { name: "Save" }).first().click();
    await expect(page.getByRole("heading", { name: "Change board size?" })).toBeVisible({ timeout: 10_000 });
    await page.getByRole("button", { name: "Resize and save" }).click();

    // The toast names the board and the "active page" surface (issue #1250),
    // proving the per-board active-page reference (not just a schedule) is tracked.
    const toast = getToastsRegion(page);
    await expect(toast).toContainText("This page no longer fits", { timeout: 10_000 });
    await expect(toast).toContainText("Kitchen");
    await expect(toast).toContainText("active page");
  });
});
