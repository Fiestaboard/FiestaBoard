import { mkdir } from "node:fs/promises";
import path from "node:path";

import { expect, test } from "@playwright/test";

import { mockHub } from "./creator-ide-hub";

// FP-2 (UX-AUDIT-1, FABLE-AUDIT-REVIEW-1 §5): a truthful, quiet IDE. On a
// Flagship page with nothing wrong, the IDE row above the Inspector stays
// small: the Console one 40 px line until opened, the Timeline at most 80 px,
// the two together at most 160 px. Page-tab settings are staged edits.

const height = (box: { height: number } | null) => box?.height ?? Number.POSITIVE_INFINITY;

for (const width of [1440, 1024]) {
  test(`${width}px: the IDE row is quiet on a page with no problems`, async ({ page }, testInfo) => {
    const shots = process.env.CREATOR_IDE_SHOTS || testInfo.outputPath("creator-ide-quiet-shots");
    await page.setViewportSize({ width, height: 900 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mockHub(page, { noProblems: true });
    await page.goto("/tests/layout/creator-ide.html?theme=light");
    await expect(page.getByRole("textbox", { name: /page name/i })).toHaveValue("Kitchen morning");

    const consoleRegion = page.getByRole("region", { name: "Console" });
    const line = consoleRegion.getByRole("button", { name: /^No problems · Sent .* to Kitchen board$/ });
    await expect(line).toBeVisible();
    const consoleCard = page.locator('[data-slot="card"]').filter({ has: consoleRegion }).last();
    expect(height(await consoleCard.boundingBox())).toBeLessThanOrEqual(40);
    const timeline = page.locator('[data-slot="ide-timeline"]');
    await expect(timeline.locator('[data-slot="ide-week-line"]')).toContainText(/Weekdays .* · next \w+/);
    expect(height(await timeline.boundingBox())).toBeLessThanOrEqual(80);
    expect(height(await page.locator('[data-slot="ide-template-regions"]').boundingBox())).toBeLessThanOrEqual(160);

    // The status line: the pill states the state, the sentence adds where and until when.
    const status = page.locator('[data-slot="preview-status"]');
    await expect(status).toContainText(/Live\s*Showing on Kitchen board now · until 8:30/);
    await expect(status.getByRole("button", { name: "0 problems" })).toBeVisible();

    // UX-7-2: Delete is reachable at 900 px tall without scrolling an area inside the
    // Inspector card (the workspace itself scrolls, as a document does).
    const innerScroll = await page.getByRole("button", { name: /^Delete page/ }).evaluate((row) => {
      const card = row.closest("#ide-inspector");
      for (let node = row.parentElement; node && node !== card?.parentElement; node = node.parentElement) {
        const { overflowY } = getComputedStyle(node);
        if (/(auto|scroll)/.test(overflowY) && node.scrollHeight > node.clientHeight + 1) return true;
      }
      return false;
    });
    expect(innerScroll).toBe(false);

    await mkdir(shots, { recursive: true });
    await page.screenshot({ path: path.join(shots, `quiet-${width}.png`), fullPage: true });

    // Opening the console is a click; then it is the full Problems | Warnings | Sent list.
    await line.click();
    await expect(consoleRegion.getByRole("tab", { name: "Problems 0" })).toBeVisible();

    // Page duration: an inline menu on the row, staged as an unsaved edit (UX-7-1).
    const duration = page.getByRole("button", { name: /^Page duration/ });
    await expect(duration).not.toContainText(/right away/);
    await duration.click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await page.getByRole("menuitemradio", { name: "1 min" }).click();
    await expect(duration).toContainText("1 min");
    // D6 (DD-W158): the header meta line says it, not a status-row chip.
    await expect(page.getByTestId("page-editor-save-state")).toHaveText(/Unsaved changes|Saving draft…|Draft saved/);
    await expect(status).not.toContainText("Unsaved");
    await page.screenshot({ path: path.join(shots, `quiet-${width}-duration.png`), fullPage: true });
  });
}

test("1024px: the one-line week truncates instead of wrapping on an unscheduled page", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mockHub(page, { notScheduled: true });
  await page.goto("/tests/layout/creator-ide.html?theme=light");
  const line = page.locator('[data-slot="ide-week-line"]');
  await expect(line).toContainText("Not scheduled this week");
  await expect(line.getByRole("link", { name: "Add to schedule" })).toBeVisible();
  expect(height(await line.boundingBox())).toBeLessThanOrEqual(24);
  expect(height(await page.locator('[data-slot="ide-timeline"]').boundingBox())).toBeLessThanOrEqual(80);
});
