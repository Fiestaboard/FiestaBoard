import { describe, expect, it } from "vitest";

import {
  bandLabel,
  bandText,
  BIG_BOARD_MAX_FIT_COLUMNS,
  deriveRowBands,
  duplicateBand,
  isBigBoard,
  lineOverflows,
  moveBand,
  noteSeamMarks,
  rowsPastBoard,
  seamStraddles,
  usedLineCount,
  wrapRowsShort,
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

  it("shortens a long variable name like any label, and bandText keeps it whole for the tooltip (UX-3-1)", () => {
    expect(bandLabel("{{date_time.day_of_week}}")).toBe("date_time.da…");
    expect(bandText("{{date_time.day_of_week}}")).toBe("date_time.day_of_week");
    expect(bandText("{red} NOW POURING COLD BREW")).toBe("NOW POURING COLD BREW");
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

describe("rowsPastBoard (W-1)", () => {
  it("keeps the hub's beyond_board problems in its own words", () => {
    expect(
      rowsPastBoard({
        valid: false,
        cols: 22,
        rows: 6,
        errors: [
          { line: 4, column: 22, message: "too long", code: "line_too_long", max_length: 24 },
          {
            line: 5,
            column: 0,
            message: "Line 5 wraps past the board's 6 rows · 1 row won't show",
            code: "beyond_board",
            max_length: null,
          },
        ],
      }),
    ).toEqual([{ line: 5, message: "Line 5 wraps past the board's 6 rows · 1 row won't show", kind: "beyond_board" }]);
    expect(rowsPastBoard(undefined)).toEqual([]);
  });

  // FABLE-2659: a wrap a line typed below stops short loses rows the same way.
  it("keeps a wrap stopped by a line below as its own kind", () => {
    expect(
      rowsPastBoard({
        valid: false,
        cols: 22,
        rows: 6,
        errors: [
          {
            line: 4,
            column: 0,
            message: "Line 4 wraps into line 5 · 2 rows won't show",
            code: "wrap_stopped",
            max_length: null,
          },
        ],
      }),
    ).toEqual([{ line: 4, message: "Line 4 wraps into line 5 · 2 rows won't show", kind: "wrap_stopped" }]);
  });
});

describe("wrapRowsShort (W-1)", () => {
  const overflow = { line: 5, columns: 46, maxColumns: 22, cut: 24 };
  const lines = ["", "", "", "HELLO WORLD", "LUNCH AT NOON TODAY FOR EVERYONE IN THE OFFICE", ""];

  it("counts the rows a wrap needs that the board does not have", () => {
    // 46 columns need 3 rows; line 5 has itself and the blank row 6.
    expect(wrapRowsShort(overflow, lines, [], 6)).toBe(1);
  });

  it("is 0 when blank rows below take the whole wrap", () => {
    expect(wrapRowsShort({ ...overflow, line: 2 }, ["", lines[4], "", "", "", ""], [], 6)).toBe(0);
  });

  it("never refuses a line whose variables may be shorter today", () => {
    expect(wrapRowsShort({ ...overflow, line: 6 }, ["", "", "", "", "", "{{news.headline}} TODAY"], [], 6)).toBe(0);
  });

  it("lets the wrap take a row with a variable below, which may render blank", () => {
    expect(wrapRowsShort({ ...overflow, line: 2 }, ["", lines[4], "{{weather.alert}}", "", "", ""], [], 6)).toBe(0);
  });

  it("stops at a row with content below, as the hub's wrap does", () => {
    // Row 3 holds text: line 2 keeps one row of the three it needs.
    expect(wrapRowsShort({ ...overflow, line: 2 }, ["", lines[4], "FOOTER", "", "", ""], [], 6)).toBe(2);
    // ...unless that row wraps too.
    expect(wrapRowsShort({ ...overflow, line: 2 }, ["", lines[4], "FOOTER", "", "", ""], [false, false, true], 6)).toBe(
      0,
    );
  });
});
