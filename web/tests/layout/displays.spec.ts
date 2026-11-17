import { expect, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

for (const width of [390, 768, 1280]) {
  for (const theme of ["light", "dark"]) {
    test(`Displays selection, health and scoped pause ${width} ${theme}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(`/tests/layout/displays.html?theme=${theme}`);
      await expect(page.getByRole("list", { name: "Needs a look" })).toContainText("Can't reach");
      const entry = page.getByTestId("display-card").filter({ hasText: "Entry clock" });
      await expect(entry).toBeVisible();
      await expect(page.getByTestId("display-detail-pane")).toHaveCount(width < 768 ? 0 : 1);
      await page.screenshot({ path: testInfo.outputPath(`impl-displays-${width}-${theme}.png`), fullPage: true });
      await injectAxe(page);
      await checkA11y(page, undefined, {
        axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } },
      });
      await entry.click();
      if (width < 768) await expect(page.getByRole("link", { name: "Back to Displays" })).toBeVisible();
      else
        await expect(
          page.getByTestId("display-detail-pane").getByRole("heading", { name: "Entry clock", exact: true }),
        ).toBeVisible();
      const pause = page.getByRole("switch", { name: "Pause display", exact: true });
      await pause.click();
      await expect(pause).toBeChecked();
      await page.getByRole("button", { name: "Diagnostics", exact: true }).click();
      await expect(page.getByTestId("display-diagnostics")).toContainText("Response timed out");
      await checkA11y(page, undefined, {
        axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } },
      });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  }
}
