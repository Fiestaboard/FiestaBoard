import { describe, expect, it } from "vitest";

import { addSnoozingIndicator, parseLine, tokensToString } from "@/lib/snoozing-indicator";

// Convenience: get the row at index `r` from the result, padded with spaces
// to the requested column width.
function row(result: string, r: number, cols: number): string {
  const lines = result.split("\n");
  const line = lines[r] ?? "";
  // Re-tokenize to drop any color codes that snuck in (none expected here).
  return tokensToString(parseLine(line)).padEnd(cols, " ").slice(0, cols);
}

describe("addSnoozingIndicator - position matrix on flagship (6x22)", () => {
  const NUM_ROWS = 6;
  const NUM_COLS = 22;
  const TEXT = "SNOOZING";

  function expectAtPosition(position: string, expectedRow: number, expectedStartCol: number) {
    const result = addSnoozingIndicator("", NUM_ROWS, NUM_COLS, TEXT, position);
    const lines = result.split("\n");
    expect(lines.length).toBe(NUM_ROWS);

    const target = row(result, expectedRow, NUM_COLS);
    expect(target.slice(expectedStartCol, expectedStartCol + TEXT.length)).toBe(TEXT);

    // All other rows are entirely blank
    for (let r = 0; r < NUM_ROWS; r++) {
      if (r === expectedRow) continue;
      expect(row(result, r, NUM_COLS).trim()).toBe("");
    }
  }

  it("center", () => {
    expectAtPosition("center", 3, Math.floor((NUM_COLS - TEXT.length) / 2));
  });
  it("top-left", () => {
    expectAtPosition("top-left", 0, 0);
  });
  it("top-right", () => {
    expectAtPosition("top-right", 0, NUM_COLS - TEXT.length);
  });
  it("bottom-left", () => {
    expectAtPosition("bottom-left", NUM_ROWS - 1, 0);
  });
  it("bottom-right", () => {
    expectAtPosition("bottom-right", NUM_ROWS - 1, NUM_COLS - TEXT.length);
  });
});

describe("addSnoozingIndicator - position matrix on note (3x15)", () => {
  const NUM_ROWS = 3;
  const NUM_COLS = 15;
  const TEXT = "SNOOZING";

  function expectAtPosition(position: string, expectedRow: number, expectedStartCol: number) {
    const result = addSnoozingIndicator("", NUM_ROWS, NUM_COLS, TEXT, position);
    const lines = result.split("\n");
    expect(lines.length).toBe(NUM_ROWS);

    const target = row(result, expectedRow, NUM_COLS);
    expect(target.slice(expectedStartCol, expectedStartCol + TEXT.length)).toBe(TEXT);

    for (let r = 0; r < NUM_ROWS; r++) {
      if (r === expectedRow) continue;
      expect(row(result, r, NUM_COLS).trim()).toBe("");
    }
  }

  it("center on 3-row board uses row 1", () => {
    expectAtPosition("center", 1, Math.floor((NUM_COLS - TEXT.length) / 2));
  });
  it("top-left", () => expectAtPosition("top-left", 0, 0));
  it("top-right", () => expectAtPosition("top-right", 0, NUM_COLS - TEXT.length));
  it("bottom-left", () => expectAtPosition("bottom-left", 2, 0));
  it("bottom-right", () => expectAtPosition("bottom-right", 2, NUM_COLS - TEXT.length));
});

describe("addSnoozingIndicator - text behavior", () => {
  it("uses custom text", () => {
    const result = addSnoozingIndicator("", 3, 15, "BEDTIME", "top-left");
    expect(result.split("\n")[0].startsWith("BEDTIME")).toBe(true);
  });

  it("truncates text longer than numCols", () => {
    const longText = "ABCDEFGHIJKLMNOPQRST"; // 20 chars
    const result = addSnoozingIndicator("", 3, 15, longText, "top-left");
    const firstLine = row(result, 0, 15);
    expect(firstLine).toBe("ABCDEFGHIJKLMNO");
  });

  it("text equal to cols at top-right starts at col 0", () => {
    const text = "A".repeat(15);
    const result = addSnoozingIndicator("", 3, 15, text, "top-right");
    expect(row(result, 0, 15)).toBe(text);
  });

  it("falls back to center when position is unknown", () => {
    const result = addSnoozingIndicator("", 6, 22, "SNOOZING", "weird");
    // Center => row 3
    expect(row(result, 3, 22).includes("SNOOZING")).toBe(true);
  });

  it("default text is SNOOZING, default position is center", () => {
    const result = addSnoozingIndicator("");
    // 6x22 default: row 3 contains SNOOZING
    expect(row(result, 3, 22).includes("SNOOZING")).toBe(true);
  });
});

describe("addSnoozingIndicator - preserves other rows", () => {
  it("does not modify rows outside the indicator row", () => {
    // A multi-line page with a color token on each row
    const content = ["{63}HELLO{/63}", "{64}WORLD{/64}", "ROW3", "ROW4", "ROW5", "ROW6"].join("\n");
    const result = addSnoozingIndicator(content, 6, 22, "ZZZ", "top-right");
    const lines = result.split("\n");

    // Row 0 (target) - tokens were re-rendered, ZZZ at the right end
    expect(lines[0].trimEnd().endsWith("ZZZ")).toBe(true);

    // Rows 1-5 are untouched (still contain original markers)
    expect(lines[1]).toBe("{64}WORLD{/64}");
    expect(lines[2]).toBe("ROW3");
    expect(lines[5]).toBe("ROW6");
  });

  it("pads short content up to numRows", () => {
    const result = addSnoozingIndicator("ONLY", 6, 22, "ZZZ", "bottom-left");
    const lines = result.split("\n");
    expect(lines.length).toBe(6);
    // Last row starts with ZZZ
    expect(lines[5].startsWith("ZZZ")).toBe(true);
  });

  it("truncates content longer than numRows", () => {
    const content = Array.from({ length: 10 }, (_, i) => `R${i}`).join("\n");
    const result = addSnoozingIndicator(content, 6, 22, "ZZZ", "center");
    expect(result.split("\n").length).toBe(6);
  });
});

describe("addSnoozingIndicator - positions non-default rows for note device", () => {
  it("center on 6-row flagship places text on row 3 (numRows/2)", () => {
    const result = addSnoozingIndicator("", 6, 22, "X", "center");
    const lines = result.split("\n");
    expect(row(result, 3, 22).trim()).toBe("X");
    for (const r of [0, 1, 2, 4, 5]) {
      expect(lines[r] === "" || row(result, r, 22).trim() === "").toBe(true);
    }
  });
});
