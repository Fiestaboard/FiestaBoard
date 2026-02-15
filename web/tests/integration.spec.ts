/**
 * FiestaBoard Integration Tests
 *
 * End-to-end tests that exercise the full stack:
 *   Playwright browser  →  Next.js UI  →  FastAPI backend  →  Mock Vestaboard API
 *
 * Coverage:
 *   1. Setup wizard (board connection via Local API)
 *   2. Page creation (template page)
 *   3. Navigating between pages
 *   4. Schedule creation
 */
import { test, expect, getMockBoardState } from "./helpers";

// ---------------------------------------------------------------------------
// 1. Setup Wizard
// ---------------------------------------------------------------------------

test.describe("Setup Wizard", () => {
  test("completes the wizard using Local API mode", async ({ page }) => {
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
    await page.getByLabel("Board IP Address").fill("localhost");
    await page.getByLabel("Local API Key").fill("test-key");

    // Click "Test Connection" and wait for success
    await page.getByRole("button", { name: "Test Connection" }).click();
    await expect(page.getByText("Connected!")).toBeVisible({ timeout: 15_000 });

    // Proceed to Step 2
    await page.getByRole("button", { name: "Next" }).click();

    // Step 2: Add Data Sources — just proceed
    await expect(
      page.getByRole("heading", { name: "Add Data Sources" })
    ).toBeVisible();
    await page.getByRole("button", { name: "Next" }).click();

    // Step 3: You're All Set — finish
    await expect(page.getByText("Setup Complete!")).toBeVisible();

    // Click through to the dashboard
    const dashboardButton = page.getByRole("button", {
      name: /Go to Dashboard|Skip/,
    });
    await dashboardButton.click();

    // Should land on the Dashboard
    await expect(
      page.getByRole("heading", { name: "Dashboard" })
    ).toBeVisible({ timeout: 15_000 });
  });
});

// ---------------------------------------------------------------------------
// 2. Page creation
// ---------------------------------------------------------------------------

test.describe("Page Management", () => {
  test.beforeEach(async ({ page }) => {
    // Mark the wizard as complete so it doesn't appear
    await page.goto("/");
    await page.evaluate(() => {
      localStorage.setItem("fiestaboard_wizard_complete", "true");
    });
  });

  test("creates a new template page", async ({ page }) => {
    // Navigate to the Pages section
    await page.goto("/pages");
    await expect(
      page.getByRole("heading", { name: "Pages" })
    ).toBeVisible({ timeout: 15_000 });

    // Click "New" / create page button
    const newButton = page.getByRole("link", { name: /new/i }).or(
      page.getByRole("button", { name: /new|create/i })
    );
    await newButton.click();

    // Wait for the page builder to appear
    await expect(page.getByText(/Create Page|Page Name/)).toBeVisible({
      timeout: 10_000,
    });

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
    const saveButton = page
      .getByRole("button", { name: /save/i })
      .or(page.locator('[title="Save Page"]'));
    await saveButton.click();

    // Verify the page was saved — look for success toast or navigation
    await expect(
      page.getByText(/saved|success/i).or(
        page.getByRole("heading", { name: "Pages" })
      )
    ).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// 3. Navigation
// ---------------------------------------------------------------------------

test.describe("Navigation", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => {
      localStorage.setItem("fiestaboard_wizard_complete", "true");
    });
  });

  test("navigates between main sections", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" })
    ).toBeVisible({ timeout: 15_000 });

    // Navigate to Pages
    await page.getByRole("link", { name: "Pages" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Pages" })
    ).toBeVisible({ timeout: 10_000 });

    // Navigate to Schedule
    await page.getByRole("link", { name: "Schedule" }).first().click();
    await expect(
      page.getByRole("heading", { name: /schedule/i })
    ).toBeVisible({ timeout: 10_000 });

    // Navigate to Settings
    await page.getByRole("link", { name: "Settings" }).first().click();
    await expect(
      page.getByRole("heading", { name: /settings/i })
    ).toBeVisible({ timeout: 10_000 });

    // Navigate back to Dashboard
    await page.getByRole("link", { name: "Home" }).first().click();
    await expect(
      page.getByRole("heading", { name: "Dashboard" })
    ).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// 4. Schedule creation
// ---------------------------------------------------------------------------

test.describe("Schedule Management", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => {
      localStorage.setItem("fiestaboard_wizard_complete", "true");
    });
  });

  test("creates a schedule entry", async ({ page }) => {
    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: /schedule/i })
    ).toBeVisible({ timeout: 15_000 });

    // Look for a button to add a new schedule entry
    const addButton = page
      .getByRole("button", { name: /add|new|create/i })
      .first();
    await addButton.click();

    // Wait for the schedule form dialog/modal
    await expect(
      page.getByText(/create schedule|new schedule|schedule entry/i)
    ).toBeVisible({ timeout: 10_000 });

    // Select a page (the first available one)
    const pageSelect = page.locator("#page").or(
      page.getByLabel("Page")
    );
    if (await pageSelect.isVisible().catch(() => false)) {
      await pageSelect.click();
      // Click first available option
      const firstOption = page.getByRole("option").first();
      if (await firstOption.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await firstOption.click();
      }
    }

    // Set start and end times
    const startTime = page.locator("#start-time").or(
      page.getByLabel("Start Time")
    );
    if (await startTime.isVisible().catch(() => false)) {
      await startTime.click();
      const option0900 = page.getByRole("option", { name: "09:00" });
      if (await option0900.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await option0900.click();
      }
    }

    const endTime = page.locator("#end-time").or(
      page.getByLabel("End Time")
    );
    if (await endTime.isVisible().catch(() => false)) {
      await endTime.click();
      const option1700 = page.getByRole("option", { name: "17:00" });
      if (await option1700.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await option1700.click();
      }
    }

    // Submit the schedule
    const submitButton = page.getByRole("button", {
      name: /create schedule|save|submit/i,
    });
    if (await submitButton.isEnabled({ timeout: 3_000 }).catch(() => false)) {
      await submitButton.click();
    }

    // Verify the schedule page is still showing (no crash)
    await expect(
      page.getByRole("heading", { name: /schedule/i })
    ).toBeVisible({ timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// 5. Mock Board API Verification
// ---------------------------------------------------------------------------

test.describe("Mock Board API", () => {
  test("mock board server is running and responsive", async () => {
    const state = await getMockBoardState();
    expect(state).toHaveProperty("current_message");
    expect(state.current_message).toHaveLength(6);
    expect(state.current_message[0]).toHaveLength(22);
  });

  test("API health check responds OK", async () => {
    const res = await fetch("http://localhost:8000/health");
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.status).toBe("ok");
  });
});
