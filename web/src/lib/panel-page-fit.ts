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
import { resolveDimensions } from "@/lib/board-dimensions";

/** A panel the app can size a page to. */
export interface PanelTarget {
  id: string;
  name: string;
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
    targets.push({ id: panel.id, name: panel.name, notesWide, notesTall, rows, cols });
  }
  return targets;
}

/**
 * The panels whose board is exactly this page's grid, first listed first.
 *
 * Compared in flaps rather than in Notes so the answer is about the board and
 * not about which device vocabulary was used to describe it: a 3×15 `note` page
 * genuinely fits a one-Note panel.
 */
export function panelsFittingGrid(
  targets: PanelTarget[],
  deviceType: string,
  notesWide = 1,
  notesTall = 1,
): PanelTarget[] {
  const dims = resolveDimensions(deviceType, notesWide, notesTall);
  return targets.filter((target) => target.rows === dims.rows && target.cols === dims.cols);
}
