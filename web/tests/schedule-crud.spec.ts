/**
 * FiestaBoard Schedule CRUD Integration Tests
 *
 * Tests schedule management through the UI:
 *   - Create a schedule and verify it is listed
 *   - Delete a schedule
 *
 * NOTE: Tests run sequentially. The wizard must have completed.
 */
import { API_URL, configureBoard, expect, test } from "./helpers";

function API() {
  return API_URL;
}

// Suppress the setup wizard for all tests in this file
test.beforeEach(async ({ page }) => {
  await configureBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

// ---------------------------------------------------------------------------
// Helper: ensure at least one page exists for schedule references
// ---------------------------------------------------------------------------

async function ensurePage(): Promise<string> {
  const pagesRes = await fetch(`${API()}/pages`);
  const pagesData = await pagesRes.json();
  if (pagesData.total > 0) {
    return pagesData.pages[0].id;
  }
  const createRes = await fetch(`${API()}/pages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: "Schedule Helper Page",
      type: "template",
      template: ["SCHEDULE", "", "", "", "", ""],
    }),
  });
  const created = await createRes.json();
  return created.page.id;
}

// ---------------------------------------------------------------------------
// Schedule list & delete
// ---------------------------------------------------------------------------

test.describe("Schedule CRUD", () => {
  test("can create a schedule and see it listed", async ({ page }) => {
    const pageId = await ensurePage();

    // Create a schedule via API
    const createRes = await fetch(`${API()}/schedules`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_id: pageId,
        day_pattern: "weekdays",
        start_time: "10:00",
        end_time: "14:00",
      }),
    });
    expect(createRes.ok).toBe(true);

    // Navigate to the schedule page
    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    // Verify the schedule entry is visible (shows the full time range)
    await expect(page.getByText("10:00 - 14:00").first()).toBeVisible({ timeout: 10_000 });
  });

  test("can delete a schedule", async ({ page }) => {
    const pageId = await ensurePage();

    // Create a schedule via API
    const createRes = await fetch(`${API()}/schedules`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_id: pageId,
        day_pattern: "weekends",
        start_time: "18:00",
        end_time: "22:00",
      }),
    });
    expect(createRes.ok).toBe(true);
    const created = await createRes.json();
    const scheduleId = created.id;

    // Verify the schedule exists via API
    const listBefore = await fetch(`${API()}/schedules`);
    const dataBefore = await listBefore.json();
    expect(dataBefore.schedules.some((s: { id: string }) => s.id === scheduleId)).toBe(true);

    // Delete via API
    const deleteRes = await fetch(`${API()}/schedules/${scheduleId}`, {
      method: "DELETE",
    });
    expect(deleteRes.ok).toBe(true);

    // Verify the schedule no longer exists via API
    const listAfter = await fetch(`${API()}/schedules`);
    const dataAfter = await listAfter.json();
    expect(dataAfter.schedules.some((s: { id: string }) => s.id === scheduleId)).toBe(false);

    // Navigate to schedule page and verify it loads without errors
    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });
  });
});
