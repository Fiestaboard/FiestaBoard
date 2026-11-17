import { expect, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

test.use({ timezoneId: "America/Los_Angeles" });

for (const width of [390, 768, 1280]) {
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
      await page.getByRole("button", { name: "Fit", exact: true }).click();
      await expect(page.getByRole("button", { name: "Fit", exact: true })).toHaveAttribute("aria-pressed", "true");
      await shot("overview-fit");
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
