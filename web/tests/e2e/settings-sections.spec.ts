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
      await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((value) => localStorage.setItem("theme", value), theme);
      for (const [section, title] of sections) {
        await page.goto(`/settings/${section}`);
        const detail = page.getByRole("region", { name: title, exact: true });
        await expect(detail).toBeVisible();
        await expect(detail.locator('[data-slot="skeleton"]')).toHaveCount(0);
        await expect
          .poll(() => page.locator("html").evaluate((html) => html.classList.contains("dark")))
          .toBe(theme === "dark");
        // Visibility can precede the kit's header and outlet entrance fades.
        // Audit final colors and capture the settled shell at each destination.
        await page.evaluate(async () => {
          await document.fonts.ready;
          const finiteAnimations = document
            .getAnimations()
            .filter((animation) => Number.isFinite(animation.effect?.getComputedTiming().endTime ?? Infinity));
          await Promise.all(finiteAnimations.map((animation) => animation.finished.catch(() => {})));
        });
        await expect
          .poll(() =>
            detail.evaluate((element) => {
              let opacity = 1;
              for (let node: Element | null = element; node; node = node.parentElement) {
                opacity *= Number(getComputedStyle(node).opacity);
              }
              return opacity;
            }),
          )
          .toBe(1);
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
        expect(
          violations,
          `Settings ${section} ${width} ${theme} violations:\n${JSON.stringify(violations, null, 2)}`,
        ).toEqual([]);
        await page.screenshot({
          path: testInfo.outputPath(`impl-settings-${section}-${width}-${theme}.png`),
          fullPage: true,
          animations: "disabled",
        });
      }
    });
  }
}
