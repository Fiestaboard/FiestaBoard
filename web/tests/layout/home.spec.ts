import { expect, test } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

const now = new Date();
const next = new Date(now.getTime() + 3600000).toISOString();
const boards = [
  {
    id: "board-1",
    name: "Kitchen board",
    device_type: "flagship",
    board_color: "black",
    enabled: true,
    output: "vestaboard",
    // Saved connection data distinguishes configured displays from the
    // untouched placeholders that correctly show Home's no-display state.
    output_config: { api_mode: "local", host: "192.0.2.10", local_api_key: "layout-test-key" },
  },
  {
    id: "board-2",
    name: "Desk Pixoo",
    device_type: "flagship",
    board_color: "black",
    enabled: true,
    device_model: "divoom_pixoo64",
    output_config: { api_mode: "local", host: "192.0.2.11", local_api_key: "layout-test-key" },
  },
];

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    // Vite also serves modules under /src/lib/api/: leave those script requests untouched.
    if (!url.pathname.startsWith("/api/")) {
      await route.continue();
      return;
    }
    let result: unknown = {};
    if (url.pathname.endsWith("/settings/board")) result = { boards, devices: ["flagship"], board_type: "black" };
    if (url.pathname.endsWith("/config/validate")) result = { valid: true, is_first_run: false, errors: [] };
    if (url.pathname.endsWith("/v1/status"))
      result = { boards: { "board-1": { health: { reachable: true } }, "board-2": { health: { reachable: true } } } };
    if (url.pathname.endsWith("/schedules/active/page")) result = { schedule_enabled: true, page_id: "page-1" };
    if (url.pathname.endsWith("/pages/active")) result = { page_id: "page-1" };
    if (url.pathname.endsWith("/pages"))
      result = {
        pages: [
          { id: "page-1", name: "Evening commute" },
          { id: "page-2", name: "Good night" },
        ],
      };
    if (url.pathname.includes("/v1/boards/"))
      result = {
        next_change_at: next,
        next_change_reason: "schedule",
        next_page_id: "page-2",
        text: "GOOD EVENING",
        characters: null,
      };
    if (url.pathname.endsWith("/board/current-message"))
      result = { message: "GOOD EVENING", rows: 6, cols: 22, characters: null, cached_at: now.toISOString() };
    if (url.pathname.endsWith("/collections")) result = { collections: [] };
    await route.fulfill({ json: result });
  });
});
for (const width of [390, 768, 1280]) {
  for (const theme of ["light", "dark"]) {
    test(`Home supporting pane ${width} ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(`/tests/layout/home.html?theme=${theme}`);
      await expect(page.getByTestId("home-next-event")).toContainText("Good night");
      const columns = await page
        .getByTestId("home-columns")
        .evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length);
      expect(columns).toBe(width >= 1024 ? 2 : 1);
      const other = page.getByRole("button", { name: "Manage Desk Pixoo" });
      if (width < 768) await expect(other).toBeHidden();
      else await expect(other).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      // The standalone fixture's main element also has an entrance animation.
      // Keep contrast checks unchanged and wait for its actual settled opacity.
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
      await injectAxe(page);
      expect(
        await getViolations(page, undefined, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } }),
      ).toEqual([]);
      if (process.env.CX_HOME_SHOTS)
        await page.screenshot({ path: `${process.env.CX_HOME_SHOTS}/impl-${width}-${theme}.png`, fullPage: true });
    });
  }
}
