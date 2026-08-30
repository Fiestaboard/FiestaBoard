import { describe, expect, it } from "vitest";

import { NOTE_COL_PITCH_IN, PANEL_PHYSICAL_WIDTH_IN, panelAutofitScale, screenPpi } from "@/lib/panel-scale";

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

  it("throws on non-positive grid measurements", () => {
    expect(() => panelAutofitScale({ ...base, gridWidthPx: 0 })).toThrow();
  });
});
