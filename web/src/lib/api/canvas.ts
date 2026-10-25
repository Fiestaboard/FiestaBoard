// Pixel canvases (mirrors src/canvas/models.py and src/canvas/schemas.py).
// A page can hold up to 8; core validates, rasterises and sends them as
// layers. Design: docs/internal/reference/PIXEL_CANVAS.md.

/** 1-based character cells of the page grid. May run past the grid's edge (clamped when drawn). */
export interface CanvasArea {
  row: number;
  col: number;
  rows: number;
  cols: number;
}

export type CanvasBleedSide = "top" | "left" | "right" | "bottom" | "all";

/** A number, or a `{{…}}` expression yielding one. */
export type CanvasNum = number | string;

interface CanvasShapeBase {
  /** `true`/`false` or a `{{…}}` expression; falsy skips the shape. */
  if?: boolean | string;
  /** A `{{…}}` expression yielding a list: the shape repeats per item. */
  foreach?: string;
  /** The item's name inside the shape (default `item`). */
  as?: string;
}

export type CanvasShape = CanvasShapeBase &
  (
    | { type: "rect"; x: CanvasNum; y: CanvasNum; w: CanvasNum; h: CanvasNum; fill?: string; stroke?: string }
    | { type: "circle"; cx: CanvasNum; cy: CanvasNum; r: CanvasNum; fill?: string; stroke?: string }
    | { type: "ellipse"; cx: CanvasNum; cy: CanvasNum; rx: CanvasNum; ry: CanvasNum; fill?: string; stroke?: string }
    | { type: "line"; x1: CanvasNum; y1: CanvasNum; x2: CanvasNum; y2: CanvasNum; stroke: string; width?: CanvasNum }
    | { type: "polygon"; points: CanvasNum[][] | string; fill?: string; stroke?: string }
    | { type: "text"; x: CanvasNum; y: CanvasNum; text: string; color: string; font?: "3x5" | "5x7" }
    | {
        type: "gradient";
        x?: CanvasNum;
        y?: CanvasNum;
        w?: CanvasNum;
        h?: CanvasNum;
        from: string;
        to: string;
        angle?: CanvasNum;
      }
  );

/** What a canvas draws, in its own coordinate space (`size`). */
export interface CanvasContent {
  size?: [number, number] | null;
  background?: string | null;
  palette?: Record<string, string>;
  shapes?: CanvasShape[];
  pixels?: string[];
}

/** One pixel canvas on a page. */
export interface Canvas {
  id: string;
  area: CanvasArea;
  bleed?: CanvasBleedSide[];
  scale?: number;
  /** `hide` (default): text under the canvas is blanked. `flow`: text flows around it. */
  text?: "hide" | "flow";
  content?: CanvasContent | null;
  /** A `{{…}}` expression yielding a content object (a plugin's `format: canvas` variable). */
  source?: string | null;
}

/**
 * A canvas rasterised in panel pixels: FiestaUI's `LedBitmapLayer` JSON
 * (`rgba` is base64 of `width × height × 4` RGBA bytes, row-major).
 */
export interface CanvasLayerJson {
  x: number;
  y: number;
  width: number;
  height: number;
  rgba: string;
}

/** A problem met drawing a canvas; the canvas still draws. */
export interface CanvasIssue {
  canvas_id: string;
  path: string;
  message: string;
}
