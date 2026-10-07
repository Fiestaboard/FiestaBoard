// Pixel canvas editing helpers for the page editor (design:
// docs/internal/reference/PIXEL_CANVAS.md §1, §2, §5). Core validates and
// rasterises canvases; these only place them for the editor, and convert the
// pixel pad's colour grid to and from `content.pixels` + `palette`.

import { type DeviceModel, LED_FONTS, type LedFontId,ledGridLayout } from "@fiestaboard/ui";

import type { Canvas, CanvasArea, CanvasContent, TemplateVariables } from "@/lib/api";

/** At most this many palette keys (`[A-Za-z0-9]`); `.` is always transparent. */
export const MAX_PALETTE_COLORS = 62;
/** Pixel rows / columns a canvas's `pixels` may hold. */
export const MAX_PIXELS = 128;
/** Canvases on one page. */
export const MAX_CANVASES = 8;
/** Panel pixels per canvas pixel. */
export const MAX_SCALE = 8;

const PALETTE_KEYS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

/** The LED renderer's board colours (src/led/matrix.py `BOARD_COLORS`). */
export const BOARD_COLOR_HEX: Readonly<Record<string, string>> = {
  red: "#eb4034",
  orange: "#f5a623",
  yellow: "#f8e71c",
  green: "#7ed321",
  blue: "#4a90d9",
  violet: "#9b59b6",
  white: "#ffffff",
  black: "#1a1a1a",
};

/** One pad pixel: `#rrggbb`, or `null` for transparent. */
export type PixelColor = string | null;
/** Rows of pad pixels, `grid[y][x]`. */
export type PixelGrid = PixelColor[][];

/** A pixel-matrix board as the canvas geometry needs it. */
export interface PixelBoard {
  width: number;
  height: number;
  font: LedFontId;
}

/** A colour string as `#rrggbb`: hex, `#rgb` or a board colour name. `null` for transparent or unknown. */
export function normalizeHex(value: string | null | undefined): string | null {
  if (!value) return null;
  const text = value.trim().toLowerCase();
  if (text in BOARD_COLOR_HEX) return BOARD_COLOR_HEX[text];
  const six = /^#([0-9a-f]{6})$/.exec(text);
  if (six) return `#${six[1]}`;
  const three = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/.exec(text);
  if (three) return `#${three[1]}${three[1]}${three[2]}${three[2]}${three[3]}${three[3]}`;
  return null;
}

/** The board's pixel size and face when its model is a pixel matrix; else `null`. */
export function pixelBoardOf(
  model: DeviceModel | null | undefined,
  ledLayout: { font?: LedFontId | null } | null | undefined,
): PixelBoard | null {
  if (!model || model.technology !== "led_matrix" || model.geometry.kind !== "pixels") return null;
  const font = ledLayout?.font ?? model.font ?? "5x7";
  return { width: model.geometry.width, height: model.geometry.height, font };
}

/** *area* cut to a `rows × cols` grid, or `null` when it starts outside it. */
export function clampArea(area: CanvasArea, rows: number, cols: number): CanvasArea | null {
  if (area.row > rows || area.col > cols || area.row < 1 || area.col < 1) return null;
  return {
    row: area.row,
    col: area.col,
    rows: Math.min(area.rows, rows - area.row + 1),
    cols: Math.min(area.cols, cols - area.col + 1),
  };
}

/**
 * The canvas's pixel size on *board* (`floor(rect / scale)`), as core places
 * it (src/canvas/geometry.py `canvas_placement`): the area's cells without
 * the trailing gutter, bleeding to the panel edge where it touches the grid
 * edge. `null` when it is off the grid or smaller than one pixel.
 */
export function canvasPixelSize(canvas: Canvas, board: PixelBoard): { width: number; height: number } | null {
  const grid = ledGridLayout({ width: board.width, height: board.height, font: board.font });
  const area = clampArea(canvas.area, grid.rows, grid.cols);
  if (!area) return null;
  const face = LED_FONTS[grid.font];
  const sx = face.spacingX;
  const sy = face.spacingY;
  const px = face.glyphWidth + sx;
  const py = face.glyphHeight + sy;
  let x0 = grid.originX + (area.col - 1) * px;
  let y0 = grid.originY + (area.row - 1) * py;
  let x1 = grid.originX + (area.col - 1 + area.cols) * px - sx;
  let y1 = grid.originY + (area.row - 1 + area.rows) * py - sy;
  const bleed = canvas.bleed ?? [];
  const sides = new Set(bleed.includes("all") ? ["top", "left", "right", "bottom"] : bleed);
  if (sides.has("left") && area.col === 1) x0 = 0;
  if (sides.has("top") && area.row === 1) y0 = 0;
  if (sides.has("right") && area.col - 1 + area.cols === grid.cols) x1 = grid.width;
  if (sides.has("bottom") && area.row - 1 + area.rows === grid.rows) y1 = grid.height;
  const scale = canvas.scale ?? 1;
  const width = Math.floor((x1 - x0) / scale);
  const height = Math.floor((y1 - y0) / scale);
  return width >= 1 && height >= 1 ? { width, height } : null;
}

/** A new canvas over *area*: hides the text under it, draws nothing yet. */
export function makeCanvas(id: string, area: CanvasArea): Canvas {
  return { id, area, bleed: [], scale: 1, text: "hide", content: { palette: {}, shapes: [], pixels: [] } };
}

/** The first `canvasN` id not already taken. */
export function nextCanvasId(canvases: Canvas[]): string {
  const taken = new Set(canvases.map((c) => c.id));
  for (let n = 1; ; n++) {
    const id = `canvas${n}`;
    if (!taken.has(id)) return id;
  }
}

/** Read-only `{canvas:<id>}` markers by 0-based first row, for the raw template view. */
export function canvasMarkers(canvases: Canvas[], rowCount: number): Record<number, string[]> {
  const out: Record<number, string[]> = {};
  for (const canvas of canvases) {
    const row = canvas.area.row - 1;
    if (row < 0 || row >= rowCount) continue;
    (out[row] ??= []).push(`{canvas:${canvas.id}}`);
  }
  return out;
}

/** `content.pixels` + `palette` as a `width × height` colour grid (rows past the content are transparent). */
export function decodePixels(
  content: Pick<CanvasContent, "palette" | "pixels"> | null | undefined,
  width: number,
  height: number,
): PixelGrid {
  const palette = content?.palette ?? {};
  const resolved: Record<string, PixelColor> = {};
  for (const [key, value] of Object.entries(palette)) resolved[key] = normalizeHex(value);
  const rows = content?.pixels ?? [];
  return Array.from({ length: height }, (_, y) =>
    Array.from({ length: width }, (_, x) => {
      const key = rows[y]?.[x];
      if (!key || key === ".") return null;
      return resolved[key] ?? null;
    }),
  );
}

/**
 * A colour grid as `pixels` rows + a `palette`: one key per colour (an
 * existing key is kept for the colour it already meant), `.` transparent,
 * unused keys dropped. Throws past {@link MAX_PALETTE_COLORS} colours.
 */
export function encodePixels(
  grid: PixelGrid,
  previous: Record<string, string> = {},
): { palette: Record<string, string>; pixels: string[] } {
  const keyOf = new Map<string, string>();
  for (const [key, value] of Object.entries(previous)) {
    const hex = normalizeHex(value);
    if (hex && !keyOf.has(hex)) keyOf.set(hex, key);
  }
  const used = new Map<string, string>();
  const usedKeys = new Set<string>();
  const colors = new Set<string>();
  for (const row of grid) for (const c of row) if (c) colors.add(c);
  if (colors.size > MAX_PALETTE_COLORS) {
    throw new Error(`A canvas draws at most ${MAX_PALETTE_COLORS} colours, this one has ${colors.size}`);
  }
  for (const color of colors) {
    const kept = keyOf.get(color);
    if (kept && !usedKeys.has(kept)) {
      used.set(color, kept);
      usedKeys.add(kept);
    }
  }
  const free = [...PALETTE_KEYS].filter((k) => !usedKeys.has(k));
  for (const color of colors) {
    if (used.has(color)) continue;
    const key = free.shift()!;
    used.set(color, key);
    usedKeys.add(key);
  }
  if (colors.size === 0) return { palette: {}, pixels: [] };
  const pixels = grid.map((row) => row.map((c) => (c ? used.get(c)! : ".")).join(""));
  const palette: Record<string, string> = {};
  for (const [color, key] of used) palette[key] = color;
  return { palette, pixels };
}

/** *grid* with the 4-connected region of `grid[y][x]`'s colour painted *color* (the same grid when nothing changes). */
export function floodFill(grid: PixelGrid, x: number, y: number, color: PixelColor): PixelGrid {
  const target = grid[y]?.[x];
  if (target === undefined || target === color) return grid;
  const next = grid.map((row) => [...row]);
  const stack: [number, number][] = [[x, y]];
  while (stack.length) {
    const [cx, cy] = stack.pop()!;
    if (next[cy]?.[cx] !== target) continue;
    next[cy][cx] = color;
    stack.push([cx + 1, cy], [cx - 1, cy], [cx, cy + 1], [cx, cy - 1]);
  }
  return next;
}

/** A plugin variable a canvas `source` can name. */
export interface CanvasSourceVariable {
  token: string;
  description?: string;
}

/** Plugin variables whose manifest `format` is `"canvas"` (each yields a content object). */
export function canvasSourceVariables(data: TemplateVariables | undefined): CanvasSourceVariable[] {
  const out: CanvasSourceVariable[] = [];
  for (const [plugin, fields] of Object.entries(data?.variable_metadata ?? {})) {
    for (const [field, meta] of Object.entries(fields)) {
      if (meta?.format === "canvas") out.push({ token: `${plugin}.${field}`, description: meta.description });
    }
  }
  return out.sort((a, b) => a.token.localeCompare(b.token));
}
