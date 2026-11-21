import { describe, expect, it } from "vitest";

import {
  bandLabel,
  BIG_BOARD_MAX_FIT_COLUMNS,
  deriveRowBands,
  duplicateBand,
  isBigBoard,
  lineOverflows,
  moveBand,
  noteSeamMarks,
  seamStraddles,
  truncationLines,
  usedLineCount,
} from "@/lib/complex-editing";

describe("isBigBoard", () => {
  it("is false for boards that fit the desktop preview at Tile sm", () => {
    expect(isBigBoard({ rows: 6, cols: 22 })).toBe(false);
    expect(isBigBoard({ rows: 12, cols: BIG_BOARD_MAX_FIT_COLUMNS })).toBe(false);
  });

  it("is true past the Tile sm fit or past 12 rows", () => {
    expect(isBigBoard({ rows: 24, cols: 96 })).toBe(true);
    expect(isBigBoard({ rows: 6, cols: BIG_BOARD_MAX_FIT_COLUMNS + 1 })).toBe(true);
    expect(isBigBoard({ rows: 13, cols: 22 })).toBe(true);
  });
});

describe("bandLabel", () => {
  it("strips template markup and keeps readable words", () => {
    expect(bandLabel('{{= PAD("TONIGHT AT ROSA\'S", 48) }} OUTSIDE')).toBe("OUTSIDE");
    expect(bandLabel("  THIS WEEK  ")).toBe("THIS WEEK");
    expect(bandLabel("{red}{red} NOW POURING COLD BREW")).toBe("NOW POURING…");
  });

  it("falls back to the first variable name, then null", () => {
    expect(bandLabel("{{weather.temp}} {{weather.rain}}")).toBe("weather.temp");
    expect(bandLabel("{63}{64}")).toBeNull();
  });
});

describe("deriveRowBands", () => {
  it("groups consecutive non-blank rows within the board", () => {
    const bands = deriveRowBands(["HEADER", "", "A", "B", "C", "", "", "TICKER", "OVER"], 8);
    expect(bands.map((b) => [b.start, b.end, b.label])).toEqual([
      [1, 1, "HEADER"],
      [3, 5, "A"],
      [8, 8, "TICKER"],
    ]);
    expect(new Set(bands.map((b) => b.id)).size).toBe(3);
  });

  it("returns nothing for an empty template", () => {
    expect(deriveRowBands(["", "  ", ""], 3)).toEqual([]);
  });
});

const state = (lines: string[]) => ({
  lines,
  alignments: lines.map((_, i) => (i % 2 ? "left" : "center") as "left" | "center"),
  wraps: lines.map((_, i) => i === 0),
});

describe("moveBand", () => {
  const lines = ["H", "", "A1", "A2", "", "B1"];
  const bands = deriveRowBands(lines, 6);

  it("swaps a band with the band above, keeping the gap and per-line metadata", () => {
    const s = state(lines);
    const next = moveBand(s, bands, bands[1].id, "up")!;
    expect(next.lines).toEqual(["A1", "A2", "", "H", "", "B1"]);
    expect(next.alignments).toEqual([
      s.alignments[2],
      s.alignments[3],
      s.alignments[1],
      s.alignments[0],
      s.alignments[4],
      s.alignments[5],
    ]);
    expect(next.wraps).toEqual([false, false, false, true, false, false]);
    expect(s.lines).toEqual(lines);
  });

  it("swaps with the band below", () => {
    const next = moveBand(state(lines), bands, bands[1].id, "down")!;
    expect(next.lines).toEqual(["H", "", "B1", "", "A1", "A2"]);
  });

  it("returns null at the edges or for an unknown band", () => {
    expect(moveBand(state(lines), bands, bands[0].id, "up")).toBeNull();
    expect(moveBand(state(lines), bands, bands[2].id, "down")).toBeNull();
    expect(moveBand(state(lines), bands, "nope", "up")).toBeNull();
  });
});

describe("duplicateBand", () => {
  it("inserts a copy after the band when trailing blank rows can absorb it", () => {
    const lines = ["A1", "A2", "", "B", "", "", "", ""];
    const bands = deriveRowBands(lines, 8);
    const next = duplicateBand(state(lines), bands, bands[0].id, 8)!;
    expect(next.lines).toEqual(["A1", "A2", "", "A1", "A2", "", "B", ""]);
    expect(next.lines).toHaveLength(8);
    expect(next.wraps.slice(0, 5)).toEqual([true, false, false, true, false]);
  });

  it("refuses when the board has no room", () => {
    const lines = ["A1", "A2", "", "B"];
    const bands = deriveRowBands(lines, 4);
    expect(duplicateBand(state(lines), bands, bands[0].id, 4)).toBeNull();
    expect(duplicateBand(state(lines), bands, "missing", 4)).toBeNull();
  });
});

describe("lineOverflows", () => {
  it("keeps only hub line_too_long problems with a measured length", () => {
    expect(
      lineOverflows(
        {
          valid: false,
          cols: 22,
          rows: 6,
          errors: [
            { line: 4, column: 22, message: "too long", code: "line_too_long", max_length: 24 },
            { line: 2, column: 0, message: "unknown", code: "unknown_field", max_length: null },
            { line: 5, column: 22, message: "too long", code: "line_too_long", max_length: null },
          ],
        },
        22,
      ),
    ).toEqual([{ line: 4, columns: 24, maxColumns: 22, cut: 2 }]);
  });

  it("is empty without a response", () => {
    expect(lineOverflows(undefined, 22)).toEqual([]);
  });
});

describe("truncationLines", () => {
  it("measures rendered rows and marks hub-validated overflow", () => {
    const lines = truncationLines(
      ["AB  ", "", "WIDE"],
      [{ line: 3, columns: 98, maxColumns: 96, cut: 2 }],
      3,
      (o) => `Row ${o.line} cut ${o.cut}`,
    );
    expect(lines).toEqual([
      { row: 1, length: 2 },
      { row: 2, length: 0 },
      { row: 3, length: 98, overflow: { column: 96, count: 2, description: "Row 3 cut 2" } },
    ]);
  });

  it("measures a row in drawn tiles, as the hub's render report does (BB-E-2)", () => {
    const lines = truncationLines(["{63}{64}{65}{66} HOT{/}", "{63}" + "{64}".repeat(11)], [], 2, () => "");
    expect(lines).toEqual([
      { row: 1, length: 8 },
      { row: 2, length: 12 },
    ]);
  });

  it("measures extended markup as the board draws it: a span its cells, an icon one tile", () => {
    const lines = truncationLines(["{red:HOT} X", "{icon:sun}"], [], 2, () => "");
    expect(lines).toEqual([
      { row: 1, length: 5 },
      { row: 2, length: 1 },
    ]);
  });

  it("ignores overflow past the board's rows", () => {
    expect(truncationLines([], [{ line: 9, columns: 30, maxColumns: 22, cut: 8 }], 2, () => "")).toEqual([
      { row: 1, length: 0 },
      { row: 2, length: 0 },
    ]);
  });
});

describe("noteSeamMarks", () => {
  it("marks every column seam of a note array", () => {
    expect(noteSeamMarks(3, "SEAM").map((m) => [m.type, m.column, m.label])).toEqual([
      ["seam", 15, "SEAM"],
      ["seam", 30, "SEAM"],
    ]);
    expect(noteSeamMarks(1, "SEAM")).toEqual([]);
  });
});

describe("seamStraddles", () => {
  it("finds words that run across a Note's column seam", () => {
    const row1 = "GOOD MORNING   FROM ROSA'S".padEnd(30);
    const row2 = "CAPPUCCINO 4.7".padEnd(14) + "5MOCHA".padEnd(16);
    expect(seamStraddles([row1, row2], 2)).toEqual([{ row: 2, column: 15, word: "4.75MOCHA" }]);
  });

  it("is empty for a single Note wide array", () => {
    expect(seamStraddles(["ABCDEFGHIJKLMNOPQRS"], 1)).toEqual([]);
  });
});

describe("usedLineCount (BB-E-18)", () => {
  it("counts rows up to the last one with content", () => {
    expect(usedLineCount(["HELLO", "", "", "", "", ""])).toBe(1);
    expect(usedLineCount(["", "", "MIDDLE", "  ", ""])).toBe(3);
    expect(usedLineCount(["A", "", "B"])).toBe(3);
  });

  it("is zero for an empty template", () => {
    expect(usedLineCount([])).toBe(0);
    expect(usedLineCount(["", " ", ""])).toBe(0);
  });
});
