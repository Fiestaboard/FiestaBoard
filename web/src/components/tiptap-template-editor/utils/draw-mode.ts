/**
 * Draw-mode utilities — cell-level editing of template lines.
 *
 * A "positional" line maps 1:1 to board cells: each literal character is one
 * cell and each color marker ({{red}}) is one cell. Dynamic tokens
 * (variables, fill_space, formulas, wrapped text) have no fixed width, so
 * painting a line drops them (the user is choosing to draw over them; undo
 * restores).
 */

import { BOARD_COLORS, type BoardColorName } from "./constants";

/**
 * The active drawing tool: a color brush, the eraser, or a stamp character
 * picked from the toolbar's character dropdown.
 */
export type DrawBrush = { kind: "color"; color: BoardColorName } | { kind: "eraser" } | { kind: "char"; char: string };

/** One board cell: a single literal character, or a "{{color}}" marker. */
export type Cell = string;

export interface CellPaint {
  col: number;
  /** Cell content to write: "{{color}}", a literal character, or " " to erase. */
  cell: Cell;
}

/**
 * The stampable character set — every REAL character on the board (A-Z,
 * digits, punctuation incl. °), mirroring BOARD_CHARS in board-display.tsx
 * codes 1-62 minus blank (that's the eraser) and the undefined placeholder
 * slots (43, 45, 51, 57, 58, 61).
 */
export const DRAW_CHARS: string[] = [
  ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ", // 1-26
  ..."1234567890", // 27-36
  "!", // 37
  "@", // 38
  "#", // 39
  "$", // 40
  "(", // 41
  ")", // 42
  "-", // 44
  "+", // 46
  "&", // 47
  "=", // 48
  ";", // 49
  ":", // 50
  "'", // 52
  '"', // 53
  "%", // 54
  ",", // 55
  ".", // 56
  "/", // 59
  "?", // 60
  "°", // 62 - Degree on Flagship, Heart on Note
];

const COLOR_CELL_RE = /^\{\{([a-z]+)\}\}$/;

/** Numeric board codes → color names (71 = filled tile, closest is black). */
const CODE_TO_NAME: Record<number, BoardColorName> = {
  63: "red",
  64: "orange",
  65: "yellow",
  66: "green",
  67: "blue",
  68: "violet",
  69: "white",
  70: "black",
  71: "black",
};

function colorCell(color: BoardColorName): Cell {
  return `{{${color}}}`;
}

/** Maps the active brush to the cell content it writes. */
export function brushToCell(brush: DrawBrush): Cell {
  switch (brush.kind) {
    case "color":
      return colorCell(brush.color);
    case "eraser":
      return " ";
    case "char": {
      const char = brush.char.toUpperCase();
      if (char.length === 1 && DRAW_CHARS.includes(char)) return char;
      console.warn(`[draw-mode] Invalid stamp character ${JSON.stringify(brush.char)} — erasing instead.`);
      return " ";
    }
  }
}

export function lineToCells(line: string): Cell[] {
  const cells: Cell[] = [];
  let remaining = line;

  while (remaining.length > 0) {
    const dbl = remaining.match(/^\{\{([^}]+)\}\}/);
    if (dbl) {
      const content = dbl[1].trim().toLowerCase();
      if (Object.hasOwn(BOARD_COLORS, content)) {
        cells.push(colorCell(content as BoardColorName));
      }
      // Non-color {{...}} tokens are dynamic — dropped.
      remaining = remaining.slice(dbl[0].length);
      continue;
    }

    const single = remaining.match(/^\{([a-z0-9]+)\}/i);
    if (single) {
      const token = single[1].toLowerCase();
      const numeric = Number(token);
      if (Object.hasOwn(BOARD_COLORS, token)) {
        cells.push(colorCell(token as BoardColorName));
        remaining = remaining.slice(single[0].length);
        continue;
      }
      if (Number.isInteger(numeric) && numeric >= 63 && numeric <= 71) {
        cells.push(colorCell(CODE_TO_NAME[numeric]));
        remaining = remaining.slice(single[0].length);
        continue;
      }
      // Not a color token — fall through to literal handling below.
    }

    cells.push(remaining[0]);
    remaining = remaining.slice(1);
  }

  return cells;
}

export function cellsToLine(cells: Cell[]): string {
  let end = cells.length;
  while (end > 0 && cells[end - 1] === " ") end--;
  return cells.slice(0, end).join("");
}

export function isPositionalLine(line: string): boolean {
  const re = /\{\{([^}]+)\}\}/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(line))) {
    if (!Object.hasOwn(BOARD_COLORS, match[1].trim().toLowerCase())) return false;
  }
  return true;
}

export function paintLine(line: string, paints: CellPaint[], cols: number): string {
  const cells = lineToCells(line);
  if (cells.length > cols) cells.length = cols;

  const validPaints = paints.filter((p) => p.col >= 0 && p.col < cols);
  for (const paint of validPaints) {
    while (cells.length <= paint.col) cells.push(" ");
    cells[paint.col] = paint.cell;
  }
  return cellsToLine(cells);
}

/**
 * Render a positional line for BoardDisplay's parser, which expects
 * single-bracket color markers ({red}) after server-side rendering.
 */
export function renderPositionalLine(line: string): string {
  return lineToCells(line)
    .map((cell) => {
      const m = cell.match(COLOR_CELL_RE);
      return m ? `{${m[1]}}` : cell;
    })
    .join("");
}
