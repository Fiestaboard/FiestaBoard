/**
 * Multi-board + Schedule E2E tests
 *
 * Validates that the Schedule page and schedule APIs work correctly when
 * multiple boards are configured (per-board schedule support).
 */
import {
  API_URL,
  configureBoard,
  createPage,
  createSchedule,
  deleteAllSchedules,
  ensureTwoBoards,
  expect,
  resetToSingleBoard,
  suppressWizard,
  test,
} from "./helpers";

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await resetToSingleBoard();
  await suppressWizard(page);
  await deleteAllSchedules();
});

test.afterEach(async () => {
  await resetToSingleBoard();
});

test.describe("Multi-Board and Schedule", () => {
  test("schedule page works with single board (no multi-board selector)", async ({ page }) => {
    // beforeEach already did resetToSingleBoard() – one board only
    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });
    // Schedule toggle is always visible (replaces the old Schedule Mode card)
    await expect(page.getByTestId("schedule-enabled-toggle")).toBeVisible({
      timeout: 5_000,
    });
  });

  test("schedule page loads with two boards and shows board selector", async ({ page }) => {
    await ensureTwoBoards();
    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });
    // The board selector dropdown should appear in the toolbar
    await expect(page.getByTestId("board-selector")).toBeVisible({
      timeout: 10_000,
    });
    // The schedule enabled toggle should also be visible
    await expect(page.getByTestId("schedule-enabled-toggle")).toBeVisible({
      timeout: 5_000,
    });
  });

  test("schedule mode toggle works with two boards", async ({ page }) => {
    await ensureTwoBoards();
    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    const switchEl = page.locator("section, div").filter({ hasText: "Schedule Mode" }).getByRole("switch").first();
    if (await switchEl.isVisible({ timeout: 5_000 }).catch(() => false)) {
      const apiResponse = page.waitForResponse((r) => r.url().includes("/schedules/enabled") && r.status() === 200);
      await switchEl.click();
      await apiResponse;
      const revertResponse = page.waitForResponse((r) => r.url().includes("/schedules/enabled") && r.status() === 200);
      await switchEl.click();
      await revertResponse;
    }
    const res = await fetch(`${API_URL}/schedules/enabled`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(typeof data.enabled).toBe("boolean");
  });

  test("schedule CRUD with two boards: create and list", async ({ page }) => {
    const { board1Id } = await ensureTwoBoards();
    const pageId = await createPage("Schedule Multi-Board Page");
    await createSchedule(pageId, "09:00", "12:00", "weekdays", board1Id);

    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("09:00").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("12:00").first()).toBeVisible({
      timeout: 5_000,
    });
  });

  test("schedules API returns data with two boards", async () => {
    await ensureTwoBoards();
    const pageId = await createPage("Schedule API Test Page");
    await createSchedule(pageId, "10:00", "14:00", "weekdays");

    const listRes = await fetch(`${API_URL}/schedules`);
    expect(listRes.ok).toBe(true);
    const listData = await listRes.json();
    expect(Array.isArray(listData.schedules)).toBe(true);
    expect(listData.schedules.length).toBeGreaterThanOrEqual(1);
    expect(listData.total).toBeGreaterThanOrEqual(1);

    const activeRes = await fetch(`${API_URL}/schedules/active/page`);
    expect(activeRes.ok).toBe(true);
    const activeData = await activeRes.json();
    expect(activeData).toHaveProperty("page_id");
    expect(activeData).toHaveProperty("schedule_enabled");
  });

  test("schedules API filtered by board_id returns only that board's schedules", async () => {
    const { board1Id, board2Id } = await ensureTwoBoards();
    const pageA = await createPage("Board A Page");
    const pageB = await createPage("Board B Page");
    await createSchedule(pageA, "09:00", "12:00", "weekdays", board1Id);
    await createSchedule(pageB, "14:00", "18:00", "weekdays", board2Id);

    const list1 = await fetch(`${API_URL}/schedules?board_id=${encodeURIComponent(board1Id)}`);
    expect(list1.ok).toBe(true);
    const data1 = await list1.json();
    expect(data1.schedules).toHaveLength(1);
    expect(data1.schedules[0].start_time).toBe("09:00");
    expect(data1.schedules[0].end_time).toBe("12:00");

    const list2 = await fetch(`${API_URL}/schedules?board_id=${encodeURIComponent(board2Id)}`);
    expect(list2.ok).toBe(true);
    const data2 = await list2.json();
    expect(data2.schedules).toHaveLength(1);
    expect(data2.schedules[0].start_time).toBe("14:00");
    expect(data2.schedules[0].end_time).toBe("18:00");
  });

  test("switching boards in UI shows each board's schedules only", async ({ page }) => {
    const { board1Id, board2Id } = await ensureTwoBoards();
    const pageA = await createPage("Board One Page");
    const pageB = await createPage("Board Two Page");
    await createSchedule(pageA, "09:00", "12:00", "weekdays", board1Id);
    await createSchedule(pageB, "14:00", "18:00", "weekdays", board2Id);

    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });
    // First board selected: should show 09:00–12:00
    await expect(page.getByText("09:00").first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("12:00").first()).toBeVisible({ timeout: 5_000 });
    // Switch to second board using the compact board selector dropdown
    const boardSelector = page.getByTestId("board-selector");
    await boardSelector.click();
    // Pick the second option in the dropdown
    await page.getByRole("option").nth(1).click();
    // After switch: should show 14:00–18:00 for board 2
    await expect(page.getByText("14:00").first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("18:00").first()).toBeVisible({ timeout: 5_000 });
  });
});
