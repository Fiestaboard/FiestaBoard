import { getViolations, injectAxe } from "axe-playwright";

import {
  configureBoard,
  createPage,
  createSchedule,
  deleteAllSchedules,
  expect,
  suppressWizard,
  test,
} from "./helpers";

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await suppressWizard(page);
  await deleteAllSchedules();
});

test("H8 displays the hub answer and clears it when the instant changes", async ({ page }) => {
  const pageId = await createPage("cx-schedule-h8", ["H8 PREVIEW", "", "", "", "", ""]);
  await createSchedule(pageId, "00:00", "23:59", "all");
  await page.goto("/schedule");
  const mode = page.getByTestId("schedule-enabled-toggle");
  await expect(mode).toBeVisible();
  if ((await mode.getAttribute("aria-checked")) === "false") await mode.click();
  const response = page.waitForResponse(
    (entry) => entry.url().includes("/schedules/active/page?") && entry.url().includes("at="),
  );
  await page.getByRole("button", { name: "Check instant" }).click();
  const answer = await (await response).json();
  expect(answer.page_id).toBe(pageId);
  await expect(
    page.getByRole("region", { name: "Active page at instant" }).getByText("cx-schedule-h8").first(),
  ).toBeVisible();
  const input = page.getByLabel("Instant", { exact: true });
  const value = await input.inputValue();
  await input.fill(`${value.slice(0, 11)}12:15`);
  await expect(page.getByRole("region", { name: "Active page at instant" })).toHaveCount(0);
});

test("H8 collection fixture renders every rule and does not send or store", async ({ page }) => {
  let writes = 0;
  await page.route("**/api/v1/collections", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      json: {
        collections: [
          {
            id: "collection:cx-rules",
            name: "cx-rules",
            page_ids: [],
            selection_mode: "variable",
            time: { interval_seconds: 60 },
            variable: { rules: [], default_page_id: "", poll_seconds: 60 },
          },
        ],
        total: 1,
      },
    });
  });
  await page.route("**/api/schedules/active/page?**", (route) =>
    route.fulfill({
      json: {
        page_id: "collection:cx-rules",
        resolved_page_id: "cx-winner",
        source: "schedule",
        schedule_enabled: true,
        silenced: true,
        temporary_override: { active: false },
      },
    }),
  );
  await page.route("**/api/collections/*/dry-run", (route) =>
    route.fulfill({
      json: {
        collection_id: "collection:cx-rules",
        at: new Date().toISOString(),
        page_id: "cx-winner",
        rules: [
          { index: 0, expression: "weather.temperature > 60", value: "true", matched: true },
          { index: 1, expression: "HOUR(NOW()) > 12", value: "false", matched: false },
        ],
        timeline: [],
        shown_on: ["cx-display"],
        sources: {},
        truncated: false,
      },
    }),
  );
  page.on("request", (request) => {
    if (
      request.method() !== "GET" &&
      /\/(?:send|render\/live|active-page|v1\/pages|v1\/schedules)(?:\?|$)/.test(request.url())
    )
      writes++;
  });
  await page.goto("/schedule");
  await page.getByRole("button", { name: "Check instant" }).click();
  await expect(page.getByText("Silenced", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Run collection dry run" }).click();
  await expect(page.getByText("weather.temperature > 60", { exact: true })).toBeVisible();
  await expect(page.getByText("HOUR(NOW()) > 12", { exact: true })).toBeVisible();
  expect(writes).toBe(0);
});

for (const width of [390, 768, 1280]) {
  for (const theme of ["light", "dark"] as const) {
    test(`Schedule ${width} ${theme} view, axe and screenshot`, async ({ page }, testInfo) => {
      const pageId = await createPage("cx-schedule-preview", ["SCHEDULE", "", "", "", "", ""]);
      await createSchedule(pageId, "09:00", "13:00", "all");
      await page.setViewportSize({ width, height: 1000 });
      await page.addInitScript((value) => {
        localStorage.setItem("theme", value);
        localStorage.removeItem("schedule-view-mode");
      }, theme);
      await page.emulateMedia({ colorScheme: theme });
      await page.goto("/schedule");
      await expect(page.getByRole("radiogroup", { name: "Schedule view" })).toBeVisible();
      await expect(
        page.getByRole("radio", { name: width < 768 ? "Day" : width < 1024 ? "List" : "Week", exact: true }),
      ).toHaveAttribute("aria-checked", "true");
      if (width < 768) await expect(page.getByRole("radiogroup", { name: "Choose a day" })).toBeVisible();
      await injectAxe(page);
      const violations = await getViolations(page, "main", {
        runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] },
      });
      expect(violations).toEqual([]);
      const path = testInfo.outputPath(`schedule-${width}-${theme}.png`);
      await page.screenshot({ path, fullPage: true });
      await testInfo.attach(`schedule-${width}-${theme}`, { path, contentType: "image/png" });
    });
  }
}
