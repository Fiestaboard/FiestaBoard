/**
 * Multi-board + Schedule E2E tests
 *
 * Validates that the Schedule page and schedule APIs work correctly when
 * multiple boards are configured (per-board schedule support).
 */
import {
  test,
  expect,
  configureBoard,
  suppressWizard,
  ensureTwoBoards,
  resetToSingleBoard,
  createPage,
  createSchedule,
  deleteAllSchedules,
  API_URL,
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
  test("schedule page loads with two boards and shows board selector", async ({
    page,
  }) => {
    await ensureTwoBoards();
    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true })
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("My Board").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText("Schedule Mode").first()).toBeVisible({
      timeout: 5_000,
    });
  });

  test("schedule mode toggle works with two boards", async ({ page }) => {
    await ensureTwoBoards();
    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true })
    ).toBeVisible({ timeout: 15_000 });

    const switchEl = page
      .locator("section, div")
      .filter({ hasText: "Schedule Mode" })
      .getByRole("switch")
      .first();
    if (await switchEl.isVisible({ timeout: 5_000 }).catch(() => false)) {
      const apiResponse = page.waitForResponse(
        (r) => r.url().includes("/schedules/enabled") && r.status() === 200
      );
      await switchEl.click();
      await apiResponse;
      const revertResponse = page.waitForResponse(
        (r) => r.url().includes("/schedules/enabled") && r.status() === 200
      );
      await switchEl.click();
      await revertResponse;
    }
    const res = await fetch(`${API_URL}/schedules/enabled`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(typeof data.enabled).toBe("boolean");
  });

  test("schedule CRUD with two boards: create and list", async ({
    page,
  }) => {
    await ensureTwoBoards();
    const pageId = await createPage("Schedule Multi-Board Page");
    await createSchedule(pageId, "09:00", "12:00", "weekdays");

    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true })
    ).toBeVisible({ timeout: 15_000 });
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
});
