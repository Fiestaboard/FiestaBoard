import { FIESTA_LOGO_WORDMARK_SELECTOR } from "@fiestaboard/ui";
import type { Page } from "@playwright/test";
import { checkA11y, configureAxe } from "axe-playwright";

export async function checkSetupA11y(page: Page) {
  // FiestaUI intentionally uses its brand wordmark token (theme.css). WCAG
  // 1.4.3 exempts logotypes: https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html
  // Preserve every other rule on that span, and contrast on every other node.
  // The kit names the one selector a contrast audit may exempt (BB-C-25).
  await configureAxe(page, {
    rules: [{ id: "color-contrast", selector: `*:not(${FIESTA_LOGO_WORDMARK_SELECTOR})` }],
  });
  await checkA11y(page, undefined, {
    detailedReport: true,
    detailedReportOptions: { html: true },
    axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } },
  });
}
