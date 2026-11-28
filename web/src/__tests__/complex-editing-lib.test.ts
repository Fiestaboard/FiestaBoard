import { describe, expect, it } from "vitest";

import {
  bandPartName,
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

describe("bandPartName (W-10)", () => {
  it("names a run for its first data part: integration, formula, colour", () => {
    expect(bandPartName(["COUNTDOWN: {{countdown.days}}"])).toBe("countdown");
    expect(bandPartName(["{{date_time.day_of_week}}"])).toBe("date_time");
    expect(bandPartName(["{{weather:home.temp|pad:3}}"])).toBe("weather");
    expect(bandPartName(["{{news.headline|wrap}}"])).toBe("news");
    expect(bandPartName(["{{ rss.title | wrap }}"])).toBe("rss");
    expect(bandPartName(["TONIGHT", '{{= "LUNCH: " & random.pick }}'])).toBe("random");
    expect(bandPartName(['{{= FOREACH(FILTER(x, y), "z") }}'])).toBe("FOREACH");
    expect(bandPartName(["{{red}}{{orange}}"])).toBe("red");
    expect(bandPartName(["{red} NOW POURING"])).toBe("red");
  });

  it("has no name for a character code, and is null for plain text, spacing and wrapped text", () => {
    expect(bandPartName(["{63}{64}"])).toBe("");
    expect(bandPartName(["DEN TV · FAMILY BOARD"])).toBeNull();
    expect(bandPartName(["A{{fill_space}}B", "{{HELLO THERE|wrap}}"])).toBeNull();
  });
});

describe("deriveRowBands", () => {
  it("bands only the runs of non-blank rows that hold data, named for the part (W-10)", () => {
    const bands = deriveRowBands(
      ["HEADER", "", "A {{weather.temp}}", "B", "C", "", "", "TICKER", "{{red}}", "OVER {{x.y}}"],
      9,
    );
    expect(bands.map((b) => [b.start, b.end, b.label, b.name])).toEqual([
      [3, 5, "weather", "weather"],
      [8, 9, "red", "red"],
    ]);
    expect(new Set(bands.map((b) => b.id)).size).toBe(2);
  });

  it("shortens a long part name for the gutter and keeps it whole for the tooltip", () => {
    const [band] = deriveRowBands(["{{date_time_long_name.day}}"], 1);
    expect(band.label).toBe("date_time_lo…");
    expect(band.name).toBe("date_time_long_name");
  });

  it("returns nothing for an empty or plain-text template", () => {
    expect(deriveRowBands(["", "  ", ""], 3)).toEqual([]);
    expect(deriveRowBands(["HELLO", "", "WORLD"], 3)).toEqual([]);
  });
});

const state = (lines: string[]) => ({
  lines,
  alignments: lines.map((_, i) => (i % 2 ? "left" : "center") as "left" | "center"),
  wraps: lines.map((_, i) => i === 0),
});

describe("moveBand", () => {
  // Bands are data rows (W-10).
  const lines = ["{{h.x}}", "", "{{a1.x}}", "{{a2.x}}", "", "{{b1.x}}"];
  const bands = deriveRowBands(lines, 6);

  it("swaps a band with the band above, keeping the gap and per-line metadata", () => {
    const s = state(lines);
    const next = moveBand(s, bands, bands[1].id, "up")!;
    expect(next.lines).toEqual(["{{a1.x}}", "{{a2.x}}", "", "{{h.x}}", "", "{{b1.x}}"]);
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
    expect(next.lines).toEqual(["{{h.x}}", "", "{{b1.x}}", "", "{{a1.x}}", "{{a2.x}}"]);
  });

  it("returns null at the edges or for an unknown band", () => {
    expect(moveBand(state(lines), bands, bands[0].id, "up")).toBeNull();
    expect(moveBand(state(lines), bands, bands[2].id, "down")).toBeNull();
    expect(moveBand(state(lines), bands, "nope", "up")).toBeNull();
  });
});

describe("duplicateBand", () => {
  it("inserts a copy after the band when trailing blank rows can absorb it", () => {
    const lines = ["{{a1.x}}", "{{a2.x}}", "", "{{b.x}}", "", "", "", ""];
    const bands = deriveRowBands(lines, 8);
    const next = duplicateBand(state(lines), bands, bands[0].id, 8)!;
    expect(next.lines).toEqual(["{{a1.x}}", "{{a2.x}}", "", "{{a1.x}}", "{{a2.x}}", "", "{{b.x}}", ""]);
    expect(next.lines).toHaveLength(8);
    expect(next.wraps.slice(0, 5)).toEqual([true, false, false, true, false]);
  });

  it("refuses when the board has no room", () => {
    const lines = ["{{a1.x}}", "{{a2.x}}", "", "{{b.x}}"];
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
    ).toEqual([{ line: 5, message: "Line 5 wraps past the board's 6 rows · 1 row won't show" }]);
    expect(rowsPastBoard(undefined)).toEqual([]);
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
