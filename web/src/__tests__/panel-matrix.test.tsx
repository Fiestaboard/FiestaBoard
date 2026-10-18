import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { PanelBoard } from "@/components/panel/panel-board";

import { FIESTAPANEL_LED_MATRIX } from "./mocks/fiestapanel-models";

afterEach(() => vi.restoreAllMocks());

it("renders calibrated physical LEDs using the monitor density in a smaller browser window", () => {
  vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(1600);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(900);
  vi.spyOn(window.screen, "width", "get").mockReturnValue(1920);
  vi.spyOn(window.screen, "height", "get").mockReturnValue(1080);
  const props = {
    model: FIESTAPANEL_LED_MATRIX,
    message: "ALL CELLS",
    animationsEnabled: false,
    deviceType: "panel" as const,
    notesWide: 1,
    notesTall: 1,
    rows: 12,
    cols: 29,
    boardColor: "black" as const,
    code62Glyph: "heart" as const,
    diagonalInches: 55,
    calibration: 1.1,
    matrixSizing: "true_size" as const,
    matrixPitch: 4,
  };
  const { rerender } = render(<PanelBoard {...props} />);
  const face = screen.getByTestId("panel-matrix").lastElementChild as HTMLElement;
  const expectedPitch = (Math.hypot(1920, 1080) / (55 * 25.4)) * 4 * 1.1;
  expect(face.style.transform).toBe(`scale(${expectedPitch / 9})`);
  expect(parseFloat(face.style.left)).toBeCloseTo((1600 - 192 * expectedPitch) / 2);
  rerender(<PanelBoard {...props} calibration={1} />);
  expect(face.style.transform).toBe(`scale(${((Math.hypot(1920, 1080) / (55 * 25.4)) * 4) / 9})`);
});
