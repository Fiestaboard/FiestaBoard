// ── Constants (mirror Python src/devices.py) ─────────────────────────────────
export const NOTE_ROWS = 3;
export const NOTE_COLS = 15;
export const MAX_NOTES_PER_AXIS = 8;
/**
 * Panel grid bounds (mirror src/devices.py). A "panel" (FiestaPanel, a virtual
 * board on a TV) is sized per character, so its grid is any rows × cols in
 * this range — never smaller than one Note.
 */
export const MIN_GRID_ROWS = NOTE_ROWS;
export const MIN_GRID_COLS = NOTE_COLS;
export const MAX_GRID_ROWS = 96;
export const MAX_GRID_COLS = 128;
/** Board display names are capped at storage time by BoardInstance.__post_init__. */
export const MAX_BOARD_NAME_LENGTH = 64;

// ── Types ─────────────────────────────────────────────────────────────────────
export interface BoardDimensions {
  rows: number;
  cols: number;
}

export interface NoteArrayPreset {
  id: string;
  label: string;
  notes_wide: number;
  notes_tall: number;
}

// ── Static device dimensions (flagship + note) ────────────────────────────────
export const DEVICE_DIMENSIONS: Record<string, BoardDimensions> = {
  flagship: { rows: 6, cols: 22 },
  note: { rows: NOTE_ROWS, cols: NOTE_COLS },
};

// ── 5 presets (exact ids/labels/values matching Python NOTE_ARRAY_PRESETS) ────
export const NOTE_ARRAY_PRESETS: NoteArrayPreset[] = [
  { id: "2_wide", label: "2 side-by-side", notes_wide: 2, notes_tall: 1 },
  { id: "4_wide", label: "4 side-by-side", notes_wide: 4, notes_tall: 1 },
  { id: "2_tall", label: "2 stacked", notes_wide: 1, notes_tall: 2 },
  { id: "4_tall", label: "4 stacked", notes_wide: 1, notes_tall: 4 },
  { id: "2x2_grid", label: "2×2 grid", notes_wide: 2, notes_tall: 2 },
];

// ── Core helpers ──────────────────────────────────────────────────────────────

/**
 * Compute dimensions for a note-array grid.
 * Does NOT validate inputs (mirrors Python note_array_dimensions()).
 */
export function noteArrayDimensions(notes_wide: number, notes_tall: number): BoardDimensions {
  return {
    rows: notes_tall * NOTE_ROWS,
    cols: notes_wide * NOTE_COLS,
  };
}

/**
 * Return true if device_type is "note_array".
 * Mirrors Python is_note_array().
 */
export function isNoteArray(deviceType: string): boolean {
  return deviceType === "note_array";
}

/**
 * Return true if device_type is "panel" (an explicit rows × cols grid).
 * Mirrors Python is_panel().
 */
export function isPanel(deviceType: string): boolean {
  return deviceType === "panel";
}

function clampAxis(value: number | null | undefined, min: number, max: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, Math.trunc(value)));
}

/**
 * Dimensions of a panel grid, each axis clamped into [MIN_GRID_*, MAX_GRID_*].
 * A missing axis resolves to its minimum (matching `@fiestaboard/ui`), where
 * Python's panel_dimensions() raises — the UI must always draw something.
 */
export function panelDimensions(gridRows?: number | null, gridCols?: number | null): BoardDimensions {
  return {
    rows: clampAxis(gridRows, MIN_GRID_ROWS, MAX_GRID_ROWS),
    cols: clampAxis(gridCols, MIN_GRID_COLS, MAX_GRID_COLS),
  };
}

/**
 * Resolve board dimensions for any device type.
 *
 * - "flagship" | "note"  → looks up DEVICE_DIMENSIONS (other args ignored)
 * - "note_array"         → computes from notes_wide × notes_tall
 * - "panel"              → grid_rows × grid_cols, clamped (see panelDimensions)
 * - unknown              → falls back to flagship (matches Python board_html_renderer.py)
 *
 * Mirrors Python resolve_dimensions(), except unknown device types fall back
 * to flagship (matching board_html_renderer.py) and a panel without a grid
 * resolves to the minimum grid, rather than raising.
 *
 * @param deviceType  "flagship" | "note" | "note_array" | "panel"
 * @param notes_wide  Number of notes wide (only used for "note_array"; default 1)
 * @param notes_tall  Number of notes tall (only used for "note_array"; default 1)
 * @param grid_rows   Rows of characters (only used for "panel")
 * @param grid_cols   Columns of characters (only used for "panel")
 * @returns           { rows, cols }
 */
export function resolveDimensions(
  deviceType: string,
  notes_wide = 1,
  notes_tall = 1,
  grid_rows?: number | null,
  grid_cols?: number | null,
): BoardDimensions {
  if (deviceType in DEVICE_DIMENSIONS) {
    return DEVICE_DIMENSIONS[deviceType];
  }
  if (deviceType === "note_array") {
    return noteArrayDimensions(notes_wide, notes_tall);
  }
  if (deviceType === "panel") {
    return panelDimensions(grid_rows, grid_cols);
  }
  // Unknown: fall back to flagship (matches Python fallback in board_html_renderer.py)
  return DEVICE_DIMENSIONS.flagship;
}

/**
 * Return true if (rows, cols) is a valid note-array size.
 * Mirrors Python is_valid_note_array_grid().
 */
export function isValidNoteArrayGrid(rows: number, cols: number): boolean {
  if (rows <= 0 || cols <= 0) return false;
  if (rows % NOTE_ROWS !== 0 || cols % NOTE_COLS !== 0) return false;
  return rows / NOTE_ROWS <= MAX_NOTES_PER_AXIS && cols / NOTE_COLS <= MAX_NOTES_PER_AXIS;
}

export interface ClassifiedDimensions {
  device_type: "flagship" | "note" | "note_array";
  rows: number;
  cols: number;
  notes_wide?: number;
  notes_tall?: number;
  matched_preset?: string | null;
}

/**
 * Classify a grid (rows × cols) into a device type and optional note-array
 * geometry. Mirrors Python classify_dimensions(): an exact 6×22 is a flagship
 * and an exact 3×15 is a Note — both are checked BEFORE the note-array branch,
 * so a single Note never classifies as a 1×1 array.
 *
 * Throws for a grid that is neither the flagship size, the Note size, nor a
 * valid note-array grid.
 */
export function classifyDimensions(rows: number, cols: number): ClassifiedDimensions {
  const flagship = DEVICE_DIMENSIONS.flagship;
  if (rows === flagship.rows && cols === flagship.cols) {
    return { device_type: "flagship", rows, cols };
  }
  const note = DEVICE_DIMENSIONS.note;
  if (rows === note.rows && cols === note.cols) {
    return { device_type: "note", rows, cols };
  }
  if (isValidNoteArrayGrid(rows, cols)) {
    const notes_wide = cols / NOTE_COLS;
    const notes_tall = rows / NOTE_ROWS;
    const preset = NOTE_ARRAY_PRESETS.find((p) => p.notes_wide === notes_wide && p.notes_tall === notes_tall);
    return {
      device_type: "note_array",
      rows,
      cols,
      notes_wide,
      notes_tall,
      matched_preset: preset ? preset.label : null,
    };
  }
  throw new Error(
    `Grid ${rows}x${cols} is unclassifiable: not a flagship (${flagship.rows}x${flagship.cols}), ` +
      `not a Note (${note.rows}x${note.cols}), and not a valid note-array grid ` +
      `(rows must be a multiple of ${NOTE_ROWS}, cols a multiple of ${NOTE_COLS}, ` +
      `each axis <= ${MAX_NOTES_PER_AXIS} notes).`,
  );
}

// ── Page <-> board size compatibility (issue #1249, mirrors src/devices.py) ──

/** Anything carrying board geometry: a Page, a BoardInstance, or a raw dict. */
export interface SizedEntity {
  device_type?: string | null;
  notes_wide?: number | null;
  notes_tall?: number | null;
  /** Panel only: rows × cols of characters. */
  grid_rows?: number | null;
  grid_cols?: number | null;
}

/**
 * Canonical family + resolved-size key for page<->board compatibility.
 * Mirrors Python size_key(): e.g. "flagship:6x22", "note:3x15",
 * "note_array:6x30" (a 2×2 note grid), "panel:12x29". The device family is
 * part of the key on purpose — a Note page is NOT compatible with a 1×1 note
 * array even though both resolve to 3×15. Unknown device types fall back to
 * flagship (family AND dimensions), matching the Python fallback.
 *
 * A panel with no grid has no size at all, so it gets a key no real board
 * has ("panel:unsized") — it must neither match a real panel nor, as the
 * Python fallback would make it, a flagship.
 */
export function sizeKey(
  deviceType: string,
  notesWide = 1,
  notesTall = 1,
  gridRows?: number | null,
  gridCols?: number | null,
): string {
  if (isPanel(deviceType)) {
    if (typeof gridRows !== "number" || typeof gridCols !== "number") return "panel:unsized";
    const { rows, cols } = panelDimensions(gridRows, gridCols);
    return `panel:${rows}x${cols}`;
  }
  const family = deviceType in DEVICE_DIMENSIONS || isNoteArray(deviceType) ? deviceType : "flagship";
  const { rows, cols } = resolveDimensions(family, notesWide, notesTall);
  return `${family}:${rows}x${cols}`;
}

/** sizeKey() of a page/board/raw dict (missing geometry → a flagship). */
export function sizeKeyOf(entity: SizedEntity): string {
  return sizeKey(
    entity.device_type || "flagship",
    entity.notes_wide || 1,
    entity.notes_tall || 1,
    entity.grid_rows,
    entity.grid_cols,
  );
}

/** Resolved rows × cols of a page/board/raw dict (missing geometry → a flagship). */
export function dimensionsOf(entity: SizedEntity): BoardDimensions {
  return resolveDimensions(
    entity.device_type || "flagship",
    entity.notes_wide || 1,
    entity.notes_tall || 1,
    entity.grid_rows,
    entity.grid_cols,
  );
}

/**
 * True when a page renders 1:1 on a board: EXACT sizeKey() match.
 * Mirrors Python pages_compatible_with_board(). Family-aware: flagship ≠ note
 * even at identical dimensions, and note arrays and panels must match the
 * resolved grid exactly.
 */
export function pagesCompatibleWithBoard(page: SizedEntity, board: SizedEntity): boolean {
  return sizeKeyOf(page) === sizeKeyOf(board);
}
