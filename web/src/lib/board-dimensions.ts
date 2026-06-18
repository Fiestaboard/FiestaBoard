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
 * Mirrors Python resolve_dimensions().
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
