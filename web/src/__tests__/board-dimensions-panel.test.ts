/**
 * The "panel" device type in the app's board-dimension helpers: a FiestaPanel
 * is fit per character, so its grid is an explicit grid_rows × grid_cols, not
 * a multiple of a Note. Mirrors src/devices.py (resolve_dimensions /
 * size_key / pages_compatible_with_board) — see tests/test_devices.py.
 */

import { describe, expect, it } from "vitest";

import {
  ABSOLUTE_MIN_GRID_COLS,
  ABSOLUTE_MIN_GRID_ROWS,
  isPanel,
  MAX_GRID_COLS,
  MAX_GRID_ROWS,
  MIN_GRID_COLS,
  MIN_GRID_ROWS,
  MIN_LED_GRID_COLS,
  MIN_LED_GRID_ROWS,
  pagesCompatibleWithBoard,
  resolveDimensions,
  sizeKey,
} from "@/lib/board-dimensions";

describe("grid bounds", () => {
  it("match src/devices.py", () => {
    expect([MIN_GRID_ROWS, MIN_GRID_COLS, MAX_GRID_ROWS, MAX_GRID_COLS]).toEqual([3, 15, 96, 128]);
  });

  it("an LED board in pixels has a 3x10 floor, the lowest any board goes (src/devices.py)", () => {
    expect([MIN_LED_GRID_ROWS, MIN_LED_GRID_COLS]).toEqual([3, 10]);
    expect([ABSOLUTE_MIN_GRID_ROWS, ABSOLUTE_MIN_GRID_COLS]).toEqual([3, 10]);
  });
});

describe("isPanel", () => {
  it("is true only for the panel device type", () => {
    expect(isPanel("panel")).toBe(true);
    expect(isPanel("note_array")).toBe(false);
    expect(isPanel("flagship")).toBe(false);
  });
});

describe("resolveDimensions — panel", () => {
  it("is the explicit grid", () => {
    expect(resolveDimensions("panel", 1, 1, 12, 29)).toEqual({ rows: 12, cols: 29 });
  });

  it("ignores note counts", () => {
    expect(resolveDimensions("panel", 4, 4, 12, 29)).toEqual({ rows: 12, cols: 29 });
  });

  it("keeps an LED board's 8x10 grid (a Pixoo 64 in the 5x7 face)", () => {
    expect(resolveDimensions("panel", 1, 1, 8, 10)).toEqual({ rows: 8, cols: 10 });
    expect(sizeKey("panel", 1, 1, 8, 10)).toBe("panel:8x10");
  });

  it("clamps each axis into the grid bounds, down to the 3x10 absolute minimum", () => {
    expect(resolveDimensions("panel", 1, 1, 1, 2)).toEqual({ rows: 3, cols: 10 });
    expect(resolveDimensions("panel", 1, 1, 500, 500)).toEqual({ rows: MAX_GRID_ROWS, cols: MAX_GRID_COLS });
  });

  it("resolves a panel with no grid to the minimum grid", () => {
    expect(resolveDimensions("panel")).toEqual({ rows: MIN_GRID_ROWS, cols: MIN_GRID_COLS });
  });

  it("ignores grid arguments for other device types", () => {
    expect(resolveDimensions("flagship", 1, 1, 12, 29)).toEqual({ rows: 6, cols: 22 });
    expect(resolveDimensions("note_array", 2, 1, 12, 29)).toEqual({ rows: 3, cols: 30 });
  });
});

describe("sizeKey — panel", () => {
  it("folds in the grid", () => {
    expect(sizeKey("panel", 1, 1, 12, 29)).toBe("panel:12x29");
  });

  it("a panel without a grid matches no real panel", () => {
    const unsized = sizeKey("panel");
    expect(unsized).not.toBe(sizeKey("panel", 1, 1, MIN_GRID_ROWS, MIN_GRID_COLS));
    expect(unsized).not.toBe(sizeKey("flagship"));
  });
});

describe("pagesCompatibleWithBoard — panel", () => {
  const panel = (grid_rows: number, grid_cols: number) => ({ device_type: "panel", grid_rows, grid_cols });

  it("a panel page fits a panel board of the identical grid", () => {
    expect(pagesCompatibleWithBoard(panel(12, 29), panel(12, 29))).toBe(true);
  });

  it("a panel page does not fit a panel board of another grid", () => {
    expect(pagesCompatibleWithBoard(panel(12, 29), panel(14, 34))).toBe(false);
    expect(pagesCompatibleWithBoard(panel(12, 29), panel(12, 30))).toBe(false);
  });

  it("a panel page does not fit a note array of the same dimensions (family mismatch)", () => {
    const array = { device_type: "note_array", notes_wide: 2, notes_tall: 2 };
    expect(pagesCompatibleWithBoard(panel(6, 30), array)).toBe(false);
    expect(pagesCompatibleWithBoard(array, panel(6, 30))).toBe(false);
  });

  it("a Note page does not fit a Note-sized panel (family mismatch)", () => {
    expect(pagesCompatibleWithBoard({ device_type: "note" }, panel(3, 15))).toBe(false);
  });

  it("null grid fields on a non-panel entity are ignored", () => {
    expect(
      pagesCompatibleWithBoard(
        { device_type: "flagship", grid_rows: null, grid_cols: null },
        { device_type: "flagship" },
      ),
    ).toBe(true);
  });
});
