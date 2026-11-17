import { mkdir } from "node:fs/promises";
import path from "node:path";

import { expect, type Page, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

import outputs from "../../src/__tests__/mocks/first-party-outputs.json" with { type: "json" };

const board = {
  id: "kitchen-board",
  name: "Kitchen board",
  device_type: "flagship",
  board_color: "black",
  enabled: true,
  output: "vestaboard",
};
const kitchenMorning = {
  id: "kitchen-morning",
  name: "Kitchen morning",
  type: "template",
  device_type: "flagship",
  template: ["GOOD MORNING", "", "{{weather.temperature}} SUNNY", "{{datetime.time}}", "", ""],
  duration_seconds: 300,
  revision: 1,
  line_metadata: Array.from({ length: 6 }, () => ({ alignment: "center", wrap: false })),
};

async function mockEditorApi(page: Page) {
  await page.route("**/api/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname.slice(4);
    let response: unknown;
    if (pathname === "/settings/board") {
      response = { boards: [board], devices: ["flagship"], board_type: "black" };
    } else if (pathname.startsWith("/v1/boards/")) {
      response = {
        ...board,
        rows: 6,
        cols: 22,
        is_primary: true,
        paused: false,
        schedule_enabled: false,
        drawing: { source: "profile", features: {} },
        next_change_at: null,
        next_page_id: null,
        active_page_id: kitchenMorning.id,
      };
    } else if (pathname === `/v1/pages/${kitchenMorning.id}`) {
      response = kitchenMorning;
    } else if (pathname === "/v1/pages" || pathname === "/pages") {
      response = { pages: [kitchenMorning] };
    } else if (pathname === "/v1/variables") {
      response = {
        variables: { weather: ["temperature"], datetime: ["time"] },
        max_lengths: { "weather.temperature": 3, "datetime.time": 5 },
        colors: { red: 63, orange: 64, yellow: 65, green: 66, blue: 67, violet: 68, white: 69, black: 70 },
        formatting: {
          fill_space: { syntax: "{{fill_space}}", description: "Fill the remaining line width" },
        },
      };
    } else if (pathname === "/templates/render" || pathname === "/templates/render/live") {
      const request = route.request().postDataJSON() as { template: string | string[] };
      const template = Array.isArray(request.template) ? request.template.join("\n") : request.template;
      const rendered = template.replaceAll("{{weather.temperature}}", "72").replaceAll("{{datetime.time}}", "7:30 AM");
      response = {
        rendered,
        lines: rendered.split("\n"),
        line_count: rendered.split("\n").length,
        charset: "vestaboard_v1",
        charset_issues: [],
        ...(pathname.endsWith("/live") && {
          sent_to_board: true,
          board_id: board.id,
          paused: false,
          silenced: false,
        }),
      };
    } else if (pathname === "/outputs") {
      response = outputs;
    } else if (pathname === "/settings/plugins") {
      response = { transition_plugins_enabled: false, output_plugins_enabled: false, auto_update: false };
    } else if (pathname === "/plugins") {
      response = { plugins: [], total: 0, enabled_count: 0, plugin_system_enabled: true };
    } else if (pathname === "/plugins/registry") {
      response = { entries: [] };
    } else if (pathname === "/silence-status") {
      response = { active: false, holds_blocked_sends: false, held: null };
    } else if (pathname === "/schedules") {
      response = { schedules: [] };
    } else if (pathname === "/collections") {
      response = { collections: [] };
    } else if (pathname === "/settings/all") {
      response = { display: { board_animations: "off", board_flap_speed: "standard" } };
    } else if (pathname === "/config") {
      response = { board_type: "black", refresh_interval: 60 };
    } else {
      // Unlisted endpoints fail visibly instead of reaching a live installation.
      await route.fulfill({ status: 404, json: { detail: `Unmocked editor fixture endpoint: ${pathname}` } });
      return;
    }
    await route.fulfill({ json: response });
  });
}

for (const theme of ["light", "dark"] as const) {
  for (const { width, coarse } of [
    { width: 390, coarse: false },
    { width: 768, coarse: false },
    { width: 1280, coarse: false },
    { width: 1024, coarse: true },
  ]) {
    test.describe(`${width}px ${coarse ? "coarse" : "fine"} pointer in ${theme}`, () => {
      test.use({ hasTouch: coarse });
      test("real editor preview and toolbar fit their independent breakpoints", async ({ page }, testInfo) => {
        const shots = process.env.EDITOR_TOUCH_SHOTS || testInfo.outputPath("editor-touch-shots");
        await page.setViewportSize({ width, height: 900 });
        await page.emulateMedia({ reducedMotion: "reduce" });
        await mockEditorApi(page);
        const rendered = page.waitForResponse(
          (response) => new URL(response.url()).pathname === "/api/templates/render",
        );
        await page.goto(`/tests/layout/editor-touch.html?theme=${theme}`);
        await rendered;
        await expect(page.getByRole("textbox", { name: /page name/i })).toHaveValue("Kitchen morning");
        await expect(page.locator('[contenteditable="true"]')).toBeVisible();
        const preview = page.locator('[data-slot="editor-preview"]');
        await expect(preview).toHaveAttribute("data-variant", width < 1024 ? "docked" : "pane");
        await expect(preview).toContainText("Live preview");
        await expect(preview.locator('[data-slot="board-preview-mode-toggle"]')).toHaveCount(1);
        await expect(page.getByRole("button", { name: /hide preview/i })).toHaveCount(0);
        const bounds = await preview.boundingBox();
        expect(bounds!.x).toBeGreaterThanOrEqual(0);
        expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        const touch = width < 768 || coarse;
        const touchToolbar = page.locator('[data-slot="editor-toolbar"][data-size="touch"]');
        expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(coarse);
        if (touch) {
          await expect(touchToolbar).toBeVisible();
          await expect(touchToolbar).toHaveAttribute("data-layout", "docked");
        } else {
          // A fine-pointer 768px tablet docks its preview but keeps the default toolbar.
          await expect(touchToolbar).toHaveCount(0);
          await expect(page.getByRole("button", { name: "Draw on board", exact: true })).toBeVisible();
        }
        await page.evaluate(() => document.fonts.ready);
        await injectAxe(page);
        await checkA11y(page, "main");
        await mkdir(shots, { recursive: true });
        await page.screenshot({ path: path.join(shots, `impl-${width}-${theme}.png`), animations: "disabled" });

        if (touch) {
          await page.getByRole("button", { name: "More", exact: true }).click();
          const sheet =
            width < 640
              ? page.getByRole("dialog", { name: "More", exact: true })
              : page.getByTestId("toolbar-dropdown-panel");
          await expect(sheet).toBeVisible();
          await expect(sheet.getByRole("switch", { name: "Mirror to board while editing", exact: true })).toBeVisible();
          if (width < 640) {
            await expect(sheet.getByText("Clipboard", { exact: true })).toBeVisible();
          } else {
            await expect(sheet.getByRole("group", { name: "Clipboard", exact: true })).toBeVisible();
          }
          const sheetBounds = await sheet.boundingBox();
          expect(sheetBounds!.x).toBeGreaterThanOrEqual(0);
          expect(sheetBounds!.x + sheetBounds!.width).toBeLessThanOrEqual(width);
          expect(sheetBounds!.y).toBeGreaterThanOrEqual(0);
          expect(sheetBounds!.y + sheetBounds!.height).toBeLessThanOrEqual(900);
          expect(await sheet.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
          for (const name of ["Cut", "Copy", "Paste"]) {
            const bounds = await sheet.getByRole("button", { name, exact: true }).boundingBox();
            expect(bounds!.x).toBeGreaterThanOrEqual(sheetBounds!.x);
            expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(sheetBounds!.x + sheetBounds!.width);
          }
          await checkA11y(page, width < 640 ? '[role="dialog"]' : '[data-testid="toolbar-dropdown-panel"]');
          await page.screenshot({ path: path.join(shots, `impl-${width}-${theme}-more.png`), animations: "disabled" });
        }
      });
    });
  }
}
