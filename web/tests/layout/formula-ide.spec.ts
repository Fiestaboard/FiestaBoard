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
          ...(request.diagnostics === true && {
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
                      {
                        id: 0,
                        parent: null,
                        kind: "call",
                        label: "IF",
                        start: 0,
                        end: 43,
                        value: `"${ifValue}"`,
                        value_truncated: false,
                        error: formula.error,
                      },
                      {
                        id: 1,
                        parent: 0,
                        kind: "binary",
                        label: ">",
                        start: 3,
                        end: 27,
                        value: "false",
                        value_truncated: false,
                        error: formula.error,
                      },
                      {
                        id: 2,
                        parent: 1,
                        kind: "variable",
                        label: "weather.temperature",
                        start: 3,
                        end: 22,
                        value: missing ? "" : "72",
                        value_truncated: false,
                        error: formula.error,
                      },
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

        // H6: Live · Sample · Missing is one radio group (DataSourceSwitch): in the
        // header on desktop, in the dock's ⋯ More below 1024 px (UX-10-2).
        const docked = width < 1024;
        const openMore = async () => {
          if (docked) await page.getByRole("button", { name: "More", exact: true }).last().click();
        };
        const closeMore = async () => {
          if (docked) await page.keyboard.press("Escape");
        };
        if (docked) {
          const preview = page.locator("#page-editor-preview");
          await expect(preview.getByRole("radiogroup", { name: "Preview data" })).toHaveCount(0);
        }
        await openMore();
        const sources = page.getByRole("radiogroup", { name: "Preview data" });
        await expect(sources).toBeVisible();
        expect(await sources.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
        await sources.getByRole("radio", { name: "Missing" }).click();
        await closeMore();
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
        await openMore();
        await sources.getByRole("radio", { name: "Live" }).click();
        await closeMore();
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

          // 04c C3: Inspect (the View menu, DD-W156), click a tile.
          await page.getByRole("button", { name: "View", exact: true }).click();
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

// BB-E-5 / BB-E-6 (Figma 53:137378, 307:46094): the preview card's header is one
// row that never reflows, the target is its meta, and Mirror sits beside Replay.
for (const width of [1280, 1440]) {
  test(`preview card header is one row at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockEditorApi(page);
    // Replay is offered only while the flaps animate; this fixture turns them off elsewhere.
    await page.route(
      (url) => url.pathname === "/api/settings/all",
      (route) => route.fulfill({ json: { display: { board_animations: "on", board_flap_speed: "standard" } } }),
    );
    await page.goto(`/tests/layout/formula-ide.html?theme=light`);
    const card = page.locator("#page-editor-preview");
    const header = card.locator('[data-slot="editor-preview-header"]');
    await expect(header.getByRole("radiogroup", { name: "Preview data" })).toBeVisible();
    const height = async () => (await header.boundingBox())!.height;
    expect(await height()).toBeLessThanOrEqual(40);
    await expect(header).toContainText("Live preview");

    await header.getByRole("radio", { name: "Sample" }).click();
    await expect(header).toContainText("Live preview");
    expect(await height()).toBeLessThanOrEqual(40);

    // D3 (DD-W159): a saved page's meta is plain text that truncates; no popup, no size row.
    await expect(page.getByRole("combobox", { name: "Change board size" })).toHaveCount(0);
    await expect(header.getByTestId("preview-target-trigger")).toHaveCount(0);
    const target = header.getByTestId("preview-target-meta");
    await expect(target).toHaveText("Kitchen board · Flagship 22 × 6");
    await expect(target).toHaveAttribute("title", "Kitchen board · Flagship 22 × 6");
    const style = await target.evaluate((el) => {
      const cs = getComputedStyle(el);
      return { overflow: cs.textOverflow, size: cs.fontSize, family: cs.fontFamily };
    });
    expect(style.overflow).toBe("ellipsis");
    // The header meta's 12 px mono (307:46094), not body text.
    expect(style.size).toBe("12px");
    expect(style.family).toMatch(/mono/i);
    // Board colour is a View choice, and the choice closes the menu.
    await header.getByRole("button", { name: "View", exact: true }).click();
    await page.getByRole("group", { name: "Board color" }).getByRole("menuitemradio", { name: "White" }).click();
    await expect(page.getByRole("menu")).toHaveCount(0);
    expect(await height()).toBeLessThanOrEqual(40);

    const live = card.locator('[data-slot="editor-preview-live"]');
    await expect(live.getByRole("button", { name: "Replay" })).toBeVisible();
  });
}

// Editor UX FP-3 (UX-4-1, UX-4-4, UX-9-3; DD-W156): the header is one 40 px row
// of `Live | Sample | Missing` and ⋯ View; the caption slot under the board
// keeps its height in every mode, so nothing moves; Esc leaves Inspect.
for (const width of [1024, 1440]) {
  test(`calm preview card at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await mockEditorApi(page);
    await page.goto(`/tests/layout/formula-ide.html?theme=light`);
    const card = page.locator("#page-editor-preview");
    const header = card.locator('[data-slot="editor-preview-header"]');
    const sources = header.getByRole("radiogroup", { name: "Preview data" });
    await expect(sources).toBeVisible();
    const height = async () => (await header.boundingBox())!.height;
    expect(await height()).toBeLessThanOrEqual(40);
    expect(await header.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    // No Inspect button, clock or zoom toggle in the row: they are View's.
    await expect(header.getByRole("button", { name: /^Inspect/ })).toHaveCount(0);
    await expect(header.locator('[data-slot="board-preview-mode-toggle"]')).toHaveCount(0);

    const view = header.getByRole("button", { name: "View", exact: true });
    await view.click();
    const menu = page.getByRole("menu");
    await expect(menu.getByRole("menuitem", { name: "Preview at a time…" })).toBeVisible();
    await expect(menu.getByRole("menuitemcheckbox", { name: /Inspect/ })).toContainText("I");
    await expect(menu.getByRole("menuitemradio", { name: /Fit/ })).toContainText("F");
    await expect(menu.getByRole("menuitemradio", { name: /Actual size/ })).toContainText("1");
    await page.keyboard.press("Escape");

    // The caption slot: same place and height in Live, Sample and Inspect.
    const caption = card.locator('[data-slot="preview-caption"]');
    const board = card.locator("[data-row]").first();
    const editor = page.getByRole("textbox", { name: "Template editor" });
    const measure = async () => ({
      caption: await caption.boundingBox(),
      board: (await board.boundingBox())!.y,
      editor: (await editor.boundingBox())!.y,
    });
    await expect(caption).toHaveCount(1);
    const live = await measure();
    await sources.getByRole("radio", { name: "Sample" }).click();
    await expect(caption).toContainText("Sample shows");
    expect(await measure()).toEqual(live);
    await sources.getByRole("radio", { name: "Live" }).click();
    await page.locator("body").click({ position: { x: 2, y: 2 } });
    await page.keyboard.press("i");
    await expect(caption).toContainText("Esc to leave");
    expect(await measure()).toEqual(live);
    await expect(card.locator("[data-inspecting]")).toHaveCount(1);
    await page.keyboard.press("Escape");
    await expect(card.locator("[data-inspecting]")).toHaveCount(0);
    await expect(editor).toBeFocused();

    // A preview time shows Figma's `At 7:00 AM ×` chip in the same row.
    await view.click();
    await page.getByRole("menuitem", { name: "Preview at a time…" }).click();
    await page.getByRole("option", { name: "7 AM" }).click();
    await page.keyboard.press("Escape");
    await expect(header.getByTestId("preview-time-chip")).toContainText("7:00 AM");
    expect(await height()).toBeLessThanOrEqual(40);
    await header.getByRole("button", { name: "Preview at the current time" }).click();
    await expect(header.getByTestId("preview-time-chip")).toHaveCount(0);

    // 1 is Actual size, F toggles back to Fit (outside text).
    const mode = card.locator('[data-slot="board-viewport"]');
    await page.locator("body").click({ position: { x: 2, y: 2 } });
    await page.keyboard.press("1");
    await expect(mode).toHaveAttribute("data-mode", "actual");
    await page.keyboard.press("f");
    await expect(mode).toHaveAttribute("data-mode", "fit");
  });
}

// Editor UX W-5 (DD-W169): one formula editor, two placements. Docked under the
// preview from 1024 (111:30911), a bottom sheet with no scrim from 640 to 1023,
// with the same names in both, and the board still in view above the sheet.
for (const width of [900, 1440]) {
  test(`one formula editor at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 1000 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mockEditorApi(page);
    await page.goto(`/tests/layout/formula-ide.html?theme=light`);
    const template = page.locator('[contenteditable="true"]');
    await expect(template).toBeVisible();
    await template.click();
    await page.keyboard.press("Control+e");

    const card = page.getByTestId("formula-code-card");
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute("data-placement", width >= 1024 ? "docked" : "sheet");
    await expect(card.getByText("New formula", { exact: true })).toBeVisible();
    await expect(card.getByRole("tab", { name: "Code" })).toBeVisible();
    await expect(card.getByRole("tab", { name: "Builder" })).toBeVisible();
    await expect(card.getByRole("button", { name: "Cancel" })).toBeVisible();
    await expect(card.getByRole("button", { name: "Insert formula" })).toBeVisible();
    // No second editor, no blurred page, no explanatory caption.
    await expect(page.getByRole("dialog", { name: "Formula editor" })).toHaveCount(0);
    // (It is the values' tooltip and the code's description, not a visible caption.)
    await expect(
      page.getByText("Values on the right are from the current preview.").and(page.locator(":not(.sr-only)")),
    ).toHaveCount(0);
    const blurred = await page.evaluate(() =>
      [...document.querySelectorAll("body *")].some((el) => getComputedStyle(el).backdropFilter.includes("blur")),
    );
    expect(blurred).toBe(false);

    // The board is in view and not under the editor.
    const board = (await page.locator('#page-editor-preview [role="img"]').first().boundingBox())!;
    const editor = (await card.boundingBox())!;
    expect(board.y).toBeGreaterThanOrEqual(0);
    expect(board.y + board.height).toBeLessThanOrEqual(editor.y);
    await page.screenshot({ path: testInfo.outputPath(`formula-${width}.png`) });

    // The caret is in the code, not on the Code tab: a tablet keeps its keyboard.
    await expect(card.locator(".cm-content")).toBeFocused();

    // Esc cancels and hands the caret back to the template.
    await page.keyboard.press("Escape");
    await expect(card).toHaveCount(0);
    await expect(template).toBeFocused();

    // Clicking an existing chip opens the same editor with the caret in its code.
    const chips = page.getByTestId("formula-atom-chip");
    await expect(chips).toHaveCount(1);
    await chips.first().click();
    await expect(card).toBeVisible();
    await expect(card.getByText("Formula · line 3")).toBeVisible();
    await expect(card.getByRole("button", { name: "Update formula" })).toBeVisible();
    await page.waitForTimeout(100);
    await expect(card.locator(".cm-content")).toBeFocused();
    await card.getByRole("button", { name: "Cancel" }).click();
    await expect(card).toHaveCount(0);

    // Inserting: a new formula goes in at the caret and the template has the caret again.
    await template.click();
    await page.keyboard.press("End");
    await page.keyboard.press("Control+e");
    await expect(card).toBeVisible();
    await page.keyboard.type("1 + 1");
    const insert = card.getByRole("button", { name: "Insert formula" });
    await expect(insert).toBeEnabled();
    await insert.click();
    await expect(card).toHaveCount(0);
    await expect(template).toContainText("1 + 1");
    await expect(template).toBeFocused();
  });
}
