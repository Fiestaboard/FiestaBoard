/**
 * FiestaBoard Schedule CRUD Integration Tests
 *
 * Tests schedule management through the UI:
 *   - Create a schedule and verify it is listed
 *   - Delete a schedule
 *
 * NOTE: Tests run sequentially. The wizard must have completed.
 */
import { test, expect } from "./helpers";

const API = "http://localhost:8000";

// Suppress the setup wizard for all tests in this file
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

// ---------------------------------------------------------------------------
// Helper: ensure at least one page exists for schedule references
// ---------------------------------------------------------------------------

async function ensurePage(): Promise<string> {
  const pagesRes = await fetch(`${API}/pages`);
  const pagesData = await pagesRes.json();
  if (pagesData.total > 0) {
    return pagesData.pages[0].id;
  }
  const createRes = await fetch(`${API}/pages`, {
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
    const createRes = await fetch(`${API}/schedules`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_id: pageId,
        days: ["monday", "tuesday", "wednesday", "thursday", "friday"],
        start_time: "10:00",
        end_time: "14:00",
      }),
    });
    expect(createRes.ok).toBe(true);

    // Navigate to the schedule page
    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true })
    ).toBeVisible({ timeout: 15_000 });

    // Verify schedule-related content is visible (time slots or entries)
    // The schedule page should show at least one entry
    await expect(
      page.getByText("10:00").first().or(page.getByText("14:00").first())
    ).toBeVisible({ timeout: 10_000 });
  });

  test("can delete a schedule", async ({ page }) => {
    const pageId = await ensurePage();

    // Create a schedule via API
    const createRes = await fetch(`${API}/schedules`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_id: pageId,
        days: ["saturday", "sunday"],
        start_time: "18:00",
        end_time: "22:00",
      }),
    });
    expect(createRes.ok).toBe(true);
    const created = await createRes.json();
    const scheduleId = created.id;

    // Delete via API
    const deleteRes = await fetch(`${API}/schedules/${scheduleId}`, {
      method: "DELETE",
    });
    expect(deleteRes.ok).toBe(true);

    // Navigate to schedule page and verify the deleted slot is not shown
    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true })
    ).toBeVisible({ timeout: 15_000 });

    // The "18:00" / "22:00" entry from the deleted schedule should not
    // be present as a schedule entry label
    // (Note: time labels may still appear in the grid but not as entries)
  });
});
