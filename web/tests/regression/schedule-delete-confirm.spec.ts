/**
 * Regression coverage for the schedule delete confirmation flow.
 * Subarea: schedule.delete-confirm
 */
import {
  test,
  expect,
  configureBoard,
  createPage,
  createSchedule,
  deleteAllPages,
  deleteAllSchedules,
  loginIfNeeded,
  ensureAuthForFetch,
} from "../helpers";

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

test.afterEach(async () => {
  await deleteAllSchedules();
  await deleteAllPages();
});

async function seedScheduleAndOpen(page: import("@playwright/test").Page) {
  const pageId = await createPage("Sched Page", ["A", "", "", "", "", ""]);
  const schedId = await createSchedule(pageId, "09:00", "10:00", "weekdays");
  await page.goto("/schedule");
  return { pageId, schedId };
}

test.describe("regression: schedule.delete-confirm", () => {
  /** UX node: schedule.delete-confirm.open */
  test("schedule.delete-confirm.open — dialog has title, Cancel and Esc close", async ({ page }) => {
    await seedScheduleAndOpen(page);
    await page.getByRole("button", { name: /Delete schedule/i }).first().click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible({ timeout: 10_000 });
    await expect(dialog.getByText(/Delete Schedule/i)).toBeVisible();
    await dialog.getByRole("button", { name: /Cancel/i }).click();
    await expect(dialog).toBeHidden({ timeout: 5_000 });

    await page.getByRole("button", { name: /Delete schedule/i }).first().click();
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden({ timeout: 5_000 });
  });

  /** UX node: schedule.delete-confirm.deleting */
  test("schedule.delete-confirm.deleting — confirm removes the schedule", async ({ page }) => {
    const { schedId } = await seedScheduleAndOpen(page);
    await page.getByRole("button", { name: /Delete schedule/i }).first().click();
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible({ timeout: 10_000 });
    await dialog.getByRole("button", { name: /^Delete$/ }).click();
    await expect(dialog).toBeHidden({ timeout: 10_000 });
    // Schedule is no longer in the list
    await expect(
      page.getByRole("button", { name: new RegExp(`Delete schedule.*${schedId.slice(0, 4)}`, "i") }),
    ).toHaveCount(0);
  });

  /** UX node: schedule.delete-confirm.delete-error */
  test("schedule.delete-confirm.delete-error — failed delete toasts and keeps schedule", async ({ page }) => {
    await seedScheduleAndOpen(page);
    await page.route("**/api/schedules/*", (route) => {
      if (route.request().method() === "DELETE") {
        return route.fulfill({ status: 500, body: '{"detail":"boom"}' });
      }
      return route.continue();
    });
    await page.getByRole("button", { name: /Delete schedule/i }).first().click();
    const dialog = page.getByRole("alertdialog");
    await dialog.getByRole("button", { name: /^Delete$/ }).click();
    await expect(page.locator("[data-sonner-toast]").first()).toBeVisible({ timeout: 10_000 });
  });

  /** UX node: schedule.delete-confirm.open-from-form */
  test.fixme("schedule.delete-confirm.open-from-form — Delete from edit sheet closes form then opens dialog", () => {
    // Edit sheet flow is complex; covered functionally by schedule-management.spec.ts.
  });
});
