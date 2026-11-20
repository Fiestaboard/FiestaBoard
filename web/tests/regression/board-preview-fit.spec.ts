/**
 * Board content stays reachable without widening the page.
 *
 * Page-card pictures fit their clipping box. Readable Home boards keep at
 * least Tile sm and scroll inside the bezel when needed (owner rule 9), so
 * shrinking every surface to fit is no longer the contract. Geometry checks
 * protect thumbnails from silent clipping and prove the scrolling board's
 * first and last columns are reachable without document overflow.
 */
import {
  configureBoard,
  createPage,
  deletePage,
  ensureAuthForFetch,
  expect,
  loginIfNeeded,
  resetToSingleBoard,
  setActivePage,
  test,
} from "../helpers";

/** iPhone 14-ish. Narrow enough that an unscaled flagship board cannot fit. */
const MOBILE = { width: 390, height: 844 };

/** A full-width board: row 3 uses all 22 columns, so nothing can shrink it. */
const WIDE_TEMPLATE = [
  "HELLO FIESTABOARD",
  "FLAP SPEED TEST",
  "ABCDEFGHIJKLMNOPQRSTUV",
  "THE QUICK BROWN FOX",
  "JUMPS OVER LAZY DOGS",
  "END OF BOARD ROW SIX",
];

interface BoardOverflow {
  slot: string;
  clipClass: string;
  clipWidth: number;
  tileSpan: number;
  overflowLeft: number;
  overflowRight: number;
}

/**
 * Measure every board on the page against its nearest clipping ancestor.
 *
 * Returns a row per board — overflowing or not — so callers can assert both
 * "nothing overflows" and "something was actually measured". The second half
 * matters: the fix for this bug changes which component renders the board, so
 * a check filtered by component identity would quietly start measuring nothing
 * and pass forever.
 */
async function measureBoards(page: import("@playwright/test").Page): Promise<BoardOverflow[]> {
  return page.evaluate(() => {
    const clipAncestor = (el: Element): Element => {
      let node = el.parentElement;
      while (node) {
        if (getComputedStyle(node).overflowX !== "visible") return node;
        node = node.parentElement;
      }
      return document.documentElement;
    };

    const boards = Array.from(document.querySelectorAll('[data-board-preview], [data-slot="static-board-display"]'));

    return boards
      .map((board) => {
        // Tiles, not the bezel: the bezel can be clamped by a max-width while
        // the grid inside it still escapes on both sides. The tiles are what a
        // user actually sees cut off.
        const tiles = Array.from(board.querySelectorAll("[data-note-row] > *"));
        if (tiles.length === 0) return null;

        const clip = clipAncestor(board).getBoundingClientRect();
        const rects = tiles.map((t) => t.getBoundingClientRect());
        const leftmost = Math.min(...rects.map((r) => r.left));
        const rightmost = Math.max(...rects.map((r) => r.right));

        return {
          slot: (board as HTMLElement).dataset.slot ?? "board-preview",
          clipClass: clipAncestor(board).className.slice(0, 60),
          clipWidth: Math.round(clip.width),
          tileSpan: Math.round(rightmost - leftmost),
          overflowLeft: Math.round(clip.left - leftmost),
          overflowRight: Math.round(rightmost - clip.right),
        };
      })
      .filter((b): b is BoardOverflow => b !== null);
  });
}

/** Wait until at least one board has rendered its tiles. */
async function waitForABoard(page: import("@playwright/test").Page): Promise<void> {
  await page.waitForFunction(
    () =>
      document.querySelectorAll(
        '[data-board-preview] [data-note-row] > *, [data-slot="static-board-display"] [data-note-row] > *',
      ).length > 0,
    undefined,
    { timeout: 15_000 },
  );
}

let pageId: string;
let secondPageId: string;

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await resetToSingleBoard();
  pageId = await createPage("Flap Check", WIDE_TEMPLATE);
  secondPageId = await createPage("Flap Check Two", WIDE_TEMPLATE);
  await setActivePage(pageId);
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
  await page.setViewportSize(MOBILE);
});

test.afterEach(async () => {
  await deletePage(pageId).catch(() => {});
  await deletePage(secondPageId).catch(() => {});
});

test.describe("board previews fit or scroll inside their container on a phone", () => {
  // Two different invariants, deliberately not merged.
  //
  // Overflowing to the *right* can be a design: the collection cascade bleeds
  // its stacked cards off the edge on purpose. Overflowing to the *left* never
  // is — it cuts the first character off every row, which reads as corrupted
  // text rather than as a cropped board. So the whole-app sweep asserts only
  // the left edge, and the surfaces that are supposed to show a complete board
  // get the stronger "fits entirely" assertion by name.

  test("no board on the Pages list is cut off at its left edge", async ({ page }) => {
    await page.goto("/pages");
    await waitForABoard(page);

    const boards = await measureBoards(page);
    expect(boards.length, "measured no boards — the check would pass vacuously").toBeGreaterThan(0);

    const cutOff = boards.filter((b) => b.overflowLeft > 1);
    expect(cutOff, `boards cut off at the left edge: ${JSON.stringify(cutOff, null, 2)}`).toEqual([]);
  });

  test("no board on the dashboard is cut off at its left edge", async ({ page }) => {
    await page.goto("/");
    await waitForABoard(page);

    const boards = await measureBoards(page);
    expect(boards.length, "measured no boards — the check would pass vacuously").toBeGreaterThan(0);

    const cutOff = boards.filter((b) => b.overflowLeft > 1);
    expect(cutOff, `boards cut off at the left edge: ${JSON.stringify(cutOff, null, 2)}`).toEqual([]);
  });

  test("the Pages list previews fit their container entirely at 390px", async ({ page }) => {
    // These previews are meant to show a whole board, so nothing may spill in
    // either direction — and specifically not on the strength of the container's
    // right-fade mask, which hid this for as long as it existed.
    //
    // No filter by component identity: the fix swaps StaticBoardDisplay for a
    // scaled board, which changes `data-slot`, so filtering on it would make
    // this test measure nothing the moment it starts working.
    await page.goto("/pages");
    await waitForABoard(page);

    const boards = await measureBoards(page);
    expect(boards.length, "measured no boards — the check would pass vacuously").toBeGreaterThan(0);

    const overflowing = boards.filter((b) => b.overflowLeft > 1 || b.overflowRight > 1);
    expect(overflowing, `page previews overflow their clipping box: ${JSON.stringify(overflowing, null, 2)}`).toEqual(
      [],
    );
  });

  // At 390 the Flagship now fits whole (phone-hero, BB-A-6); the scrolling
  // contract is held at 360, below the kit's 13 px tile floor.
  test("the dashboard keeps readable tiles and reaches its last column inside the bezel at 360px", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 780 });
    await page.goto("/");
    await waitForABoard(page);

    const viewport = page.locator("[data-slot=board-viewport]").first();
    const scroller = viewport.locator("[data-slot=board-viewport-scroller]");
    await expect(viewport).toHaveAttribute("data-mode", "actual");
    await expect(viewport).toHaveAttribute("data-overflow", "true");
    await expect(scroller.locator("[data-note-row] > *")).toHaveCount(6 * 22);
    const initial = await scroller.evaluate((el) => ({
      tileWidth: Math.min(
        ...Array.from(el.querySelectorAll("[data-note-row] > *"), (t) => t.getBoundingClientRect().width),
      ),
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    }));
    expect(initial.tileWidth).toBeGreaterThanOrEqual(13);
    expect(initial.scrollWidth).toBeGreaterThan(initial.clientWidth);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);

    await scroller.focus();
    await page.keyboard.press("End");
    await expect.poll(() => scroller.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
    await expect
      .poll(() =>
        scroller.evaluate((el) => {
          const edge = el.getBoundingClientRect().right;
          const last = Math.max(
            ...Array.from(el.querySelectorAll("[data-note-row] > *"), (t) => t.getBoundingClientRect().right),
          );
          return last <= edge + 1;
        }),
      )
      .toBe(true);
  });

  test("no board pushes the document wider than the viewport at 390px", async ({ page }) => {
    // The complement of the checks above: a board can fit its own clipping box
    // and still widen the page. Both are user-visible; neither implies the other.
    await page.goto("/pages");
    await waitForABoard(page);

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scrollWidth).toBeLessThanOrEqual(MOBILE.width);
  });
});
