/**
 * Regression coverage for the schedule delete confirmation flow.
 * Subarea: schedule.delete-confirm
 */
import type { Page } from "@playwright/test";

import {
  API_URL,
  authHeaders,
  configureBoard,
  createPage,
  createSchedule,
  deleteAllPages,
  deleteAllSchedules,
  ensureAuthForFetch,
  expect,
  loginIfNeeded,
  test,
} from "../helpers";

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await deleteAllSchedules();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
    localStorage.setItem("schedule-view-mode", "list");
  });
});

test.afterEach(async () => {
  await deleteAllSchedules();
  await deleteAllPages();
});

async function seedScheduleAndOpen(page: Page) {
  const pageId = await createPage("Sched Page", ["A", "", "", "", "", ""]);
  const schedId = await createSchedule(pageId, "09:00", "10:00", "weekdays");
  await page.goto("/schedule");
  await openDeleteConfirmation(page);
  return { pageId, schedId };
}

async function openDeleteConfirmation(page: Page) {
  await page
    .getByRole("button", { name: /Sched Page/ })
    .first()
    .click();
  const editor = page.getByRole("dialog", { name: "Edit Schedule", exact: true });
  await expect(editor.getByLabel("Start Time", { exact: true })).toHaveValue("09:00");
  await editor.getByRole("button", { name: "Delete entry…", exact: true }).click();
  await expect(page.getByRole("alertdialog", { name: "Delete Schedule", exact: true })).toBeVisible();
}

async function expectPersisted(schedId: string, exists: boolean) {
  const response = await fetch(`${API_URL}/v1/schedules`, { headers: authHeaders() });
  expect(response.ok).toBe(true);
  const data = await response.json();
  expect(data.schedules.some((entry: { id: string }) => entry.id === schedId)).toBe(exists);
}

test.describe("regression: schedule.delete-confirm", () => {
  test("schedule.delete-confirm.open — dialog has title, Cancel and Esc close", async ({ page }) => {
    let deletes = 0;
    page.on("request", (request) => {
      if (request.method() === "DELETE" && request.url().includes("/api/v1/schedules/")) deletes++;
    });
    const { schedId } = await seedScheduleAndOpen(page);
    const dialog = page.getByRole("alertdialog", { name: "Delete Schedule", exact: true });
    await expect(dialog.getByRole("heading", { name: "Delete Schedule", exact: true })).toBeVisible();
    await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(dialog).toBeHidden();
    await expectPersisted(schedId, true);

    await openDeleteConfirmation(page);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expectPersisted(schedId, true);
    expect(deletes).toBe(0);
    await expect(page.getByRole("button", { name: /Sched Page/ }).first()).toBeVisible();
  });

  test("schedule.delete-confirm.deleting — confirm deletes the entry and dismisses the dialog", async ({ page }) => {
    const { schedId } = await seedScheduleAndOpen(page);
    const dialog = page.getByRole("alertdialog", { name: "Delete Schedule", exact: true });
    const deleted = page.waitForResponse(
      (response) => response.url().includes(`/api/v1/schedules/${schedId}`) && response.request().method() === "DELETE",
    );
    await dialog.getByRole("button", { name: "Delete", exact: true }).click();
    expect((await deleted).ok()).toBe(true);
    await expect(dialog).toBeHidden();
    await expect(page.getByRole("button", { name: /Sched Page/ })).toHaveCount(0);
    await expectPersisted(schedId, false);
  });

  test("schedule.delete-confirm.delete-error — failed delete preserves the entry and permits retry", async ({
    page,
  }) => {
    const { schedId } = await seedScheduleAndOpen(page);
    let attempts = 0;
    let rejectDeletes = true;
    await page.route(`**/api/v1/schedules/${schedId}*`, (route) => {
      if (route.request().method() === "DELETE") {
        attempts++;
        // Providers retries failed mutations once. Keep the outage active until
        // the user sees the terminal error and explicitly retries below.
        if (rejectDeletes) {
          return route.fulfill({ status: 500, contentType: "application/json", body: '{"detail":"boom"}' });
        }
      }
      return route.continue();
    });
    const dialog = page.getByRole("alertdialog", { name: "Delete Schedule", exact: true });
    const failed = page.waitForResponse(
      (response) => response.url().includes(`/api/v1/schedules/${schedId}`) && response.request().method() === "DELETE",
    );
    await dialog.getByRole("button", { name: "Delete", exact: true }).click();
    expect((await failed).status()).toBe(500);
    await expect(dialog).toBeHidden();
    await expect(page.getByText("boom", { exact: true }).first()).toBeVisible();
    expect(attempts).toBe(2);
    await expectPersisted(schedId, true);

    rejectDeletes = false;
    await openDeleteConfirmation(page);
    const retried = page.waitForResponse(
      (response) => response.url().includes(`/api/v1/schedules/${schedId}`) && response.request().method() === "DELETE",
    );
    await dialog.getByRole("button", { name: "Delete", exact: true }).click();
    expect((await retried).ok()).toBe(true);
    await expect(page.getByRole("button", { name: /Sched Page/ })).toHaveCount(0);
    expect(attempts).toBe(3);
    await expectPersisted(schedId, false);
  });

  test("schedule.delete-confirm.open-from-form — edit sheet exposes Delete affordance", async ({ page }) => {
    const pageId = await createPage("Open-from-form Page");
    const schedId = await createSchedule(pageId, "09:00", "10:00", "weekdays");
    await page.goto("/schedule");
    await page
      .getByRole("button", { name: /Open-from-form Page/ })
      .first()
      .click();
    const sheet = page.getByRole("dialog", { name: "Edit Schedule", exact: true });
    await expect(sheet.getByRole("button", { name: "Delete entry…", exact: true })).toBeVisible();
    await expectPersisted(schedId, true);
  });
});
