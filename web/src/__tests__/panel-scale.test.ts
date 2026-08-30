import { describe, expect, it } from "vitest";

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
  // fail one of the suites.
  it('65" 16:9 → 2×4', () => {
    expect(computeAutofitGrid(65)).toEqual({ notesWide: 2, notesTall: 4 });
  });

  it('43" 16:9 → 1×3', () => {
    expect(computeAutofitGrid(43)).toEqual({ notesWide: 1, notesTall: 3 });
  });

  it('85" 16:9 → 3×6', () => {
    expect(computeAutofitGrid(85)).toEqual({ notesWide: 3, notesTall: 6 });
  });

  it('3" pocket screen → 1×1', () => {
    expect(computeAutofitGrid(3)).toEqual({ notesWide: 1, notesTall: 1 });
  });

  it('55" ultrawide 21:9 → 2×3', () => {
    expect(computeAutofitGrid(55, 21, 9)).toEqual({ notesWide: 2, notesTall: 3 });
  });

  it('55" portrait 9:16 → 1×7', () => {
    expect(computeAutofitGrid(55, 9, 16)).toEqual({ notesWide: 1, notesTall: 7 });
  });

  it('40" 4:3 signage → 1×3', () => {
    expect(computeAutofitGrid(40, 4, 3)).toEqual({ notesWide: 1, notesTall: 3 });
  });

  it("clamps a gigantic screen to 8 blocks per axis", () => {
    expect(computeAutofitGrid(400)).toEqual({ notesWide: 8, notesTall: 8 });
  });

  it("throws on non-positive inputs", () => {
    expect(() => computeAutofitGrid(0)).toThrow();
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
