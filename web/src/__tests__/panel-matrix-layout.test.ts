import { describe, expect, it } from "vitest";

import { panelMatrixLayout } from "@/lib/panel-matrix-layout";

describe("matrix presentation", () => {
  it("keeps the original pixel geometry when filling or fitting", () => {
    for (const mode of ["fill_tv", "fit_panel"] as const) {
      expect(panelMatrixLayout(192, 96, 1920, 1080, mode, 55, 6)).toEqual({ pitch: 10, x: 0, y: 60 });
    }
  });
  it("uses physical screen width and caps large matrices to the viewport", () => {
    expect(panelMatrixLayout(192, 96, 1920, 1080, "true_size", 55, 5).pitch).toBeCloseTo(7.88442, 4);
    expect(panelMatrixLayout(192, 96, 1920, 1080, "true_size", 75, 5).pitch).toBeCloseTo(5.78191, 4);
    expect(panelMatrixLayout(192, 96, 1920, 1080, "true_size", 32, 20).pitch).toBe(10);
  });
});

it("applies calibration before the no-crop cap", () => {
  expect(panelMatrixLayout(192, 96, 1920, 1080, "true_size", 75, 5, { calibration: 1.1 }).pitch).toBeCloseTo(
    6.360101,
    4,
  );
  expect(panelMatrixLayout(192, 96, 1920, 1080, "true_size", 32, 20, { calibration: 1.15 }).pitch).toBe(10);
});
it("keeps physical LEDs the same size when a browser window shrinks", () => {
  const screen = { screenWidth: 1920, screenHeight: 1080 };
  const full = panelMatrixLayout(64, 32, 1920, 1080, "true_size", 55, 5, screen);
  const windowed = panelMatrixLayout(64, 32, 960, 540, "true_size", 55, 5, screen);
  expect(windowed.pitch).toBeCloseTo(full.pitch);
  expect(windowed.x).toBeCloseTo((960 - 64 * full.pitch) / 2);
});
