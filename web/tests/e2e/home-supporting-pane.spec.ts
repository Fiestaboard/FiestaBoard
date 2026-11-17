import type { Page } from "@playwright/test";
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

// Visibility can pass partway through the route's entrance fade. Axe must
// sample settled ancestor opacity, not the lighter colors during that fade.
async function waitForHomeEntrance(page: Page) {
  await expect
    .poll(() =>
      page.getByTestId("now-showing").evaluate((card) => {
        for (let element: Element | null = card; element; element = element.parentElement) {
          if (getComputedStyle(element).opacity !== "1") return false;
        }
        return true;
      }),
    )
    .toBe(true);
}

test("Home Manual Mode switch resumes this display's Schedule and offers Undo", async ({ page }, testInfo) => {
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
  await expect(toast).toHaveCSS("opacity", "1");
  await waitForHomeEntrance(page);
  await injectAxe(page);
  expect(
    await getViolations(page, undefined, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } }),
  ).toEqual([]);
  await toast.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(pane.getByRole("switch", { name: "Schedule Mode" })).not.toBeChecked();
  await expect(toast).toHaveCount(0);
  await waitForHomeEntrance(page);
  await injectAxe(page);
  const violations = await getViolations(page, undefined, {
    runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
  });
  expect(violations).toEqual([]);
  // Hosted browsers also retain reviewable captures when local Docker is unavailable.
  for (const width of [390, 768, 1280]) {
    for (const theme of ["light", "dark"]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate((value) => localStorage.setItem("theme", value), theme);
      await page.reload();
      await expect(page.getByTestId("now-showing").getByRole("heading", { name: "Evening commute" })).toBeVisible();
      await expect(pane.getByText("Schedule Mode is off")).toBeVisible();
      await waitForHomeEntrance(page);
      await page.screenshot({ path: testInfo.outputPath(`impl-${width}-${theme}.png`), fullPage: true });
    }
  }
});

test("Home supporting cards follow the selected display across responsive shell sizes", async ({ page }, testInfo) => {
  test.setTimeout(90000);
  await configureBoard();
  await resetToSingleBoard();
  await suppressWizard(page);
  const boards = [
    { id: "kitchen", name: "Kitchen board", device_type: "flagship", board_color: "black", enabled: true },
    {
      id: "desk",
      name: "Desk Pixoo",
      device_type: "panel",
      device_model: "divoom_pixoo64",
      grid_rows: 8,
      grid_cols: 10,
      enabled: true,
    },
    {
      id: "clock",
      name: "Entry clock",
      device_type: "panel",
      device_model: "ulanzi_tc001_awtrix",
      grid_rows: 1,
      grid_cols: 5,
      enabled: true,
    },
  ];
  const next = new Date(Date.now() + 3600000).toISOString();
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith("/api/") || route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    const selected = url.searchParams.get("board_id") ?? "kitchen";
    const pageId = selected === "desk" ? "collection:agenda" : selected === "clock" ? "clock-page" : "evening";
    let result: unknown;
    if (url.pathname.endsWith("/settings/board")) result = { boards, board_type: "black", devices: ["flagship"] };
    else if (url.pathname.endsWith("/v1/status"))
      result = {
        running: true,
        initialized: true,
        boards: Object.fromEntries(boards.map((b) => [b.id, { health: { reachable: true, breaker_open: false } }])),
      };
    else if (url.pathname.endsWith("/schedules/active/page")) result = { schedule_enabled: true, page_id: pageId };
    else if (url.pathname.endsWith("/settings/active-page")) result = { page_id: pageId };
    else if (url.pathname.endsWith("/v1/pages"))
      result = {
        pages: [
          { id: "evening", name: "Evening commute" },
          { id: "night", name: "Good night" },
          { id: "clock-page", name: "Clock" },
        ],
        total: 3,
      };
    else if (url.pathname.endsWith("/v1/collections"))
      result = {
        collections: [
          {
            id: "collection:agenda",
            name: "Desk agenda",
            page_ids: ["evening"],
            selection_mode: "time",
            time: { interval_seconds: 60 },
          },
        ],
        total: 1,
      };
    else if (url.pathname.startsWith("/api/v1/boards/"))
      result = { next_change_at: next, next_change_reason: "schedule", next_page_id: "night" };
    else if (url.pathname.endsWith("/board/current-message"))
      result = {
        message: selected === "clock" ? "72° OK" : "GOOD EVENING",
        characters: null,
        expected_characters: null,
        rows: selected === "desk" ? 8 : selected === "clock" ? 1 : 6,
        cols: selected === "desk" ? 10 : selected === "clock" ? 5 : 22,
        cached_at: new Date().toISOString(),
      };
    else if (url.pathname.endsWith("/silence-status")) result = { enabled: false, active: false };
    if (result === undefined) await route.continue();
    else await route.fulfill({ json: result });
  });
  await page.goto("/");
  for (const width of [390, 768, 1280])
    for (const theme of ["light", "dark"]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.evaluate((value) => localStorage.setItem("theme", value), theme);
      await page.reload();
      await expect(page.getByTestId("home-next-event")).toContainText("Good night");
      if (width < 768) await expect(page.getByRole("button", { name: "Manage Desk Pixoo" })).toBeHidden();
      else {
        await expect(page.getByRole("button", { name: "Manage Desk Pixoo" })).toContainText("Collection · Desk agenda");
        await expect(page.getByRole("button", { name: "Manage Entry clock" })).toContainText("Schedule Mode · Clock");
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await waitForHomeEntrance(page);
      await injectAxe(page);
      expect(
        await getViolations(page, undefined, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } }),
      ).toEqual([]);
      await waitForHomeEntrance(page);
      await page.screenshot({ path: testInfo.outputPath(`impl-schedule-${width}-${theme}.png`), fullPage: true });
    }
  await page.getByRole("button", { name: "Manage Desk Pixoo" }).click();
  await expect(page.getByTestId("home-supporting-pane")).toContainText("Up next · Desk Pixoo");
  await expect(page.getByRole("button", { name: "Manage Kitchen board" })).toBeVisible();
});
