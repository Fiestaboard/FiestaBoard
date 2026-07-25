/**
 * Tests for the page<->board size-compatibility helpers (issue #1249).
 *
 * These mirror the Python predicate in src/devices.py exactly — see
 * tests/test_devices.py (TestSizeKey / TestPagesCompatibleWithBoard) for the
 * backend truth table this must stay in sync with.
 */

import { describe, expect, it } from "vitest";

import { classifyDimensions, pagesCompatibleWithBoard, sizeKey } from "@/lib/board-dimensions";

describe("sizeKey", () => {
  it("flagship resolves to flagship:6x22", () => {
    expect(sizeKey("flagship")).toBe("flagship:6x22");
  });

  it("note resolves to note:3x15", () => {
    expect(sizeKey("note")).toBe("note:3x15");
  });

  it("note_array folds in resolved dimensions", () => {
    expect(sizeKey("note_array", 2, 2)).toBe("note_array:6x30");
    expect(sizeKey("note_array", 2, 1)).toBe("note_array:3x30");
    expect(sizeKey("note_array", 1, 4)).toBe("note_array:12x15");
    expect(sizeKey("note_array")).toBe("note_array:3x15");
  });

  it("flagship ignores note counts", () => {
    expect(sizeKey("flagship", 3, 2)).toBe("flagship:6x22");
  });

  it("unknown device type falls back to flagship (family and dims)", () => {
    expect(sizeKey("mystery")).toBe("flagship:6x22");
  });
});

describe("pagesCompatibleWithBoard", () => {
  const board = (device_type: string, notes_wide = 1, notes_tall = 1) => ({
    device_type,
    notes_wide,
    notes_tall,
  });

  it("flagship page fits flagship board", () => {
    expect(pagesCompatibleWithBoard(board("flagship"), board("flagship"))).toBe(true);
  });

  it("flagship page does not fit note board", () => {
    expect(pagesCompatibleWithBoard(board("flagship"), board("note"))).toBe(false);
  });

  it("note page fits note board", () => {
    expect(pagesCompatibleWithBoard(board("note"), board("note"))).toBe(true);
  });

  it("note page does not fit a 1x1 note array (family mismatch at same dims)", () => {
    expect(pagesCompatibleWithBoard(board("note"), board("note_array", 1, 1))).toBe(false);
  });

  it("note arrays must match the W×H grid exactly", () => {
    expect(pagesCompatibleWithBoard(board("note_array", 2, 2), board("note_array", 2, 2))).toBe(true);
    expect(pagesCompatibleWithBoard(board("note_array", 2, 2), board("note_array", 2, 1))).toBe(false);
    expect(pagesCompatibleWithBoard(board("note_array", 2, 2), board("note_array", 4, 1))).toBe(false);
  });

  it("missing geometry defaults to a flagship", () => {
    expect(pagesCompatibleWithBoard({}, board("flagship"))).toBe(true);
    expect(pagesCompatibleWithBoard({ device_type: "note" }, {})).toBe(false);
  });
});

describe("classifyDimensions", () => {
  it("classifies the flagship size", () => {
    expect(classifyDimensions(6, 22)).toEqual({ device_type: "flagship", rows: 6, cols: 22 });
  });

  it("classifies the note size (never a 1x1 array)", () => {
    expect(classifyDimensions(3, 15)).toEqual({ device_type: "note", rows: 3, cols: 15 });
  });

  it("classifies note-array grids with preset matching", () => {
    expect(classifyDimensions(6, 30)).toEqual({
      device_type: "note_array",
      rows: 6,
      cols: 30,
      notes_wide: 2,
      notes_tall: 2,
      matched_preset: "2×2 grid",
    });
    expect(classifyDimensions(9, 45)).toMatchObject({
      device_type: "note_array",
      notes_wide: 3,
      notes_tall: 3,
      matched_preset: null,
    });
  });

  it("throws for unclassifiable grids", () => {
    expect(() => classifyDimensions(5, 20)).toThrow(/unclassifiable/);
    expect(() => classifyDimensions(0, 15)).toThrow(/unclassifiable/);
    // 9 notes on an axis exceeds MAX_NOTES_PER_AXIS
    expect(() => classifyDimensions(3, 135)).toThrow(/unclassifiable/);
  });
});
