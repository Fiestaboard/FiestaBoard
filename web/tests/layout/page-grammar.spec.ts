import { expect, test } from "@playwright/test";

import { measurePage } from "./page-grammar-measure";

/**
 * THE FLAT PAGE GRAMMAR (owner ruling 2026-11-21): every page is drawn on the
 * page ground, with no rounded card around its structure, and one set of
 * insets and gaps, from the 07a/07c/07d web frames:
 *
 *   width  header top             left gutter   header → content
 *   390    8 below the phone bar  16            12   (07d `320:17086`, 07c `303:16324`)
 *   900    24                     24 off rail   16   (07d `320:14392`)
 *   1440   28                     24 off rail   20   (07a `302:20841`; 07c `297:1824`, 07d `320:9461`)
 *
 * Differences of 2 px or more are bugs (BUGBASH-FIDELITY).
 */
const GRAMMAR = {
  390: { top: 8, left: 16, headerGap: 12 },
  900: { top: 24, left: 24, headerGap: 16 },
  1440: { top: 28, left: 24, headerGap: 20 },
} as const;

const ROUTES = [
  "/",
  "/pages",
  "/collections",
  "/displays",
  "/displays/kitchen",
  "/integrations",
  "/settings",
  "/picks",
];

for (const [width, want] of Object.entries(GRAMMAR)) {
  test.describe(`flat page grammar at ${width}`, () => {
    test.use({ viewport: { width: Number(width), height: Number(width) === 390 ? 844 : 900 } });
    for (const route of ROUTES) {
      test(`${route} sits on the shared insets with no page card`, async ({ page }) => {
        await page.goto(`/tests/layout/page-grammar.html?path=${encodeURIComponent(route)}`);
        await expect(page.locator("#main-content h1").first()).toBeVisible();
        const got = await measurePage(page);
        const off = (key: keyof typeof want) => Math.abs(got[key] - want[key]) >= 2;
        expect
          .soft(
            { card: got.card, top: off("top"), left: off("left"), headerGap: off("headerGap") },
            `${route} @${width}: ${JSON.stringify(got)}`,
          )
          .toEqual({ card: false, top: false, left: false, headerGap: false });
      });
    }
  });
}
