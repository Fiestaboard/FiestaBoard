import { expect, type Page, test } from "@playwright/test";

// BB-FC-12: 07e Accessibility (`333:57132`). The settings switches put a class
// on <html> (unit-tested with ReduceMotionApplier); this checks what those
// classes do to the real kit components in a browser.

const boards = [
  {
    id: "board-1",
    name: "Kitchen board",
    device_type: "flagship",
    board_color: "black",
    enabled: true,
    output: "vestaboard",
    output_config: { api_mode: "local", host: "192.0.2.10", local_api_key: "layout-test-key" },
  },
];

async function openHome(page: Page) {
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith("/api/")) return route.continue();
    let json: unknown = {};
    if (url.pathname.endsWith("/settings/board")) json = { boards, devices: ["flagship"], board_type: "black" };
    if (url.pathname.endsWith("/config/validate")) json = { valid: true, is_first_run: false, errors: [] };
    if (url.pathname.endsWith("/v1/status")) json = { boards: { "board-1": { health: { reachable: true } } } };
    if (url.pathname.endsWith("/board/current-message"))
      json = { message: "GOOD EVENING", rows: 6, cols: 22, characters: null, cached_at: new Date().toISOString() };
    return route.fulfill({ json });
  });
  await page.goto("/tests/layout/home.html");
  await expect(page.getByTestId("now-showing")).toBeVisible();
}

/** The colour of the first board glyph that draws a "G". */
function glyphColor(page: Page) {
  return page.evaluate(() => {
    const board = document.querySelector('[data-slot="board-display"]')!;
    // The innermost element that draws the letter (a tile also holds its flap layers).
    const glyph = [...board.querySelectorAll("*")].find(
      (el) => el.textContent === "G" && ![...el.children].some((child) => child.textContent === "G"),
    );
    return glyph ? getComputedStyle(glyph).color : null;
  });
}

test("High-contrast board text draws board-black glyphs in the board's white", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openHome(page);
  await expect.poll(() => glyphColor(page)).toBe("rgb(240, 240, 232)");
  await page.evaluate(() => document.documentElement.classList.add("a11y-board-high-contrast"));
  await expect.poll(() => glyphColor(page)).toBe("rgb(255, 255, 255)");
});

test.describe("on a touch screen", () => {
  test.use({ hasTouch: true, isMobile: true, viewport: { width: 390, height: 844 } });

  test("Larger touch targets raise the kit's touch floor from 44 to 48 px", async ({ page }) => {
    await openHome(page);
    // root.tsx opts the app into the kit's touch layer; this harness has no root.
    await page.evaluate(() => document.documentElement.classList.add("fui-coarse"));
    const changePage = page.getByRole("button", { name: "Change Page" }).first();
    await expect.poll(async () => (await changePage.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    const before = (await changePage.boundingBox())!.height;
    expect(before).toBeLessThan(48);
    await page.evaluate(() => document.documentElement.classList.add("a11y-large-targets"));
    await expect.poll(async () => (await changePage.boundingBox())!.height).toBeGreaterThanOrEqual(48);
  });
});
