import { afterEach, describe, expect, it, vi } from "vitest";

import {
  brushToCell,
  cellsToLine,
  DRAW_CHARS,
  isPositionalLine,
  lineToCells,
  paintLine,
  renderPositionalLine,
} from "@/components/tiptap-template-editor/utils/draw-mode";

describe("lineToCells", () => {
  it("splits literal characters into one cell each", () => {
    expect(lineToCells("AB C")).toEqual(["A", "B", " ", "C"]);
  });
  it("treats {{color}} as a single cell", () => {
    expect(lineToCells("A{{red}}B")).toEqual(["A", "{{red}}", "B"]);
  });
  it("normalizes single-bracket named colors to double-bracket cells", () => {
    expect(lineToCells("{red}X")).toEqual(["{{red}}", "X"]);
  });
  it("normalizes numeric color codes 63-70 to named cells", () => {
    expect(lineToCells("{63}{67}")).toEqual(["{{red}}", "{{blue}}"]);
  });
  it("maps filled-tile code 71 to black", () => {
    expect(lineToCells("{71}")).toEqual(["{{black}}"]);
  });
  it("drops dynamic tokens (variables, fill_space, formulas, wrap)", () => {
    expect(lineToCells("A{{weather.temp}}B")).toEqual(["A", "B"]);
    expect(lineToCells("{{fill_space}}X")).toEqual(["X"]);
    expect(lineToCells("{{= 1 + 2 }}X")).toEqual(["X"]);
    expect(lineToCells("{{long text|wrap}}X")).toEqual(["X"]);
  });
  it("keeps non-color single-bracket tokens as literal characters", () => {
    expect(lineToCells("{sun}")).toEqual(["{", "s", "u", "n", "}"]);
  });
  it("does not treat inherited object keys as colors", () => {
    expect(lineToCells("{{constructor}}X")).toEqual(["X"]);
  });
});

describe("cellsToLine", () => {
  it("joins cells and trims trailing blanks", () => {
    expect(cellsToLine(["A", " ", "{{red}}", " ", " "])).toBe("A {{red}}");
  });
  it("returns empty string for all-blank cells", () => {
    expect(cellsToLine([" ", " "])).toBe("");
  });
});

describe("isPositionalLine", () => {
  it("is true for literals and colors", () => {
    expect(isPositionalLine("AB {{red}} {blue}")).toBe(true);
    expect(isPositionalLine("")).toBe(true);
  });
  it("is false when a dynamic token is present", () => {
    expect(isPositionalLine("A{{weather.temp}}")).toBe(false);
    expect(isPositionalLine("{{fill_space}}")).toBe(false);
    expect(isPositionalLine("{{= 1 }}")).toBe(false);
  });
  it("is false for inherited object keys", () => {
    expect(isPositionalLine("{{constructor}}")).toBe(false);
  });
});

describe("DRAW_CHARS", () => {
  it("contains A-Z, digits, and the real punctuation subset of the board charset", () => {
    for (const ch of "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890") {
      expect(DRAW_CHARS).toContain(ch);
    }
    const punctuation = [
      "!",
      "@",
      "#",
      "$",
      "(",
      ")",
      "-",
      "+",
      "&",
      "=",
      ";",
      ":",
      "'",
      '"',
      "%",
      ",",
      ".",
      "/",
      "?",
      "°",
    ];
    for (const ch of punctuation) {
      expect(DRAW_CHARS).toContain(ch);
    }
  });
  it("excludes blank and undefined placeholder slots", () => {
    expect(DRAW_CHARS).not.toContain(" ");
    // 26 letters + 10 digits + 20 real punctuation marks = 56
    expect(DRAW_CHARS).toHaveLength(56);
    expect(new Set(DRAW_CHARS).size).toBe(DRAW_CHARS.length);
  });
});

describe("brushToCell", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("maps a color brush to a {{color}} cell", () => {
    expect(brushToCell({ kind: "color", color: "red" })).toBe("{{red}}");
    expect(brushToCell({ kind: "color", color: "black" })).toBe("{{black}}");
  });
  it("maps the eraser brush to a blank cell", () => {
    expect(brushToCell({ kind: "eraser" })).toBe(" ");
  });
  it("maps a char brush to the literal character", () => {
    expect(brushToCell({ kind: "char", char: "A" })).toBe("A");
    expect(brushToCell({ kind: "char", char: "°" })).toBe("°");
  });
  it("coerces lowercase char brushes to uppercase", () => {
    expect(brushToCell({ kind: "char", char: "a" })).toBe("A");
  });
  it("treats an invalid char brush as eraser and warns", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(brushToCell({ kind: "char", char: "~" })).toBe(" ");
    expect(brushToCell({ kind: "char", char: "AB" })).toBe(" ");
    expect(brushToCell({ kind: "char", char: "" })).toBe(" ");
    expect(warn).toHaveBeenCalledTimes(3);
  });
});

describe("paintLine", () => {
  it("paints a color into an empty line, padding with blanks", () => {
    expect(paintLine("", [{ col: 3, cell: "{{red}}" }], 22)).toBe("   {{red}}");
  });
  it("overwrites an existing character", () => {
    expect(paintLine("HELLO", [{ col: 1, cell: "{{blue}}" }], 22)).toBe("H{{blue}}LLO");
  });
  it("erases with a blank cell", () => {
    expect(paintLine("HELLO", [{ col: 4, cell: " " }], 22)).toBe("HELL");
  });
  it("stamps a literal character into an empty line, padding with blanks", () => {
    expect(paintLine("", [{ col: 2, cell: "A" }], 22)).toBe("  A");
  });
  it("stamps a character over a color tile", () => {
    expect(paintLine("{{red}}{{red}}", [{ col: 1, cell: "X" }], 22)).toBe("{{red}}X");
  });
  it("erases a stamped character", () => {
    expect(paintLine("AB", [{ col: 1, cell: " " }], 22)).toBe("A");
  });
  it("applies multiple paints in one call", () => {
    expect(
      paintLine(
        "",
        [
          { col: 0, cell: "{{red}}" },
          { col: 2, cell: "{{red}}" },
        ],
        22,
      ),
    ).toBe("{{red}} {{red}}");
  });
  it("strips dynamic tokens when painting a line containing them", () => {
    expect(paintLine("HI {{weather.temp}}", [{ col: 0, cell: "{{green}}" }], 22)).toBe("{{green}}I");
  });
  it("ignores out-of-bounds columns", () => {
    expect(
      paintLine(
        "AB",
        [
          { col: 30, cell: "{{red}}" },
          { col: -1, cell: "{{red}}" },
        ],
        22,
      ),
    ).toBe("AB");
  });
  it("truncates content beyond the board width", () => {
    const long = "X".repeat(30);
    expect(paintLine(long, [{ col: 0, cell: "{{red}}" }], 22)).toBe("{{red}}" + "X".repeat(21));
  });
});

describe("renderPositionalLine", () => {
  it("converts color cells to single-bracket render form", () => {
    expect(renderPositionalLine("A{{red}}B")).toBe("A{red}B");
  });
  it("passes literals through and drops dynamic tokens", () => {
    expect(renderPositionalLine("HI {{weather.temp}}!")).toBe("HI !");
  });
});
