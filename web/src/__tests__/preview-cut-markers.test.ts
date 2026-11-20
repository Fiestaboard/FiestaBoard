import { describe, expect, it } from "vitest";

import { cutCells } from "@/components/complex-editing/preview-cut-markers";

describe("cutCells (BB-E-10)", () => {
  const overflow = (line: number, cut = 2) => ({ line, columns: 22 + cut, maxColumns: 22, cut });
  it("marks the last tile of each cut row", () => {
    expect(cutCells([overflow(4), overflow(1, 5)], 6, 22, [])).toEqual([
      { line: 4, cut: 2, row: 3, col: 21 },
      { line: 1, cut: 5, row: 0, col: 21 },
    ]);
  });
  it("skips a wrapping line and a line below the board", () => {
    expect(cutCells([overflow(2), overflow(7)], 6, 22, [false, true])).toEqual([]);
  });
});
