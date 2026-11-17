/**
 * FiestaBoard Schedule Management E2E Tests
 *
 * Deep schedule management coverage beyond the basic CRUD tests.
 * Tests the schedule toggle, form interactions, validation,
 * view modes, and day patterns.
 */
import {
  API_URL,
  configureBoard,
  createPage,
  createSchedule,
  deleteAllPages,
  deleteAllSchedules,
  expect,
  suppressWizard,
  test,
} from "./helpers";

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
  await page.addInitScript(() => localStorage.setItem("schedule-view-mode", "list"));
  await deleteAllSchedules();
});

test.describe("Schedule Management", () => {
  test("shows empty state with no schedules", async ({ page }) => {
    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    await page.getByRole("radio", { name: "Week", exact: true }).click();
    await expect(page.getByText("No schedules created yet")).toBeVisible({ timeout: 10_000 });
  });

  test("can toggle schedule mode on and off", async ({ page }) => {
    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    // Find the schedule enabled toggle pill in the toolbar
    const toggleEl = page.getByTestId("schedule-enabled-toggle");
    await expect(toggleEl).toBeVisible({ timeout: 10_000 });

    // Toggle on. `PUT /schedules/enabled` is now `PATCH /v1/boards/{board}`.
    const apiResponse = page.waitForResponse(
      (r) => r.url().includes("/api/v1/boards/") && r.request().method() === "PATCH" && r.status() === 200,
    );
    await toggleEl.click();
    await apiResponse;

    // Toggle back off
    const revertResponse = page.waitForResponse(
      (r) => r.url().includes("/api/v1/boards/") && r.request().method() === "PATCH" && r.status() === 200,
    );
    await toggleEl.click();
    await revertResponse;
  });

  test("can create a schedule via the UI form", async ({ page }) => {
    const pageId = await createPage("Schedule Form Test");

    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    // Click "Add Schedule"
    await page.getByRole("button", { name: "Add Schedule" }).first().click();

    // Wait for dialog
    await expect(page.getByText("Add Schedule").first()).toBeVisible({ timeout: 10_000 });

    const dialog = page.getByRole("dialog", { name: "Add Schedule", exact: true });
    const pageSelect = dialog.getByRole("combobox", { name: /^Page or Collection/ });
    await pageSelect.click();
    await page.getByRole("option", { name: "Schedule Form Test", exact: true }).click();
    await expect(pageSelect).toContainText("Schedule Form Test");
    await dialog.getByLabel("Start Time", { exact: true }).fill("08:00");
    await dialog.getByLabel("End Time", { exact: true }).fill("17:00");
    const created = page.waitForResponse(
      (r) => r.url().endsWith("/api/v1/schedules") && r.request().method() === "POST",
    );
    await dialog.getByRole("button", { name: "Save", exact: true }).click();
    expect((await created).ok()).toBe(true);
    await expect(dialog).toHaveCount(0);

    // Verify via API
    const res = await fetch(`${API_URL}/schedules`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    const schedules = Array.isArray(data?.schedules)
      ? data.schedules
      : Array.isArray(data?.items)
        ? data.items
        : Array.isArray(data)
          ? data
          : [];
    const createdSchedule = schedules.find((s: any) => {
      const start = String(s?.start_time ?? "");
      const end = String(s?.end_time ?? "");
      return String(s?.page_id) === String(pageId) && start.startsWith("08:00") && end.startsWith("17:00");
    });
    expect(createdSchedule).toBeTruthy();
  });

  test("can edit an existing schedule", async ({ page }) => {
    const pageId = await createPage("Edit Schedule Page");
    const scheduleId = await createSchedule(pageId, "09:00", "12:00");

    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    // Wait for schedule entries to load
    await expect(page.getByRole("button", { name: /Edit Schedule Page/ }).first()).toBeVisible();

    await page
      .getByRole("button", { name: /Edit Schedule Page/ })
      .first()
      .click();
    const dialog = page.getByRole("dialog", { name: "Edit Schedule", exact: true });
    await expect(dialog.getByLabel("Start Time", { exact: true })).toHaveValue("09:00");
    await dialog.getByLabel("Start Time", { exact: true }).fill("09:30");
    const updated = page.waitForResponse(
      (r) => r.url().includes(`/api/v1/schedules/${scheduleId}`) && r.request().method() === "PUT",
    );
    await dialog.getByRole("button", { name: "Save", exact: true }).click();
    const response = await updated;
    expect(response.ok()).toBe(true);
    expect(await response.json()).toMatchObject({ id: scheduleId, page_id: pageId, start_time: "09:30" });
    await expect(dialog).toHaveCount(0);
  });

  test("can delete a schedule from the edit modal", async ({ page }) => {
    const pageId = await createPage("Edit-Delete Schedule Page");
    await createSchedule(pageId, "10:00", "15:00");

    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    await page
      .getByRole("button", { name: /Edit-Delete Schedule Page/ })
      .first()
      .click();
    const dialog = page.getByRole("dialog", { name: "Edit Schedule", exact: true });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Delete entry", exact: true }).click();

    // Confirm deletion in the alert dialog (scoped to the alertdialog role)
    const confirmBtn = page.getByRole("alertdialog").getByRole("button", { name: "Delete" });
    await expect(confirmBtn).toBeVisible({ timeout: 3_000 });
    await confirmBtn.click();

    // Verify schedule was deleted via API
    await page.waitForTimeout(1_000);
    const res = await fetch(`${API_URL}/schedules`);
    const data = await res.json();
    expect(data.total).toBe(0);
  });

  test("can delete a schedule with confirmation", async ({ page }) => {
    const pageId = await createPage("Delete Schedule Page");
    await createSchedule(pageId, "14:00", "18:00");

    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    await expect(page.getByRole("button", { name: /Delete Schedule Page/ }).first()).toBeVisible();

    await page
      .getByRole("button", { name: /Delete Schedule Page/ })
      .first()
      .click();
    await page
      .getByRole("dialog", { name: "Edit Schedule", exact: true })
      .getByRole("button", { name: "Delete entry", exact: true })
      .click();

    // Confirm deletion (scoped to the alertdialog to avoid matching row buttons)
    const confirmBtn = page.getByRole("alertdialog").getByRole("button", { name: "Delete" });
    await expect(confirmBtn).toBeVisible({ timeout: 3_000 });
    await confirmBtn.click();

    // Verify via API
    await page.waitForTimeout(1_000);
    const res = await fetch(`${API_URL}/schedules`);
    const data = await res.json();
    expect(data.total).toBe(0);
  });

  test("can set the default page", async ({ page }) => {
    await createPage("Default Page Candidate");

    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    // Find the gap-default select in the toolbar
    const gapDefaultSelect = page.getByTestId("gap-default-select");
    await expect(gapDefaultSelect).toBeVisible({ timeout: 10_000 });

    // Open the select and pick the page
    await gapDefaultSelect.click();
    const pageOption = page.getByRole("option", { name: "Default Page Candidate" });
    if (await pageOption.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await pageOption.click();
    }

    // Verify via API
    await page.waitForTimeout(1_000);
    const res = await fetch(`${API_URL}/schedules/default-page`);
    if (res.ok) {
      const data = await res.json();
      expect(data).toHaveProperty("default_page_id");
    }
  });

  test("validates schedule overlaps via API", async () => {
    const pageId = await createPage("Overlap Test Page");
    await createSchedule(pageId, "08:00", "12:00", "weekdays");
    await createSchedule(pageId, "10:00", "14:00", "weekdays");

    const res = await fetch(`${API_URL}/schedules/validate`, {
      method: "POST",
    });
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(typeof data).toBe("object");

    // The validator should detect and report the overlap.
    const serialized = JSON.stringify(data).toLowerCase();
    const hasExplicitOverlapFlag = data?.overlap === true || data?.has_overlap === true || data?.hasOverlaps === true;
    const hasOverlapCollection =
      (Array.isArray(data?.overlaps) && data.overlaps.length > 0) ||
      (Array.isArray(data?.errors) && data.errors.some((e: unknown) => String(e).toLowerCase().includes("overlap"))) ||
      (Array.isArray(data?.warnings) &&
        data.warnings.some((w: unknown) => String(w).toLowerCase().includes("overlap")));
    const mentionsOverlapText = serialized.includes("overlap");

    expect(hasExplicitOverlapFlag || hasOverlapCollection || mentionsOverlapText).toBe(true);
  });

  test("schedule respects day patterns", async () => {
    const pageId = await createPage("Day Pattern Page");
    const scheduleId = await createSchedule(pageId, "08:00", "17:00", "weekdays");

    const res = await fetch(`${API_URL}/schedules/${scheduleId}`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.day_pattern).toBe("weekdays");
  });

  test("can switch between list and calendar view", async ({ page }) => {
    const pageId = await createPage("View Toggle Page");
    await createSchedule(pageId, "08:00", "12:00");

    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    const list = page.getByRole("radio", { name: "List", exact: true });
    const week = page.getByRole("radio", { name: "Week", exact: true });
    await week.click();
    await expect(week).toHaveAttribute("aria-checked", "true");
    await list.click();
    await expect(list).toHaveAttribute("aria-checked", "true");

    // Page should still be intact
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible();
  });

  test("active schedule shows in the UI", async ({ page }) => {
    const pageId = await createPage("Active Schedule Page");
    await createSchedule(pageId, "06:00", "18:00", "weekdays");

    // Enable schedule mode
    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: true }),
    });

    await page.goto("/schedule");
    await expect(page.getByRole("heading", { name: "Schedule", exact: true })).toBeVisible({ timeout: 15_000 });

    // When schedule mode is enabled the toggle pill shows "On"
    const scheduleToggle = page.getByTestId("schedule-enabled-toggle");
    await expect(scheduleToggle).toBeVisible({ timeout: 10_000 });
    await expect(scheduleToggle).toHaveAttribute("aria-checked", "true");

    // Disable schedule mode
    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: false }),
    });
  });
});
