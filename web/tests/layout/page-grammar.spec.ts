import { expect, type Page, test } from "@playwright/test";

import { measurePage } from "./page-grammar-measure";

/**
 * THE FLAT PAGE GRAMMAR (owner ruling 2026-11-21): every page is drawn on the
 * page ground, with no rounded card around its structure, and one set of
 * insets and gaps, from the 07a/07c/07d web frames:
 *
 *   width  header top             left gutter   header → content
 *   390    8 below the phone bar  16            12   (07d `320:17086`, 07c `303:16324`)
 *   900    24                     16 off rail   16   (07a `307:61756`: rail x 8-72, main x 88; the older 07d
 *                                                    frames still draw the 12 px rail inset BB-FS-8 replaced)
 *   1440   28                     24 off rail   20   (07a `302:20841`; 07c `297:1824`, 07d `320:9461`)
 *
 * Differences of 2 px or more are bugs (BUGBASH-FIDELITY).
 */
const GRAMMAR = {
  390: { top: 8, left: 16, headerGap: 12 },
  900: { top: 24, left: 16, headerGap: 16 },
  1440: { top: 28, left: 24, headerGap: 20 },
} as const;

const ROUTES = [
  "/",
  "/pages",
  "/collections",
  "/displays",
  "/displays/kitchen",
  "/integrations",
  "/schedule",
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

/** The gap between two boxes, top-to-bottom, and how far the second's left edge sits from the first's. */
async function between(page: Page, above: string, below: string) {
  return page.evaluate(
    ([a, b]) => {
      const visible = (sel: string) =>
        Array.from(document.querySelectorAll<HTMLElement>(sel)).find((el) => el.getBoundingClientRect().height > 0)!;
      const [ra, rb] = [visible(a).getBoundingClientRect(), visible(b).getBoundingClientRect()];
      return { gap: Math.round(rb.top - ra.bottom), dx: Math.round(rb.left - ra.left) };
    },
    [above, below],
  );
}

for (const [width, want] of Object.entries(GRAMMAR)) {
  test.describe(`one gap between the page's blocks at ${width}`, () => {
    test.use({ viewport: { width: Number(width), height: Number(width) === 390 ? 844 : 900 } });
    const gap = { 390: 12, 900: 16, 1440: 20 }[width]!;
    const open = async (page: Page, path: string) => {
      await page.goto(`/tests/layout/page-grammar.html?${path}`);
      await expect(page.locator("#main-content h1").first()).toBeVisible();
      await measurePage(page); // settles fonts and animations
    };

    test("Pages: toolbar, toolbar, then the library", async ({ page }) => {
      await open(page, "path=/pages");
      const toolbars = "#main-content [data-slot=page-toolbar]";
      const first = await between(
        page,
        `${toolbars}:nth-child(1 of [data-slot=page-toolbar])`,
        `${toolbars}:nth-child(2 of [data-slot=page-toolbar])`,
      );
      const last = await between(
        page,
        `${toolbars}:nth-child(2 of [data-slot=page-toolbar])`,
        "#main-content [data-slot=page-section]",
      );
      expect({ first, last }).toEqual({ first: { gap, dx: 0 }, last: { gap, dx: 0 } });
    });

    test("a display's Playback cards sit one gap under the tabs, on the tabs' gutter (07d 320:18175)", async ({
      page,
    }) => {
      await open(page, `path=${encodeURIComponent("/displays/kitchen?section=playback")}`);
      const region = page.getByRole("region", { name: "Playback" });
      await expect(region).toBeVisible();
      const got = await between(
        page,
        "#main-content [role=tablist]",
        "#main-content [role=region][aria-label=Playback] [data-slot=card]",
      );
      expect(got).toEqual({ gap, dx: 0 });
    });

    test("Settings: the update banner keeps one gap above the settings", async ({ page }) => {
      await open(page, `path=/settings&update=1`);
      await expect(page.getByText("11.1.0").first()).toBeVisible();
      const got = await between(
        page,
        "#main-content [data-slot=page-section]",
        "#main-content [data-slot=settings-columns]",
      );
      expect(got.gap).toBe(gap);
    });
  });
}
