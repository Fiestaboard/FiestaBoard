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
  await context.setOffline(false);
  await expect(dialog.getByRole("button", { name: "Show now", exact: true })).toBeEnabled({ timeout: 30000 });
  await expect(dialog.getByRole("textbox", { name: "Message", exact: true })).toHaveValue("GOOD LUCK");
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await context.setOffline(true);
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

test("Home's held, silence-soon, out-of-sync and unreachable-hub states use one banner and keep captures", async ({
  page,
}, testInfo) => {
  test.setTimeout(180000);
  await configureBoard();
  await resetToSingleBoard();
  await suppressWizard(page);
  await deleteAllSchedules();
  await deleteAllPages();
  await setScheduleEnabled(false);
  const id = await createPage("Evening commute", ["GOOD EVENING", "", "", "", "", ""]);
  await setActivePage(id);
  let mode = "held";
  await page.route("**/api/v1/status", async (route) => {
    if (mode === "hub") {
      await route.fulfill({ status: 502, json: { detail: "Hub unavailable" } });
      return;
    }
    const response = await route.fetch();
    const body = await response.json();
    for (const value of Object.values(body.boards ?? {}) as Array<Record<string, unknown>>) {
      value.health = { reachable: true, breaker_open: false };
      value.error = null;
      value.paused = false;
    }
    await route.fulfill({ json: body });
  });
  await page.route("**/api/silence-status*", async (route) => {
    await route.fulfill({
      json: {
        enabled: mode === "held" || mode === "soon",
        active: mode === "held",
        mode: "page",
        page_id: id,
        start_time_utc: "05:00+00:00",
        end_time_utc: "13:30+00:00",
        seconds_until_next_change: mode === "soon" ? 720 : 3600,
        ends_at_utc: new Date(Date.now() + 3600000).toISOString(),
        held:
          mode === "held" ? { kind: "text", preview: "GOOD LUCK TOMORROW", queued_at: new Date().toISOString() } : null,
      },
    });
  });
  await page.route("**/api/board/current-message*", async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    if (mode === "sync") {
      body.characters = Array.from({ length: 6 }, () => Array(22).fill(1));
      body.expected_characters = Array.from({ length: 6 }, () => Array(22).fill(2));
    }
    await route.fulfill({ json: body });
  });
  await page.goto("/");
  for (const state of ["held", "soon", "sync", "hub"]) {
    mode = state;
    for (const width of [390, 768, 1280])
      for (const theme of ["light", "dark"]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate((value) => localStorage.setItem("theme", value), theme);
        await page.goto("/");
        if (state === "held") {
          await expect(page.getByTestId("home-held-message")).toBeVisible();
          await expect(page.getByTestId("status-banners")).toContainText("1 message is held");
        }
        if (state === "soon") await expect(page.getByRole("link", { name: "Edit Silence Schedule" })).toBeVisible();
        if (state === "sync") {
          await expect(page.getByTestId("board-out-of-sync")).toContainText("is out of sync");
          await expect(page.getByRole("button", { name: "Show Evening commute again" })).toBeVisible();
        }
        if (state === "hub") {
          await expect(page.getByRole("button", { name: "Compose a message", exact: true })).toBeDisabled({
            timeout: 30000,
          });
          await expect(page.getByTestId("home-board-state")).toHaveCSS("opacity", "0.5");
        }
        await injectAxe(page);
        expect(
          await getViolations(page, undefined, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } }),
        ).toEqual([]);
        await page.screenshot({ path: testInfo.outputPath(`impl-${state}-${width}-${theme}.png`), fullPage: true });
      }
  }
});
