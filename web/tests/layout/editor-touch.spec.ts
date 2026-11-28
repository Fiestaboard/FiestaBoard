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

async function mockEditorApi(page: Page, drawingSource: "profile" | "baseline" = "profile") {
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
          max_lengths: { "weather.temperature": 3, "datetime.time": 5 },
          colors: { red: 63, orange: 64, yellow: 65, green: 66, blue: 67, violet: 68, white: 69, black: 70 },
          formatting: {
            fill_space: { syntax: "{{fill_space}}", description: "Fill the remaining line width" },
          },
        };
      } else if (pathname === "/templates/validate") {
        // 2.9: the editor's real-width overflow check (H4); nothing overflows here.
        response = { valid: true, errors: [], rows: 6, cols: 22 };
      } else if (pathname === "/templates/render" || pathname === "/templates/render/live") {
        const request = route.request().postDataJSON() as { template: string | string[] };
        const template = Array.isArray(request.template) ? request.template.join("\n") : request.template;
        const rendered = template
          .replaceAll("{{weather.temperature}}", "72")
          .replaceAll("{{datetime.time}}", "7:30 AM");
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
        page.on("pageerror", (error) => console.error("Editor fixture page error:", error.message));
        const shots = process.env.EDITOR_TOUCH_SHOTS || testInfo.outputPath("editor-touch-shots");
        if (process.env.EDITOR_TOUCH_DEBUG) {
          page.on("console", (message) => console.log("browser-console", message.type(), message.text()));
          page.on("requestfailed", (request) => console.log("request-failed", request.url(), request.failure()));
          page.on("response", (response) => {
            if (response.status() >= 400) console.log("bad-response", response.status(), response.url());
          });
        }
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
        if (width === 390) {
          const header = page.locator('[data-slot="card-header"]').first();
          const headerBounds = await header.boundingBox();
          const previewBounds = await preview.boundingBox();
          const viewport = preview.locator('[data-slot="board-viewport"]');
          if (process.env.EDITOR_TOUCH_DEBUG)
            console.log("phone-header-preview", {
              headerBounds,
              previewBounds,
              mode: await viewport.getAttribute("data-mode"),
              overflow: await viewport.getAttribute("data-overflow"),
              metrics: await viewport.evaluate((element) => {
                const scroller = element.querySelector('[data-slot="board-viewport-scroller"]')!;
                const board = element.querySelector('[data-slot="board-display"]')!;
                const tile = board.querySelector("[data-note-tile]")!;
                return {
                  documentWidth: document.documentElement.clientWidth,
                  viewportWidth: element.clientWidth,
                  scrollerWidth: scroller.clientWidth,
                  scrollWidth: scroller.scrollWidth,
                  boardWidth: board.getBoundingClientRect().width,
                  tileWidth: tile.getBoundingClientRect().width,
                  tileCss: getComputedStyle(tile).width,
                  boardStyle: (board as HTMLElement).style.cssText,
                };
              }),
            });
          expect.soft(headerBounds!.height).toBeLessThanOrEqual(64);
          expect.soft(Math.abs(previewBounds!.y - (headerBounds!.y + headerBounds!.height))).toBeLessThanOrEqual(8);
          // Fit by default on every geometry (UX-4-2, FABLE-2651 should-fix 1); a Flagship
          // at 390 fits either way (57:64661 draws Actual, where the two coincide).
          await expect.soft(viewport).toHaveAttribute("data-mode", "fit");
          await expect.soft(viewport).toHaveAttribute("data-overflow", "false");
          const scroller = viewport.locator('[data-slot="board-viewport-scroller"]');
          expect.soft(await scroller.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
        }

        // Fit / Actual (BB-E-5, 307:46094): the header's when it has the row to
        // itself, otherwise the viewport's own, drawn while the board overflows.
        // Either way it is there whenever the board does not fit.
        const toggles = await preview.locator('[data-slot="board-preview-mode-toggle"]').count();
        const overflows =
          (await preview.locator('[data-slot="board-viewport"]').getAttribute("data-overflow")) === "true";
        expect(toggles).toBeLessThanOrEqual(1);
        if (overflows) expect(toggles).toBe(1);
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
        if (touch) {
          const geometry = await touchToolbar.evaluate((element) => {
            const rect = element.getBoundingClientRect();
            const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
            const ancestors = [];
            for (let ancestor = element.parentElement; ancestor; ancestor = ancestor.parentElement) {
              const style = getComputedStyle(ancestor);
              ancestors.push({
                tag: ancestor.tagName,
                class: ancestor.className,
                overflow: style.overflow,
                transform: style.transform,
                contain: style.contain,
                filter: style.filter,
              });
            }
            return {
              x: rect.x,
              y: rect.y,
              width: rect.width,
              height: rect.height,
              hit: !!hit && element.contains(hit),
              ancestors,
            };
          });
          if (process.env.EDITOR_TOUCH_DEBUG) console.log("touch-toolbar-geometry", JSON.stringify(geometry));
          expect(geometry.x).toBeGreaterThanOrEqual(0);
          expect(geometry.y).toBeGreaterThanOrEqual(0);
          expect(geometry.x + geometry.width).toBeLessThanOrEqual(width);
          expect(geometry.y + geometry.height).toBeLessThanOrEqual(900);
          expect(geometry.height).toBeGreaterThanOrEqual(44);
          expect(geometry.hit).toBe(true);
        }

        await page.screenshot({ path: path.join(shots, `impl-${width}-${theme}.png`) });

        if (touch) {
          await page.getByRole("button", { name: "More", exact: true }).click();
          const sheet =
            width < 640
              ? page.getByRole("dialog", { name: "More", exact: true })
              : page.getByTestId("toolbar-dropdown-panel");
          await expect(sheet).toBeVisible();
          await expect(sheet.getByRole("switch", { name: "Mirror to board while editing", exact: true })).toBeVisible();
          await expect(sheet.getByRole("group", { name: "Clipboard", exact: true })).toBeVisible();
          await checkA11y(page, width < 640 ? '[role="dialog"]' : '[data-testid="toolbar-dropdown-panel"]');
          const sheetBounds = await sheet.boundingBox();
          if (process.env.EDITOR_TOUCH_DEBUG)
            console.log(
              "more-geometry",
              sheetBounds,
              await sheet.evaluate((element) => ({
                transform: getComputedStyle(element).transform,
                inlineTransform: (element as HTMLElement).style.transform,
              })),
            );
          expect(sheetBounds!.x).toBeGreaterThanOrEqual(0);
          const paintRight =
            width < 640
              ? width
              : await touchToolbar.evaluate(
                  (element) =>
                    Math.min(element.getBoundingClientRect().right, document.body.getBoundingClientRect().right) - 8,
                );
          expect(sheetBounds!.x + sheetBounds!.width).toBeLessThanOrEqual(paintRight);
          expect(sheetBounds!.y).toBeGreaterThanOrEqual(0);
          expect(sheetBounds!.y + sheetBounds!.height).toBeLessThanOrEqual(900);
          expect(await sheet.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
          for (const control of await sheet.getByRole("switch").all()) {
            expect(
              await control.evaluate((element) => {
                const bounds = element.getBoundingClientRect();
                const hit = document.elementFromPoint(bounds.right - 2, bounds.y + bounds.height / 2);
                return !!hit && element.contains(hit);
              }),
            ).toBe(true);
          }
          for (const name of ["Cut", "Copy", "Paste"]) {
            const bounds = await sheet.getByRole("button", { name, exact: true }).boundingBox();
            expect(bounds!.x).toBeGreaterThanOrEqual(sheetBounds!.x);
            expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(sheetBounds!.x + sheetBounds!.width);
          }
          await page.screenshot({ path: path.join(shots, `impl-${width}-${theme}-more.png`) });
        }
      });
    });
  }
}

async function openFinePointerMore(page: Page) {
  await page.setViewportSize({ width: 900, height: 900 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockEditorApi(page);
  await page.goto("/tests/layout/editor-touch.html?theme=light");
  await expect(page.getByRole("textbox", { name: /page name/i })).toHaveValue("Kitchen morning");
  // The lazy rich editor mounts its toolbar above the docked preview, moving
  // the More trigger down. Open More only once the editor is in place: the
  // anchored panel does not follow a trigger that moves after it opened, so a
  // late mount repositioned it (and the nested menu) between mousedown and
  // mouseup on a slow runner.
  await expect(page.locator('[contenteditable="true"]')).toBeVisible();
  await page.getByRole("button", { name: "More", exact: true }).click();
  const popup = page.getByTestId("toolbar-dropdown-panel");
  await expect(popup).toBeVisible();
  return popup;
}

async function clickThroughMouseDown(page: Page, button: ReturnType<Page["getByRole"]>) {
  await button.hover();
  const bounds = await button.boundingBox();
  await page.mouse.move(bounds!.x + bounds!.width / 2, bounds!.y + bounds!.height / 2);
  await page.mouse.down();
  // A parent outside-click handler must not unmount a nested portal at mousedown.
  await expect(button).toBeVisible();
  await page.mouse.up();
}

test.describe("900px fine-pointer nested More actions", () => {
  test.use({ hasTouch: false });
  test("selects a portaled transition without dismissing its parent before mousedown", async ({ page }) => {
    const popup = await openFinePointerMore(page);
    const transition = popup.getByRole("button", { name: "Page transition", exact: true });
    await expect(transition.locator('span[aria-hidden="true"].bg-brand')).toHaveCount(0);
    // Baseline once the panel's own enter transition has settled.
    await popup.evaluate((el) => Promise.all(el.getAnimations({ subtree: true }).map((a) => a.finished)));
    const panelTop = (await popup.boundingBox())!.y;
    await transition.click();
    const option = page.getByRole("menuitemradio", { name: "Wave", exact: true });
    await expect(option).toBeVisible();
    // Regression: nothing may shift the open panel (and its nested menu) under the pointer.
    await page.waitForTimeout(400);
    expect((await popup.boundingBox())!.y).toBe(panelTop);
    await clickThroughMouseDown(page, option);
    await expect(option).toBeHidden();
    await expect(popup).toBeVisible();
    await expect(transition.locator('span[aria-hidden="true"].bg-brand')).toBeVisible();
    await transition.click();
    await expect(page.getByRole("menuitemradio", { name: "Wave", exact: true })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  test("keeps portaled Delete confirmation mounted through Cancel and confirmed mousedown", async ({ page }) => {
    const deletes: string[] = [];
    page.on("request", (request) => {
      if (request.method() === "DELETE") deletes.push(request.url());
    });
    const popup = await openFinePointerMore(page);
    const openDelete = async () => {
      await popup.getByRole("button", { name: "Delete page", exact: true }).click();
      // UX-8-4: the dialog names the page.
      const dialog = page.getByRole("alertdialog", { name: /^Delete “.+”\?$/ });
      await expect(dialog).toBeVisible();
      return dialog;
    };
    const cancelled = await openDelete();
    await clickThroughMouseDown(page, cancelled.getByRole("button", { name: "Cancel", exact: true }));
    await expect(cancelled).toBeHidden();
    expect(deletes).toHaveLength(0);
    // The confirmation is the editor's own dialog now (D6: the desktop opens it
    // from the Inspector), so More closes behind it; open it again.
    await expect(popup).toBeHidden();
    await page.getByRole("button", { name: "More", exact: true }).click();
    await expect(popup).toBeVisible();
    const confirmed = await openDelete();
    await clickThroughMouseDown(page, confirmed.getByRole("button", { name: "Delete page", exact: true }));
    await expect.poll(() => deletes.length).toBe(1);
    const url = new URL(deletes[0]);
    expect(url.pathname).toBe("/api/v1/pages/kitchen-morning");
    expect(url.searchParams.get("expected_revision")).toBe("1");
    await expect(confirmed).toBeHidden();
  });
});

for (const { width, coarse } of [
  { width: 640, coarse: false },
  { width: 767, coarse: false },
  { width: 1180, coarse: true },
]) {
  test.describe(`H3 More at ${width}px ${coarse ? "coarse" : "fine"} pointer`, () => {
    test.use({ hasTouch: coarse });
    test("opens above the toolbar within the viewport and preserves mirroring and dismissal focus", async ({
      page,
    }, testInfo) => {
      const height = 900;
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ reducedMotion: "reduce" });
      await mockEditorApi(page, "baseline");
      await page.goto("/tests/layout/editor-touch.html?theme=light");
      await expect(page.getByRole("textbox", { name: /page name/i })).toHaveValue("Kitchen morning");
      await expect(page.getByText("Can’t tell what this display draws", { exact: true })).toBeVisible();
      await expect(page.locator('[data-slot="board-preview-mode-toggle"]')).toHaveCount(0);
      expect(await page.evaluate(() => matchMedia("(pointer: coarse)").matches)).toBe(coarse);

      const toolbar = page.locator('[data-slot="editor-toolbar"][data-size="touch"][data-capabilities="plain-text"]');
      await expect(toolbar).toBeVisible();
      await expect(toolbar.getByRole("button", { name: "Colors", exact: true })).toBeDisabled();
      await expect(toolbar.getByRole("button", { name: "Spacing", exact: true })).toBeDisabled();
      const trigger = toolbar.getByRole("button", { name: "More", exact: true });
      await trigger.click();
      const popup = page.getByTestId("toolbar-dropdown-panel");
      await expect(popup).toBeVisible();
      await expect(popup).toHaveAttribute("data-slot", "popover-content");
      await expect(popup).toHaveAttribute("data-side", "top");
      expect(await popup.evaluate((element) => element.closest('[data-slot="editor-toolbar"]') === null)).toBe(true);

      await expect
        .poll(async () => {
          const popupBounds = await popup.boundingBox();
          const toolbarBounds = await toolbar.boundingBox();
          return !!popupBounds && !!toolbarBounds && popupBounds.y + popupBounds.height <= toolbarBounds.y + 1;
        })
        .toBe(true);
      const popupBounds = await popup.boundingBox();
      expect(popupBounds!.x).toBeGreaterThanOrEqual(0);
      expect(popupBounds!.y).toBeGreaterThanOrEqual(0);
      expect(popupBounds!.x + popupBounds!.width).toBeLessThanOrEqual(width);
      expect(popupBounds!.y + popupBounds!.height).toBeLessThanOrEqual(height);
      expect(await popup.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

      const mirror = popup.getByRole("switch", { name: "Mirror to board while editing", exact: true });
      await expect(mirror).not.toBeChecked();
      await mirror.click();
      await expect(mirror).toBeChecked();
      if (width < 1024) await expect(page.getByText("Mirroring", { exact: true })).toBeVisible();
      else
        await expect(
          page
            .locator('[data-slot="editor-preview-live"]')
            .getByRole("switch", { name: "Mirror to board while editing" }),
        ).toBeChecked();
      await page.evaluate(() => document.fonts.ready);
      await injectAxe(page);
      // The body-level toolbar and popup must be included in the scan.
      await checkA11y(page);
      const shots = process.env.EDITOR_TOUCH_SHOTS || testInfo.outputPath("editor-touch-shots");
      await mkdir(shots, { recursive: true });
      await page.screenshot({ path: path.join(shots, `impl-h3-${width}-${coarse ? "coarse" : "fine"}-more.png`) });

      await mirror.press("Escape");
      await expect(popup).toBeHidden();
      await expect(trigger).toBeFocused();
      await trigger.click();
      await expect(popup).toBeVisible();
      await expect(popup.getByRole("switch", { name: "Mirror to board while editing", exact: true })).toBeChecked();
      await popup.getByRole("switch", { name: "Mirror to board while editing", exact: true }).click();
      await expect(popup.getByRole("switch", { name: "Mirror to board while editing", exact: true })).not.toBeChecked();
      await page.keyboard.press("Escape");
      await expect(trigger).toBeFocused();
      await checkA11y(page);
    });
  });
}

test.describe("1280px template field (BB-E-8, BB-E-16)", () => {
  const colors = ["red", "orange", "yellow", "green", "blue", "violet"];
  // More tiles than the card is wide, so a break opportunity between tiles shows.
  const longTileRow = Array.from({ length: 66 }, (_, i) => `{{${colors[i % 6]}}}`).join("");

  async function openTemplate(page: Page, template: string[]) {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mockEditorApi(page);
    await page.route(
      (url) => url.pathname === `/api/v1/pages/${kitchenMorning.id}`,
      (route) => route.fulfill({ json: { ...kitchenMorning, template } }),
    );
    await page.goto("/tests/layout/editor-touch.html?theme=light");
    await expect(page.locator('[contenteditable="true"]')).toBeVisible();
  }

  // W-6 (DD-W170): a long row soft-wraps at the card's width, Docs-style, with a
  // wrap glyph in the gutter; nothing scrolls the other rows out of view, and
  // nothing is painted past the card (BB-E-8).
  test("a row of tiles wraps inside the card, marked in the gutter", async ({ page }) => {
    await openTemplate(page, [longTileRow, "", "", "", "", ""]);
    const chips = page.locator(".ProseMirror .react-renderer");
    await expect(chips).toHaveCount(66);
    const card = (await page.locator('[data-slot="template-card"]').boundingBox())!;
    const rights = await chips.evaluateAll((els) => els.map((e) => e.getBoundingClientRect().right));
    expect(Math.max(...rights)).toBeLessThanOrEqual(card.x + card.width);
    await expect(page.getByTestId("template-row-wraps")).toHaveCount(1);
  });

  test("with the caret at column 86 every other row still shows its text", async ({ page }) => {
    const long = "A REALLY LONG LINE AT THE BOTTOM THAT RUNS WELL PAST THE RIGHT EDGE OF THE PANEL GRID!";
    expect(long.length).toBe(86);
    // Rows 2 and 4 carry chips: a chip makes a row a little taller, which is not a wrap.
    await openTemplate(page, [
      "ROW ONE",
      "ROW TWO {{weather.temperature}}",
      "ROW THREE",
      'ROW FOUR {{= IF(weather.temperature > 80, "HOT", "NICE") }}',
      "ROW FIVE",
      long,
    ]);
    await page.locator('[contenteditable="true"]').click();
    await page.keyboard.press("Control+End");
    await expect(page.getByTestId("template-card-meta")).toContainText("Ln 6, Col 87");
    const rows = page.locator('[data-slot="template-rows"]');
    expect(await rows.evaluate((el) => el.scrollLeft)).toBe(0);
    expect(await rows.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
    const box = (await rows.boundingBox())!;
    for (const text of ["ROW ONE", "ROW TWO", "ROW THREE", "ROW FOUR", "ROW FIVE"]) {
      const first = await page.evaluate((needle) => {
        const p = document.querySelector(".ProseMirror p")!;
        const walker = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
        let node: Node | null;
        while ((node = walker.nextNode())) {
          const at = node.textContent!.indexOf(needle);
          if (at < 0) continue;
          const range = document.createRange();
          range.setStart(node, at);
          range.setEnd(node, at + 1);
          return range.getBoundingClientRect().toJSON() as DOMRect;
        }
        return null;
      }, text);
      expect(first, text).not.toBeNull();
      expect(first!.left).toBeGreaterThanOrEqual(box.x);
      expect(first!.right).toBeLessThanOrEqual(box.x + box.width);
    }
    await expect(page.getByTestId("template-row-wraps")).toHaveCount(1);
    // Nothing of the template is painted right of the card.
    const card = (await page.locator('[data-slot="template-card"]').boundingBox())!;
    const outside = await page.evaluate(({ x, y }) => !!document.elementFromPoint(x, y)?.closest(".ProseMirror"), {
      x: card.x + card.width + 12,
      y: box.y + 12,
    });
    expect(outside).toBe(false);
  });

  // W-7: squeezed, the card header drops the line count, never the caret.
  test("a narrow template card keeps the caret and drops the line count", async ({ page }) => {
    await openTemplate(page, kitchenMorning.template);
    const meta = page.getByTestId("template-card-meta");
    const caret = page.getByTestId("template-caret");
    const lines = page.getByTestId("template-line-count");
    const shown = (locator: typeof meta) =>
      locator.evaluate((el) => {
        const r = el.getBoundingClientRect();
        const m = el.closest('[data-testid="template-card-meta"]')!.getBoundingClientRect();
        return (
          r.width > 0 &&
          r.top >= m.top - 1 &&
          r.bottom <= m.bottom + 1 &&
          r.left >= m.left - 1 &&
          r.right <= m.right + 1
        );
      });
    expect(await shown(caret)).toBe(true);
    expect(await shown(lines)).toBe(true);
    // Squeeze the card as the Explorer or a 1024 px window does.
    await page.locator('[data-slot="template-card"]').evaluate((el) => {
      (el as HTMLElement).style.width = "300px";
    });
    await expect.poll(() => shown(lines)).toBe(false);
    expect(await shown(caret)).toBe(true);
    // Dropped, not ellipsised.
    expect(await meta.evaluate((el) => getComputedStyle(el).textOverflow)).not.toBe("ellipsis");
  });

  test("the template card shows a focus ring while the template has focus", async ({ page }) => {
    await openTemplate(page, kitchenMorning.template);
    const card = page.locator('[data-slot="template-card"]');
    const before = await card.evaluate((el) => getComputedStyle(el).boxShadow);
    await page.locator('[contenteditable="true"]').click();
    await expect.poll(() => card.evaluate((el) => getComputedStyle(el).boxShadow)).not.toBe(before);
  });
});
