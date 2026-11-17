import { expect, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

test.use({ timezoneId: "America/Los_Angeles" });

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
        await expect(cards.filter({ hasText: "Desk Pixoo" }).getByText("Override", { exact: true })).toBeVisible();
        for (const card of await cards.all()) {
          await expect(card).toHaveAttribute("data-layout", "inline");
          const title = await card.locator('[data-slot="list-row-title"]').boundingBox();
          const meta = await card.locator('[data-slot="list-row-meta"]').boundingBox();
          const bounds = await card.boundingBox();
          expect(title).not.toBeNull();
          expect(meta).not.toBeNull();
          expect(bounds).not.toBeNull();
          expect(meta!.y).toBeLessThan(title!.y + title!.height);
          expect(bounds!.height).toBeLessThanOrEqual(80);
        }
      }
      await expect(page.getByTestId("display-detail-pane")).toHaveCount(width < 768 ? 0 : 1);
      await page.screenshot({ path: testInfo.outputPath(`impl-displays-${width}-${theme}.png`), fullPage: true });
      await injectAxe(page);
      await checkA11y(page, undefined, {
        detailedReport: true,
        detailedReportOptions: { html: true },
        axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } },
      });
      const shot = async (state: string) => {
        await page.screenshot({
          path: testInfo.outputPath(`impl-displays-${state}-${width}-${theme}.png`),
          fullPage: true,
        });
      };
      await entry.click();
      if (width < 768) await expect(page.getByRole("link", { name: "Back to Displays" })).toBeVisible();
      else
        await expect(
          page.getByTestId("display-detail-pane").getByRole("heading", { name: "Entry clock", exact: true }),
        ).toBeVisible();
      await shot("overview");
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
          indicator: effectiveOpacity('[data-slot="board-viewport-indicator-text"]'),
        };
      });
      // Offline imagery stays dim; controls and their explanation stay readable.
      expect(offlineOpacity).toEqual({ board: 0.6, fit: 1, actual: 1, indicator: 1 });
      await shot("overview-fit");
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
      await page.getByRole("link", { name: "Back to Displays" }).click();
      await page.getByTestId("display-card").filter({ hasText: "Fridge note" }).click();
      await page.getByRole("button", { name: "Diagnostics", exact: true }).click();
      await expect(page.getByTestId("display-detail-pane")).toHaveCount(0);
      await expect(page.getByTestId("display-frame-comparison").getByRole("img")).toHaveCount(2);
      await shot("comparison");
      await page.getByRole("link", { name: "Back to Displays" }).click();
      await page.getByTestId("display-card").filter({ hasText: "Living room TV" }).click();
      await page.getByRole("tab", { name: "Settings", exact: true }).click();
      await expect(page.getByTestId("display-panel-settings")).toBeVisible();
      await shot("panel-settings");
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
