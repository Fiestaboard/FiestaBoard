// ── Constants (mirror Python src/devices.py) ─────────────────────────────────
export const NOTE_ROWS = 3;
export const NOTE_COLS = 15;
export const MAX_NOTES_PER_AXIS = 8;

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
 * Resolve board dimensions for any device type.
 *
 * - "flagship" | "note"  → looks up DEVICE_DIMENSIONS (w/h ignored)
 * - "note_array"         → computes from notes_wide × notes_tall
 * - unknown              → falls back to flagship (matches Python board_html_renderer.py)
 *
 * Mirrors Python resolve_dimensions(), except unknown device types fall back
 * to flagship (matching board_html_renderer.py) rather than raising.
 *
 * @param deviceType  "flagship" | "note" | "note_array"
 * @param notes_wide  Number of notes wide (only used for "note_array"; default 1)
 * @param notes_tall  Number of notes tall (only used for "note_array"; default 1)
 * @returns           { rows, cols }
 */
export function resolveDimensions(deviceType: string, notes_wide = 1, notes_tall = 1): BoardDimensions {
  if (deviceType in DEVICE_DIMENSIONS) {
    return DEVICE_DIMENSIONS[deviceType];
  }
  if (deviceType === "note_array") {
    return noteArrayDimensions(notes_wide, notes_tall);
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
}

/**
 * Canonical family + resolved-size key for page<->board compatibility.
 * Mirrors Python size_key(): e.g. "flagship:6x22", "note:3x15",
 * "note_array:6x30" (a 2×2 note grid). The device family is part of the key
 * on purpose — a Note page is NOT compatible with a 1×1 note array even
 * though both resolve to 3×15. Unknown device types fall back to flagship
 * (family AND dimensions), matching the Python fallback.
 */
export function sizeKey(deviceType: string, notesWide = 1, notesTall = 1): string {
  const family = deviceType in DEVICE_DIMENSIONS || isNoteArray(deviceType) ? deviceType : "flagship";
  const { rows, cols } = resolveDimensions(family, notesWide, notesTall);
  return `${family}:${rows}x${cols}`;
}

/**
 * True when a page renders 1:1 on a board: EXACT sizeKey() match.
 * Mirrors Python pages_compatible_with_board(). Family-aware: flagship ≠ note
 * even at identical dimensions, and note arrays must match the resolved W×H
 * grid exactly.
 */
export function pagesCompatibleWithBoard(page: SizedEntity, board: SizedEntity): boolean {
  return (
    sizeKey(page.device_type || "flagship", page.notes_wide || 1, page.notes_tall || 1) ===
    sizeKey(board.device_type || "flagship", board.notes_wide || 1, board.notes_tall || 1)
  );
}
