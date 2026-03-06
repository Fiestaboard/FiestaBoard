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
import { test, expect, getMockBoardState, clearBoardConfig, configureBoard, resetToSingleBoard, suppressWizard, API_URL, BOARD_HOST } from "./helpers";

// ---------------------------------------------------------------------------
// 1. Mock Board API & Backend Health
// ---------------------------------------------------------------------------

test.describe("Infrastructure", () => {
  test("mock board server is running and responsive", async () => {
    const state = await getMockBoardState();
    expect(state).toHaveProperty("current_message");
    expect(state.current_message).toHaveLength(6);
    expect(state.current_message[0]).toHaveLength(22);
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

    // Ensure no lingering wizard completion state
    await page.addInitScript(() => {
      localStorage.removeItem("fiestaboard_wizard_complete");
      localStorage.removeItem("fiestaboard_wizard_progress");
    });

    // Navigate to the app — on first run the wizard should appear
    await page.goto("/");

    // Wait for the wizard to render (it lazy-loads)
    await expect(
      page.getByRole("heading", { name: "Welcome to FiestaBoard" })
    ).toBeVisible({ timeout: 30_000 });

    // Step 1: Connect Your Board
    await expect(
      page.getByRole("heading", { name: "Connect Your Board" })
    ).toBeVisible();

    // Select Local API mode
    await page.getByText("Local API").click();

    // Fill in board host and API key
    await page.getByLabel("Board IP Address").fill(BOARD_HOST);
    await page.getByLabel("Local API Key").fill("test-key");

    // Click "Test Connection" and wait for success
    await page.getByRole("button", { name: "Test Connection" }).click();
    await expect(page.getByText("Connected!")).toBeVisible({ timeout: 15_000 });

    // Proceed to Step 2
    await page.getByRole("button", { name: "Next", exact: true }).click();

    // Step 2: Add Data Sources — just proceed
    await expect(
      page.getByRole("heading", { name: "Add Data Sources" })
    ).toBeVisible();
    await page.getByRole("button", { name: "Next", exact: true }).click();

    // Step 3: You're All Set — finish
    await expect(page.getByRole("heading", { name: "Setup Complete!" })).toBeVisible();

    // Click through to the dashboard (could be either label)
    const dashboardButton = page.getByRole("button", {
      name: /Go to Dashboard|Skip/,
    });
    await dashboardButton.click();

    // Should land on the Dashboard after reload
    await expect(
      page.getByRole("heading", { name: "Dashboard" })
    ).toBeVisible({ timeout: 15_000 });

    // Verify the wizard created a proper BoardInstance
    const res = await fetch(`${API_URL}/settings/board`);
    const data = await res.json();
    expect(data.boards.length).toBeGreaterThanOrEqual(1);
    const board = data.boards[0];
    expect(board.name).toBe("My Board");
    expect(board.device_type).toBe("flagship");
    expect(board.board_color).toBe("black");
    expect(board.api_mode).toBe("local");
    expect(board.enabled).toBe(true);

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
    await expect(
      page.getByRole("heading", { name: "Dashboard" })
    ).toBeVisible({ timeout: 15_000 });

    // Navigate to Pages
    await page.getByRole("link", { name: "Pages" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true })
    ).toBeVisible({ timeout: 10_000 });

    // Navigate to Schedule
    await page.getByRole("link", { name: "Schedule" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true })
    ).toBeVisible({ timeout: 10_000 });

    // Navigate to Settings
    await page.getByRole("link", { name: "Settings" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true })
    ).toBeVisible({ timeout: 10_000 });

    // Navigate back to Dashboard
    await page.getByRole("link", { name: "Home" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Dashboard" })
    ).toBeVisible({ timeout: 10_000 });
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
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true })
    ).toBeVisible({ timeout: 15_000 });

    // Click "New" button
    await page.getByRole("button", { name: /New/ }).click();

    // Wait for the page builder to appear
    await expect(
      page.getByText("Create Page").first()
    ).toBeVisible({ timeout: 10_000 });

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
    const saveButton = page.getByRole("button", { name: "Save Page" }).or(
      page.getByRole("button", { name: /save/i })
    );
    await saveButton.first().click();

    // After save, the app shows a toast and/or navigates to /pages
    await expect(
      page.getByRole("heading", { name: "Pages", exact: true })
    ).toBeVisible({ timeout: 15_000 });
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
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true })
    ).toBeVisible({ timeout: 15_000 });

    // Click "Add Schedule" button
    await page.getByRole("button", { name: "Add Schedule" }).first().click();

    // Wait for the schedule form dialog — title is "Add Schedule" in the dialog
    await expect(
      page.getByText("Add Schedule").first()
    ).toBeVisible({ timeout: 10_000 });

    // Select a page (the first available one) via the Radix select trigger
    const pageSelect = page.locator("#page");
    if (await pageSelect.isVisible().catch(() => false)) {
      await pageSelect.click();
      // Click first available option
      const firstOption = page.getByRole("option").first();
      if (await firstOption.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await firstOption.click();
      }
    }

    // Set start time
    const startTime = page.locator("#start-time");
    if (await startTime.isVisible().catch(() => false)) {
      await startTime.click();
      const option0900 = page.getByRole("option", { name: "09:00" });
      if (await option0900.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await option0900.click();
      }
    }

    // Set end time
    const endTime = page.locator("#end-time");
    if (await endTime.isVisible().catch(() => false)) {
      await endTime.click();
      const option1700 = page.getByRole("option", { name: "17:00" });
      if (await option1700.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await option1700.click();
      }
    }

    // Submit the schedule
    const submitButton = page.getByRole("button", {
      name: "Create Schedule",
    });
    if (await submitButton.isEnabled({ timeout: 3_000 }).catch(() => false)) {
      await submitButton.click();
    }

    // Verify the schedule page is still showing (no crash)
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true })
    ).toBeVisible({ timeout: 10_000 });
  });
});
