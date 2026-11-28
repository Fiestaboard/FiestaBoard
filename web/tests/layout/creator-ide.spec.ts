import { mkdir } from "node:fs/promises";
import path from "node:path";

import { expect, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

import { mockHub } from "./creator-ide-hub";

// Web 2.11 Creator IDE (Figma 04d 4.3 `184:159319`). Desktop (>= 1024 px):
// Explorer, five Inspector tabs, Problems | Warnings | Sent docked console,
// week timeline. Below 1024 px: Problems is the sixth tab (Jev
// desktop_console_two_option). Every hub response is mocked here.

for (const theme of ["light", "dark"] as const) {
  for (const width of [390, 900, 1440]) {
    test.describe(`${width}px in ${theme}`, () => {
      test("Creator IDE regions follow the 04d breakpoints and pass axe", async ({ page }, testInfo) => {
        page.on("pageerror", (error) => console.error("Creator IDE fixture page error:", error.message));
        const shots = process.env.CREATOR_IDE_SHOTS || testInfo.outputPath("creator-ide-shots");
        await page.setViewportSize({ width, height: 900 });
        await page.emulateMedia({ reducedMotion: "reduce" });
        await mockHub(page);
        await page.goto(`/tests/layout/creator-ide.html?theme=${theme}`);
        await expect(page.getByRole("textbox", { name: /page name/i })).toHaveValue("Kitchen morning");
        const ide = page.locator('[data-slot="creator-ide"]');
        await expect(ide).toBeVisible();
        const desktop = width >= 1024;
        await expect(ide).toHaveAttribute("data-layout", desktop ? "desktop" : "compact");

        const inspector = page.getByRole("tablist", { name: "Inspector" });
        await expect(inspector.getByRole("tab")).toHaveCount(desktop ? 5 : 6);
        await expect(page.getByText(/Showing on Kitchen board now · until 8:30/)).toBeVisible();
        // Live: the header offers Save draft beside Save & update board (04d decision 4).
        await expect(page.getByRole("button", { name: "Save draft" })).toBeVisible();
        await expect(page.getByRole("button", { name: "Save & update board" })).toBeVisible();
        // The page name keeps usable room beside the header actions, and they stay on screen.
        const nameBox = await page.getByRole("textbox", { name: /page name/i }).boundingBox();
        expect(nameBox!.width).toBeGreaterThanOrEqual(width < 640 ? 56 : 200);
        const publishBox = await page.getByRole("button", { name: "Save & update board" }).boundingBox();
        expect(publishBox!.x + publishBox!.width).toBeLessThanOrEqual(width);

        if (desktop) {
          // A Flagship page opens with the Explorer closed (D2); it opens on request.
          await expect(page.getByRole("navigation", { name: "Explorer" })).toHaveCount(0);
          await page.getByRole("button", { name: "Show Explorer" }).click();
          await expect(page.getByRole("navigation", { name: "Explorer" })).toBeVisible();
          const console = page.getByRole("region", { name: "Console" });
          await expect(console.getByRole("tab", { name: "Problems 1" })).toBeVisible();
          await expect(console.getByText("Too long · Row 3")).toBeVisible();
          // UX-6-3 (FP-2): one line in the Timeline slot until the kit's WeekStrip.
          await expect(page.locator('[data-slot="ide-week-line"]')).toBeVisible();
        } else {
          await expect(page.getByRole("navigation", { name: "Explorer" })).toHaveCount(0);
          await expect(page.getByRole("region", { name: "Console" })).toHaveCount(0);
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

        await page.evaluate(() => document.fonts.ready);
        await injectAxe(page);
        await checkA11y(page, '[data-slot="creator-ide"]');
        await mkdir(shots, { recursive: true });
        await ide.scrollIntoViewIfNeeded();
        await page.screenshot({ path: path.join(shots, `impl-${width}-${theme}.png`), fullPage: true });

        // History: versions with Compare / Restore (RevisionRow), and the diff.
        await inspector.getByRole("tab", { name: "History" }).click();
        await expect(page.locator('[data-slot="ide-history"]')).toBeVisible();
        await page
          .getByRole("button", { name: /Compare/ })
          .nth(1)
          .click();
        await expect(page.getByRole("group", { name: "Version comparison" })).toBeVisible();
        await checkA11y(page, '[data-slot="creator-ide"]');
        await page.screenshot({ path: path.join(shots, `impl-${width}-${theme}-history.png`), fullPage: true });

        // Shows on: the hub's Now beside the schedule entry.
        await inspector.getByRole("tab", { name: "Shows on" }).click();
        await expect(page.locator('[data-slot="ide-shows-on"]').getByText("Now", { exact: true })).toBeVisible();
        await checkA11y(page, '[data-slot="creator-ide"]');
        await page.screenshot({ path: path.join(shots, `impl-${width}-${theme}-shows-on.png`), fullPage: true });

        if (!desktop) {
          await inspector.getByRole("tab", { name: /Problems/ }).click();
          await expect(page.getByText("Too long · Row 3")).toBeVisible();
          await checkA11y(page, '[data-slot="creator-ide"]');
        }
      });
    });
  }
}
