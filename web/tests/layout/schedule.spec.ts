import { expect, type Locator, type Page, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

async function expectOpaque(target: Locator) {
  await expect(target).toBeVisible();
  await expect
    .poll(() =>
      target.evaluate((element) => {
        let opacity = 1;
        for (let ancestor: Element | null = element; ancestor; ancestor = ancestor.parentElement) {
          opacity *= Number(getComputedStyle(ancestor).opacity);
        }
        return opacity;
      }),
    )
    .toBe(1);
}

async function expectScheduleReady(page: Page, width: number, theme: "light" | "dark", empty = false) {
  await expect
    .poll(() => page.locator("html").evaluate((element) => (element.classList.contains("dark") ? "dark" : "light")))
    .toBe(theme);
  const board = page.getByRole("combobox", { name: "Select board to manage", exact: true }).filter({ visible: true });
  await expect(board).toContainText("Kitchen board");
  await expect(page.getByTestId("active-board-indicator")).toContainText("Kitchen board");
  await expect(page.getByTestId("gap-default-select")).toContainText("Breakfast specials");
  if (empty) {
    // The route enables validation only for nonempty schedules, so this state
    // hydrates the default-page EmptyState without a validation indicator.
    const emptyState = page.getByRole("region", { name: "No schedules created yet", exact: true });
    await expect(emptyState).toBeVisible();
    await expect(emptyState).toContainText("Gaps use Breakfast specials.");
    await expect(page.getByRole("button", { name: /\d+ schedule (?:conflicts?|gaps?)/ })).toHaveCount(0);
  } else {
    // Conflicts no longer hide gaps: the badge names both counts (BB-C-2).
    await expect(page.getByRole("button", { name: /^1 schedule conflict, \d+ schedule gaps?$/ })).toBeVisible();
    const conflicts =
      width >= 1024
        ? page.locator('[data-slot="week-calendar-entry"][data-conflict]')
        : page.locator('[data-kind="conflict"]');
    const occurrences = width < 768 ? 1 : 7;
    await expect(conflicts.filter({ hasText: "Breakfast specials" })).toHaveCount(occurrences);
    await expect(conflicts.filter({ hasText: "Lunch menu" })).toHaveCount(occurrences);
    // Today's gap holds the board right now (18:18 in the hub's zone), so it is the "Now" row (BB-C-3).
    const gaps = page.locator('[data-kind="gap"], [data-kind="now"]').filter({ hasText: "Breakfast specials" });
    await expect(gaps).toHaveCount(occurrences);
    if (width < 1024) await expect(page.locator('[data-kind="now"]')).toHaveText(/Gap · Breakfast specials.*Now/);
  }
  const toolbar = page.locator('[data-slot="page-toolbar"]');
  await expectOpaque(board);
  await expectOpaque(toolbar);
  await expectOpaque(page.getByRole("button", { name: "Add entry", exact: true }).first());
  if (width < 768) {
    // 07d Schedule · Day (322:19169): title + Add, one Schedule Mode row, day chips, then the agenda;
    // no Day/Week/List choice and no seven-column week on a phone (BB-C-3, BB-C-4).
    await expect(page.getByRole("radio", { name: "Week", exact: true })).toHaveCount(0);
    await expect(page.locator('label[for="schedule-mode"]')).toHaveText("Schedule Mode · Kitchen board");
    if (!empty) {
      // 07d draws the first row at y≈340 of 844; it used to start at ≈555 (BB-C-3).
      const firstRow = page.locator('[data-slot="list-row"]').first();
      expect((await firstRow.boundingBox())!.y).toBeLessThan(440);
    }
  }
}

async function settleCapture(page: Page, resetScroll = true) {
  await page.evaluate(async (origin) => {
    await document.fonts.ready;
    await Promise.all(
      document
        .getAnimations()
        .filter((animation) => Number.isFinite(animation.effect?.getComputedTiming().endTime))
        .map((animation) => animation.finished.catch(() => undefined)),
    );
    // Full-page shots include sticky chrome, so focused H8 controls must not
    // leave the document or a visible overflow region scrolled mid-capture.
    // Viewport-only entry shots retain their deliberate Save-button scroll.
    if (origin) {
      document.scrollingElement?.scrollTo({ top: 0, left: 0, behavior: "instant" });
      for (const element of document.querySelectorAll<HTMLElement>("*")) {
        if (!element.checkVisibility()) continue;
        const style = getComputedStyle(element);
        if (/(auto|scroll)/.test(`${style.overflowX} ${style.overflowY}`))
          element.scrollTo({ top: 0, left: 0, behavior: "instant" });
      }
    }
    await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  }, resetScroll);
}

test.use({ timezoneId: "UTC", reducedMotion: "reduce" });
for (const width of [390, 768, 1280]) {
  for (const theme of ["light", "dark"] as const) {
    test(`Schedule agenda, entry and H8 ${width} ${theme}`, async ({ page }, testInfo) => {
      test.setTimeout(90_000);
      await page.clock.install({ time: new Date("2026-11-17T02:18:00Z") });
      await page.setViewportSize({ width, height: 1000 });
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto(`/tests/layout/schedule.html?theme=${theme}`);
      if (width >= 768)
        await expect(page.getByRole("radio", { name: width < 1024 ? "List" : "Week", exact: true })).toHaveAttribute(
          "aria-checked",
          "true",
        );
      await expectScheduleReady(page, width, theme);
      const shot = async (state: string, fullPage = true) => {
        await settleCapture(page, fullPage);
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
      } else await page.getByRole("button", { name: "Add entry", exact: true }).first().click();
      await expect(page.getByLabel("Start Time", { exact: true })).toHaveAttribute("type", "time");
      if (width < 768) await expect(page.locator('[data-slot="sheet-grabber"]')).toBeVisible();
      await shot("entry", false);
      await axe();
      if (width < 768) {
        // BB-C-5: the phone sheet is the compact form, Save in view without scrolling.
        await expect(page.locator('[data-slot="schedule-entry-form"]')).toHaveAttribute("data-layout", "compact");
        await expect(page.getByRole("button", { name: "Save", exact: true })).toBeInViewport({ ratio: 1 });
        await page.getByRole("button", { name: "More options" }).click();
      }
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
      await settleCapture(page);
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
    if (width >= 768)
      await expect(page.getByRole("radio", { name: "Week", exact: true })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByText("No schedules created yet", { exact: true })).toBeVisible();
    await expectScheduleReady(page, width, "light", true);
    await settleCapture(page);
    const empty = page.getByRole("region", { name: "No schedules created yet", exact: true });
    const preview = empty.locator('[data-slot="board-viewport"]');
    await expect(preview.locator('[data-slot="board-display"]')).toHaveAttribute("aria-label", /BREAKFAST SPECIALS/);
    await expect(preview).toHaveAttribute("data-mode", "actual");
    const bounds = await empty.boundingBox();
    for (const target of [preview, empty.getByRole("button", { name: "Add entry", exact: true })]) {
      const box = await target.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(bounds!.x);
      expect(box!.x + box!.width).toBeLessThanOrEqual(bounds!.x + bounds!.width);
    }
    if (width >= 1024) expect(bounds!.width).toBeGreaterThan(850);
    const path = testInfo.outputPath(`impl-schedule-empty-${width}.png`);
    await settleCapture(page);
    await page.screenshot({ path, fullPage: true, animations: "disabled" });
    await testInfo.attach(`schedule-empty-${width}`, { path, contentType: "image/png" });
    if (width < 768) {
      await preview.getByRole("button", { name: "Fit", exact: true }).click();
      await expect(preview).toHaveAttribute("data-mode", "fit");
      const fitPath = testInfo.outputPath(`impl-schedule-empty-fit-${width}.png`);
      await settleCapture(page);
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

// BB-C-5: in landscape the entry opens as a side sheet that reaches the bottom of the screen.
test("Schedule entry side sheet runs the full height in landscape", async ({ page }) => {
  await page.clock.install({ time: new Date("2026-11-17T02:18:00Z") });
  await page.setViewportSize({ width: 844, height: 390 });
  await page.goto("/tests/layout/schedule.html");
  await page.getByRole("button", { name: "Add entry", exact: true }).first().click();
  const sheet = page.getByRole("dialog");
  await expect(page.getByLabel("Start Time", { exact: true })).toBeVisible();
  await expect
    .poll(async () => Math.round((await sheet.boundingBox())!.y + (await sheet.boundingBox())!.height))
    .toBe(390);
});
