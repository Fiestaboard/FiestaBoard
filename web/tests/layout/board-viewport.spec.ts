/**
 * Slice 2.4 (WEB-07): boards scroll horizontally; Actual size is the default.
 *
 * The app's board wrapper on real Chromium layout (no hub): a board wider than
 * its slot keeps its tiles and scrolls inside its bezel, with the edge fade,
 * snap, "Note 1 of 3" indicator, ← → / Home / End / F keys, and a labelled Fit
 * overview below the 13 px tile floor. Figma: 07 `57:27771`, 02 `36:35275`,
 * `52:122709`–`52:123502`.
 */
import { expect, type Page, test } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

const FIXTURE = "/tests/layout/board-viewport.html";

async function open(page: Page, width: number, query = "") {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(`${FIXTURE}${query}`);
  await page.evaluate(() => window.sessionStorage.clear());
  await page.reload();
}

const viewport = (page: Page, id: string) => page.getByTestId(id).locator("[data-slot=board-viewport]");
const scroller = (page: Page, id: string) => page.getByTestId(id).locator("[data-slot=board-viewport-scroller]");
const indicator = (page: Page, id: string) => page.getByTestId(id).locator("[data-slot=board-viewport-indicator-text]");

test.describe("at phone width (390)", () => {
  test.beforeEach(async ({ page }) => open(page, 390));

  test("a Flagship keeps its real tiles and scrolls instead of shrinking", async ({ page }) => {
    await expect(viewport(page, "flagship")).toHaveAttribute("data-overflow", "true");
    await expect(viewport(page, "flagship")).toHaveAttribute("data-mode", "actual");
    // Tile md at the base step is 14 px wide; a fit-scaled board would be under it.
    const tile = page.getByTestId("flagship").locator("[data-note-row]").first().locator("> *").first();
    const box = await tile.boundingBox();
    expect(box!.width).toBeGreaterThanOrEqual(13);
    // The scroller really scrolls.
    const { scrollWidth, clientWidth } = await scroller(page, "flagship").evaluate((el) => ({
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    }));
    expect(scrollWidth).toBeGreaterThan(clientWidth);
    await expect(indicator(page, "flagship")).toHaveText(/^Columns 1–\d+ of 22$/);
  });

  test("the region is named, focusable, and described by the indicator", async ({ page }) => {
    const region = page.getByTestId("note-array").getByRole("region", { name: "Board preview" });
    await expect(region).toHaveAttribute("tabindex", "0");
    await expect(region).toHaveAttribute("aria-describedby", /.+/);
  });

  test("← → / Home / End page a note array one Note at a time", async ({ page }) => {
    const region = scroller(page, "note-array");
    await expect(indicator(page, "note-array")).toHaveText("Note 1 of 3");
    await region.focus();
    await page.keyboard.press("ArrowRight");
    await expect(indicator(page, "note-array")).toHaveText("Note 2 of 3");
    await page.keyboard.press("End");
    await expect(indicator(page, "note-array")).toHaveText("Note 3 of 3");
    await page.keyboard.press("Home");
    await expect(indicator(page, "note-array")).toHaveText("Note 1 of 3");
  });

  test("scroll snaps per Note on a note array and per column of Notes on a 2×2", async ({ page }) => {
    await expect(scroller(page, "note-array")).toHaveCSS("scroll-snap-type", "x mandatory");
    await expect(indicator(page, "note-array-2x2")).toHaveText("Column 1 of 2 · 4 notes");
  });

  test("the hint follows the indicator while the board scrolls", async ({ page }) => {
    await expect(page.getByTestId("note-array").locator("[data-slot=board-viewport-indicator]")).toContainText(
      "Snaps to each Note.",
    );
    await expect(page.getByTestId("flagship").locator("[data-slot=board-viewport-indicator]")).toContainText(
      "Snaps to each column.",
    );
  });

  test("an edge fade marks only the side with more board", async ({ page }) => {
    const fades = page.getByTestId("note-array").locator("[data-slot=board-viewport-fade]");
    await expect(fades.and(page.locator("[data-side=start]"))).toHaveAttribute("data-visible", "false");
    await expect(fades.and(page.locator("[data-side=end]"))).toHaveAttribute("data-visible", "true");
    await scroller(page, "note-array").focus();
    await page.keyboard.press("End");
    await expect(fades.and(page.locator("[data-side=start]"))).toHaveAttribute("data-visible", "true");
    await expect(fades.and(page.locator("[data-side=end]"))).toHaveAttribute("data-visible", "false");
  });

  test("F gives a labelled Fit overview, and F again reads at Actual size", async ({ page }) => {
    await scroller(page, "note-array").focus();
    await page.keyboard.press("f");
    await expect(viewport(page, "note-array")).toHaveAttribute("data-mode", "fit");
    await expect(viewport(page, "note-array")).toHaveAttribute("data-overview", "true");
    await expect(indicator(page, "note-array")).toHaveText("Overview · 3 notes · tap Actual to read");
    await page.keyboard.press("f");
    await expect(viewport(page, "note-array")).toHaveAttribute("data-mode", "actual");
    await expect(indicator(page, "note-array")).toHaveText("Note 1 of 3");
  });

  test("the Fit / Actual size toggle is two 44 px targets", async ({ page }) => {
    const group = page.getByTestId("note-array").getByRole("group", { name: "Preview size" });
    for (const name of ["Fit", "Actual size"]) {
      const box = await group.getByRole("button", { name }).boundingBox();
      expect(box!.height).toBeGreaterThanOrEqual(44);
      expect(box!.width).toBeGreaterThanOrEqual(44);
    }
    await expect(group.getByRole("button", { name: "Actual size" })).toHaveAttribute("aria-pressed", "true");
  });

  test("a Fit tap lasts the session, for boards mounted later too", async ({ page }) => {
    await page
      .getByTestId("note-array")
      .getByRole("group", { name: "Preview size" })
      .getByRole("button", { name: "Fit" })
      .click();
    await page.reload();
    await expect(viewport(page, "note-array")).toHaveAttribute("data-mode", "fit");
    await expect(viewport(page, "flagship")).toHaveAttribute("data-mode", "fit");
  });

  test("a page-card thumbnail stays a fit picture, whatever the session says", async ({ page }) => {
    await page.evaluate(() => window.sessionStorage.setItem("fiestaboard:boardPreviewMode", "actual"));
    await page.reload();
    const thumb = page.getByTestId("thumbnail");
    await expect(thumb.locator("[data-slot=board-viewport]")).toHaveCount(0);
    await expect(thumb.getByRole("region")).toHaveCount(0);
    const slot = await thumb.locator(".overflow-hidden").first().boundingBox();
    const board = await thumb.locator("[data-slot=board-display]").boundingBox();
    expect(board!.width).toBeLessThanOrEqual(slot!.width + 1);
  });

  test("no serious or critical axe violations", async ({ page }) => {
    await injectAxe(page);
    const violations = await getViolations(page, "[data-testid=flagship], [data-testid=note-array]");
    expect(violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
  });
});

test("a board that fits draws no toggle, indicator or fade (1280)", async ({ page }) => {
  await open(page, 1280);
  await expect(viewport(page, "flagship")).toHaveAttribute("data-overflow", "false");
  await expect(page.getByTestId("flagship").getByRole("group", { name: "Preview size" })).toHaveCount(0);
  await expect(page.getByTestId("flagship").locator("[data-slot=board-viewport-indicator]")).toHaveCount(0);
  await expect(page.getByTestId("flagship").locator("[data-slot=board-viewport-fade]")).toHaveCount(0);
});

test("a 3×1 note array still scrolls in a tablet slot (768)", async ({ page }) => {
  await open(page, 768);
  await expect(viewport(page, "note-array")).toHaveAttribute("data-overflow", "true");
  await expect(indicator(page, "note-array")).toHaveText("Note 1 of 3");
});

test.describe("on a touch phone (coarse pointer)", () => {
  test.use({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });

  test("the hint says 'swipe' (02), not the keyboard hint", async ({ page }) => {
    await page.goto(FIXTURE);
    const row = page.getByTestId("note-array").locator("[data-slot=board-viewport-indicator]");
    await expect(row).toContainText("Note 1 of 3 · swipe");
    await expect(row).not.toContainText("Shift + scroll");
  });
});
