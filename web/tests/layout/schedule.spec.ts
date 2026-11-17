import { expect, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

test.use({ timezoneId: "UTC", reducedMotion: "reduce" });
for (const width of [390, 768, 1280]) {
  for (const theme of ["light", "dark"]) {
    test(`Schedule agenda, entry and H8 ${width} ${theme}`, async ({ page }, testInfo) => {
      test.setTimeout(90_000);
      await page.clock.install({ time: new Date("2026-11-17T02:18:00Z") });
      await page.setViewportSize({ width, height: 1000 });
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto(`/tests/layout/schedule.html?theme=${theme}`);
      await expect(
        page.getByRole("radio", { name: width < 768 ? "Day" : width < 1024 ? "List" : "Week", exact: true }),
      ).toHaveAttribute("aria-checked", "true");
      const shot = async (state: string, fullPage = true) => {
        const path = testInfo.outputPath(`impl-schedule-${state}-${width}-${theme}.png`);
        await page.screenshot({ path, fullPage, animations: "disabled" });
        await testInfo.attach(`schedule-${state}-${width}-${theme}`, { path, contentType: "image/png" });
      };
      await injectAxe(page);
      const axe = () =>
        checkA11y(page, undefined, {
          detailedReport: true,
          detailedReportOptions: { html: true },
          axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } },
        });
      await shot("agenda");
      await axe();
      if (width >= 1024) {
        await page
          .getByRole("button", { name: /Lunch menu/ })
          .first()
          .click();
        await expect(page.getByRole("button", { name: "Edit entry", exact: true })).toBeVisible();
        await shot("inspector");
        await page.getByRole("button", { name: "Edit entry", exact: true }).click();
      } else await page.getByRole("button", { name: "Add Schedule", exact: true }).first().click();
      await expect(page.getByLabel("Start Time", { exact: true })).toHaveAttribute("type", "time");
      if (width < 768) await expect(page.locator('[data-slot="sheet-grabber"]')).toBeVisible();
      await shot("entry", false);
      await axe();
      await page.getByRole("radio", { name: "Specific date", exact: true }).click();
      await expect(page.getByLabel("Date", { exact: true })).toHaveAttribute("type", "date");
      await shot("date-entry", false);
      const save = page.getByRole("button", { name: "Save", exact: true });
      await save.scrollIntoViewIfNeeded();
      await expect(save).toBeInViewport({ ratio: 1 });
      await shot("entry-actions", false);
      await page.getByRole("button", { name: "Cancel", exact: true }).click();
      await page.getByRole("button", { name: "Which page at…", exact: true }).click();
      // Browser zone is UTC, while this value must stay in the hub's Los Angeles zone.
      await expect(page.getByLabel("Instant", { exact: true })).toHaveValue("2026-11-16T18:18");
      await page.getByRole("button", { name: "Check instant" }).click();
      const actual = page.getByRole("region", { name: "Active page at instant", exact: true });
      await expect(actual.getByText("Schedule", { exact: true })).toBeVisible();
      await expect(actual.locator('[data-slot="board-display"]')).toHaveAttribute("aria-label", /BREAKFAST SPECIALS/);
      await page.getByRole("button", { name: "Add a value…" }).click();
      await page.getByLabel("Variable path", { exact: true }).fill("weather.temperature");
      await page.getByLabel("Value (text or JSON)", { exact: true }).fill("65");
      await page.getByRole("button", { name: "Add value", exact: true }).click();
      await page.getByRole("button", { name: "Run collection dry run" }).click();
      const simulated = page.getByRole("region", { name: "Collection dry run", exact: true });
      await expect(simulated.locator('[data-slot="board-display"]')).toHaveAttribute(
        "aria-label",
        /RAINY DAY SPECIALS/,
      );
      await expect(actual.locator('[data-slot="board-display"]')).toHaveAttribute("aria-label", /BREAKFAST SPECIALS/);
      await expect(page.getByText("First winning rule", { exact: true })).toBeVisible();
      if (width >= 1024) {
        const actualCard = await actual.boundingBox();
        const simulatedCard = await simulated.locator("xpath=ancestor::*[@data-slot='card'][1]").boundingBox();
        expect(actualCard).not.toBeNull();
        expect(simulatedCard).not.toBeNull();
        expect(actualCard!.width).toBeGreaterThan(350);
        expect(simulatedCard!.x).toBeGreaterThan(actualCard!.x + actualCard!.width);
        expect(Math.abs(actualCard!.y - simulatedCard!.y)).toBeLessThan(2);
        expect((await page.locator('[data-slot="slider"]').boundingBox())!.width).toBeGreaterThan(700);
        expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThan(1900);
      }
      await shot("h8");
      await axe();
      await page.getByLabel("Instant", { exact: true }).fill("2026-11-16T19:00");
      await expect(actual).toHaveCount(0);
      await expect(simulated).toHaveCount(0);
      expect(errors).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  }
}
for (const width of [390, 1280]) {
  test(`Schedule empty default ${width}`, async ({ page }, testInfo) => {
    await page.clock.install({ time: new Date("2026-11-17T02:18:00Z") });
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/tests/layout/schedule.html?state=empty");
    await expect(page.getByRole("radio", { name: width < 768 ? "Day" : "Week", exact: true })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await expect(page.getByText("No schedules created yet", { exact: true })).toBeVisible();
    const empty = page.getByRole("region", { name: "No schedules created yet", exact: true });
    const preview = empty.locator('[data-slot="board-viewport"]');
    await expect(preview.locator('[data-slot="board-display"]')).toHaveAttribute("aria-label", /BREAKFAST SPECIALS/);
    await expect(preview).toHaveAttribute("data-mode", "actual");
    const bounds = await empty.boundingBox();
    for (const target of [preview, empty.getByRole("button", { name: "Add Schedule", exact: true })]) {
      const box = await target.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(bounds!.x);
      expect(box!.x + box!.width).toBeLessThanOrEqual(bounds!.x + bounds!.width);
    }
    if (width >= 1024) expect(bounds!.width).toBeGreaterThan(850);
    const path = testInfo.outputPath(`impl-schedule-empty-${width}.png`);
    await page.screenshot({ path, fullPage: true, animations: "disabled" });
    await testInfo.attach(`schedule-empty-${width}`, { path, contentType: "image/png" });
    if (width < 768) {
      await preview.getByRole("button", { name: "Fit", exact: true }).click();
      await expect(preview).toHaveAttribute("data-mode", "fit");
      const fitPath = testInfo.outputPath(`impl-schedule-empty-fit-${width}.png`);
      await page.screenshot({ path: fitPath, fullPage: true, animations: "disabled" });
      await testInfo.attach(`schedule-empty-fit-${width}`, { path: fitPath, contentType: "image/png" });
    }
    await page.getByRole("button", { name: "Copy from another display…", exact: true }).click();
    await page.getByRole("combobox", { name: "Source display", exact: true }).click();
    await page.getByRole("option", { name: "Source display", exact: true }).click();
    await page.getByRole("button", { name: "Copy entries", exact: true }).click();
    await expect(page.getByText("No schedules created yet", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Breakfast specials/ }).first()).toBeVisible();
  });
}
