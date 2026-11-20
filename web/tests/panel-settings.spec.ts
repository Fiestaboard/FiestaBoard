/**
 * FiestaPanel settings-flow E2E.
 *
 * Covers the app-side lifecycle the viewer spec (panel.spec.ts) doesn't:
 *  - Creating a panel from Displays → Add a display and how its virtual
 *    board then appears — the FiestaPanel badge, never the red "Not
 *    configured" credentials prompt (the reported bug).
 *  - Inline panel settings offering no credential/type controls and
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

  test("creating a panel shows inline FiestaPanel settings, never 'Not configured'", async ({ page }) => {
    await openDisplays(page);
    await page.getByRole("button", { name: "Add a display" }).click();
    await page.getByRole("radio", { name: /FiestaPanel/ }).click();
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await page.getByLabel("TV name").fill("E2E Wall TV");
    await page.getByRole("combobox", { name: /Screen size/ }).click();
    await page.getByRole("option", { name: "55-inch TV · automatic board size", exact: true }).click();
    const created = page.waitForResponse(
      (response) => response.url().endsWith("/api/panels") && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Add display", exact: true }).click();
    const response = await created;
    expect(response.status()).toBe(201);
    const panel = (await response.json()) as PanelListEntry;

    // Creation opens the new display; its Settings tab contains immediate
    // panel controls, rather than the old virtual board/pencil editor card.
    await expect(page).toHaveURL((url) => url.pathname === `/displays/${panel.board_id}`, { timeout: 15_000 });
    const settings = page.getByTestId("display-panel-settings");
    // The URL can change before the outlet replaces the previous embedded
    // display. Wait for this panel's mounted content before using its tabs.
    await expect(settings.getByTestId("board-name-input")).toHaveValue("E2E Wall TV", { timeout: 10_000 });
    await page.getByRole("tab", { name: "Settings", exact: true }).click();
    await expect(settings.getByTestId("board-name-input")).toBeVisible();
    await expect(settings.getByRole("heading", { name: "FiestaPanel", exact: true })).toBeVisible();
    await expect(settings.getByLabel("Panel URL")).toHaveValue(/\/p\/\d+$/);
    await expect(settings.getByRole("radiogroup", { name: "TV size" })).toBeVisible();
    await expect(settings.getByRole("radiogroup", { name: "Render style" })).toBeVisible();
    await expect(settings.getByText("Not configured", { exact: true })).toHaveCount(0);
    await expect(page.getByTestId("board-card")).toHaveCount(0);

    // The retained advanced display controls explain the virtual board and
    // still prevent removing it separately while the panel exists.
    await settings.getByRole("button", { name: "Advanced display settings", exact: true }).click();
    await expect(settings.getByTestId("virtual-board-hint")).toBeVisible();
    await expect(settings.getByRole("radio", { name: /Local API/ })).toHaveCount(0);
    await expect(settings.getByText("Cloud API Token")).toHaveCount(0);
    await expect(settings.getByLabel("Board type and size")).toHaveCount(0);
    await expect(settings.getByRole("button", { name: "Auto-detect from board" })).toHaveCount(0);
    await expect(settings.getByRole("button", { name: "Remove Board", exact: true })).toBeDisabled();
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

    const settings = await openDisplay(page, "E2E Resize TV");
    await expect(settings.getByTestId("board-name-input")).toHaveValue("E2E Resize TV");
    await settings.getByRole("radio", { name: "Custom (inches)", exact: true }).click();
    const size = settings.getByRole("spinbutton", { name: "Custom (inches)", exact: true });
    await size.fill("85");
    const saved = page.waitForResponse(
      (response) =>
        response.url().endsWith(`/api/panels/${panel.id}`) && response.request().method() === "PATCH" && response.ok(),
    );
    await size.blur();
    expect((await saved).request().postDataJSON()).toEqual({ screen_diagonal_inches: 85 });
    await expect(settings.getByText("Preview at 85″", { exact: true })).toBeVisible();
    await expect(page.getByRole("dialog")).toHaveCount(0);
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

  test("converts a legacy LED panel with the server preview and an explicit content-copy choice", async ({ page }) => {
    const panel = await createPanelViaApi("E2E LED Layout");
    const switched = await fetch(`${API_URL}/panels/${panel.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ render_style: "led_matrix", matrix_layout: "legacy" }),
    });
    expect(switched.ok).toBe(true);
    await openDisplay(page, "E2E LED Layout");
    await page.getByRole("button", { name: "Advanced panel settings", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("button", { name: "Keep existing grid" })).toHaveAttribute("aria-pressed", "true");
    await dialog.getByRole("button", { name: "Fit screen shape" }).click();
    await expect(dialog.getByText("32 × 13 characters", { exact: true })).toBeVisible();
    await dialog.getByRole("button", { name: "Small (3 × 5)" }).click();
    await expect(dialog.getByText("48 × 18 characters", { exact: true })).toBeVisible();
    await expect(dialog.locator('[data-slot="led-matrix-display"]')).toHaveAttribute("data-matrix-height", "108");
    await expect(dialog.getByRole("checkbox", { name: "Copy this panel’s content to the new grid" })).not.toBeChecked();
    await dialog.getByRole("button", { name: "Save", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    const config = await (await fetch(`${API_URL}/panel/${panel.id}`)).json();
    expect(config).toMatchObject({
      rows: 18,
      cols: 48,
      matrix_layout: "screen",
      matrix_font: "3x5",
      matrix_sizing: "fill_tv",
    });
    expect(config.device_model_spec.geometry).toMatchObject({ width: 192, height: 108 });
    expect(config.device_model_spec.charset).toBe("led_3x5");
  });

  test("deleting a panel removes its display", async ({ page }) => {
    await createPanelViaApi("E2E Doomed Panel");

    const settings = await openDisplay(page, "E2E Doomed Panel");
    await expect(settings.getByTestId("board-name-input")).toHaveValue("E2E Doomed Panel");
    await settings.getByRole("button", { name: "Remove display…", exact: true }).click();
    const confirmation = page.getByRole("alertdialog");
    await expect(confirmation).toBeVisible();
    await confirmation.getByRole("button", { name: "Delete", exact: true }).click();

    // Back on Displays, without it.
    await expect(page).toHaveURL(/\/displays$/, { timeout: 10_000 });
    await expect(displayCard(page, "E2E Doomed Panel")).toHaveCount(0, { timeout: 10_000 });
  });
});
