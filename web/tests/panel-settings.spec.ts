/**
 * FiestaPanel settings-flow E2E.
 *
 * Covers the app-side lifecycle the viewer spec (panel.spec.ts) doesn't:
 *  - Creating a panel from Displays → Add a display and how its virtual
 *    board then appears — the FiestaPanel badge, never the red "Not
 *    configured" credentials prompt (the reported bug).
 *  - The virtual board card offering no credential/type controls and
 *    refusing removal while the panel exists (409 from the API too).
 *  - Editing the TV size: the board grid re-fits and the public frame
 *    endpoint never serves a stale-shaped frame afterwards.
 *  - Deleting the panel (from its display's page) removes its display.
 */
import {
  API_URL,
  authHeaders,
  configureBoard,
  displayCard,
  ensureAuthForFetch,
  expect,
  openDisplay,
  openDisplays,
  resetToSingleBoard,
  suppressWizard,
  test,
} from "./helpers";

interface PanelListEntry {
  id: string;
  short_code: number;
  board_id: string;
}

async function deleteAllPanels(): Promise<void> {
  const res = await fetch(`${API_URL}/panels`, { headers: authHeaders() });
  if (!res.ok) return;
  const body = (await res.json()) as { panels: PanelListEntry[] };
  for (const panel of body.panels ?? []) {
    await fetch(`${API_URL}/panels/${panel.id}`, { method: "DELETE", headers: authHeaders() });
  }
}

async function createPanelViaApi(name: string, inches = 43): Promise<PanelListEntry> {
  const res = await fetch(`${API_URL}/panels`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, screen_diagonal_inches: inches }),
  });
  // 201 with the bare panel since Phase 2 slice 8 (was 200 + { panel }).
  expect(res.status).toBe(201);
  return (await res.json()) as PanelListEntry;
}

async function driveBoard(boardId: string, lines: string[]): Promise<void> {
  const res = await fetch(`${API_URL}/templates/render/live`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ template: lines, board_id: boardId }),
  });
  expect(res.ok).toBe(true);
}

test.describe("FiestaPanel settings flow", () => {
  test.beforeEach(async ({ page }) => {
    await ensureAuthForFetch();
    await configureBoard();
    await deleteAllPanels();
    await resetToSingleBoard();
    await suppressWizard(page);
  });

  test.afterEach(async () => {
    await deleteAllPanels();
    await resetToSingleBoard();
  });

  test("creating a panel shows a FiestaPanel board card, never 'Not configured'", async ({ page }) => {
    await openDisplays(page);
    await page.getByRole("button", { name: "Add a display" }).click();
    await page.getByRole("radio", { name: /FiestaPanel/ }).click();
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await page.getByLabel("TV name").fill("E2E Wall TV");
    await page.getByLabel(/Screen size/).fill("55");
    await page.getByRole("button", { name: "Create TV board" }).click();

    // The new display's page opens, its panel's controls (viewer URL, QR,
    // TV size) on it.
    await expect(page).toHaveURL(/\/displays\/[^/]+$/, { timeout: 15_000 });
    const panel = page.getByTestId("display-panel-settings");
    await expect(panel.getByText("E2E Wall TV", { exact: true })).toBeVisible({ timeout: 10_000 });

    // Its virtual board shows the FiestaPanel badge — the reported bug
    // rendered this as a red "Not configured" card asking for API
    // credentials.
    const card = page.locator('[data-testid="board-card"]', { hasText: "E2E Wall TV (Panel)" });
    await expect(card).toBeVisible({ timeout: 10_000 });
    await expect(card.getByTestId("board-virtual-badge")).toBeVisible();
    await expect(card.getByText("Not configured")).toHaveCount(0);

    // No credentials form, no API-mode toggle, no type selector — just the
    // virtual-board explanation, and Remove is blocked while the panel
    // exists.
    await expect(card.getByTestId("virtual-board-hint")).toBeVisible();
    await expect(card.getByRole("radio", { name: /Local API/ })).toHaveCount(0);
    await expect(card.getByText("Cloud API Token")).toHaveCount(0);
    await expect(card.getByLabel("Board type and size")).toHaveCount(0);
    await expect(card.getByRole("button", { name: "Auto-detect from board" })).toHaveCount(0);
    await expect(card.getByRole("button", { name: "Remove Board" })).toBeDisabled();
  });

  test("the API refuses to remove a virtual board its panel still uses", async () => {
    const panel = await createPanelViaApi("E2E Guarded Panel");
    const res = await fetch(`${API_URL}/settings/board/${panel.board_id}`, {
      method: "DELETE",
      headers: authHeaders(),
    });
    expect(res.status).toBe(409);
    const body = (await res.json()) as { detail: string };
    expect(body.detail).toContain("E2E Guarded Panel");
  });

  test("resizing the TV re-fits the grid and never serves a stale-shaped frame", async ({ page }) => {
    const panel = await createPanelViaApi("E2E Resize TV", 43);
    await driveBoard(panel.board_id, ["BEFORE RESIZE", "", ""]);

    await openDisplay(page, "E2E Resize TV (Panel)");
    await expect(page.getByText("E2E Resize TV", { exact: true })).toBeVisible({ timeout: 10_000 });

    await page.getByRole("button", { name: "Edit panel" }).click();
    await page.getByRole("button", { name: '85"' }).click();
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0, { timeout: 10_000 });

    // Public viewer contract after the re-fit: config and frame agree on the
    // new dimensions, and the old-shape frame is gone rather than served
    // stale (the pre-fix behavior froze the TV on mismatched content).
    const config = (await (await fetch(`${API_URL}/panel/${panel.short_code}`)).json()) as {
      rows: number;
      cols: number;
    };
    const frame = (await (await fetch(`${API_URL}/panel/${panel.short_code}/frame`)).json()) as {
      rows: number;
      cols: number;
      characters: number[][] | null;
    };
    expect(config.rows).toBeGreaterThan(9); // 85" fits more than the 43" grid
    expect(frame.rows).toBe(config.rows);
    expect(frame.cols).toBe(config.cols);
    expect(frame.characters).toBeNull();

    // A new send at the new shape reaches the viewer.
    await driveBoard(panel.board_id, ["AFTER RESIZE", "", ""]);
    const refreshed = (await (await fetch(`${API_URL}/panel/${panel.short_code}/frame`)).json()) as {
      rows: number;
      characters: number[][] | null;
      message: string | null;
    };
    expect(refreshed.characters).not.toBeNull();
    expect(refreshed.rows).toBe(config.rows);
    expect(refreshed.message).toContain("AFTER RESIZE");
  });

  test("deleting a panel removes its display", async ({ page }) => {
    await createPanelViaApi("E2E Doomed Panel");

    const card = await openDisplay(page, "E2E Doomed Panel (Panel)");
    await expect(card).toContainText("E2E Doomed Panel (Panel)");

    await page.getByRole("button", { name: "Delete panel" }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();

    // Back on Displays, without it.
    await expect(page).toHaveURL(/\/displays$/, { timeout: 10_000 });
    await expect(displayCard(page, "E2E Doomed Panel (Panel)")).toHaveCount(0, { timeout: 10_000 });
  });
});
