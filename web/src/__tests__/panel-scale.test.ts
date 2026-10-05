import { describe, expect, it } from "vitest";

import { MAX_GRID_COLS, MAX_GRID_ROWS, MIN_GRID_COLS, MIN_GRID_ROWS } from "@/lib/board-dimensions";
import {
  computeAutofitGrid,
  NOTE_COL_PITCH_IN,
  PANEL_PHYSICAL_WIDTH_IN,
  panelAutofitScale,
  screenPpi,
} from "@/lib/panel-scale";

describe("screenPpi", () => {
  it("computes CSS pixels per inch from resolution and diagonal", () => {
    // 1920×1080 across a 55" diagonal → hypot(1920,1080)/55 ≈ 40.05
    expect(screenPpi(1920, 1080, 55)).toBeCloseTo(40.05, 2);
  });

  it("throws on non-positive inputs", () => {
    expect(() => screenPpi(0, 1080, 55)).toThrow();
    expect(() => screenPpi(1920, 1080, 0)).toThrow();
    expect(() => screenPpi(1920, -1, 55)).toThrow();
  });
});

describe("computeAutofitGrid (parity with src/panels/autofit.py)", () => {
  // These example cases are mirrored VERBATIM in
  // tests/test_panels_autofit.py — the backend sizes the board it actually
  // creates with the Python twin, so drift between the two mirrors must
  // fail one of the suites. The grid is fit per character (rows × cols),
  // not in whole 15×3 Note blocks.
  it("returns rows and cols", () => {
    expect(computeAutofitGrid(55)).toEqual({ rows: 12, cols: 29 });
  });

  it('a 55" TV fills the width a Note-block fit wasted', () => {
    expect(computeAutofitGrid(55).cols).toBe(29);
  });

  it("columns are not rounded to Note blocks", () => {
    expect(computeAutofitGrid(65)).toEqual({ rows: 14, cols: 34 });
  });

  it("rows are not rounded to Note blocks", () => {
    expect(computeAutofitGrid(32)).toEqual({ rows: 7, cols: 17 });
  });

  it('43" TV', () => {
    expect(computeAutofitGrid(43)).toEqual({ rows: 9, cols: 22 });
  });

  it('85" TV', () => {
    expect(computeAutofitGrid(85)).toEqual({ rows: 18, cols: 45 });
  });

  it('3" pocket screen gets a Note-sized grid', () => {
    expect(computeAutofitGrid(3)).toEqual({ rows: MIN_GRID_ROWS, cols: MIN_GRID_COLS });
  });

  it("a screen narrower than a Note keeps Note width", () => {
    expect(computeAutofitGrid(24)).toEqual({ rows: 5, cols: MIN_GRID_COLS });
  });

  it("the largest supported screen fits without clamping", () => {
    expect(computeAutofitGrid(200)).toEqual({ rows: 44, cols: 106 });
  });

  it("a gigantic screen clamps to the grid maximum", () => {
    expect(computeAutofitGrid(500)).toEqual({ rows: MAX_GRID_ROWS, cols: MAX_GRID_COLS });
  });

  it('ultrawide 21:9 55"', () => {
    expect(computeAutofitGrid(55, 21, 9)).toEqual({ rows: 9, cols: 30 });
  });

  it('portrait 9:16 55"', () => {
    expect(computeAutofitGrid(55, 9, 16)).toEqual({ rows: 21, cols: 16 });
  });

  it('portrait 9:16 200"', () => {
    expect(computeAutofitGrid(200, 9, 16)).toEqual({ rows: 78, cols: 60 });
  });

  it('4:3 signage 40"', () => {
    expect(computeAutofitGrid(40, 4, 3)).toEqual({ rows: 10, cols: 19 });
  });

  it("default aspect is 16:9", () => {
    expect(computeAutofitGrid(65)).toEqual(computeAutofitGrid(65, 16, 9));
  });

  it("rejects a non-positive diagonal", () => {
    expect(() => computeAutofitGrid(0)).toThrow();
    expect(() => computeAutofitGrid(-1)).toThrow();
  });

  it("rejects a non-positive aspect", () => {
    expect(() => computeAutofitGrid(55, 0, 9)).toThrow();
    expect(() => computeAutofitGrid(55, 16, -1)).toThrow();
  });
});

describe("PANEL_PHYSICAL_WIDTH_IN", () => {
  it("carries the published Vestaboard unit widths", () => {
    expect(PANEL_PHYSICAL_WIDTH_IN.flagship).toBe(41.2);
    expect(PANEL_PHYSICAL_WIDTH_IN.note).toBe(24.5);
  });
});

describe("panelAutofitScale", () => {
  const base = {
    screenWidthPx: 1920,
    screenHeightPx: 1080,
    diagonalInches: 65,
    cols: 30,
    gridWidthPx: 1600,
    gridHeightPx: 866,
    calibration: 1,
  };

  it("anchors flap width to the Note column pitch (within the fill stretch)", () => {
    // Spec-level bound: a rendered column is never narrower than the real
    // Note pitch at this screen's ppi and never more than 10% wider.
    const ppi = screenPpi(1920, 1080, 65);
    const physicalColWidthPx = NOTE_COL_PITCH_IN * ppi;
    const scale = panelAutofitScale(base);
    const renderedColWidthPx = (base.gridWidthPx / base.cols) * scale;
    expect(renderedColWidthPx).toBeGreaterThanOrEqual(physicalColWidthPx * (1 - 1e-9));
    expect(renderedColWidthPx).toBeLessThanOrEqual(physicalColWidthPx * 1.1 * (1 + 1e-9));
  });

  it("stretches toward the nearest edge but never beyond 10%", () => {
    const ppi = screenPpi(1920, 1080, 65);
    const trueScale = (30 * NOTE_COL_PITCH_IN * ppi) / base.gridWidthPx;
    const scale = panelAutofitScale(base);
    const stretch = scale / trueScale;
    expect(stretch).toBeGreaterThan(1);
    expect(stretch).toBeLessThanOrEqual(1.1 + 1e-9);
    // the stretched grid must still fit inside the screen
    expect(base.gridWidthPx * scale).toBeLessThanOrEqual(1920 + 1e-6);
    expect(base.gridHeightPx * scale).toBeLessThanOrEqual(1080 + 1e-6);
  });

  it("shrinks to fit when the grid overflows the screen at true size", () => {
    // Auto-fit always picks a grid that fits, so this only happens on a
    // screen smaller than one Note block (3" pocket displays): the whole
    // block must shrink to fit, not render a life-size crop of one corner.
    const ppi = screenPpi(1920, 1080, 3);
    const trueScale = (30 * NOTE_COL_PITCH_IN * ppi) / base.gridWidthPx;
    const scale = panelAutofitScale({ ...base, diagonalInches: 3 });
    expect(scale).toBeLessThan(trueScale);
    // The shrunk grid exactly fits the tighter screen axis and never
    // overflows the other.
    expect(base.gridWidthPx * scale).toBeLessThanOrEqual(1920 + 1e-6);
    expect(base.gridHeightPx * scale).toBeLessThanOrEqual(1080 + 1e-6);
    const fitsExactly =
      Math.abs(base.gridWidthPx * scale - 1920) < 1e-6 || Math.abs(base.gridHeightPx * scale - 1080) < 1e-6;
    expect(fitsExactly).toBe(true);
  });

  it("applies calibration multiplicatively", () => {
    const unit = panelAutofitScale(base);
    const nudged = panelAutofitScale({ ...base, calibration: 0.9 });
    expect(nudged).toBeCloseTo(unit * 0.9, 6);
  });

  it("throws on non-positive grid measurements", () => {
    expect(() => panelAutofitScale({ ...base, gridWidthPx: 0 })).toThrow();
  });
});
