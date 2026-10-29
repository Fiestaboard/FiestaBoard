/**
 * Tests for pageFitForBoard, the web mirror of Python page_fit_for_board
 * (src/pages/fit.py; truth table in tests/test_page_fit.py). An LED board
 * that can draw more than one text size shows a panel page whose grid it
 * produces at another face; anything else keeps the exact sizeKey rule.
 */

import { describe, expect, it } from "vitest";

import { pageFitForBoard, pagesCompatibleWithBoard } from "@/lib/board-dimensions";

const PIXOO = {
  device_type: "panel",
  grid_rows: 8,
  grid_cols: 10,
  producible_grids: { "5x7": [8, 10] as [number, number], "3x5": [10, 16] as [number, number] },
  led_layout: { font: "5x7" },
};

describe("pageFitForBoard", () => {
  it("fits a 10x16 page on an 8x10 Pixoo at 3x5", () =>
    expect(pageFitForBoard({ device_type: "panel", grid_rows: 10, grid_cols: 16 }, PIXOO)).toEqual({
      fits: true,
      face: "3x5",
      rows: 10,
      cols: 16,
    }));

  it("takes today's path at the board's own grid", () =>
    expect(pageFitForBoard({ device_type: "panel", grid_rows: 8, grid_cols: 10 }, PIXOO).face).toBeNull());

  it("flags a flagship page on a Pixoo", () =>
    expect(pageFitForBoard({ device_type: "flagship" }, PIXOO)).toMatchObject({ fits: false, rows: 6, cols: 22 }));

  it("keeps the exact rule for a board with no producible grids", () =>
    expect(pagesCompatibleWithBoard({ device_type: "note" }, { device_type: "note_array" })).toBe(false));
});
