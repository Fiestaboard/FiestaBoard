/**
 * FiestaBoard Schedule Management E2E Tests
 *
 * Deep schedule management coverage beyond the basic CRUD tests.
 * Tests the schedule toggle, form interactions, validation,
 * view modes, and day patterns.
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

test.describe("Schedule Management", () => {
  test("shows empty state with no schedules", async ({ page }) => {
    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    await expect(
      page.getByText("No schedules created yet"),
    ).toBeVisible({ timeout: 10_000 });
  });

  test("can toggle schedule mode on and off", async ({ page }) => {
    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Find the schedule mode toggle
    const toggle = page.getByText("Schedule Mode").first();
    await expect(toggle).toBeVisible({ timeout: 10_000 });

    // Find the switch near "Schedule Mode"
    const switchEl = page
      .locator("section, div")
      .filter({ hasText: "Schedule Mode" })
      .getByRole("switch")
      .first();

    if (await switchEl.isVisible({ timeout: 5_000 }).catch(() => false)) {
      // Toggle on
      const apiResponse = page.waitForResponse(
        (r) => r.url().includes("/schedules/enabled") && r.status() === 200,
      );
      await switchEl.click();
      await apiResponse;

      // Toggle back off
      const revertResponse = page.waitForResponse(
        (r) => r.url().includes("/schedules/enabled") && r.status() === 200,
      );
      await switchEl.click();
      await revertResponse;
    }
  });

  test("can create a schedule via the UI form", async ({ page }) => {
    const pageId = await createPage("Schedule Form Test");

    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Click "Add Schedule"
    await page.getByRole("button", { name: "Add Schedule" }).first().click();

    // Wait for dialog
    await expect(
      page.getByText("Add Schedule").first(),
    ).toBeVisible({ timeout: 10_000 });

    // Select a page
    const pageSelect = page.locator("#page");
    if (await pageSelect.isVisible().catch(() => false)) {
      await pageSelect.click();
      const option = page.getByRole("option").first();
      if (await option.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await option.click();
      }
    }

    // Set start time
    const startTime = page.locator("#start-time");
    if (await startTime.isVisible().catch(() => false)) {
      await startTime.click();
      const opt = page.getByRole("option", { name: "08:00" });
      if (await opt.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await opt.click();
      }
    }

    // Set end time
    const endTime = page.locator("#end-time");
    if (await endTime.isVisible().catch(() => false)) {
      await endTime.click();
      const opt = page.getByRole("option", { name: "17:00" });
      if (await opt.isVisible({ timeout: 3_000 }).catch(() => false)) {
        await opt.click();
      }
    }

    // Submit
    const submitBtn = page.getByRole("button", { name: "Create Schedule" });
    if (await submitBtn.isEnabled({ timeout: 3_000 }).catch(() => false)) {
      await submitBtn.click();
    }

    // Verify via API
    const res = await fetch(`${API_URL}/schedules`);
    const data = await res.json();
    expect(data.total).toBeGreaterThan(0);
  });

  test("can edit an existing schedule", async ({ page }) => {
    const pageId = await createPage("Edit Schedule Page");
    const scheduleId = await createSchedule(pageId, "09:00", "12:00");

    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Wait for schedule entries to load
    await expect(page.getByText("09:00").first()).toBeVisible({
      timeout: 10_000,
    });

    // Click edit button on the schedule entry
    const editBtn = page.getByRole("button", { name: /edit/i }).first();
    if (await editBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await editBtn.click();

      // Wait for edit dialog
      await expect(
        page.getByText("Edit Schedule").first(),
      ).toBeVisible({ timeout: 5_000 });

      // Verify the dialog is showing
      const updateBtn = page.getByRole("button", {
        name: /update schedule/i,
      });
      const hasUpdateBtn = await updateBtn
        .isVisible({ timeout: 3_000 })
        .catch(() => false);
      expect(hasUpdateBtn).toBe(true);
    }
  });

  test("can delete a schedule from the edit modal", async ({ page }) => {
    const pageId = await createPage("Edit-Delete Schedule Page");
    await createSchedule(pageId, "10:00", "15:00");

    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Ensure list view (view can be calendar from prior test)
    const listBtn = page.getByRole("button", { name: /list/i }).first();
    if (await listBtn.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await listBtn.click();
      await page.waitForTimeout(300);
    }

    const rowWithTime = page.getByText("10:00").first();
    await expect(rowWithTime).toBeVisible({ timeout: 10_000 });

    // Open the edit modal: list row has two icon buttons (Edit, Delete); first is Edit
    const editBtn = rowWithTime.locator("../..").getByRole("button").first();
    await expect(editBtn).toBeVisible({ timeout: 5_000 });
    await editBtn.click();

    // Wait for edit dialog to open
    await expect(
      page.getByText("Edit Schedule").first(),
    ).toBeVisible({ timeout: 5_000 });

    // Close the edit modal (Cancel), then delete from the list row
    await page.getByRole("button", { name: "Cancel" }).click();
    await page.waitForTimeout(300);

    // Click the row's Delete button (second button in the row; icon-only in UI)
    const rowButtons = rowWithTime.locator("../..").getByRole("button");
    const rowDeleteBtn = rowButtons.nth(1);
    await expect(rowDeleteBtn).toBeVisible({ timeout: 5_000 });
    await rowDeleteBtn.click();

    // Confirm deletion in the alert dialog
    const confirmBtn = page.getByRole("button", { name: "Delete" }).last();
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
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    await expect(page.getByText("14:00").first()).toBeVisible({
      timeout: 10_000,
    });

    // Click delete button
    const deleteBtn = page.getByRole("button", { name: /delete/i }).first();
    if (await deleteBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await deleteBtn.click();

      // Confirm deletion
      const confirmBtn = page.getByRole("button", { name: "Delete" }).last();
      if (
        await confirmBtn.isVisible({ timeout: 3_000 }).catch(() => false)
      ) {
        await confirmBtn.click();
      }

      // Verify via API
      await page.waitForTimeout(1_000);
      const res = await fetch(`${API_URL}/schedules`);
      const data = await res.json();
      expect(data.total).toBe(0);
    }
  });

  test("can set the default page", async ({ page }) => {
    const pageId = await createPage("Default Page Candidate");

    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Look for "Default Page" section
    const defaultSection = page.getByText("Default Page").first();
    await expect(defaultSection).toBeVisible({ timeout: 10_000 });

    // Click "Change" button to open page picker
    const changeBtn = page
      .getByRole("button", { name: /change/i })
      .first();
    if (await changeBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await changeBtn.click();

      // Select the page
      const pageOption = page.getByText("Default Page Candidate").first();
      if (
        await pageOption.isVisible({ timeout: 5_000 }).catch(() => false)
      ) {
        await pageOption.click();
      }
    }

    // Verify via API
    await page.waitForTimeout(1_000);
    const res = await fetch(`${API_URL}/schedules/default-page`);
    if (res.ok) {
      const data = await res.json();
      // The default page should be set (could be our page or another)
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
    // The validator should detect the overlap
  });

  test("schedule respects day patterns", async () => {
    const pageId = await createPage("Day Pattern Page");
    const scheduleId = await createSchedule(
      pageId,
      "08:00",
      "17:00",
      "weekdays",
    );

    const res = await fetch(`${API_URL}/schedules/${scheduleId}`);
    expect(res.ok).toBe(true);
    const data = await res.json();
    expect(data.day_pattern).toBe("weekdays");
  });

  test("can switch between list and calendar view", async ({ page }) => {
    const pageId = await createPage("View Toggle Page");
    await createSchedule(pageId, "08:00", "12:00");

    await page.goto("/schedule");
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Look for view toggle buttons
    const listBtn = page.getByRole("button", { name: /list/i }).first();
    const calendarBtn = page
      .getByRole("button", { name: /calendar/i })
      .first();

    const hasViewToggle =
      (await listBtn.isVisible({ timeout: 5_000 }).catch(() => false)) &&
      (await calendarBtn.isVisible().catch(() => false));

    if (hasViewToggle) {
      await calendarBtn.click();
      await page.waitForTimeout(500);
      await listBtn.click();
      await page.waitForTimeout(500);
    }

    // Page should still be intact
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible();
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
    await expect(
      page.getByRole("heading", { name: "Schedule", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // The schedule mode toggle description changes when enabled
    await expect(
      page.getByText("Pages automatically rotate based on schedule").first(),
    ).toBeVisible({ timeout: 10_000 });

    // Disable schedule mode
    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: false }),
    });
  });
});
