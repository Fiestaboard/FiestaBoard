/**
 * Matching pages to FiestaPanels.
 *
 * A panel is a virtual board whose grid is auto-fit from the TV's diagonal,
 * per character: a `panel` board of `grid_rows` × `grid_cols`. So a page "for
 * a panel" is simply a `panel` page whose grid equals the panel's board —
 * nothing is stored on the page to say which panel it was made for, and
 * nothing needs to be: two boards of the same shape display the same page
 * identically. (Panels created before per-character fitting were `note_array`
 * boards fit in whole Notes; their payloads are still understood.)
 *
 * That makes the geometry the whole relationship, and this module the one place
 * the comparison lives.
 */
import type { Panel } from "@/lib/api";
import { isPanel, sizeKey } from "@/lib/board-dimensions";

/** A panel the app can size a page to. */
export interface PanelTarget {
  id: string;
  name: string;
  /**
   * The panel board's device family, which is part of the compatibility key:
   * "panel" for a per-character board, "note_array" for a legacy one.
   */
  deviceType: string;
  /** Notes across / down for a legacy note-array board; 1 for a panel board. */
  notesWide: number;
  notesTall: number;
  /** The character grid of a panel board; null for a legacy note-array board. */
  gridRows: number | null;
  gridCols: number | null;
  /** The grid in flaps, whatever the family. */
  rows: number;
  cols: number;
}

/**
 * The panels a page can be sized to, in the order the API listed them.
 *
 * Skips a panel whose board is gone (`board_missing`) and one whose payload
 * lacks the grid its family needs (rows/cols for a panel board,
 * `notes_wide`/`notes_tall` for a legacy note-array one) — an unknown grid is
 * not something to guess at, because guessing wrong authors a page that
 * renders clipped.
 */
export function panelTargets(panels: Panel[] | undefined): PanelTarget[] {
  if (!panels) return [];
  const targets: PanelTarget[] = [];
  for (const panel of panels) {
    if (panel.board_missing) continue;
    const { notes_wide: notesWide, notes_tall: notesTall, rows, cols } = panel;
    if (typeof rows !== "number" || typeof cols !== "number") continue;
    if (isPanel(panel.device_type ?? "")) {
      targets.push({
        id: panel.id,
        name: panel.name,
        deviceType: "panel",
        notesWide: 1,
        notesTall: 1,
        gridRows: rows,
        gridCols: cols,
        rows,
        cols,
      });
      continue;
    }
    if (typeof notesWide !== "number" || typeof notesTall !== "number") continue;
    targets.push({
      id: panel.id,
      name: panel.name,
      deviceType: panel.device_type || "note_array",
      notesWide,
      notesTall,
      gridRows: null,
      gridCols: null,
      rows,
      cols,
    });
  }
  return targets;
}

/** The compatibility key of a panel's board (see `sizeKey`). */
export function panelTargetKey(target: PanelTarget): string {
  return sizeKey(target.deviceType, target.notesWide, target.notesTall, target.gridRows, target.gridCols);
}

/**
 * The panels this page renders 1:1 on, first listed first.
 *
 * Decided by ``sizeKey`` — the platform's own page↔board compatibility key,
 * mirrored in ``src/devices.py`` — and not by comparing raw flap counts. That
 * key is FAMILY-aware on purpose: a plain ``note`` page, a 1×1 ``note_array``
 * and a 3×15 ``panel`` all resolve to 3×15, and the platform refuses to call
 * them compatible. Comparing flaps alone would label a Note page "Fits Office
 * TV" while ``page-grid-selector`` filters that page out for that board and
 * ``schedule-entry-form`` warns it is incompatible. The label must never
 * promise a fit the rest of the app then refuses.
 */
export function panelsFittingGrid(
  targets: PanelTarget[],
  deviceType: string,
  notesWide = 1,
  notesTall = 1,
  gridRows?: number | null,
  gridCols?: number | null,
): PanelTarget[] {
  const pageKey = sizeKey(deviceType, notesWide, notesTall, gridRows, gridCols);
  return targets.filter((target) => panelTargetKey(target) === pageKey);
}
