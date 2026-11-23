import { expect, type Page, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

test.use({ timezoneId: "America/Los_Angeles" });

async function settleCapture(page: Page) {
  await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all(
      document
        .getAnimations()
        .filter((animation) => Number.isFinite(animation.effect?.getComputedTiming().endTime))
        .map((animation) => animation.finished.catch(() => undefined)),
    );
    // Full-page captures must start at the document origin. Actions above can
    // scroll focused controls into view, leaving sticky chrome mid-capture.
    document.scrollingElement?.scrollTo({ top: 0, left: 0, behavior: "instant" });
    for (const element of document.querySelectorAll<HTMLElement>("*")) {
      if (!element.checkVisibility()) continue;
      const style = getComputedStyle(element);
      if (/(auto|scroll)/.test(`${style.overflowX} ${style.overflowY}`))
        element.scrollTo({ top: 0, left: 0, behavior: "instant" });
    }
    // Let ResizeObserver's scheduled measurements and React's resulting
    // layout paint after reveal/scroll, without an elapsed-time sleep.
    await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  });
}

async function expectPanelFit(page: Page) {
  const panel = page.getByTestId("display-panel-settings");
  const viewport = panel.locator('[data-slot="board-viewport"]');
  await expect(viewport).toHaveAttribute("data-mode", "fit");
  await expect
    .poll(async () =>
      viewport.evaluate((root) => {
        const scroller = root.querySelector<HTMLElement>('[data-slot="board-viewport-scroller"]');
        const board = root.querySelector<HTMLElement>('[data-slot="board-display"]');
        if (!scroller || !board) return ["Missing board or viewport"];
        const issues: string[] = [];
        const clip = scroller.getBoundingClientRect();
        const bounds = board.getBoundingClientRect();
        const style = getComputedStyle(scroller);
        const available = scroller.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
        const fittedWidth = Math.min(available, board.offsetWidth);
        if (fittedWidth <= 0 || Math.abs(bounds.width - fittedWidth) > 1)
          issues.push(`Fit width ${bounds.width}, expected ${fittedWidth}`);
        const contains = (outer: DOMRect, inner: DOMRect) =>
          inner.width > 0 &&
          inner.height > 0 &&
          inner.left >= outer.left - 1 &&
          inner.top >= outer.top - 1 &&
          inner.right <= outer.right + 1 &&
          inner.bottom <= outer.bottom + 1;
        if (!contains(clip, bounds)) issues.push("Full board extends beyond viewport");
        if (Math.abs(bounds.left + bounds.width / 2 - (clip.left + clip.width / 2)) > 1)
          issues.push("Fit board is displaced from viewport center");
        const rows = Array.from(board.querySelectorAll<HTMLElement>("[data-note-row]"));
        if (rows.length !== 12) issues.push(`Expected 12 rows, got ${rows.length}`);
        rows.forEach((row, rowIndex) => {
          const tiles = Array.from(row.querySelectorAll<HTMLElement>("[data-note-tile]"));
          if (tiles.length !== 29) issues.push(`Row ${rowIndex}: expected 29 columns, got ${tiles.length}`);
          tiles.forEach((tile, colIndex) => {
            const tileBounds = tile.getBoundingClientRect();
            if (!contains(bounds, tileBounds) || !contains(clip, tileBounds))
              issues.push(`Tile ${rowIndex},${colIndex} is clipped or empty`);
          });
        });
        return issues;
      }),
    )
    .toEqual([]);
}

for (const width of [390, 768, 900, 1280]) {
  for (const theme of ["light", "dark"]) {
    test(`Displays selection, health and scoped pause ${width} ${theme}`, async ({ page }, testInfo) => {
      test.setTimeout(90_000);
      await page.clock.install({ time: new Date("2026-11-17T02:18:00Z") });
      await page.setViewportSize({ width, height: 1000 });
      await page.emulateMedia({ reducedMotion: "reduce" });
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto(`/tests/layout/displays.html?theme=${theme}`);
      await expect(page.getByRole("list", { name: "Needs a look" })).toContainText("Can't reach");
      await expect(page.getByTestId("display-card").filter({ hasText: "Kitchen board" })).toContainText("Good night");
      await expect(
        page.getByRole("list", { name: "Needs a look" }).getByTestId("display-card").filter({ hasText: "Fridge note" }),
      ).toContainText("Out of sync");
      const entry = page.getByTestId("display-card").filter({ hasText: "Entry clock" });
      await expect(entry).toBeVisible();
      if (width < 1024) {
        const cards = page.getByTestId("display-card");
        const kitchen = cards.filter({ hasText: "Kitchen board" });
        await expect(kitchen.getByText("Then Good night", { exact: true })).toBeVisible();
        const desk = cards.filter({ hasText: "Desk Pixoo" });
        await expect(desk.getByText("Override", { exact: true })).toBeVisible();
        const expiry = desk.getByText("Holds until 9:00 PM, then Schedule resumes.", { exact: true });
        await expect(expiry).toBeVisible();
        expect(
          await expiry.evaluate(
            (element) => element.scrollWidth <= element.clientWidth && element.scrollHeight <= element.clientHeight,
          ),
        ).toBe(true);
        for (const card of await cards.all()) {
          await expect(card).toHaveAttribute("data-layout", "inline");
          const title = await card.locator('[data-slot="list-row-title"]').boundingBox();
          const meta = await card.locator('[data-slot="list-row-meta"]').boundingBox();
          const bounds = await card.boundingBox();
          expect(title).not.toBeNull();
          expect(meta).not.toBeNull();
          expect(bounds).not.toBeNull();
          expect(meta!.y).toBeLessThan(title!.y + title!.height);
          if (await card.getByText("Override", { exact: true }).count()) {
            const expiryBounds = await expiry.boundingBox();
            expect(expiryBounds).not.toBeNull();
            expect(expiryBounds!.y + expiryBounds!.height).toBeLessThanOrEqual(bounds!.y + bounds!.height);
          } else expect(bounds!.height).toBeLessThanOrEqual(80);
        }
      }
      await expect(page.getByTestId("display-detail-pane")).toHaveCount(width < 768 ? 0 : 1);
      await settleCapture(page);
      await page.screenshot({ path: testInfo.outputPath(`impl-displays-${width}-${theme}.png`), fullPage: true });
      await injectAxe(page);
      await checkA11y(page, undefined, {
        detailedReport: true,
        detailedReportOptions: { html: true },
        axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } },
      });
      const shot = async (state: string) => {
        await settleCapture(page);
        await page.screenshot({
          path: testInfo.outputPath(`impl-displays-${state}-${width}-${theme}.png`),
          fullPage: true,
        });
      };
      // On a phone the section shell's "‹ Displays" is the one way back (07d
      // `328:27519`, BB-A-19); wider screens go back through the trail, with
      // no back button stacked over the tabs (BB-FH-5).
      const backToList = () =>
        width < 768
          ? page.getByRole("main").getByRole("link", { name: "Displays", exact: true })
          : page.getByRole("navigation", { name: "Breadcrumb" }).getByRole("link", { name: "Displays", exact: true });
      await entry.click();
      if (width < 768) await expect(backToList()).toBeVisible();
      else
        await expect(
          page.getByTestId("display-detail-pane").getByRole("heading", { name: "Entry clock", exact: true }),
        ).toBeVisible();
      await shot("overview");
      // On a phone the board runs edge to edge in the phone-hero placement
      // (BB-A-19); a board that fits there draws no Fit/Actual toggle, and the
      // offline dim holds for the board alone.
      // "Entry clock" is a Flagship (22 × 6): at phone width it fits whole in
      // the phone-hero placement, edge to edge inside the viewport.
      const heroFits = width < 768;
      if (heroFits) {
        const hero = page.locator("[data-slot=board-viewport]").first();
        await expect(hero).toHaveAttribute("data-layout", "phone-hero");
        await expect(hero).toHaveAttribute("data-overflow", "false");
        const bezel = await page.locator('[data-slot="board-viewport-bezel"]').first().boundingBox();
        expect(bezel).not.toBeNull();
        expect(bezel!.x).toBeGreaterThanOrEqual(0);
        expect(bezel!.x + bezel!.width).toBeLessThanOrEqual(width);
      }
      if (heroFits) {
        await expect(page.getByRole("button", { name: "Fit", exact: true })).toHaveCount(0);
        const dim = await page
          .locator('[data-slot="last-known-board"] [data-slot="board-viewport-bezel"]')
          .evaluate((element) => {
            let opacity = 1;
            for (let node: Element | null = element; node; node = node.parentElement)
              opacity *= Number(getComputedStyle(node).opacity);
            return opacity;
          });
        expect(dim).toBe(0.6);
      } else {
        // Actual size remains the established default. Capture the user's Fit
        // overview separately for the fitted board drawn in the reference.
        const fit = page.getByRole("button", { name: "Fit", exact: true });
        await expect(fit).toBeVisible({ timeout: 10_000 });
        const fitBounds = await fit.boundingBox();
        expect(fitBounds).not.toBeNull();
        expect(fitBounds!.x).toBeGreaterThanOrEqual(0);
        expect(fitBounds!.x + fitBounds!.width).toBeLessThanOrEqual(width);
        await fit.click();
        await expect(fit).toHaveAttribute("aria-pressed", "true");
        const offlineOpacity = await page.locator('[data-slot="last-known-board"]').evaluate((root) => {
          const effectiveOpacity = (selector: string) => {
            let element = root.querySelector(selector);
            if (!element) throw new Error(`Missing offline preview element: ${selector}`);
            let opacity = 1;
            while (element) {
              opacity *= Number(getComputedStyle(element).opacity);
              element = element.parentElement;
            }
            return opacity;
          };
          return {
            board: effectiveOpacity('[data-slot="board-viewport-bezel"]'),
            fit: effectiveOpacity('[data-slot="board-preview-mode-option"][data-value="fit"]'),
            actual: effectiveOpacity('[data-slot="board-preview-mode-option"][data-value="actual"]'),
            // The kit draws the "n columns" line only while Fit is an overview
            // (tiles below the readable size). How wide the pane is decides
            // that, so the line must exist exactly when the board says so.
            overview: root.querySelector('[data-slot="board-viewport"]')?.getAttribute("data-overview") === "true",
            indicator: root.querySelector('[data-slot="board-viewport-indicator-text"]')
              ? effectiveOpacity('[data-slot="board-viewport-indicator-text"]')
              : null,
          };
        });
        // Offline imagery stays dim; controls and their explanation stay readable.
        expect(offlineOpacity).toEqual({
          board: 0.6,
          fit: 1,
          actual: 1,
          overview: offlineOpacity.overview,
          indicator: offlineOpacity.overview ? 1 : null,
        });
        await shot("overview-fit");
      }
      await checkA11y(page, undefined, {
        detailedReport: true,
        detailedReportOptions: { html: true },
        axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } },
      });
      const pause = page.getByRole("switch", { name: "Pause display", exact: true });
      await pause.click();
      await expect(pause).toBeChecked();
      await page.getByRole("button", { name: "Diagnostics", exact: true }).click();
      await expect(page.getByTestId("display-detail-pane")).toHaveCount(0);
      await expect(page.getByTestId("display-diagnostics")).toContainText("Response timed out");
      await checkA11y(page, undefined, {
        detailedReport: true,
        detailedReportOptions: { html: true },
        axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } },
      });
      await shot("diagnostics");
      // Full-width Playback and inline FiestaPanel Settings, at the same slot.
      await page.getByRole("tab", { name: "Playback", exact: true }).click();
      await expect(page.getByRole("region", { name: "Playback", exact: true })).toBeVisible();
      const transition = page.getByRole("region", { name: "Playback", exact: true }).getByTestId("display-transition");
      const selector = await transition.getByRole("combobox", { name: "Transition", exact: true }).boundingBox();
      const preview = await transition.getByTestId("transition-preview").boundingBox();
      expect(selector).not.toBeNull();
      expect(preview).not.toBeNull();
      expect(preview!.y).toBeGreaterThanOrEqual(selector!.y + selector!.height);
      const cells = await transition.locator("[data-native-strategy] > span").evaluateAll((elements) =>
        elements.map((element) => {
          const { x, y, width, height } = element.getBoundingClientRect();
          return { x, y, width, height, scrollWidth: element.scrollWidth, clientWidth: element.clientWidth };
        }),
      );
      expect(cells).toHaveLength(24);
      for (let index = 0; index < cells.length; index++) {
        const cell = cells[index];
        expect(cell.width).toBeGreaterThan(0);
        expect(cell.x).toBeGreaterThanOrEqual(preview!.x);
        expect(cell.x + cell.width).toBeLessThanOrEqual(preview!.x + preview!.width);
        expect(cell.scrollWidth).toBeLessThanOrEqual(cell.clientWidth);
        if (index % 12 > 0) expect(cell.x).toBeGreaterThanOrEqual(cells[index - 1].x + cells[index - 1].width);
      }
      await shot("playback");
      await checkA11y(page, undefined, {
        detailedReport: true,
        detailedReportOptions: { html: true },
        axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } },
      });
      await backToList().click();
      await page.getByTestId("display-card").filter({ hasText: "Fridge note" }).click();
      await page.getByRole("button", { name: "Diagnostics", exact: true }).click();
      await expect(page.getByTestId("display-detail-pane")).toHaveCount(0);
      await expect(page.getByTestId("display-frame-comparison").getByRole("img")).toHaveCount(2);
      await shot("comparison");
      await backToList().click();
      await page.getByTestId("display-card").filter({ hasText: "Living room TV" }).click();
      await page.getByRole("tab", { name: "Settings", exact: true }).click();
      await expect(page.getByTestId("display-panel-settings")).toBeVisible();
      await settleCapture(page);
      // The fixture is a 29×12 panel. A Fit caption alone does not prove its
      // hidden-tab measurements have caught up or that every tile is visible.
      // On a phone the Overview board fitted on its own (phone-hero), so the
      // session's Fit is chosen here instead.
      if (heroFits)
        await page.getByTestId("display-panel-settings").getByRole("button", { name: "Fit", exact: true }).click();
      await expectPanelFit(page);
      await shot("panel-settings");
      // Keep a truthful preview capture alongside the long page: fixed mobile
      // navigation can overlap the bottom of a full-page browser screenshot.
      await page
        .getByTestId("display-panel-settings")
        .locator('[data-slot="board-viewport"]')
        .screenshot({ path: testInfo.outputPath(`impl-displays-panel-preview-${width}-${theme}.png`) });
      await checkA11y(page, undefined, {
        detailedReport: true,
        detailedReportOptions: { html: true },
        axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } },
      });
      expect(errors).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  }
}

// A landscape phone (844 × 390) keeps the phone chrome (BB-A-13), so Displays
// keeps its phone layout too: "‹ Displays" over the display's name, no card
// header or tabs above it (07d, BB-A-19/A-24).
test("Displays on a landscape phone keeps the phone layout", async ({ page }, testInfo) => {
  await page.clock.install({ time: new Date("2026-11-17T02:18:00Z") });
  await page.setViewportSize({ width: 844, height: 390 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/tests/layout/displays.html?theme=light");
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Displays" })).toBeVisible();
  await page.getByTestId("display-card").filter({ hasText: "Entry clock" }).click();
  await expect(main.getByRole("link", { name: "Displays", exact: true })).toBeVisible();
  await expect(main.getByRole("heading", { level: 1, name: "Entry clock" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toHaveCount(0);
  await settleCapture(page);
  await page.screenshot({ path: testInfo.outputPath("impl-displays-landscape-844x390.png"), fullPage: true });
});
