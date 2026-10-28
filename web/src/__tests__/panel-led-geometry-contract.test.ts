import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { layoutLedCellGrid, ledGridLayout, rasterizeLedLayout } from "@fiestaboard/ui";
import { describe, expect, it } from "vitest";

interface GeometryCase {
  name: string;
  width: number;
  height: number;
  font: "5x7" | "3x5";
  rows: number;
  cols: number;
  origin_x: number;
  origin_y: number;
}
const fixture = JSON.parse(
  readFileSync(resolve(process.cwd(), "../tests/fixtures/panel-led-geometry.json"), "utf8"),
) as { cases: GeometryCase[] };

describe("shared panel geometry against the pinned FiestaUI renderer", () => {
  it.each(fixture.cases)("$name preserves all corner cells and all-edge canvas pixels", (sample) => {
    const grid = ledGridLayout(sample);
    expect(grid).toEqual({
      width: sample.width,
      height: sample.height,
      font: sample.font,
      rows: sample.rows,
      cols: sample.cols,
      originX: sample.origin_x,
      originY: sample.origin_y,
    });
    const cells: { type: "char"; value: string }[][] = Array.from({ length: sample.rows }, () =>
      Array.from({ length: sample.cols }, () => ({ type: "char", value: " " })),
    );
    const corners = [
      [0, 0],
      [0, sample.cols - 1],
      [sample.rows - 1, 0],
      [sample.rows - 1, sample.cols - 1],
    ];
    for (const [row, col] of corners) cells[row][col] = { type: "char", value: "X" };
    const layout = layoutLedCellGrid(cells, sample);
    const frame = rasterizeLedLayout(layout);
    const glyphWidth = sample.font === "5x7" ? 5 : 3;
    const glyphHeight = sample.font === "5x7" ? 7 : 5;
    for (const [row, col] of corners) {
      const x = sample.origin_x + col * (glyphWidth + 1);
      const y = sample.origin_y + row * (glyphHeight + 1);
      // X has lit pixels at both top corners in either supported font.
      for (const offset of [0, glyphWidth - 1]) {
        const index = (y * sample.width + x + offset) * 3;
        expect([...frame.pixels.slice(index, index + 3)]).toEqual([255, 255, 255]);
      }
    }
    const rgba = new Uint8ClampedArray(sample.width * sample.height * 4);
    for (let i = 0; i < rgba.length; i += 4) rgba.set([255, 0, 0, 255], i);
    const bleed = rasterizeLedLayout(
      layoutLedCellGrid(cells, sample, {
        layers: [{ x: 0, y: 0, width: sample.width, height: sample.height, rgba }],
      }),
    );
    for (const pixel of [0, sample.width - 1, (sample.height - 1) * sample.width, sample.width * sample.height - 1]) {
      expect([...bleed.pixels.slice(pixel * 3, pixel * 3 + 3)]).toEqual([255, 0, 0]);
    }
  });
});
