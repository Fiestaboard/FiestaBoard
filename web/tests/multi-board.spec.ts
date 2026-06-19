/**
 * Multi-Board & Board Configuration E2E Tests
 *
 * Comprehensive coverage of the per-board configuration model:
 *  - Settings page: board card display (name, type, dimensions, connection badge)
 *  - Settings page: board CRUD (add, change type/color, delete)
 *  - Setup Wizard: board type picker, color swatches, BoardInstance creation
 *  - Cross-feature: board config changes affect pages list tabs
 */
import {
  API_URL,
  BOARD_HOST,
  clearBoardConfig,
  configureBoard,
  deleteAllPages,
  expect,
  openSettingsTab,
  resetToSingleBoard,
  suppressWizard,
  test,
  waitForFirstRun,
} from "./helpers";

// ---------------------------------------------------------------------------
// Test Group 1: Settings – Board Card Display
// ---------------------------------------------------------------------------

test.describe("Settings – Board Card Display", () => {
  test.beforeEach(async ({ page }) => {
    await configureBoard();
    await resetToSingleBoard();
    await suppressWizard(page);
  });

  test.afterEach(async () => {
    await resetToSingleBoard();
  });

  test("board card header shows name, device type, and dimensions", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await openSettingsTab(page, "Hardware");

    await expect(page.getByText("My Board").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("22 × 6").first()).toBeVisible();
  });

  test("board card shows Connected badge when credentials are set", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await openSettingsTab(page, "Hardware");

    await expect(page.getByText("Connected").first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("board card shows Not configured badge when credentials are missing", async ({ page }) => {
    // Add a second board with no connection credentials
    await fetch(`${API_URL}/settings/board/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_type: "note" }),
    });

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await openSettingsTab(page, "Hardware");

    await expect(page.getByText("Not configured").first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("Flagship and Note boards show correct dimensions", async ({ page }) => {
    await fetch(`${API_URL}/settings/board/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_type: "note" }),
    });

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await openSettingsTab(page, "Hardware");

    await expect(page.getByText("22 × 6").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("15 × 3").first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Test Group 2: Settings – Board Instance CRUD
// ---------------------------------------------------------------------------

test.describe("Settings – Board Instance CRUD", () => {
  test.beforeEach(async ({ page }) => {
    await configureBoard();
    await resetToSingleBoard();
    await suppressWizard(page);
  });

  test.afterEach(async () => {
    await resetToSingleBoard();
  });

  test("can add a Note board via the Add Board picker", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await openSettingsTab(page, "Hardware");

    // Click Add Board to reveal type picker
    await page.getByRole("button", { name: "Add Board" }).click();
    await expect(page.getByText("Select type:")).toBeVisible({
      timeout: 5_000,
    });

    // Click the Note option in the type picker
    await page.getByRole("button", { name: "Note", exact: true }).click();

    // Verify Note dimensions appear
    await expect(page.getByText("15 × 3").first()).toBeVisible({
      timeout: 10_000,
    });

    // Verify via API
    const res = await fetch(`${API_URL}/settings/board`);
    const data = await res.json();
    expect(data.boards.length).toBe(2);
    expect(data.boards.some((b: { device_type: string }) => b.device_type === "note")).toBe(true);
  });

  test("can add a Flagship board via the Add Board picker", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await openSettingsTab(page, "Hardware");

    await page.getByRole("button", { name: "Add Board" }).click();
    await expect(page.getByText("Select type:")).toBeVisible({
      timeout: 5_000,
    });

    // Click the Flagship option in the type picker
    await page.getByRole("button", { name: "Flagship", exact: true }).click();

    await expect(page.getByText("Board added"))
      .toBeVisible({ timeout: 5_000 })
      .catch(() => {});
    await page.waitForTimeout(1_000);

    const res = await fetch(`${API_URL}/settings/board`);
    const data = await res.json();
    expect(data.boards.length).toBe(2);
    const types = data.boards.map((b: { device_type: string }) => b.device_type);
    expect(types.filter((t: string) => t === "flagship").length).toBe(2);
  });

  test("can change device type via type pills", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await openSettingsTab(page, "Hardware");

    // Expand board card
    await page.getByText("My Board").first().click();
    await expect(page.getByText("Type").first()).toBeVisible({
      timeout: 5_000,
    });

    // Click Note pill (the small pill button, not the header text)
    await page.getByRole("button", { name: "Note", exact: true }).first().click();
    await page.waitForTimeout(1_500);

    // Header should now show 15 × 3 dimensions
    await expect(page.getByText("15 × 3").first()).toBeVisible({
      timeout: 5_000,
    });

    const res = await fetch(`${API_URL}/settings/board`);
    const data = await res.json();
    expect(data.boards[0].device_type).toBe("note");
  });

  test("can change board color via swatches", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await openSettingsTab(page, "Hardware");

    // Expand board card
    await page.getByText("My Board").first().click();
    await expect(page.getByText("Color").first()).toBeVisible({
      timeout: 5_000,
    });

    // Click the White swatch
    await page.getByRole("button", { name: "White", exact: true }).first().click();
    await page.waitForTimeout(1_500);

    const res = await fetch(`${API_URL}/settings/board`);
    const data = await res.json();
    expect(data.boards[0].board_color).toBe("white");

    // Click Black swatch to revert
    await page.getByRole("button", { name: "Black", exact: true }).first().click();
    await page.waitForTimeout(1_500);

    const res2 = await fetch(`${API_URL}/settings/board`);
    const data2 = await res2.json();
    expect(data2.boards[0].board_color).toBe("black");
  });

  test("can delete a board when more than one exists", async ({ page }) => {
    // Add a Note board first
    await fetch(`${API_URL}/settings/board/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_type: "note" }),
    });

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await openSettingsTab(page, "Hardware");

    const resBefore = await fetch(`${API_URL}/settings/board`);
    const dataBefore = await resBefore.json();
    expect(dataBefore.boards.length).toBe(2);

    // Expand the Note board (click on 15 × 3 dimensions to target the right card)
    await expect(page.getByText("15 × 3").first()).toBeVisible({
      timeout: 10_000,
    });
    await page.getByText("15 × 3").first().click();

    // Click Remove Board
    const removeBtn = page.getByRole("button", { name: /Remove Board/i });
    await expect(removeBtn.first()).toBeVisible({ timeout: 5_000 });
    await expect(removeBtn.first()).toBeEnabled();
    await removeBtn.first().click();
    await page.waitForTimeout(1_500);

    const resAfter = await fetch(`${API_URL}/settings/board`);
    const dataAfter = await resAfter.json();
    expect(dataAfter.boards.length).toBe(1);
  });

  test("cannot delete the last remaining board", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await openSettingsTab(page, "Hardware");

    const res = await fetch(`${API_URL}/settings/board`);
    const data = await res.json();
    expect(data.boards.length).toBe(1);

    // Expand the board card
    await page.getByText("My Board").first().click();

    const removeBtn = page.getByRole("button", { name: /Remove Board/i });
    await expect(removeBtn).toBeVisible({ timeout: 5_000 });
    await expect(removeBtn).toBeDisabled();
  });

  test("new boards get auto-incrementing names", async () => {
    const res1 = await fetch(`${API_URL}/settings/board`);
    const data1 = await res1.json();
    expect(data1.boards[0].name).toBe("My Board");

    // Add second board
    await fetch(`${API_URL}/settings/board/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_type: "note" }),
    });

    const res2 = await fetch(`${API_URL}/settings/board`);
    const data2 = await res2.json();
    const names2 = data2.boards.map((b: { name: string }) => b.name);
    expect(names2).toContain("My Board");
    expect(names2).toContain("My Board 2");

    // Add third board
    await fetch(`${API_URL}/settings/board/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_type: "flagship" }),
    });

    const res3 = await fetch(`${API_URL}/settings/board`);
    const data3 = await res3.json();
    const names3 = data3.boards.map((b: { name: string }) => b.name);
    expect(names3).toContain("My Board 3");
  });
});

// ---------------------------------------------------------------------------
// Test Group 3: Setup Wizard – Board Configuration
// ---------------------------------------------------------------------------

test.describe("Setup Wizard – Board Configuration", () => {
  test.beforeEach(async () => {
    await clearBoardConfig();
    await waitForFirstRun();
  });

  test.afterEach(async () => {
    await configureBoard();
    await resetToSingleBoard();
  });

  test("wizard shows Board Type picker with Flagship and Note pills", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
    });

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Welcome to FiestaBoard" })).toBeVisible({ timeout: 30_000 });

    await expect(page.getByText("Board Type")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("Flagship")).toBeVisible();
    await expect(page.getByText("22 × 6 characters")).toBeVisible();
    await expect(page.getByText("Note")).toBeVisible();
    await expect(page.getByText("15 × 3 characters")).toBeVisible();
  });

  test("wizard shows Board Color swatches with Black and White options", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
    });

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Welcome to FiestaBoard" })).toBeVisible({ timeout: 30_000 });

    await expect(page.getByText("Board Color")).toBeVisible({
      timeout: 5_000,
    });
    await expect(page.getByRole("button", { name: "Black" })).toBeVisible();
    await expect(page.getByRole("button", { name: "White" })).toBeVisible();
  });

  test("wizard creates BoardInstance with correct name, type, color, and credentials", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
    });

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Connect Your Board" })).toBeVisible({ timeout: 30_000 });

    // Fill Local API credentials first
    await page.getByText("Local API").click();
    await page.getByLabel("Board IP Address").fill(BOARD_HOST);
    await page.getByLabel("Local API Key").fill("test-key");

    // Select Note type and White color LAST (right before Test Connection)
    // so these are the most recent React state changes in the closure
    const noteTypeBtn = page.locator("button", {
      hasText: "15 × 3 characters",
    });
    await noteTypeBtn.scrollIntoViewIfNeeded();
    await expect(noteTypeBtn).toBeVisible({ timeout: 5_000 });
    await noteTypeBtn.click();
    await expect(noteTypeBtn).toHaveClass(/border-primary/, {
      timeout: 2_000,
    });

    const whiteBtn = page.getByRole("button", { name: "White" });
    await whiteBtn.click();
    await expect(whiteBtn).toHaveClass(/ring-2/, { timeout: 2_000 });

    // Allow React to fully settle all state updates
    await page.waitForTimeout(500);

    // Click Test Connection
    const testConnBtn = page.getByRole("button", {
      name: "Test Connection",
    });
    await testConnBtn.scrollIntoViewIfNeeded();
    await testConnBtn.click();
    await expect(page.getByText("Connected!")).toBeVisible({
      timeout: 15_000,
    });

    // Verify the board instance was saved via API
    const res = await fetch(`${API_URL}/settings/board`);
    const data = await res.json();
    expect(data.boards.length).toBe(1);

    const board = data.boards[0];
    expect(board.name).toBe("My Board");
    expect(board.device_type).toBe("note");
    expect(board.board_color).toBe("white");
    expect(board.api_mode).toBe("local");
    expect(board.host).toBe(BOARD_HOST);
    expect(board.enabled).toBe(true);
  });

  test("wizard defaults to Flagship and Black when no selection is made", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
    });

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Connect Your Board" })).toBeVisible({ timeout: 30_000 });

    // Don't change type or color — use defaults
    await page.getByText("Local API").click();
    await page.getByLabel("Board IP Address").fill(BOARD_HOST);
    await page.getByLabel("Local API Key").fill("test-key");

    await page.getByRole("button", { name: "Test Connection" }).click();
    await expect(page.getByText("Connected!")).toBeVisible({
      timeout: 15_000,
    });

    const res = await fetch(`${API_URL}/settings/board`);
    const data = await res.json();
    expect(data.boards[0].device_type).toBe("flagship");
    expect(data.boards[0].board_color).toBe("black");
  });

  test("wizard-created board shows correctly on settings page", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
    });

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Connect Your Board" })).toBeVisible({ timeout: 30_000 });

    // Select Note type first — scroll to Board Type section
    const noteTypeBtn = page.locator("button", {
      hasText: "15 × 3 characters",
    });
    await noteTypeBtn.scrollIntoViewIfNeeded();
    await expect(noteTypeBtn).toBeVisible({ timeout: 5_000 });
    await noteTypeBtn.click();
    await expect(noteTypeBtn).toHaveClass(/border-primary/, {
      timeout: 2_000,
    });

    // Select White color
    const whiteBtn = page.getByRole("button", { name: "White" });
    await whiteBtn.click();
    await expect(whiteBtn).toHaveClass(/ring-2/, { timeout: 2_000 });

    // Fill Local API credentials (scrolls up)
    await page.getByText("Local API").click();
    await page.getByLabel("Board IP Address").fill(BOARD_HOST);
    await page.getByLabel("Local API Key").fill("test-key");

    // Click Test Connection
    await page.getByRole("button", { name: "Test Connection" }).click();
    await expect(page.getByText("Connected!")).toBeVisible({
      timeout: 15_000,
    });

    // Proceed through wizard steps
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Add Data Sources" })).toBeVisible();
    await page.getByRole("button", { name: "Next", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Setup Complete!" })).toBeVisible();

    await page.getByRole("button", { name: /Go to Dashboard|Skip/ }).click();

    // Navigate to settings page
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await openSettingsTab(page, "Hardware");

    // Verify board card shows correct info
    await expect(page.getByText("My Board").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("15 × 3").first()).toBeVisible();
    await expect(page.getByText("Connected").first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Test Group 4: Cross-Feature – Board Config affects Pages
// ---------------------------------------------------------------------------

test.describe("Cross-Feature – Board Config affects Pages", () => {
  test.beforeEach(async ({ page }) => {
    await configureBoard();
    await resetToSingleBoard();
    await suppressWizard(page);
    await deleteAllPages();
  });

  test.afterEach(async () => {
    await deleteAllPages();
    await resetToSingleBoard();
  });

  test("adding Note board enables Note tab in pages list", async ({ page }) => {
    await page.goto("/pages");
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });

    // Note tab should NOT be visible with only Flagship
    await expect(page.getByRole("tab", { name: "Note" })).toHaveCount(0, {
      timeout: 3_000,
    });

    // Add a Note board via API
    await fetch(`${API_URL}/settings/board/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_type: "note" }),
    });

    await page.reload();
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });

    await expect(page.getByRole("tab", { name: "Note" })).toBeVisible({
      timeout: 5_000,
    });
    await expect(page.getByRole("tab", { name: "Flagship" })).toBeVisible();
  });

  test("removing Note board hides Note tab in pages list", async ({ page }) => {
    // Start with both device types
    await fetch(`${API_URL}/settings/board/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_type: "note" }),
    });

    await page.goto("/pages");
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });

    await expect(page.getByRole("tab", { name: "Note" })).toBeVisible({
      timeout: 5_000,
    });

    // Remove Note by resetting to single Flagship board
    await resetToSingleBoard();

    await page.reload();
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });

    await expect(page.getByRole("tab", { name: "Note" })).toHaveCount(0, {
      timeout: 3_000,
    });
  });

  test("Note page editor loads 3-line layout when Note device exists", async ({ page }) => {
    // Add a Note board
    await fetch(`${API_URL}/settings/board/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_type: "note" }),
    });

    await page.goto("/pages/new?device=note");
    await expect(page.getByText("Create Page")).toBeVisible({
      timeout: 15_000,
    });

    const editor = page.locator('[contenteditable="true"]').first();
    await expect(editor).toBeVisible();
    const brCount = await editor.locator("br").count();
    expect(brCount).toBe(2);
  });
});
