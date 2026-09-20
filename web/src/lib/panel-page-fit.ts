/**
 * Matching pages to FiestaPanels.
 *
 * A panel is a virtual board whose grid is auto-fit from the TV's diagonal, and
 * that grid is always a note array. So a page "for a panel" is simply a
 * `note_array` page whose grid equals the panel's board — nothing is stored on
 * the page to say which panel it was made for, and nothing needs to be: two
 * boards of the same shape display the same page identically.
 *
 * That makes the geometry the whole relationship, and this module the one place
 * the comparison lives.
 */
import type { Panel } from "@/lib/api";
import { sizeKey } from "@/lib/board-dimensions";

/** A panel the app can size a page to. */
export interface PanelTarget {
  id: string;
  name: string;
  /** The panel board's device family, which is part of the compatibility key. */
  deviceType: string;
  /** Notes across / down, as the API reports them. */
  notesWide: number;
  notesTall: number;
  /** The same grid in flaps. */
  rows: number;
  cols: number;
}

/**
 * The panels a page can be sized to, in the order the API listed them.
 *
 * Skips a panel whose board is gone (`board_missing`) and one whose payload
 * predates `notes_wide`/`notes_tall` — an unknown grid is not something to
 * guess at, because guessing wrong authors a page that renders clipped.
 */
export function panelTargets(panels: Panel[] | undefined): PanelTarget[] {
  if (!panels) return [];
  const targets: PanelTarget[] = [];
  for (const panel of panels) {
    if (panel.board_missing) continue;
    const { notes_wide: notesWide, notes_tall: notesTall, rows, cols } = panel;
    if (
      typeof notesWide !== "number" ||
      typeof notesTall !== "number" ||
      typeof rows !== "number" ||
      typeof cols !== "number"
    ) {
      continue;
    }
    targets.push({
      id: panel.id,
      name: panel.name,
      deviceType: panel.device_type || "note_array",
      notesWide,
      notesTall,
      rows,
      cols,
    });
  }
  return targets;
}

/**
 * The panels this page renders 1:1 on, first listed first.
 *
 * Decided by ``sizeKey`` — the platform's own page↔board compatibility key,
 * mirrored in ``src/devices.py`` — and not by comparing raw flap counts. That
 * key is FAMILY-aware on purpose: a plain ``note`` page and a 1×1 ``note_array``
 * both resolve to 3×15, and the platform refuses to call them compatible. A 1×1
 * panel is easy to come by (``compute_autofit_grid`` returns 1×1 under about 25
 * inches), so comparing flaps alone would label every Note page "Fits Office
 * TV" while ``page-grid-selector`` filters that page out for that board and
 * ``schedule-entry-form`` warns it is incompatible. The label must never promise
 * a fit the rest of the app then refuses.
 */
export function panelsFittingGrid(
  targets: PanelTarget[],
  deviceType: string,
  notesWide = 1,
  notesTall = 1,
): PanelTarget[] {
  const pageKey = sizeKey(deviceType, notesWide, notesTall);
  return targets.filter((target) => sizeKey(target.deviceType, target.notesWide, target.notesTall) === pageKey);
}
