/**
 * Complex editing (web slice 2.9, Figma 04b): the pure model behind the big
 * board editor's row bands, truncation map and ruler, and the note array's
 * seams. Everything here is derived from what the editor already holds (the
 * template lines and their per-line metadata, the rendered preview rows and
 * the hub's real-width validation, H4) — it never changes the page model.
 */
import { type ColumnRulerMark, parseLine, type TruncationMapLine } from "@fiestaboard/ui";

import type { TemplateValidationAtResponse } from "@/lib/api/template-validation";

/** The desktop preview pane (740 wide, 720 inside) fits 44 Tile sm columns (04b `126:149604`). */
export const BIG_BOARD_MAX_FIT_COLUMNS = 44;
/** More rows than a Den TV (29×12) makes the template a big board too. */
export const BIG_BOARD_MAX_ROWS = 12;
/** One Note is 15 columns × 3 rows. */
export const NOTE_COLUMNS = 15;

const BAND_LABEL_MAX = 12;

export interface BoardSize {
  rows: number;
  cols: number;
}

/** A board the desktop editor opens with the 04b tools: ruler, minimap, truncation map, row bands. */
export function isBigBoard({ rows, cols }: BoardSize): boolean {
  return cols > BIG_BOARD_MAX_FIT_COLUMNS || rows > BIG_BOARD_MAX_ROWS;
}

export interface RowBandModel {
  id: string;
  /** One-based, inclusive. */
  start: number;
  end: number;
  /** Readable words from the first row, or null when it has none. */
  label: string | null;
}

/**
 * The words a band is named for: its first row's literal text, without
 * `{{…}}` expressions or `{…}` tile codes. A row that is only variables is
 * named for its first variable; a row of colour tiles has no name.
 */
export function bandLabel(line: string): string | null {
  const text = line
    .replace(/\{\{[\s\S]*?\}\}/g, " ")
    .replace(/\{[^{}]*\}/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (text) return text.length > BAND_LABEL_MAX ? `${text.slice(0, BAND_LABEL_MAX).trimEnd()}…` : text;
  const variable = /\{\{\s*([A-Za-z_][\w.]*)/.exec(line);
  return variable ? variable[1] : null;
}

/** Bands are the runs of non-blank rows the board shows; blank rows separate them. */
export function deriveRowBands(lines: readonly string[], rows: number): RowBandModel[] {
  const bands: RowBandModel[] = [];
  let start = -1;
  const limit = Math.min(lines.length, rows);
  for (let i = 0; i <= limit; i++) {
    const filled = i < limit && lines[i].trim().length > 0;
    if (filled && start < 0) start = i;
    if (!filled && start >= 0) {
      bands.push({ id: `band-${start + 1}-${i}`, start: start + 1, end: i, label: bandLabel(lines[start]) });
      start = -1;
    }
  }
  return bands;
}

/** The editor's per-line state that moves with a row. */
export interface TemplateRowsState<A = string> {
  lines: string[];
  alignments: A[];
  wraps: boolean[];
}

function reorder<A>(state: TemplateRowsState<A>, order: number[]): TemplateRowsState<A> {
  return {
    lines: order.map((i) => state.lines[i] ?? ""),
    alignments: order.map((i) => state.alignments[i] ?? state.alignments[0]),
    wraps: order.map((i) => state.wraps[i] ?? false),
  };
}

function range(from: number, to: number): number[] {
  return Array.from({ length: Math.max(0, to - from) }, (_, k) => from + k);
}

/** Swap a band with its neighbour; the blank rows between them stay where they are. Null when it cannot move. */
export function moveBand<A>(
  state: TemplateRowsState<A>,
  bands: readonly RowBandModel[],
  id: string,
  direction: "up" | "down",
): TemplateRowsState<A> | null {
  const index = bands.findIndex((b) => b.id === id);
  if (index < 0) return null;
  const other = direction === "up" ? index - 1 : index + 1;
  if (other < 0 || other >= bands.length) return null;
  const [first, second] = direction === "up" ? [bands[other], bands[index]] : [bands[index], bands[other]];
  const order = [
    ...range(0, first.start - 1),
    ...range(second.start - 1, second.end),
    ...range(first.end, second.start - 1),
    ...range(first.start - 1, first.end),
    ...range(second.end, state.lines.length),
  ];
  return reorder(state, order);
}

/**
 * Insert a copy of a band (and one blank separator row) right after it. The
 * board keeps its row count, so the copy only fits when that many blank rows
 * trail the template; null otherwise.
 */
export function duplicateBand<A>(
  state: TemplateRowsState<A>,
  bands: readonly RowBandModel[],
  id: string,
  rows: number,
): TemplateRowsState<A> | null {
  const band = bands.find((b) => b.id === id);
  if (!band) return null;
  const size = band.end - band.start + 1;
  const n = Math.max(rows, state.lines.length);
  let trailing = 0;
  for (let i = n - 1; i >= 0 && !(state.lines[i] ?? "").trim(); i--) trailing++;
  if (trailing < size + 1) return null;
  // A blank separator, then the copy; the blank rows it displaces fall off the end.
  const order = [...range(0, band.end), n - 1, ...range(band.start - 1, band.end), ...range(band.end, n)].slice(0, n);
  return reorder(state, order);
}

/** One template line the hub measured past the board's real width (H4). */
export interface LineOverflow {
  /** One-based template line. */
  line: number;
  /** Columns the line needs with its variables at their longest. */
  columns: number;
  maxColumns: number;
  cut: number;
}

/** The validator's `line_too_long` verdicts, each with the length it measured. */
export function lineOverflows(response: TemplateValidationAtResponse | undefined, cols: number): LineOverflow[] {
  if (!response) return [];
  const width = response.cols ?? cols;
  return response.errors.flatMap((error) =>
    error.code === "line_too_long" && typeof error.max_length === "number" && error.max_length > width
      ? [{ line: error.line, columns: error.max_length, maxColumns: width, cut: error.max_length - width }]
      : [],
  );
}

/**
 * The columns a rendered row draws: a colour code (`{63}`) or icon is one
 * tile and a closing tag none, as the board parses it and as the hub's render
 * report measures it (BB-E-2). Trailing blanks are not counted.
 */
export function drawnWidth(row: string): number {
  return parseLine(row.trimEnd()).length;
}

/**
 * Template rows the board will draw something on: up to the last row with
 * content. Blank rows after it (a smaller board's padding) are not lines the
 * board limit applies to (BB-E-18), as the hub's `beyond_board` check counts.
 */
export function usedLineCount(lines: readonly string[]): number {
  for (let i = lines.length - 1; i >= 0; i--) {
    if (lines[i].trim() !== "") return i + 1;
  }
  return 0;
}

/** Rows for the truncation map: each rendered row's length, and the hub's overflow verdict on its line. */
export function truncationLines(
  rendered: readonly string[],
  overflows: readonly LineOverflow[],
  rows: number,
  describe: (overflow: LineOverflow) => string,
): TruncationMapLine[] {
  const byLine = new Map(overflows.map((o) => [o.line, o]));
  return Array.from({ length: rows }, (_, i) => {
    const row = i + 1;
    const overflow = byLine.get(row);
    if (overflow) {
      return {
        row,
        length: overflow.columns,
        overflow: { column: overflow.maxColumns, count: overflow.cut, description: describe(overflow) },
      };
    }
    return { row, length: drawnWidth(rendered[i] ?? "") };
  });
}

/** Ruler marks after each Note column of a note array (04b `127:135751`). */
export function noteSeamMarks(notesWide: number, label: string): ColumnRulerMark[] {
  return Array.from({ length: Math.max(0, notesWide - 1) }, (_, k) => ({
    id: `seam-${k + 1}`,
    type: "seam" as const,
    column: NOTE_COLUMNS * (k + 1),
    label,
  }));
}

export interface SeamStraddle {
  /** One-based board row. */
  row: number;
  /** The last column before the seam. */
  column: number;
  word: string;
}

/** Words the rendered board splits across a Note's physical seam (found client-side, as 04b notes). */
export function seamStraddles(rendered: readonly string[], notesWide: number): SeamStraddle[] {
  const found: SeamStraddle[] = [];
  rendered.forEach((line, i) => {
    for (let k = 1; k < notesWide; k++) {
      const seam = NOTE_COLUMNS * k;
      const before = line[seam - 1];
      const after = line[seam];
      if (!before || !after || before === " " || after === " ") continue;
      let start = seam - 1;
      while (start > 0 && line[start - 1] !== " ") start--;
      let end = seam;
      while (end < line.length && line[end] !== " ") end++;
      found.push({ row: i + 1, column: seam, word: line.slice(start, end) });
    }
  });
  return found;
}
