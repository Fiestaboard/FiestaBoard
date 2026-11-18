import { mkdir } from "node:fs/promises";
import path from "node:path";

import { expect, type Page, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

import outputs from "../../src/__tests__/mocks/first-party-outputs.json" with { type: "json" };

// Web 2.11 Creator IDE (Figma 04d 4.3 `184:159319`). Desktop (>= 1024 px):
// Explorer, five Inspector tabs, Problems | Warnings | Sent docked console,
// week timeline. Below 1024 px: Problems is the sixth tab (Jev
// desktop_console_two_option). Every hub response is mocked here.

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
  template: ["GOOD MORNING", "", "{{weather.temperature}} SUNNY", '{{= DEFAULT(weather.alert, "OK") }}', "", ""],
  duration_seconds: 30,
  revision: "r-live",
  line_metadata: Array.from({ length: 6 }, () => ({ alignment: "center", wrap: false })),
};
const revisions = [
  {
    id: "r2",
    saved_at: "2026-11-17T15:12:00Z",
    origin: "edited",
    via: "web",
    name: kitchenMorning.name,
    rows: 6,
    cols: 22,
    current: true,
  },
  {
    id: "r1",
    saved_at: "2026-11-16T21:02:00Z",
    origin: "assistant",
    via: "mcp",
    name: kitchenMorning.name,
    rows: 6,
    cols: 22,
    current: false,
  },
];

async function mockHub(page: Page) {
  await page.route(
    (url) => url.pathname.startsWith("/api/"),
    async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname.slice(4);
      let response: unknown;
      let status = 200;
      if (pathname === "/settings/board") {
        response = { boards: [board], devices: ["flagship"], board_type: "black" };
      } else if (pathname.startsWith("/v1/boards/")) {
        response = {
          ...board,
          rows: 6,
          cols: 22,
          is_primary: true,
          paused: false,
          schedule_enabled: true,
          drawing: { source: "profile", features: {} },
          next_change_at: null,
          next_page_id: null,
          active_page_id: kitchenMorning.id,
        };
      } else if (pathname === `/v1/pages/${kitchenMorning.id}`) {
        response = kitchenMorning;
      } else if (pathname === "/v1/pages" || pathname === "/pages") {
        response = { pages: [kitchenMorning, { ...kitchenMorning, id: "evening", name: "Evening news" }], total: 2 };
      } else if (pathname === "/v1/variables") {
        response = {
          variables: { weather: ["temperature", "alert"] },
          max_lengths: { "weather.temperature": 3, "weather.alert": 10 },
          colors: { red: 63, orange: 64, yellow: 65, green: 66, blue: 67, violet: 68, white: 69, black: 70 },
          formatting: {},
        };
      } else if (pathname === "/v1/functions") {
        response = { functions: {} };
      } else if (pathname === "/templates/render" || pathname === "/templates/render/live") {
        const body = request.postDataJSON() as { template: string | string[] };
        const lines = (Array.isArray(body.template) ? body.template : body.template.split("\n")).map((line) =>
          line.replace("{{weather.temperature}}", "72").replace(/\{\{=[^}]*\}\}/, "OK"),
        );
        response = {
          rendered: lines.join("\n"),
          lines,
          line_count: lines.length,
          charset: "vestaboard_v1",
          charset_issues: [],
          ...(pathname.endsWith("/live") && {
            sent_to_board: true,
            board_id: board.id,
            paused: false,
            silenced: false,
          }),
        };
      } else if (pathname === "/templates/validate") {
        response = {
          valid: false,
          rows: 6,
          cols: 22,
          errors: [{ line: 3, column: 22, code: "line_too_long", message: "Needs 25 of 22 columns", max_length: 25 }],
        };
      } else if (pathname === `/pages/${kitchenMorning.id}/draft`) {
        status = 404;
        response = { detail: "No draft" };
      } else if (pathname === `/pages/${kitchenMorning.id}/revisions`) {
        response = { page_id: kitchenMorning.id, revisions, total: revisions.length };
      } else if (pathname.startsWith(`/pages/${kitchenMorning.id}/revisions/`)) {
        const id = pathname.split("/").pop();
        response = { ...revisions.find((revision) => revision.id === id), content: kitchenMorning };
      } else if (pathname === `/pages/${kitchenMorning.id}/sends`) {
        response = {
          page_id: kitchenMorning.id,
          total: 2,
          sends: [
            {
              at: "2026-11-17T15:41:00Z",
              outcome: "sent",
              via: "auto",
              board_id: board.id,
              board_name: board.name,
              count: 1,
            },
            {
              at: "2026-11-17T14:55:00Z",
              outcome: "held",
              via: "show_now",
              board_id: board.id,
              board_name: board.name,
            },
          ],
        };
      } else if (pathname === "/v1/schedules" || pathname === "/schedules") {
        response = {
          schedules: [
            {
              id: "s1",
              page_id: kitchenMorning.id,
              board_id: board.id,
              start_time: "07:30",
              end_time: "08:30",
              day_pattern: "weekdays",
              enabled: true,
              created_at: "",
            },
          ],
          total: 1,
          default_page_id: null,
          enabled: null,
        };
      } else if (pathname === "/schedules/active/page") {
        response = {
          page_id: kitchenMorning.id,
          source: "schedule",
          schedule_enabled: true,
          current_time: "07:41",
          current_day: "friday",
          default_page_id: null,
          temporary_override: { active: false },
        };
      } else if (pathname === "/collections" || pathname === "/v1/collections") {
        response = { collections: [], total: 0 };
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
      } else if (pathname === "/v1/status") {
        response = { running: true, initialized: true, config_summary: {} };
      } else if (pathname === "/panels") {
        response = { panels: [], total: 0 };
      } else if (pathname === "/settings/all") {
        response = { display: { board_animations: "off", board_flap_speed: "standard" } };
      } else if (pathname === "/config") {
        response = { board_type: "black", refresh_interval: 60 };
      } else {
        await route.fulfill({ status: 404, json: { detail: `Unmocked Creator IDE fixture endpoint: ${pathname}` } });
        return;
      }
      await route.fulfill({ status, json: response });
    },
  );
}

for (const theme of ["light", "dark"] as const) {
  for (const width of [390, 900, 1440]) {
    test.describe(`${width}px in ${theme}`, () => {
      test("Creator IDE regions follow the 04d breakpoints and pass axe", async ({ page }, testInfo) => {
        page.on("pageerror", (error) => console.error("Creator IDE fixture page error:", error.message));
        const shots = process.env.CREATOR_IDE_SHOTS || testInfo.outputPath("creator-ide-shots");
        await page.setViewportSize({ width, height: 900 });
        await page.emulateMedia({ reducedMotion: "reduce" });
        await mockHub(page);
        await page.goto(`/tests/layout/creator-ide.html?theme=${theme}`);
        await expect(page.getByRole("textbox", { name: /page name/i })).toHaveValue("Kitchen morning");
        const ide = page.locator('[data-slot="creator-ide"]');
        await expect(ide).toBeVisible();
        const desktop = width >= 1024;
        await expect(ide).toHaveAttribute("data-layout", desktop ? "desktop" : "compact");

        const inspector = page.getByRole("tablist", { name: "Inspector" });
        await expect(inspector.getByRole("tab")).toHaveCount(desktop ? 5 : 6);
        await expect(page.getByText(/Showing on Kitchen board now · until 8:30/)).toBeVisible();
        // Live: the header offers Save draft beside Save & update board (04d decision 4).
        await expect(page.getByRole("button", { name: "Save draft" })).toBeVisible();
        await expect(page.getByRole("button", { name: "Save & update board" })).toBeVisible();
        // The page name keeps usable room beside the header actions, and they stay on screen.
        const nameBox = await page.getByRole("textbox", { name: /page name/i }).boundingBox();
        expect(nameBox!.width).toBeGreaterThanOrEqual(width < 640 ? 80 : 200);
        const publishBox = await page.getByRole("button", { name: "Save & update board" }).boundingBox();
        expect(publishBox!.x + publishBox!.width).toBeLessThanOrEqual(width);

        if (desktop) {
          await expect(page.getByRole("navigation", { name: "Explorer" })).toBeVisible();
          const console = page.getByRole("region", { name: "Console" });
          await expect(console.getByRole("tab", { name: "Problems 1" })).toBeVisible();
          await expect(console.getByText("Too long · Row 3")).toBeVisible();
          await expect(page.locator('[data-slot="ide-week"]')).toBeVisible();
        } else {
          await expect(page.getByRole("navigation", { name: "Explorer" })).toHaveCount(0);
          await expect(page.getByRole("region", { name: "Console" })).toHaveCount(0);
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

        await page.evaluate(() => document.fonts.ready);
        await injectAxe(page);
        await checkA11y(page, '[data-slot="creator-ide"]');
        await mkdir(shots, { recursive: true });
        await ide.scrollIntoViewIfNeeded();
        await page.screenshot({ path: path.join(shots, `impl-${width}-${theme}.png`), fullPage: true });

        // History: versions with Compare / Restore (RevisionRow), and the diff.
        await inspector.getByRole("tab", { name: "History" }).click();
        await expect(page.locator('[data-slot="ide-history"]')).toBeVisible();
        await page
          .getByRole("button", { name: /Compare/ })
          .nth(1)
          .click();
        await expect(page.getByRole("group", { name: "Version comparison" })).toBeVisible();
        await checkA11y(page, '[data-slot="creator-ide"]');
        await page.screenshot({ path: path.join(shots, `impl-${width}-${theme}-history.png`), fullPage: true });

        // Shows on: the hub's Now beside the schedule entry.
        await inspector.getByRole("tab", { name: "Shows on" }).click();
        await expect(page.locator('[data-slot="ide-shows-on"]').getByText("Now", { exact: true })).toBeVisible();
        await checkA11y(page, '[data-slot="creator-ide"]');
        await page.screenshot({ path: path.join(shots, `impl-${width}-${theme}-shows-on.png`), fullPage: true });

        if (!desktop) {
          await inspector.getByRole("tab", { name: /Problems/ }).click();
          await expect(page.getByText("Too long · Row 3")).toBeVisible();
          await checkA11y(page, '[data-slot="creator-ide"]');
        }
      });
    });
  }
}
