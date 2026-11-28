/**
 * FiestaBoard Integration Tests
 *
 * End-to-end tests that exercise the full stack:
 *   Playwright browser  →  Next.js UI  →  FastAPI backend  →  Mock Vestaboard API
 *
 * Coverage:
 *   1. Mock Board API health checks
 *   2. Setup wizard (board connection via Local API)
 *   3. Navigation between sections
 *   4. Page creation (template page)
 *   5. Schedule creation
 *
 * NOTE: Tests run sequentially. The wizard test runs first and configures
 * the board so subsequent tests have a working backend.
 */
import {
  API_URL,
  authHeaders,
  BOARD_HOST,
  chooseVestaboardInWizard,
  clearBoardConfig,
  configureBoard,
  createPage,
  expect,
  getMockBoardState,
  mockBoardGrid,
  resetToSingleBoard,
  suppressWizard,
  test,
  waitForFirstRun,
} from "./helpers";
import { pickTime } from "./time-picker";

// ---------------------------------------------------------------------------
// 1. Mock Board API & Backend Health
// ---------------------------------------------------------------------------

test.describe("Infrastructure", () => {
  test("mock board server is running and responsive", async () => {
    const state = await getMockBoardState();
    expect(state).toHaveProperty("current_message");
    const grid = mockBoardGrid(state);
    expect(grid).toHaveLength(6);
    expect(grid[0]).toHaveLength(22);
  });

  test("API health check responds OK", async () => {
    const res = await fetch(`${API_URL}/health`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.status).toBe("ok");
  });
});

// ---------------------------------------------------------------------------
// 2. Setup Wizard
// ---------------------------------------------------------------------------

test.describe("Setup Wizard", () => {
  test("completes the wizard using Local API mode", async ({ page }) => {
    // Clear any board config so the backend reports first-run mode
    await clearBoardConfig();
    await waitForFirstRun();

    // Ensure no lingering wizard completion state
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
      localStorage.removeItem("fiestaboard_wizard_progress");
    });

    // Navigate to the app — on first run the wizard should appear
    await page.goto("/");

    // Wait for the wizard to render (it lazy-loads)
    await expect(page.getByRole("heading", { name: "Welcome to FiestaBoard" })).toBeVisible({ timeout: 30_000 });

    // Welcome, choose the first display, then connect it.
    await chooseVestaboardInWizard(page);
    await expect(page.getByRole("heading", { name: "Connect your Vestaboard" })).toBeVisible();

    // Select Local API mode
    await page.getByRole("radio", { name: "Local API", exact: true }).click();

    // Fill in board host and API key
    await page.getByLabel("Address", { exact: true }).fill(BOARD_HOST);
    await page.getByLabel("Local API key", { exact: true }).fill("test-key");

    const pagesBefore = await (await fetch(`${API_URL}/pages`, { headers: authHeaders() })).json();
    const settingsBefore = await (await fetch(`${API_URL}/settings/board`, { headers: authHeaders() })).json();

    // Testing a draft must not create a board or persist its secret.
    await page.getByRole("button", { name: "Test connection", exact: true }).click();
    await expect(page.getByRole("status").filter({ hasText: /Connected · \d+ ms/ })).toBeVisible({ timeout: 15_000 });

    expect(await (await fetch(`${API_URL}/settings/board`, { headers: authHeaders() })).json()).toEqual(settingsBefore);

    // Continue saves the tested display, then opens data sources.
    await page.getByRole("button", { name: "Continue", exact: true }).click();

    // Step 3: Add data sources — just proceed
    await expect(page.getByRole("heading", { name: "Add data sources" })).toBeVisible();
    await page.getByRole("button", { name: "Continue", exact: true }).click();

    // Step 4: review, then finish without creating starter content.
    await expect(page.getByRole("heading", { name: "Ready to go" })).toBeVisible();

    // Finish returns to Home.
    const dashboardButton = page.getByRole("button", {
      name: "Finish setup",
    });
    await dashboardButton.click();

    // The wizard yields to Home.
    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible({ timeout: 15_000 });

    // Verify the wizard created a proper BoardInstance
    const res = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
    const data = await res.json();
    expect(data.boards).toHaveLength(1);
    const board = data.boards[0];
    expect(board.name).toBe("My board");
    expect(board.device_type).toBe("flagship");
    expect(board.board_color).toBe("black");
    expect(board.output_config.api_mode).toBe("local");
    expect(board.enabled).toBe(true);

    expect(board.output_config.host).toBe(BOARD_HOST);
    expect(board.output_config.local_api_key).toBe("***");
    const pagesAfter = await (await fetch(`${API_URL}/pages`, { headers: authHeaders() })).json();
    expect(pagesAfter.pages.map((item: { id: string }) => item.id).sort()).toEqual(
      pagesBefore.pages.map((item: { id: string }) => item.id).sort(),
    );

    // Clean up
    await resetToSingleBoard();
  });
});

// ---------------------------------------------------------------------------
// 3. Navigation
// ---------------------------------------------------------------------------

test.describe("Navigation", () => {
  test("navigates between main sections", async ({ page }) => {
    await configureBoard();
    await suppressWizard(page);

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible({ timeout: 15_000 });

    // Navigate to Pages
    await page.getByRole("link", { name: "Pages" }).first().click();
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 10_000 });

    // Navigate to Schedule
    await page.getByRole("link", { name: "Schedule" }).first().click();
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 10_000 });

    // Navigate to Settings — from the rail's footer menu, not the nav list.
    await page.locator('aside [data-slot="sidebar-account-trigger"]').click();
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 10_000 });

    // Navigate back to Dashboard
    await page.getByRole("link", { name: "Home" }).first().click();
    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// 4. Page creation
// ---------------------------------------------------------------------------

test.describe("Page Management", () => {
  test("creates a new template page", async ({ page }) => {
    await configureBoard();
    await suppressWizard(page);

    // Navigate to the Pages section
    await page.goto("/pages");
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });

    // Click "New" button
    await page.getByRole("button", { name: /New/ }).click();

    // Wait for the page builder to appear
    await expect(page.locator("#page-name")).toBeVisible({ timeout: 10_000 });

    // Fill in page name
    const nameInput = page.getByPlaceholder("My Custom Page");
    await nameInput.fill("Integration Test Page");

    // The editor should be visible — type some content
    const editor = page.locator('[contenteditable="true"]').first();
    if (await editor.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await editor.click();
      await editor.fill("HELLO WORLD");
    }

    // Save the page
    const saveButton = page.getByRole("button", { name: "Save page" }).or(page.getByRole("button", { name: /save/i }));
    await saveButton.first().click();

    // After save the editor stays open (it draws its own header, not the
    // section's), announces the save, and its way back returns to the list.
    await expect(page.getByText("Saved to Pages").first()).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "Back to Pages" }).click();
    await expect(page.getByRole("heading", { name: "Pages", exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Integration Test Page").first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 5. Schedule creation
// ---------------------------------------------------------------------------

test.describe("Schedule Management", () => {
  test("creates a schedule entry", async ({ page }) => {
    await configureBoard();
    await suppressWizard(page);

    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    const targetName = `Integration schedule ${Date.now()}`;
    const pageId = await createPage(targetName);
    // Reload the page list after creating the independent compatible target.
    await page.reload();
    await page.getByRole("button", { name: "Add entry", exact: true }).first().click();
    const dialog = page.getByRole("dialog", { name: "Add Schedule", exact: true });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("combobox", { name: /^Page or Collection/ }).click();
    const target = page.getByRole("option", { name: targetName, exact: true });
    await target.click();
    await pickTime(page, dialog.getByLabel("Start Time", { exact: true }), "09:00");
    await pickTime(page, dialog.getByLabel("End Time", { exact: true }), "17:00");
    const createdResponse = page.waitForResponse(
      (response) => response.url().includes("/api/v1/schedules") && response.request().method() === "POST",
    );
    await dialog.getByRole("button", { name: "Save", exact: true }).click();
    const response = await createdResponse;
    expect(response.ok()).toBe(true);
    const created = await response.json();
    expect(created).toMatchObject({ page_id: pageId, start_time: "09:00", end_time: "17:00", enabled: true });
    expect(created.id).toEqual(expect.any(String));
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible();
    const persisted = await page.request.get(`${API_URL}/v1/schedules`);
    expect(persisted.ok()).toBe(true);
    expect((await persisted.json()).schedules).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: created.id, page_id: pageId, start_time: "09:00", end_time: "17:00" }),
      ]),
    );
  });
});
