/**
 * Multi-Board Instance Management Integration Tests
 *
 * Covers:
 *  - Settings page: add, rename, toggle color, delete, cannot-delete-last
 *  - Setup Wizard: device selection switches, enable Note, cannot-deselect-all
 *  - Cross-feature: board config changes affect pages list tabs
 */
import {
  test,
  expect,
  configureBoard,
  clearBoardConfig,
  suppressWizard,
  deleteAllPages,
  createPage,
  createNotePage,
  API_URL,
  BOARD_HOST,
} from "./helpers";

// ---------------------------------------------------------------------------
// Test Group 1: Settings Page — Board Instance Management
// ---------------------------------------------------------------------------

test.describe("Settings – Board Instance Management", () => {
  test.beforeEach(async ({ page }) => {
    await configureBoard();
    await suppressWizard(page);
  });

  test.afterEach(async () => {
    // Reset to single flagship board
    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ devices: ["flagship"] }),
    });
  });

  test("can add a Note board instance from settings", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Find and click the "Note" add-board button
    const addNoteBtn = page.locator("button", { hasText: "Note" }).filter({
      has: page.locator("text=Note"),
    });
    await expect(addNoteBtn.first()).toBeVisible({ timeout: 10_000 });
    await addNoteBtn.first().click();

    // Verify Note dimensions appear
    await expect(page.getByText("15×3").first()).toBeVisible({ timeout: 5_000 });

    // Verify via API
    const res = await fetch(`${API_URL}/settings/board`);
    const data = await res.json();
    const noteBoard = data.boards.find(
      (b: { device_type: string }) => b.device_type === "note",
    );
    expect(noteBoard).toBeDefined();
  });

  test("can rename a board instance", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Wait for board cards to load
    await expect(page.getByText("Your Boards").first()).toBeVisible({
      timeout: 10_000,
    });

    // Find the board name input (should default to "Flagship")
    const nameInput = page.locator(
      ".rounded-lg.border input",
    ).first();
    await expect(nameInput).toBeVisible({ timeout: 5_000 });

    // Clear and type new name
    await nameInput.fill("My Living Room Board");
    await nameInput.blur();

    // Wait for save
    await page.waitForTimeout(1_000);

    // Verify via API
    const res = await fetch(`${API_URL}/settings/board`);
    const data = await res.json();
    const renamed = data.boards.find(
      (b: { name: string }) => b.name === "My Living Room Board",
    );
    expect(renamed).toBeDefined();
  });

  test("can toggle board color", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    await expect(page.getByText("Your Boards").first()).toBeVisible({
      timeout: 10_000,
    });

    // Find the color toggle button (should show "Black" initially)
    const colorBtn = page.locator("button:has-text('Black')").first();
    await expect(colorBtn).toBeVisible({ timeout: 5_000 });

    // Click to toggle to White
    await colorBtn.click();

    // Verify it changed
    await expect(page.locator("button:has-text('White')").first()).toBeVisible({
      timeout: 5_000,
    });

    // Verify via API
    const res = await fetch(`${API_URL}/settings/board`);
    const data = await res.json();
    const whiteBoard = data.boards.find(
      (b: { board_color: string }) => b.board_color === "white",
    );
    expect(whiteBoard).toBeDefined();

    // Toggle back to Black
    await page.locator("button:has-text('White')").first().click();
    await expect(page.locator("button:has-text('Black')").first()).toBeVisible({
      timeout: 5_000,
    });
  });

  test("can delete a board instance (when more than one exists)", async ({
    page,
  }) => {
    // Add a Note board first via API
    await fetch(`${API_URL}/settings/board/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_type: "note" }),
    });

    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    await expect(page.getByText("15×3").first()).toBeVisible({
      timeout: 10_000,
    });

    // Count boards before delete
    const resBefore = await fetch(`${API_URL}/settings/board`);
    const dataBefore = await resBefore.json();
    const countBefore = dataBefore.boards.length;
    expect(countBefore).toBeGreaterThanOrEqual(2);

    // Find a delete button that is enabled (not the last board)
    const deleteButtons = page.locator(
      ".rounded-lg.border button:has(svg)",
    );
    // Click the last delete button (the Note board)
    const lastDelete = deleteButtons.last();
    await expect(lastDelete).toBeVisible({ timeout: 5_000 });
    await expect(lastDelete).toBeEnabled();
    await lastDelete.click();

    // Wait for removal
    await page.waitForTimeout(1_000);

    // Verify via API that board count decreased
    const resAfter = await fetch(`${API_URL}/settings/board`);
    const dataAfter = await resAfter.json();
    expect(dataAfter.boards.length).toBe(countBefore - 1);
  });

  test("cannot delete the last board", async ({ page }) => {
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    await expect(page.getByText("Your Boards").first()).toBeVisible({
      timeout: 10_000,
    });

    // Verify only one board exists via API
    const res = await fetch(`${API_URL}/settings/board`);
    const data = await res.json();
    expect(data.boards.length).toBe(1);

    // The delete button should be disabled
    const deleteBtn = page.locator(
      ".rounded-lg.border button:has(svg)",
    ).last();
    await expect(deleteBtn).toBeVisible({ timeout: 5_000 });
    await expect(deleteBtn).toBeDisabled();
  });

  test("board dimensions display correctly for both device types", async ({
    page,
  }) => {
    // Add a Note board
    await fetch(`${API_URL}/settings/board/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_type: "note" }),
    });

    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Both dimension labels should be visible
    await expect(page.getByText("22×6").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("15×3").first()).toBeVisible({
      timeout: 5_000,
    });
  });
});

// ---------------------------------------------------------------------------
// Test Group 2: Setup Wizard — Device Selection
// ---------------------------------------------------------------------------

test.describe("Setup Wizard – Device Selection", () => {
  test.beforeEach(async () => {
    await clearBoardConfig();
  });

  test.afterEach(async () => {
    await configureBoard();
  });

  test("wizard shows device selection switches", async ({ page }) => {
    // Clear wizard completion so it appears
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
    });

    await page.goto("/");
    // Wizard should appear — look for the first step content
    await expect(page.getByText("Local API").first()).toBeVisible({
      timeout: 15_000,
    });

    // Device selection section should be visible
    await expect(page.getByText("Your Devices").first()).toBeVisible({
      timeout: 5_000,
    });

    // Both device labels should appear
    await expect(page.getByText("Flagship").first()).toBeVisible();
    await expect(page.getByText("Note").first()).toBeVisible();
  });

  test("can enable Note device in wizard and complete setup", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
    });

    await page.goto("/");
    await expect(page.getByText("Your Devices").first()).toBeVisible({
      timeout: 15_000,
    });

    // Find the Note switch and enable it
    // The Note switch is near the "Note" label and "15×3" text
    const noteSection = page.getByText("Note").first().locator("..");
    const noteSwitch = noteSection.getByRole("switch");
    if (await noteSwitch.isVisible().catch(() => false)) {
      const isChecked = await noteSwitch.isChecked();
      if (!isChecked) {
        await noteSwitch.click();
      }
    } else {
      // Fallback: click the Note text area to toggle
      const switches = page.getByRole("switch");
      const count = await switches.count();
      if (count >= 2) {
        // Second switch is typically Note
        const secondSwitch = switches.nth(1);
        if (!(await secondSwitch.isChecked())) {
          await secondSwitch.click();
        }
      }
    }

    // Fill in connection details to proceed
    await page.getByLabel("Board IP Address").fill(BOARD_HOST);
    await page.getByLabel("Local API Key").fill("test-key");

    // Click Next/Continue to proceed through wizard
    const nextBtn = page.getByRole("button", { name: /next|continue/i });
    if (await nextBtn.isVisible().catch(() => false)) {
      await nextBtn.click();
    }

    // Skip plugins step if it appears
    await page.waitForTimeout(1_000);
    const skipBtn = page.getByRole("button", { name: /next|skip|continue/i });
    if (await skipBtn.isVisible().catch(() => false)) {
      await skipBtn.click();
    }

    // Complete wizard — look for finish/done button
    await page.waitForTimeout(1_000);
    const finishBtn = page.getByRole("button", {
      name: /finish|done|get started|complete/i,
    });
    if (await finishBtn.isVisible().catch(() => false)) {
      await finishBtn.click();
    }

    // Wait for completion
    await page.waitForTimeout(2_000);

    // Verify via API that Note device is configured
    const res = await fetch(`${API_URL}/settings/board`);
    const data = await res.json();
    expect(data.devices).toContain("note");
    const noteBoard = data.boards.find(
      (b: { device_type: string }) => b.device_type === "note",
    );
    expect(noteBoard).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// Test Group 3: Cross-Feature Integration
// ---------------------------------------------------------------------------

test.describe("Cross-Feature – Board Config affects Pages", () => {
  test.beforeEach(async ({ page }) => {
    await configureBoard();
    await suppressWizard(page);
    await deleteAllPages();
  });

  test.afterEach(async () => {
    await deleteAllPages();
    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ devices: ["flagship"] }),
    });
  });

  test("adding Note board enables Note tab in pages list", async ({
    page,
  }) => {
    // Start with flagship only — no Note tab
    await page.goto("/pages");
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Note tab should NOT be visible with only Flagship
    const noteTab = page.getByRole("tab", { name: "Note" });
    await expect(noteTab).toHaveCount(0, { timeout: 3_000 });

    // Add a Note board via API
    await fetch(`${API_URL}/settings/board/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_type: "note" }),
    });

    // Reload and verify Note tab appears
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    await expect(page.getByRole("tab", { name: "Note" })).toBeVisible({
      timeout: 5_000,
    });
    await expect(page.getByRole("tab", { name: "Flagship" })).toBeVisible();
  });

  test("removing Note board hides Note tab in pages list", async ({
    page,
  }) => {
    // Configure both devices
    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ devices: ["flagship", "note"] }),
    });

    await page.goto("/pages");
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Both tabs visible
    await expect(page.getByRole("tab", { name: "Note" })).toBeVisible({
      timeout: 5_000,
    });

    // Remove Note by resetting to flagship only
    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ devices: ["flagship"] }),
    });

    // Reload and verify Note tab is gone
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    await expect(page.getByRole("tab", { name: "Note" })).toHaveCount(0, {
      timeout: 3_000,
    });
  });

  test("Note page create loads 3-line editor when Note device is configured", async ({
    page,
  }) => {
    // Enable both devices
    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ devices: ["flagship", "note"] }),
    });

    await page.goto("/pages/new?device=note");
    await expect(page.getByText("Create Page")).toBeVisible({
      timeout: 15_000,
    });

    // Editor should have 2 hard breaks (3 lines)
    const editor = page.locator('[contenteditable="true"]').first();
    await expect(editor).toBeVisible();
    const brCount = await editor.locator("br").count();
    expect(brCount).toBe(2);
  });
});
