/**
 * Tests for pageFitForBoard, the web mirror of Python page_fit_for_board
 * (src/pages/fit.py; truth table in tests/test_page_fit.py). An LED board
 * that can draw more than one text size shows a panel page whose grid it
 * produces at another face; anything else keeps the exact sizeKey rule.
 */

import { describe, expect, it } from "vitest";

import { pageFitForBoard, pagesCompatibleWithBoard } from "@/lib/board-dimensions";

const PIXOO = {
  physical_surface: { version: 1, width: 64, height: 64, modes: ["ordinary"] },
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

  it("fits a flexible page on a Pixoo, with no face (it has no grid)", () =>
    expect(pageFitForBoard({ type: "flexible" }, PIXOO)).toEqual({ fits: true, face: null, rows: 0, cols: 0 }));

  it("keeps the exact rule for a board with no producible grids", () =>
    expect(pagesCompatibleWithBoard({ device_type: "note" }, { device_type: "note_array" })).toBe(false));

  it("enforces both flexible board and technology restrictions", () => {
    const page = { type: "flexible", targets: { boards: ["desk"], technology: ["led_matrix"] } };
    expect(pageFitForBoard(page, { ...PIXOO, id: "other", device_model: "divoom_pixoo64" }).fits).toBe(false);
    expect(pageFitForBoard(page, { id: "desk", device_type: "flagship", output: "vestaboard" }).fits).toBe(false);
    expect(pageFitForBoard(page, { ...PIXOO, id: "desk", device_model: "divoom_pixoo64" }).fits).toBe(true);
  });

  it("does not guess unknown technology, and empty target lists restrict nothing", () => {
    expect(pageFitForBoard({ type: "flexible", targets: { technology: ["led_matrix"] } }, PIXOO).fits).toBe(false);
    expect(pageFitForBoard({ type: "flexible", targets: { boards: [], technology: [] } }, PIXOO).fits).toBe(true);
  });
});

it("refuses flexible pixels without adapter support while keeping the legacy grid valid", () => {
  const board = { ...PIXOO, device_model: "divoom_pixoo64", physical_surface: undefined };
  expect(pageFitForBoard({ type: "flexible" }, board)).toMatchObject({ fits: false, reason: "physicalFrame" });
  expect(pageFitForBoard({ type: "template", device_type: "panel", grid_rows: 8, grid_cols: 10 }, board).fits).toBe(
    true,
  );
  expect(
    pageFitForBoard(
      { type: "flexible" },
      { ...board, physical_surface: { version: 1, width: 64, height: 64, modes: ["ordinary"] } },
    ).fits,
  ).toBe(true);
});

it("admits the effective cell-only path of an integer pixel output", () => {
  expect(
    pageFitForBoard(
      { type: "flexible" },
      { ...PIXOO, device_model: "divoom_pixoo64", physical_surface: undefined, flexible_page_support: "cells" },
    ).fits,
  ).toBe(true);
});
