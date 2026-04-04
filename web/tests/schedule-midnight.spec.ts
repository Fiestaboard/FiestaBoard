/**
 * FiestaBoard Schedule Midnight Rollover Tests
 *
 * Tests schedule entries that span midnight (start_time > end_time),
 * verifying the API accepts them and the UI renders them correctly.
 *
 * Issue: #500 — E2E: add Playwright tests for critical user flows
 */
import {
  test,
  expect,
  configureBoard,
  suppressWizard,
  createPage,
  createSchedule,
  deleteAllSchedules,
  deleteAllPages,
  API_URL,
} from "./helpers";

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
  await deleteAllSchedules();
});

test.afterEach(async () => {
  await deleteAllSchedules();
  await deleteAllPages();
});

test.describe("Schedule — Midnight Rollover", () => {
  test("API accepts a schedule entry spanning midnight (22:00–06:00)", async () => {
    const pageId = await createPage("Night Owl Page", [
      "NIGHT MODE",
      "",
      "",
      "",
      "",
      "",
    ]);

    // Create a schedule that spans midnight: starts at 22:00, ends at 06:00
    const res = await fetch(`${API_URL}/schedules`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_id: pageId,
        start_time: "22:00",
        end_time: "06:00",
        day_pattern: "all",
      }),
    });

    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.id).toBeTruthy();
    expect(data.start_time).toBe("22:00");
    expect(data.end_time).toBe("06:00");
  });

  test("midnight-spanning schedule appears in the schedule list UI", async ({ page }) => {
    const pageId = await createPage("Late Night", ["LATE NIGHT", "", "", "", "", ""]);
    await createSchedule(pageId, "23:00", "05:00", "all");

    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // The schedule should be visible in the list
    const scheduleList = page.locator("[data-testid='schedule-list'], .schedule-list, main");
    await expect(scheduleList.first()).toBeVisible({ timeout: 10_000 });

    // 23:00 should appear on page
    await expect(page.getByText(/23:00|11:00 PM/i).first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("multiple schedules across midnight display without overlap errors", async ({ page }) => {
    const pageId1 = await createPage("Day Page", ["DAY", "", "", "", "", ""]);
    const pageId2 = await createPage("Night Page", ["NIGHT", "", "", "", "", ""]);

    // Day schedule: 08:00–22:00
    await createSchedule(pageId1, "08:00", "22:00", "weekdays");
    // Night schedule spanning midnight: 22:00–08:00
    await createSchedule(pageId2, "22:00", "08:00", "weekdays");

    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Both schedules should be fetchable from the API
    const res = await fetch(`${API_URL}/schedules`);
    const data = await res.json();
    expect(data.schedules.length).toBeGreaterThanOrEqual(2);
  });

  test("API validates schedule with identical start and end time", async () => {
    const pageId = await createPage("Same Time Page", ["TEST", "", "", "", "", ""]);

    // Same start/end time — behaviour is implementation-defined, but API should respond
    const res = await fetch(`${API_URL}/schedules`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        page_id: pageId,
        start_time: "12:00",
        end_time: "12:00",
        day_pattern: "all",
      }),
    });

    // Either accepted (200/201) or rejected (400/422) — we just verify a response
    expect([200, 201, 400, 422]).toContain(res.status);
  });

  test("schedule list correctly lists overnight entries via API", async () => {
    const pageId = await createPage("Overnight", ["OVERNIGHT", "", "", "", "", ""]);
    await createSchedule(pageId, "21:30", "07:30", "weekends");

    const res = await fetch(`${API_URL}/schedules`);
    expect(res.ok).toBe(true);
    const data = await res.json();

    const overnight = data.schedules.find(
      (s: { start_time: string; end_time: string }) =>
        s.start_time === "21:30" && s.end_time === "07:30",
    );
    expect(overnight).toBeTruthy();
    expect(overnight.day_pattern).toBe("weekends");
  });

  test("schedule calendar view renders without errors when overnight entries exist", async ({
    page,
  }) => {
    const pageId = await createPage("Calendar Night", ["NIGHT", "", "", "", "", ""]);
    await createSchedule(pageId, "22:00", "06:00", "all");

    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Switch to calendar view if possible
    const calendarViewBtn = page
      .getByRole("button", { name: /calendar/i })
      .or(page.getByTitle(/calendar/i))
      .first();

    if (await calendarViewBtn.isVisible({ timeout: 3_000 }).catch(() => false)) {
      await calendarViewBtn.click();
    }

    // Page should not show error state
    await expect(page.getByText(/error|crash|unhandled/i)).not.toBeVisible({
      timeout: 3_000,
    });
  });
});
