/**
 * The page editor's canvas helpers (web/src/lib/canvas-editing.ts): where a
 * canvas sits on a pixel board, how the pixel pad's grid round-trips to
 * `content.pixels` + `palette`, and which plugin variables are canvas sources.
 */
import { tryResolveDeviceModel } from "@fiestaboard/ui";
import { describe, expect, it } from "vitest";

import type { Canvas, TemplateVariables } from "@/lib/api";
import {
  canvasMarkers,
  canvasPixelSize,
  canvasSourceVariables,
  decodePixels,
  encodePixels,
  floodFill,
  makeCanvas,
  MAX_PALETTE_COLORS,
  nextCanvasId,
  normalizeHex,
  pixelBoardOf,
} from "@/lib/canvas-editing";

const PIXOO = { width: 64, height: 64, font: "3x5" as const };

describe("pixelBoardOf", () => {
  it("answers a pixel LED model's size and face", () => {
    const model = tryResolveDeviceModel("divoom_pixoo64").model!;
    expect(pixelBoardOf(model, { font: "3x5" })).toEqual({ width: 64, height: 64, font: "3x5" });
  });

  it("is null for a split-flap model and for no model", () => {
    expect(pixelBoardOf(tryResolveDeviceModel("vestaboard_flagship").model!, null)).toBeNull();
    expect(pixelBoardOf(null, null)).toBeNull();
  });
});

describe("canvasPixelSize (mirrors src/canvas/geometry.py canvas_placement)", () => {
  // 3x5 face on 64x64: glyph 3x5 + 1px gutters -> pitch 4x6, 16 cols x 10 rows,
  // origin (0, 2) — the same grid core draws.
  it("is the area's pixels without the trailing gutter", () => {
    const canvas = makeCanvas("a", { row: 1, col: 1, rows: 2, cols: 4 });
    expect(canvasPixelSize(canvas, PIXOO)).toEqual({ width: 15, height: 11 });
  });

  it("bleeds to the panel edge where the area touches the grid edge", () => {
    const canvas = { ...makeCanvas("a", { row: 1, col: 1, rows: 10, cols: 16 }), bleed: ["all" as const] };
    expect(canvasPixelSize(canvas, PIXOO)).toEqual({ width: 64, height: 64 });
  });

  it("bleeds only the sides it names", () => {
    // 5x7 on 64x64: 10 cols x 8 rows, origin (2, 0) — a 2px margin left and right.
    const board = { width: 64, height: 64, font: "5x7" as const };
    const area = { row: 1, col: 1, rows: 8, cols: 10 };
    expect(canvasPixelSize(makeCanvas("a", area), board)).toEqual({ width: 59, height: 63 });
    expect(canvasPixelSize({ ...makeCanvas("a", area), bleed: ["left"] }, board)).toEqual({ width: 61, height: 63 });
  });

  it("divides by scale and clamps an oversized area to the grid", () => {
    const canvas = { ...makeCanvas("a", { row: 1, col: 1, rows: 96, cols: 128 }), scale: 2 };
    expect(canvasPixelSize(canvas, PIXOO)).toEqual({ width: 31, height: 29 });
  });

  it("is null for an area that starts off the grid", () => {
    expect(canvasPixelSize(makeCanvas("a", { row: 11, col: 1, rows: 1, cols: 1 }), PIXOO)).toBeNull();
  });
});

describe("pixel grid <-> content.pixels + palette", () => {
  it("decodes palette keys, board colour names and '.' transparent", () => {
    const grid = decodePixels({ palette: { k: "#000000", r: "red", y: "#fc0" }, pixels: ["kr", "y."] }, 3, 2);
    expect(grid).toEqual([
      ["#000000", "#eb4034", null],
      ["#ffcc00", null, null],
    ]);
  });

  it("encodes colours to single-character keys with '.' for transparent", () => {
    const { palette, pixels } = encodePixels([
      ["#ff0000", null],
      [null, "#00ff00"],
    ]);
    expect(pixels).toHaveLength(2);
    expect(pixels[0][1]).toBe(".");
    expect(palette[pixels[0][0]]).toBe("#ff0000");
    expect(palette[pixels[1][1]]).toBe("#00ff00");
    expect(Object.keys(palette)).toHaveLength(2);
  });

  it("keeps an existing key for a colour it already had and drops unused ones", () => {
    const { palette, pixels } = encodePixels([["#ff0000", "#0000ff"]], { r: "#ff0000", g: "#00ff00" });
    expect(pixels).toEqual(["r" + pixels[0][1]]);
    expect(palette.r).toBe("#ff0000");
    expect(palette.g).toBeUndefined();
  });

  it("encodes an all-transparent grid as no pixels at all", () => {
    expect(encodePixels([[null, null]])).toEqual({ palette: {}, pixels: [] });
  });

  it("refuses more than 62 colours", () => {
    const row = Array.from({ length: MAX_PALETTE_COLORS + 1 }, (_, i) => `#0000${i.toString(16).padStart(2, "0")}`);
    expect(() => encodePixels([row])).toThrow(/62/);
  });

  it("round-trips", () => {
    const grid = [
      ["#123456", null, "#123456"],
      [null, "#abcdef", null],
    ];
    const encoded = encodePixels(grid);
    expect(decodePixels(encoded, 3, 2)).toEqual(grid);
  });
});

describe("floodFill", () => {
  it("fills the 4-connected region of the start colour only", () => {
    const grid = [
      [null, null, "#ff0000"],
      [null, "#ff0000", null],
    ];
    expect(floodFill(grid, 0, 0, "#00ff00")).toEqual([
      ["#00ff00", "#00ff00", "#ff0000"],
      ["#00ff00", "#ff0000", null],
    ]);
  });

  it("is a no-op when the colour is already there", () => {
    const grid = [["#ff0000"]];
    expect(floodFill(grid, 0, 0, "#ff0000")).toBe(grid);
  });
});

describe("ids, markers and sources", () => {
  it("picks the first free canvas id", () => {
    expect(nextCanvasId([])).toBe("canvas1");
    expect(nextCanvasId([makeCanvas("canvas1", { row: 1, col: 1, rows: 1, cols: 1 })])).toBe("canvas2");
  });

  it("marks each canvas on its first row", () => {
    const canvases: Canvas[] = [
      makeCanvas("sky", { row: 1, col: 1, rows: 2, cols: 3 }),
      makeCanvas("sun", { row: 1, col: 5, rows: 1, cols: 1 }),
      makeCanvas("sea", { row: 3, col: 1, rows: 1, cols: 1 }),
    ];
    expect(canvasMarkers(canvases, 4)).toEqual({ 0: ["{canvas:sky}", "{canvas:sun}"], 2: ["{canvas:sea}"] });
    expect(canvasMarkers(canvases, 2)).toEqual({ 0: ["{canvas:sky}", "{canvas:sun}"] });
  });

  it("lists only plugin variables whose format is canvas", () => {
    const vars = {
      variables: { art: ["canvas", "title"], weather: ["temp"] },
      variable_metadata: {
        art: { canvas: { description: "A drawing", format: "canvas" }, title: { description: "Title" } },
        weather: { temp: { description: "Temp" } },
      },
    } as unknown as TemplateVariables;
    expect(canvasSourceVariables(vars)).toEqual([{ token: "art.canvas", description: "A drawing" }]);
  });

  it("normalises colours to #rrggbb", () => {
    expect(normalizeHex("#FC0")).toBe("#ffcc00");
    expect(normalizeHex("blue")).toBe("#4a90d9");
    expect(normalizeHex("transparent")).toBeNull();
    expect(normalizeHex("nope")).toBeNull();
  });
});
