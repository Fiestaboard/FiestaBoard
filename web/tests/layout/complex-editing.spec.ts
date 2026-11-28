import { mkdir } from "node:fs/promises";
import path from "node:path";

import { expect, type Page, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

import outputs from "../../src/__tests__/mocks/first-party-outputs.json" with { type: "json" };

/**
 * Web 2.9 (Figma 04b + 07c): the real page editor with the complex-editing
 * lenses, at 390 / 900 / 1440 in light and dark, axe-checked.
 * - Lobby TV 96 × 24 (04b `126:134198`): desktop zoom, ruler, minimap,
 *   truncation map, Go to and row bands; scroll viewport below 1024.
 * - Lobby wall Note array 2 × 2 (04b `127:133562`, 07c `310:68695`/`310:71145`):
 *   Note focus and seams at desktop; "Column 1 of 2" scrolling below.
 * - Den TV 29 × 12 (07c `310:72331`): "Columns 1–… of 29" on the phone.
 * - Kitchen Flagship (07c `307:41698`/`307:44268`): H4 per-line overflow.
 */
const board = {
  id: "kitchen-board",
  name: "Kitchen board",
  device_type: "flagship",
  board_color: "black",
  enabled: true,
  output: "vestaboard",
};

const blank = (n: number) => Array.from({ length: n }, () => "");
const meta = (n: number) => Array.from({ length: n }, () => ({ alignment: "left", wrap: false }));

const pages = {
  "kitchen-morning": {
    id: "kitchen-morning",
    name: "Kitchen morning",
    type: "template",
    device_type: "flagship",
    template: ["GOOD MORNING", "", "", "N JUDAH {{muni.next}}", "", ""],
    line_metadata: meta(6),
  },
  "lobby-this-week": {
    id: "lobby-this-week",
    name: "Lobby this week",
    type: "template",
    device_type: "panel",
    grid_rows: 24,
    grid_cols: 96,
    template: [
      "ROSA'S CAFE  GOOD MORNING",
      "",
      "TONIGHT AT ROSA'S",
      "6:30 PM  OPEN MIC NIGHT",
      "7:00 PM  JAZZ TRIO ON THE PATIO",
      "",
      "THIS WEEK",
      "THU  POETRY SLAM",
      "",
      // A variable-named band two rows above the next: its long name wrapped
      // and overlapped its neighbour before UX-3-1 (Den TV rows 8/10).
      "{{date_time.day_of_week_name_in_full}}",
      "",
      "FRIDAY FISH FRY",
      ...blank(11),
      "NOW POURING COLD BREW  HOUSE CHAI  OAT LATTE  SPECIALS",
    ],
    line_metadata: meta(24),
  },
  "lobby-menu": {
    id: "lobby-menu",
    name: "Lobby menu",
    type: "template",
    device_type: "note_array",
    notes_wide: 2,
    notes_tall: 2,
    template: [
      "GOOD MORNING   FROM ROSA'S",
      "LATTE    4.50  MOCHA    5.00",
      // "CAPPUCCINO" (columns 12–21) runs across the seam after column 15.
      "TEA 3.00   CAPPUCCINO 4.75",
      "",
      "",
      "",
    ],
    line_metadata: meta(6),
  },
  "cafe-menu": {
    id: "cafe-menu",
    name: "Café menu",
    type: "template",
    device_type: "panel",
    grid_rows: 12,
    grid_cols: 29,
    template: ["", "    LOBBY MENU", "", "  COFFEE               $3", "  TEA                  $2", ...blank(7)],
    line_metadata: meta(12),
  },
} as const;
type PageId = keyof typeof pages;

async function mockEditorApi(page: Page, pageId: PageId) {
  const current = { ...pages[pageId], duration_seconds: 300, revision: 1 };
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
          drawing: { source: "profile", features: {} },
          next_change_at: null,
          next_page_id: null,
          active_page_id: current.id,
        };
      } else if (pathname === `/v1/pages/${current.id}`) {
        response = current;
      } else if (pathname === "/v1/pages" || pathname === "/pages") {
        response = { pages: [current] };
      } else if (pathname === "/v1/variables") {
        response = {
          variables: { muni: ["next"] },
          max_lengths: { "muni.next": 16 },
          colors: { red: 63, orange: 64, yellow: 65, green: 66, blue: 67, violet: 68, white: 69, black: 70 },
          formatting: {},
        };
      } else if (pathname === "/templates/validate") {
        response =
          pageId === "kitchen-morning"
            ? {
                valid: false,
                rows: 6,
                cols: 22,
                errors: [{ line: 4, column: 22, message: "Line 4 is too long", code: "line_too_long", max_length: 24 }],
              }
            : { valid: true, errors: [] };
      } else if (pathname === "/templates/render" || pathname === "/templates/render/live") {
        const request = route.request().postDataJSON() as { template: string | string[] };
        const lines = (Array.isArray(request.template) ? request.template : request.template.split("\n")).map((line) =>
          line.replaceAll("{{muni.next}}", "4, 12 AND 25 MIN"),
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
            weather_enabled: false,
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
        await route.fulfill({ status: 404, json: { detail: `Unmocked editor fixture endpoint: ${pathname}` } });
        return;
      }
      await route.fulfill({ json: response });
    },
  );
}

async function openEditor(page: Page, pageId: PageId, width: number, theme: "light" | "dark") {
  page.on("pageerror", (error) => console.error("Complex editing fixture page error:", error.message));
  await page.setViewportSize({ width, height: 900 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockEditorApi(page, pageId);
  const rendered = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/templates/render");
  await page.goto(`/tests/layout/complex-editing.html?theme=${theme}&page=${pageId}`);
  await rendered;
  await expect(page.getByRole("textbox", { name: /page name/i })).toHaveValue(pages[pageId].name);
  await expect(page.locator('[data-slot="editor-preview"] [data-slot="board-viewport"]')).toBeVisible();
}

async function finish(page: Page, testInfo: { outputPath: (...p: string[]) => string }, name: string) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => document.fonts.ready);
  await injectAxe(page);
  await checkA11y(page, "main", { detailedReport: true, detailedReportOptions: { html: true } });
  const shots = process.env.COMPLEX_EDITING_SHOTS || testInfo.outputPath("complex-editing-shots");
  await mkdir(shots, { recursive: true });
  await page.screenshot({ path: path.join(shots, `${name}.png`) });
}

const indicator = (page: Page) =>
  page.locator('[data-slot="editor-preview"] [data-slot="board-viewport-indicator-text"]');

for (const theme of ["light", "dark"] as const) {
  test.describe(`complex editing in ${theme}`, () => {
    // UX-4-2 / UX-4-3 (DD-W156): a big board opens at Fit with no chip row, ruler,
    // minimap or cut chart; zoom and the ruler live in the header's View menu.
    test("1440: big board opens at Fit; zoom, ruler and minimap come from View", async ({ page }, testInfo) => {
      await openEditor(page, "lobby-this-week", 1440, theme);
      const preview = page.locator('[data-slot="editor-preview"]');
      const viewport = preview.locator('[data-slot="board-viewport"]');
      await expect(viewport).toHaveAttribute("data-mode", "fit");
      await expect(preview.getByRole("group", { name: "Preview zoom" })).toHaveCount(0);
      await expect(preview.locator('[data-slot="board-preview-mode-toggle"]')).toHaveCount(0);
      await expect(preview.locator('[data-slot="complex-preview-ruler"]')).toHaveCount(0);
      await expect(preview.locator('[data-slot="complex-preview-overview"]')).toHaveCount(0);
      await expect(preview.getByText("Where lines are cut")).toHaveCount(0);
      const header = preview.locator('[data-slot="editor-preview-header"]');
      expect((await header.boundingBox())!.height).toBeLessThanOrEqual(40);
      // UX-3-2: the card header's caret readout replaced the Row · Col pill and its caption.
      await expect(page.getByRole("textbox", { name: "Go to row and column" })).toHaveCount(0);
      await expect(page.getByText(/rendered length per row/)).toHaveCount(0);
      const bands = page.getByRole("list", { name: "Row bands" });
      await expect(bands).toBeVisible();
      await expect(bands.getByText("THIS WEEK", { exact: true })).toBeVisible();
      await finish(page, testInfo, `impl-1440-${theme}-big-board`);

      // Tile md crops the board: the minimap appears, the page stays inside the viewport.
      const view = header.getByRole("button", { name: "View", exact: true });
      await view.click();
      await page.getByRole("menuitemradio", { name: "Tile md" }).click();
      await expect(viewport).toHaveAttribute("data-mode", "actual");
      await expect(indicator(page)).toContainText(/Columns 1–\d+ of 96/);
      await expect(preview.locator('[data-slot="complex-preview-overview"]')).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
      await view.click();
      await page.getByRole("menuitemcheckbox", { name: "Ruler" }).click();
      await expect(preview.getByRole("img", { name: /Column ruler · 96 columns/ })).toBeVisible();
      // F returns to Fit, and the minimap goes with the crop.
      await page.locator("body").click({ position: { x: 2, y: 2 } });
      await page.keyboard.press("f");
      await expect(viewport).toHaveAttribute("data-mode", "fit");
      await expect(preview.locator('[data-slot="complex-preview-overview"]')).toHaveCount(0);
      await finish(page, testInfo, `impl-1440-${theme}-big-board-zoomed`);
    });

    for (const width of [1440, 1024]) {
      test(`${width}: the template card header counts lines and follows the caret (UX-3-2)`, async ({ page }) => {
        await openEditor(page, "kitchen-morning", width, theme);
        const meta = page.getByTestId("template-card-meta");
        const card = page.locator('[data-slot="template-card"]');
        // Inside the card, above the first row.
        const [metaBox, cardBox, rowBox] = await Promise.all([
          meta.boundingBox(),
          card.boundingBox(),
          page.locator(".ProseMirror p").boundingBox(),
        ]);
        expect(metaBox!.y).toBeGreaterThan(cardBox!.y);
        expect(metaBox!.y + metaBox!.height).toBeLessThanOrEqual(rowBox!.y);
        await expect(meta).toHaveText("4 / 6 lines · Ln 1, Col 1");
        await page.locator('[contenteditable="true"]').click();
        await page.keyboard.press("Control+Home");
        await page.keyboard.press("ArrowDown");
        await page.keyboard.press("ArrowDown");
        await page.keyboard.press("ArrowDown");
        await page.keyboard.press("End");
        await expect(meta).toHaveText(/4 \/ 6 lines · Ln 4, Col \d+/);
        // The header never changes height as the caret moves.
        expect((await meta.boundingBox())!.height).toBe(metaBox!.height);
      });
    }

    test("1440: the template card stretches to the height its host gives it (card fill, UX-3-1)", async ({ page }) => {
      await openEditor(page, "kitchen-morning", 1440, theme);
      const editor = page.locator('[data-slot="template-editor"]');
      const card = page.locator('[data-slot="template-card"]');
      const natural = (await card.boundingBox())!.height;
      // FP-1's column gives the editor's host a height (down to the IDE row); stand in for it.
      await editor.evaluate((el) => {
        (el.parentElement as HTMLElement).style.height = "640px";
      });
      const [host, filled] = await Promise.all([
        editor.evaluate((el) => el.parentElement!.getBoundingClientRect().toJSON() as DOMRect),
        card.boundingBox(),
      ]);
      expect(filled!.height).toBeGreaterThan(natural + 100);
      expect(Math.abs(filled!.y + filled!.height - (host.y + host.height))).toBeLessThanOrEqual(2);
    });

    test("1440: band labels are one clamped line, never overlap, and the gutters stay on Ctrl+End (UX-3-1)", async ({
      page,
    }) => {
      await openEditor(page, "lobby-this-week", 1440, theme);
      const bands = page.getByRole("list", { name: "Row bands" }).getByTestId("row-band");
      await expect(bands.first()).toBeVisible();
      const boxes = await bands.evaluateAll((els) =>
        els.map((el) => {
          const r = el.getBoundingClientRect();
          const label = el.querySelector('[data-slot="row-band-label"]')!.getBoundingClientRect();
          return { top: r.top, bottom: r.bottom, label: label.height, title: el.getAttribute("title") };
        }),
      );
      for (const box of boxes) {
        expect(box.label).toBeLessThanOrEqual(16);
        expect(box.title).toBeTruthy();
      }
      for (let i = 1; i < boxes.length; i++) expect(boxes[i].top).toBeGreaterThanOrEqual(boxes[i - 1].bottom);
      await page.locator('[contenteditable="true"]').click();
      await page.keyboard.press("Control+End");
      await expect(page.getByTestId("template-card-meta")).toContainText("Ln 24");
      const gutter = await page.getByRole("list", { name: "Row bands" }).boundingBox();
      const number = await page.locator('[data-slot="template-card"] .select-none').first().boundingBox();
      for (const box of [gutter!, number!]) {
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(1440);
      }
    });

    test("1440: note array has Note focus and a clear seam check", async ({ page }, testInfo) => {
      await openEditor(page, "lobby-menu", 1440, theme);
      const focus = page.getByRole("radiogroup", { name: "Note focus" });
      await expect(focus).toBeVisible();
      await focus.getByRole("radio", { name: "Note 2" }).click();
      await expect(focus.getByRole("radio", { name: "Note 2" })).toBeChecked();
      await expect(page.locator('[data-slot="note-seam-summary"]')).toHaveText(
        "Row 3: “CAPPUCCINO” runs across the seam after column 15.",
      );
      await finish(page, testInfo, `impl-1440-${theme}-note-array`);
    });

    test("1440: hub-validated overflow card (H4)", async ({ page }, testInfo) => {
      await openEditor(page, "kitchen-morning", 1440, theme);
      const warning = page.locator('[data-slot="line-overflow-warnings"]');
      await expect(warning.getByText("Line 4", { exact: true })).toBeVisible();
      await expect(warning.getByText("24 of 22 columns · 2 cut off")).toBeVisible();
      await expect(warning.getByRole("button", { name: "Wrap line 4" })).toBeVisible();
      // BB-E-10 / 307:41698: a dashed cut marker on the preview at the cut, on row 4's last tile.
      const marker = page.getByTestId("preview-cut-marker");
      await expect(marker).toHaveCount(1);
      await expect(marker).toContainText("+2 cut off");
      const tile = page.locator('#page-editor-preview [data-row="3"][data-col="21"]').first();
      const [box, tileBox] = await Promise.all([marker.boundingBox(), tile.boundingBox()]);
      expect(Math.abs(box!.x + box!.width / 2 - (tileBox!.x + tileBox!.width / 2))).toBeLessThan(tileBox!.width);
      expect(Math.abs(box!.y - tileBox!.y)).toBeLessThan(tileBox!.height);
      await finish(page, testInfo, `impl-1440-${theme}-overflow`);
    });

    // UX-4-2 (FABLE-2651 should-fix 1): the dock opens at Fit on every geometry, so a big
    // board shows all its columns; Actual size (the dock's toggle) is for reading.
    const actualSize = (page: Page) =>
      page
        .locator('[data-slot="editor-preview"] [data-slot="board-preview-mode-toggle"]')
        .getByRole("button", { name: "Actual size" });

    for (const width of [900, 390]) {
      test(`${width}: big board opens at Fit in the docked preview, and scrolls at Actual size`, async ({
        page,
      }, testInfo) => {
        await openEditor(page, "lobby-this-week", width, theme);
        await expect(page.getByRole("group", { name: "Preview zoom" })).toHaveCount(0);
        await expect(page.getByRole("textbox", { name: "Go to row and column" })).toHaveCount(0);
        const viewport = page.locator('[data-slot="editor-preview"] [data-slot="board-viewport"]');
        await expect(viewport).toHaveAttribute("data-mode", "fit");
        await expect(indicator(page)).toContainText("Overview · 96 columns");
        await finish(page, testInfo, `impl-${width}-${theme}-big-board`);
        await actualSize(page).click();
        await expect(viewport).toHaveAttribute("data-mode", "actual");
        await expect(indicator(page)).toContainText("of 96");
      });

      test(`${width}: note array opens at Fit, and scrolls a column of Notes at a time at Actual size`, async ({
        page,
      }, testInfo) => {
        await openEditor(page, "lobby-menu", width, theme);
        await expect(page.getByRole("radiogroup", { name: "Note focus" })).toHaveCount(0);
        await expect(indicator(page)).toContainText("Overview · 4 notes");
        // At 900 the preview is the right half (UX-4-5, 61:17544), as on a phone it
        // is the screen's width: at Actual size the 2 × 2 wall scrolls a column of Notes at a time.
        await actualSize(page).click();
        await expect(indicator(page)).toContainText("Column 1 of 2");
        await finish(page, testInfo, `impl-${width}-${theme}-note-array`);
      });

      test(`${width}: Den TV 29 × 12 opens showing all 29 columns, and swipes at Actual size`, async ({
        page,
      }, testInfo) => {
        await openEditor(page, "cafe-menu", width, theme);
        await expect(page.locator('[data-slot="editor-preview"] [data-slot="board-viewport"]')).toHaveAttribute(
          "data-mode",
          "fit",
        );
        await expect(indicator(page)).toContainText("Overview · 29 columns");
        await finish(page, testInfo, `impl-${width}-${theme}-den-tv`);
        await actualSize(page).click();
        await expect(indicator(page)).toContainText(/Columns 1–\d+ of 29/);
      });
    }

    test("390: hub-validated overflow card uses touch actions (H4)", async ({ page }, testInfo) => {
      await openEditor(page, "kitchen-morning", 390, theme);
      const action = page.locator('[data-slot="line-overflow-warnings"]').getByRole("button", { name: "Wrap line 4" });
      await expect(action).toBeVisible();
      expect((await action.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      await finish(page, testInfo, `impl-390-${theme}-overflow`);
    });
  });
}
