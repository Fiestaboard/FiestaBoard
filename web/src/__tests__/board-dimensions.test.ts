import { describe, expect, it } from "vitest";

import {
  isNoteArray,
  MAX_NOTES_PER_AXIS,
  NOTE_ARRAY_PRESETS,
  NOTE_COLS,
  NOTE_ROWS,
  noteArrayDimensions,
  resolveDimensions,
} from "@/lib/board-dimensions";

// =============================================================================
// Constants
// =============================================================================

describe("constants", () => {
  it("NOTE_ROWS equals 3", () => {
    expect(NOTE_ROWS).toBe(3);
  });

  it("NOTE_COLS equals 15", () => {
    expect(NOTE_COLS).toBe(15);
  });

  it("MAX_NOTES_PER_AXIS equals 8", () => {
    expect(MAX_NOTES_PER_AXIS).toBe(8);
  });
});

// =============================================================================
// NOTE_ARRAY_PRESETS — preset math for all 5 presets
// =============================================================================

describe("NOTE_ARRAY_PRESETS", () => {
  it('preset "2_wide" has correct values and computed dims', () => {
    const p = NOTE_ARRAY_PRESETS.find((x) => x.id === "2_wide");
    expect(p).toBeDefined();
    expect(p!.notes_wide).toBe(2);
    expect(p!.notes_tall).toBe(1);
    expect(noteArrayDimensions(p!.notes_wide, p!.notes_tall)).toEqual({ rows: 3, cols: 30 });
  });

  it('preset "4_wide" has correct values and computed dims', () => {
    const p = NOTE_ARRAY_PRESETS.find((x) => x.id === "4_wide");
    expect(p).toBeDefined();
    expect(p!.notes_wide).toBe(4);
    expect(p!.notes_tall).toBe(1);
    expect(noteArrayDimensions(p!.notes_wide, p!.notes_tall)).toEqual({ rows: 3, cols: 60 });
  });

  it('preset "2_tall" has correct values and computed dims', () => {
    const p = NOTE_ARRAY_PRESETS.find((x) => x.id === "2_tall");
    expect(p).toBeDefined();
    expect(p!.notes_wide).toBe(1);
    expect(p!.notes_tall).toBe(2);
    expect(noteArrayDimensions(p!.notes_wide, p!.notes_tall)).toEqual({ rows: 6, cols: 15 });
  });

  it('preset "4_tall" has correct values and computed dims', () => {
    const p = NOTE_ARRAY_PRESETS.find((x) => x.id === "4_tall");
    expect(p).toBeDefined();
    expect(p!.notes_wide).toBe(1);
    expect(p!.notes_tall).toBe(4);
    expect(noteArrayDimensions(p!.notes_wide, p!.notes_tall)).toEqual({ rows: 12, cols: 15 });
  });

  it('preset "2x2_grid" has correct values and computed dims', () => {
    const p = NOTE_ARRAY_PRESETS.find((x) => x.id === "2x2_grid");
    expect(p).toBeDefined();
    expect(p!.notes_wide).toBe(2);
    expect(p!.notes_tall).toBe(2);
    expect(noteArrayDimensions(p!.notes_wide, p!.notes_tall)).toEqual({ rows: 6, cols: 30 });
  });

  it("all 5 preset IDs exist and are unique", () => {
    expect(NOTE_ARRAY_PRESETS).toHaveLength(5);
    const ids = NOTE_ARRAY_PRESETS.map((p) => p.id);
    const uniqueIds = new Set(ids);
    expect(uniqueIds.size).toBe(5);
    expect(ids).toContain("2_wide");
    expect(ids).toContain("4_wide");
    expect(ids).toContain("2_tall");
    expect(ids).toContain("4_tall");
    expect(ids).toContain("2x2_grid");
  });

  it("preset labels are non-empty strings", () => {
    for (const p of NOTE_ARRAY_PRESETS) {
      expect(typeof p.label).toBe("string");
      expect(p.label.length).toBeGreaterThan(0);
    }
  });
});

// =============================================================================
// noteArrayDimensions — custom W×H
// =============================================================================

describe("noteArrayDimensions", () => {
  it("noteArrayDimensions(1, 1) → { rows: 3, cols: 15 }", () => {
    expect(noteArrayDimensions(1, 1)).toEqual({ rows: 3, cols: 15 });
  });

  it("noteArrayDimensions(3, 2) → { rows: 6, cols: 45 }", () => {
    expect(noteArrayDimensions(3, 2)).toEqual({ rows: 6, cols: 45 });
  });

  it("noteArrayDimensions(8, 8) → { rows: 24, cols: 120 } (max axis)", () => {
    expect(noteArrayDimensions(8, 8)).toEqual({ rows: 24, cols: 120 });
  });

  it("noteArrayDimensions(4, 1) → { rows: 3, cols: 60 }", () => {
    expect(noteArrayDimensions(4, 1)).toEqual({ rows: 3, cols: 60 });
  });
});

// =============================================================================
// resolveDimensions — flagship
// =============================================================================

describe("resolveDimensions — flagship", () => {
  it('resolveDimensions("flagship") → { rows: 6, cols: 22 }', () => {
    expect(resolveDimensions("flagship")).toEqual({ rows: 6, cols: 22 });
  });

  it('resolveDimensions("flagship", 4, 2) → { rows: 6, cols: 22 } (w/h ignored)', () => {
    expect(resolveDimensions("flagship", 4, 2)).toEqual({ rows: 6, cols: 22 });
  });
});

// =============================================================================
// resolveDimensions — note
// =============================================================================

describe("resolveDimensions — note", () => {
  it('resolveDimensions("note") → { rows: 3, cols: 15 }', () => {
    expect(resolveDimensions("note")).toEqual({ rows: 3, cols: 15 });
  });

  it('resolveDimensions("note", 3, 3) → { rows: 3, cols: 15 } (w/h ignored)', () => {
    expect(resolveDimensions("note", 3, 3)).toEqual({ rows: 3, cols: 15 });
  });
});

// =============================================================================
// resolveDimensions — note_array (key acceptance-criteria case)
// =============================================================================

describe("resolveDimensions — note_array", () => {
  it('resolveDimensions("note_array", 4, 1) → { rows: 3, cols: 60 } (acceptance-criteria case)', () => {
    expect(resolveDimensions("note_array", 4, 1)).toEqual({ rows: 3, cols: 60 });
  });

  it('resolveDimensions("note_array", 2, 2) → { rows: 6, cols: 30 }', () => {
    expect(resolveDimensions("note_array", 2, 2)).toEqual({ rows: 6, cols: 30 });
  });

  it('resolveDimensions("note_array", 1, 4) → { rows: 12, cols: 15 }', () => {
    expect(resolveDimensions("note_array", 1, 4)).toEqual({ rows: 12, cols: 15 });
  });

  it('resolveDimensions("note_array") defaults → { rows: 3, cols: 15 } (1×1)', () => {
    expect(resolveDimensions("note_array")).toEqual({ rows: 3, cols: 15 });
  });
});

// =============================================================================
// resolveDimensions — unknown device type fallback
// =============================================================================

describe("resolveDimensions — unknown device type fallback", () => {
  it('resolveDimensions("unknown_device") → { rows: 6, cols: 22 } (flagship fallback)', () => {
    expect(resolveDimensions("unknown_device")).toEqual({ rows: 6, cols: 22 });
  });
});

// =============================================================================
// isNoteArray
// =============================================================================

describe("isNoteArray", () => {
  it('isNoteArray("note_array") → true', () => {
    expect(isNoteArray("note_array")).toBe(true);
  });

  it('isNoteArray("flagship") → false', () => {
    expect(isNoteArray("flagship")).toBe(false);
  });

  it('isNoteArray("note") → false', () => {
    expect(isNoteArray("note")).toBe(false);
  });

  it('isNoteArray("") → false', () => {
    expect(isNoteArray("")).toBe(false);
  });

  it('isNoteArray("NOTE_ARRAY") → false (case-sensitive)', () => {
    expect(isNoteArray("NOTE_ARRAY")).toBe(false);
  });
});
