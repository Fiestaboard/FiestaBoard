import { describe, expect, it } from "vitest";

import {
  NOTE_COL_PITCH_IN,
  NOTE_ROW_PITCH_IN,
  PANEL_PHYSICAL_WIDTH_IN,
  panelAutofitScale,
  panelBoardScale,
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

describe("panelBoardScale", () => {
  it("scales a flagship to its real 41.2 inch width", () => {
    const scale = panelBoardScale({
      screenWidthPx: 1920,
      screenHeightPx: 1080,
      diagonalInches: 55,
      deviceType: "flagship",
      boardNaturalWidthPx: 1600,
      calibration: 1,
    });
    // 41.2in × 40.05ppi / 1600px ≈ 1.031
    expect(scale).toBeCloseTo((41.2 * screenPpi(1920, 1080, 55)) / 1600, 6);
    expect(scale).toBeCloseTo(1.031, 2);
  });

  it("uses the note's 24.5 inch width", () => {
    const scale = panelBoardScale({
      screenWidthPx: 1920,
      screenHeightPx: 1080,
      diagonalInches: 43,
      deviceType: "note",
      boardNaturalWidthPx: 1000,
      calibration: 1,
    });
    expect(scale).toBeCloseTo((24.5 * screenPpi(1920, 1080, 43)) / 1000, 6);
  });

  it("applies the calibration nudge multiplicatively", () => {
    const base = {
      screenWidthPx: 1920,
      screenHeightPx: 1080,
      diagonalInches: 55,
      deviceType: "flagship" as const,
      boardNaturalWidthPx: 1600,
    };
    const unit = panelBoardScale({ ...base, calibration: 1 });
    const nudged = panelBoardScale({ ...base, calibration: 0.9 });
    expect(nudged).toBeCloseTo(unit * 0.9, 6);
  });

  it("throws when the measured board width is not positive", () => {
    expect(() =>
      panelBoardScale({
        screenWidthPx: 1920,
        screenHeightPx: 1080,
        diagonalInches: 55,
        deviceType: "flagship",
        boardNaturalWidthPx: 0,
        calibration: 1,
      }),
    ).toThrow();
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

  it("anchors flap width to the Note column pitch", () => {
    const ppi = screenPpi(1920, 1080, 65);
    const expectedTrue = (30 * NOTE_COL_PITCH_IN * ppi) / 1600;
    // Enormous grid height → the stretch factor clamps to 1 (never shrinks).
    const scale = panelAutofitScale({ ...base, gridHeightPx: 100000 });
    expect(scale).toBeCloseTo(expectedTrue, 6);
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

  it("never shrinks below true size to fill", () => {
    // On a tiny screen the true-size grid overflows; stretch clamps to 1.
    const ppi = screenPpi(1920, 1080, 20);
    const trueScale = (30 * NOTE_COL_PITCH_IN * ppi) / base.gridWidthPx;
    const scale = panelAutofitScale({ ...base, diagonalInches: 20 });
    expect(scale).toBeCloseTo(trueScale, 6);
  });

  it("applies calibration multiplicatively", () => {
    const unit = panelAutofitScale(base);
    const nudged = panelAutofitScale({ ...base, calibration: 0.9 });
    expect(nudged).toBeCloseTo(unit * 0.9, 6);
  });

  it("row pitch constant follows the renderer geometry", () => {
    expect(NOTE_ROW_PITCH_IN).toBeCloseTo(NOTE_COL_PITCH_IN * (1.145 / 0.845), 6);
  });

  it("throws on non-positive grid measurements", () => {
    expect(() => panelAutofitScale({ ...base, gridWidthPx: 0 })).toThrow();
  });
});
