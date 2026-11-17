import { getViolations, injectAxe } from "axe-playwright";

import { configureBoard, expect, suppressWizard, test } from "../helpers";

const sections = [
  ["network", "Network"],
  ["language-time", "Language & time"],
  ["system", "System & backups"],
  ["ai-provider", "AI provider"],
  ["fiestabot", "FiestaBot"],
  ["appearance", "Appearance"],
  ["accessibility", "Accessibility"],
] as const;

for (const width of [390, 768, 1280]) {
  for (const theme of ["light", "dark"] as const) {
    test(`Settings sections fit ${width}px in ${theme}`, async ({ page }, testInfo) => {
      test.setTimeout(120_000);
      await configureBoard();
      await suppressWizard(page);
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
      for (const [section, title] of sections) {
        await page.goto(`/settings/${section}`);
        const detail = page.getByRole("region", { name: title, exact: true });
        await expect(detail).toBeVisible();
        await expect(detail.locator('[data-slot="skeleton"]')).toHaveCount(0);
        if (width < 768) {
          await expect(page.getByRole("link", { name: "Settings", exact: true })).toHaveAttribute("href", "/settings");
          await expect(page.locator('[data-slot="settings-index"]')).toHaveCount(0);
        } else {
          await expect(page.getByRole("link", { name: title, exact: true })).toHaveAttribute("aria-current", "page");
        }
        // Classic vertical scrollbars reduce the content viewport. Assert no
        // horizontal overflow against that viewport rather than window width.
        await expect
          .poll(() =>
            page.evaluate(
              () =>
                Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) -
                document.documentElement.clientWidth,
            ),
          )
          .toBeLessThanOrEqual(0);
        await injectAxe(page);
        const violations = await getViolations(page, '[data-slot="settings-detail"]', {
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
          // axe disables this WCAG 2.2 AA rule by default; browser layout is available here.
          rules: { "target-size": { enabled: true } },
        });
        expect(violations).toEqual([]);
        await page.screenshot({
          path: testInfo.outputPath(`impl-settings-${section}-${width}-${theme}.png`),
          fullPage: true,
        });
      }
    });
  }
}
