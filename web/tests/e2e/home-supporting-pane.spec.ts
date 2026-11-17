import { getViolations, injectAxe } from "axe-playwright";

import {
  configureBoard,
  createPage,
  deleteAllPages,
  deleteAllSchedules,
  expect,
  resetToSingleBoard,
  setActivePage,
  setScheduleEnabled,
  suppressWizard,
  test,
} from "../helpers";

test("Home Manual Mode switch resumes this display's Schedule and offers Undo", async ({ page }) => {
  await configureBoard();
  await resetToSingleBoard();
  await suppressWizard(page);
  await deleteAllSchedules();
  await deleteAllPages();
  await setScheduleEnabled(false);
  const id = await createPage("Evening commute", ["GOOD EVENING", "", "", "", "", ""]);
  await setActivePage(id);
  await page.goto("/");
  const pane = page.getByTestId("home-supporting-pane");
  await expect(pane.getByText("Schedule Mode is off")).toBeVisible();
  await pane.getByRole("switch", { name: "Schedule Mode", exact: true }).click();
  await expect(pane.getByText("Schedule Mode is off")).toHaveCount(0);
  const toast = page.locator("[data-sonner-toast]").filter({ hasText: "Back on Schedule Mode" });
  await expect(toast).toBeVisible();
  await toast.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(pane.getByRole("switch", { name: "Schedule Mode" })).not.toBeChecked();
  await injectAxe(page);
  const violations = await getViolations(page, undefined, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
  });
  expect(violations).toEqual([]);
});
