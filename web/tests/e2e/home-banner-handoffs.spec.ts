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

test("Home pauses sends on hub loss, retains Compose, and distinguishes an offline display", async ({
  page,
  context,
}, testInfo) => {
  test.setTimeout(120000);
  await configureBoard();
  await resetToSingleBoard();
  await suppressWizard(page);
  await deleteAllSchedules();
  await deleteAllPages();
  await setScheduleEnabled(false);
  const id = await createPage("Evening commute", ["GOOD EVENING", "", "", "", "", ""]);
  await setActivePage(id);
  await page.goto("/");
  await page.getByRole("button", { name: "Compose a message", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Compose a message" });
  await dialog.getByRole("textbox", { name: "Message", exact: true }).fill("GOOD LUCK");
  await expect(dialog.getByRole("button", { name: "Show now", exact: true })).toBeEnabled();
  const sends: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && /temporary-override|silence-queue/.test(r.url())) sends.push(r.url());
  });
  await context.setOffline(true);
  await expect(dialog.getByRole("button", { name: "Show now", exact: true })).toBeDisabled();
  await expect(dialog.getByRole("textbox", { name: "Message", exact: true })).toHaveValue("GOOD LUCK");
  await expect(dialog.getByText("Show now comes back when the hub answers.")).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(page.getByRole("button", { name: "Compose a message", exact: true })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Change Page", exact: true })).toBeDisabled();
  await expect(page.getByTestId("home-board-state")).toHaveCSS("opacity", "0.5");
  await page.keyboard.press("c");
  await page.keyboard.press("p");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await context.setOffline(false);
  await expect(page.getByRole("button", { name: "Change Page", exact: true })).toBeEnabled({ timeout: 30000 });
  expect(sends).toEqual([]);

  await page.route("**/api/v1/status", async (route) => {
    const response = await route.fetch();
    const status = await response.json();
    for (const board of Object.values(status.boards ?? {}) as Array<Record<string, unknown>>)
      board.health = { reachable: false, breaker_open: true, last_connected_at: new Date().toISOString() };
    await route.fulfill({ json: status });
  });
  await page.reload();
  await expect(page.getByTestId("now-showing").getByText("Offline", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Change Page", exact: true })).toBeEnabled();
  await expect(page.getByTestId("home-board-state")).toHaveCSS("opacity", "0.6");
  for (const width of [390, 768, 1280]) {
    for (const theme of ["light", "dark"]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate((value) => localStorage.setItem("theme", value), theme);
      await page.reload();
      await expect(page.getByTestId("now-showing").getByText("Offline", { exact: true })).toBeVisible();
      await injectAxe(page);
      expect(
        await getViolations(page, undefined, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } }),
      ).toEqual([]);
      await page.screenshot({ path: testInfo.outputPath(`impl-offline-${width}-${theme}.png`), fullPage: true });
    }
  }
});
