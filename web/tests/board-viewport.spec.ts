/**
 * Slice 2.4 (WEB-07): boards scroll horizontally; Actual size is the default.
 *
 * Against the full stack: on a phone, Home's board keeps its real tiles and
 * scrolls inside its bezel instead of shrinking (owner rule 9). F gives the
 * labelled Fit overview, the choice lasts the session, and a page card's
 * thumbnail stays a fit picture inside its button. The component behaviour
 * itself (snap, fades, every indicator string) is pinned in
 * tests/layout/board-viewport.spec.ts.
 */
import type { Page } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

import {
  API_URL,
  authHeaders,
  configureBoard,
  createPage,
  deleteAllPages,
  deleteAllSchedules,
  expect,
  resetToSingleBoard,
  setActivePage,
  suppressWizard,
  test,
} from "./helpers";

const homeViewport = (page: Page) => page.locator("[data-slot=board-viewport]").first();
const homeScroller = (page: Page) => page.locator("[data-slot=board-viewport-scroller]").first();
const homeIndicator = (page: Page) => page.locator("[data-slot=board-viewport-indicator-text]").first();

test.beforeEach(async ({ page }) => {
  await configureBoard();
  await resetToSingleBoard();
  await suppressWizard(page);
  await deleteAllSchedules();
  await deleteAllPages();
  const id = await createPage("Board viewport", ["GOOD MORNING", "72 SUNNY HI 78", "", "", "", "HAVE A GREAT DAY"]);
  await setActivePage(id);
});

test.describe("phone (390)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("Home's Flagship scrolls at Actual size instead of shrinking", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("char-tile-0-0")).toBeVisible({ timeout: 15_000 });
    await expect(homeViewport(page)).toHaveAttribute("data-mode", "actual");
    await expect(homeViewport(page)).toHaveAttribute("data-overflow", "true");
    await expect(homeIndicator(page)).toHaveText(/^Columns 1–\d+ of 22$/);
    // Real tiles: no transform scales the board down.
    const scaled = page.locator("[data-slot=board-viewport-scaled]").first();
    await expect(scaled).not.toHaveAttribute("style", /scale\(/);
  });

  test("End reaches the last column, and F gives the labelled overview", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("char-tile-0-0")).toBeVisible({ timeout: 15_000 });
    await homeScroller(page).focus();
    await page.keyboard.press("End");
    await expect(homeIndicator(page)).toHaveText(/^Columns \d+–22 of 22$/);
    await page.keyboard.press("f");
    await expect(homeViewport(page)).toHaveAttribute("data-mode", "fit");
    // At phone width the fit Flagship is either a readable fit or an overview;
    // either way the session remembers the choice across a reload.
    await page.reload();
    await expect(page.getByTestId("char-tile-0-0")).toBeAttached({ timeout: 15_000 });
    await expect(homeViewport(page)).toHaveAttribute("data-mode", "fit");
  });

  test("no serious or critical axe violations on Home with a scrolling board", async ({ page }) => {
    await page.goto("/");
    await expect(homeViewport(page)).toHaveAttribute("data-overflow", "true", { timeout: 15_000 });
    await injectAxe(page);
    const violations = await getViolations(page, "[data-slot=board-viewport]", {
      rules: { "color-contrast": { enabled: false } },
    });
    expect(violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([]);
  });
});

test("a page card's thumbnail is not a scroll region (it sits inside a button)", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/pages");
  const card = page.getByRole("button", { name: /Board viewport/ }).first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  await expect(card.locator("[data-slot=board-viewport]")).toHaveCount(0);
  await expect(card.getByRole("region")).toHaveCount(0);
});

test("a desktop Home board that fits draws no toggle or indicator (1280)", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  await expect(page.getByTestId("char-tile-0-0")).toBeVisible({ timeout: 15_000 });
  await expect(homeViewport(page)).toHaveAttribute("data-overflow", "false");
  await expect(homeViewport(page).getByRole("group", { name: "Preview size" })).toHaveCount(0);
});

// M1 (review of #2482): a note-array page card used to carry the kit's Fit /
// Actual pills inside its <button>, a dead control that axe flags as
// nested-interactive. The card's board is a picture with no controls.
test.describe("note-array page card", () => {
  test.afterEach(async () => {
    await resetToSingleBoard();
  });

  test("has no control inside the card button, and axe finds no nested-interactive", async ({ page }) => {
    const res = await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        boards: [
          {
            name: "Lobby wall",
            device_type: "note_array",
            board_color: "black",
            enabled: true,
            api_mode: "cloud",
            notes_wide: 3,
            notes_tall: 1,
            note_array_token: `test-array-token-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          },
        ],
      }),
    });
    expect(res.ok).toBe(true);
    const created = await fetch(`${API_URL}/pages`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        name: "Open mic",
        type: "template",
        template: ["OPEN MIC TONIGHT", "", ""],
        device_type: "note_array",
        notes_wide: 3,
        notes_tall: 1,
      }),
    });
    expect(created.ok).toBe(true);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/pages");
    const card = page.getByRole("button", { name: /Open mic/ }).first();
    await expect(card).toBeVisible({ timeout: 15_000 });
    await expect(card.locator("[data-slot=board-display]")).toBeVisible({ timeout: 15_000 });
    await expect(card.locator("button, [role=region], [tabindex]")).toHaveCount(0);
    await expect(card.getByRole("group", { name: "Preview size" })).toHaveCount(0);

    await injectAxe(page);
    const violations = await getViolations(page, "[data-section-item]", {
      runOnly: { type: "rule", values: ["nested-interactive"] },
    });
    expect(violations).toEqual([]);
  });
});

test.describe("touch Home actions and viewport controls", () => {
  test.use({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });

  for (const width of [390, 768, 1280]) {
    test(`at ${width}px the actions stay above the preview and its mode controls`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto("/");
      await expect(homeViewport(page)).toHaveAttribute("data-mode", "actual", { timeout: 15_000 });
      const actions = page.getByRole("button", { name: /^Actions for / });
      await expect(actions).toBeVisible();
      const [actionBox, previewBox] = await Promise.all([actions.boundingBox(), homeViewport(page).boundingBox()]);
      expect(actionBox && previewBox).toBeTruthy();
      expect(actionBox!.y + actionBox!.height).toBeLessThanOrEqual(previewBox!.y);
      if (width !== 1280) {
        const modes = homeViewport(page).getByRole("group", { name: "Preview size" });
        await modes.getByRole("button", { name: "Fit", exact: true }).click();
        await expect(homeViewport(page)).toHaveAttribute("data-mode", "fit");
        await modes.getByRole("button", { name: "Actual size", exact: true }).click();
        await expect(homeViewport(page)).toHaveAttribute("data-mode", "actual");
      }
      await actions.click();
      await expect(page.getByRole("menuitem", { name: /Refresh board/ })).toBeVisible();
      await page.keyboard.press("Escape");
    });
  }
});
