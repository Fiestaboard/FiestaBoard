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
  template: [
    "GOOD MORNING",
    "{{weather.temperature}}°",
    '{{= IF(weather.temperature > 80, "HOT", "NICE") }} OUT',
    "{{datetime.time}}",
    "",
    "HAVE A GREAT DAY",
  ],
  duration_seconds: 300,
  revision: 1,
  line_metadata: Array.from({ length: 6 }, () => ({ alignment: "center", wrap: false })),
};

async function mockEditorApi(page: Page, drawingSource: "profile" | "baseline" = "profile") {
  const renders: Array<Record<string, unknown>> = [];
  // Match backend URLs only: Vite also loads source modules under /src/lib/api/.
  await page.route(
    (url) => url.pathname.startsWith("/api/"),
    async (route) => {
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
          drawing: { source: drawingSource, features: {} },
          next_change_at: null,
          next_page_id: null,
          active_page_id: kitchenMorning.id,
        };
      } else if (pathname === `/v1/pages/${kitchenMorning.id}`) {
        response =
          route.request().method() === "DELETE"
            ? {
                id: kitchenMorning.id,
                message: "Page deleted",
                active_page_updated: false,
                default_page_created: false,
              }
            : kitchenMorning;
      } else if (pathname === "/v1/pages" || pathname === "/pages") {
        response = { pages: [kitchenMorning] };
      } else if (pathname === "/v1/variables") {
        response = {
          variables: { weather: ["temperature"], datetime: ["time"] },
          variable_metadata: {
            weather: { temperature: { example: "68" } },
            datetime: { time: { example: "7:00 AM" } },
          },
          max_lengths: { "weather.temperature": 3, "datetime.time": 5 },
          colors: { red: 63, orange: 64, yellow: 65, green: 66, blue: 67, violet: 68, white: 69, black: 70 },
          formatting: {
            fill_space: { syntax: "{{fill_space}}", description: "Fill the remaining line width" },
          },
        };
      } else if (pathname === "/templates/render" || pathname === "/templates/render/live") {
        const request = route.request().postDataJSON() as Record<string, unknown> & { template: string | string[] };
        renders.push(request);
        const preview = request.preview as { missing?: string[] } | undefined;
        const missing = !!preview?.missing?.length;
        const template = Array.isArray(request.template) ? request.template : [request.template];
        const ifValue = missing ? "#REF" : "NICE";
        const lines = template.map((line) =>
          line
            .replaceAll("{{weather.temperature}}", missing ? "???" : "72")
            .replaceAll("{{datetime.time}}", missing ? "???" : "7:30 AM")
            .replace(/\{\{=[^}]*\}\}/, ifValue),
        );
        const rendered = lines.join("\n");
        const debug = request.debug as { trace?: { line: number; start: number }; source_map?: boolean } | undefined;
        const formula = {
          line: 3,
          start: 0,
          end: 44,
          source: 'IF(weather.temperature > 80, "HOT", "NICE")',
          value: ifValue,
          error: missing ? "#REF" : null,
          error_at: null,
          message: missing ? "No value at weather.temperature" : null,
        };
        response = {
          rendered,
          lines,
          line_count: lines.length,
          charset: "vestaboard_v1",
          charset_issues: [],
          ...(request.diagnostics && {
            diagnostics: {
              formulas: [formula],
              lines: lines.map((text, index) => ({
                line: index + 1,
                first_row: index + 1,
                rows_wanted: 1,
                rows_shown: 1,
                clip: null,
                clip_line: null,
                widest: text.length,
                cut: false,
                hidden: [],
              })),
            },
          }),
          ...(preview && { sources: { weather: { state: "stale", updated_at: "2026-11-17T14:12:00Z" } } }),
          ...(debug && {
            debug: {
              trace: debug.trace
                ? {
                    ...formula,
                    truncated: false,
                    events: [
                      { id: 0, parent: null, kind: "call", label: "IF", start: 0, end: 43, value: `"${ifValue}"`, value_truncated: false, error: formula.error },
                      { id: 1, parent: 0, kind: "binary", label: ">", start: 3, end: 27, value: "false", value_truncated: false, error: formula.error },
                      { id: 2, parent: 1, kind: "variable", label: "weather.temperature", start: 3, end: 22, value: missing ? "" : "72", value_truncated: false, error: formula.error },
                    ],
                  }
                : null,
              source_map: debug.source_map
                ? {
                    rows: 6,
                    cols: 22,
                    sources: [{ line: 3, start: 0, end: 44, kind: "formula" }],
                    cells: Array.from({ length: 6 }, (_, row) =>
                      Array.from({ length: 22 }, (_, col) => (row === 2 && col < 4 ? 0 : null)),
                    ),
                  }
                : null,
              source_map_status: debug.source_map ? "complete" : "not_requested",
            },
          }),
          ...(pathname.endsWith("/live") && {
            sent_to_board: true,
            board_id: board.id,
            paused: false,
            silenced: false,
          }),
        };
      } else if (pathname === "/v1/functions") {
        response = {
          functions: {
            IF: { category: "logic", signature: "IF(cond, then[, else])", summary: "Conditional value" },
            FORMATDATE: { category: "date", signature: 'FORMATDATE(d, "MMM DD")', summary: "Format a date" },
            FOREACH: { category: "array", signature: "FOREACH(array, rowExpr[, limit])", summary: "One row per item" },
          },
        };
      } else if (pathname === "/templates/validate") {
        response = { valid: true, errors: [] };
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
      } else if (pathname === "/collections" || pathname === "/v1/collections") {
        response = { collections: [] };
      } else if (pathname === "/v1/status") {
        response = {
          running: true,
          initialized: true,
          config_summary: {
            weather_enabled: true,
            home_assistant_enabled: false,
            guest_wifi_enabled: false,
            star_trek_quotes_enabled: false,
          },
        };
      } else if (pathname === "/panels") {
        response = { panels: [], total: 0 };
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
    },
  );
  return renders;
}

for (const theme of ["light", "dark"] as const) {
  for (const width of [390, 900, 1440]) {
    test.describe(`formula IDE at ${width}px in ${theme}`, () => {
      test("formula values, preview data sources and inspect", async ({ page }, testInfo) => {
        page.on("pageerror", (error) => console.error("Formula IDE fixture page error:", error.message));
        const shots = process.env.FORMULA_IDE_SHOTS || testInfo.outputPath("formula-ide-shots");
        await mkdir(shots, { recursive: true });
        await page.setViewportSize({ width, height: 1000 });
        await page.emulateMedia({ reducedMotion: "reduce" });
        const renders = await mockEditorApi(page);
        await page.goto(`/tests/layout/formula-ide.html?theme=${theme}`);
        await expect(page.locator('[contenteditable="true"]')).toBeVisible();

        // H5: the chip shows its value from the same render as the board.
        const chip = page.getByTestId("formula-atom-chip");
        await expect(chip).toContainText("= NICE");
        expect(renders.some((body) => body.diagnostics === true)).toBe(true);

        // H6: Live · Sample · Missing is one radio group (DataSourceSwitch).
        const sources = page.getByRole("radiogroup", { name: "Preview data" });
        await expect(sources).toBeVisible();
        expect(await sources.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
        await sources.getByRole("radio", { name: "Missing" }).click();
        const missing = page.getByTestId("missing-values");
        await expect(missing).toContainText("2 missing");
        await expect(missing).toContainText("weather.temperature");
        await expect(chip).toContainText("#REF");
        expect(renders.some((body) => (body.preview as { missing?: string[] })?.missing?.includes("weather"))).toBe(
          true,
        );
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
        await injectAxe(page);
        await checkA11y(page, "main");
        await page.screenshot({ path: path.join(shots, `impl-${width}-${theme}-missing.png`), fullPage: true });
        await sources.getByRole("radio", { name: "Live" }).click();
        await expect(missing).toHaveCount(0);

        if (width >= 1024) {
          // 04c C1: the chip opens the docked Code editor.
          await chip.click();
          const codeCard = page.getByTestId("formula-code-card");
          await expect(codeCard).toBeVisible();
          await expect(codeCard).toContainText("Formula · line 3");
          await expect(page.getByTestId("line-produces")).toContainText("Line 3 produces");
          await checkA11y(page, "main");
          await page.screenshot({ path: path.join(shots, `impl-${width}-${theme}-code.png`), fullPage: true });

          // 04c C2: Builder recipes.
          await page.getByTestId("tab-builder").click();
          await expect(page.getByRole("radiogroup", { name: "Recipes" })).toBeVisible();
          await expect(page.getByTestId("generated-code")).toBeVisible();
          await checkA11y(page, "main");
          await page.screenshot({ path: path.join(shots, `impl-${width}-${theme}-builder.png`), fullPage: true });
          await page.getByRole("button", { name: "Cancel" }).click();

          // 04c C3: Inspect, click a tile.
          await page.getByTestId("inspect-toggle").click();
          await page.locator('[data-inspecting] [data-row="2"][data-col="1"]').first().click();
          const inspector = page.getByTestId("inspector-pane");
          await expect(inspector).toContainText("Row 3 → line 3");
          await expect(inspector.getByTestId("trace-steps")).toContainText("weather.temperature > 80");
          await expect(page.getByTestId("inspect-cell")).toBeVisible();
          await checkA11y(page, "main");
          await page.screenshot({ path: path.join(shots, `impl-${width}-${theme}-inspect.png`), fullPage: true });
        } else {
          // 07c H5 phone/tablet: long-press (context menu) a chip › Inspect sheet with TraceStep.
          await chip.click({ button: "right" });
          const sheet = page.getByTestId("inspect-sheet");
          await expect(sheet).toBeVisible();
          await expect(sheet).toContainText("Inspect · line 3");
          await expect(sheet.getByTestId("trace-steps")).toContainText("weather.temperature");
          await expect(sheet.getByTestId("fit-report")).toContainText("Fits");
          await checkA11y(page, '[role="dialog"]');
          await page.screenshot({ path: path.join(shots, `impl-${width}-${theme}-inspect-sheet.png`) });
        }
      });
    });
  }
}
