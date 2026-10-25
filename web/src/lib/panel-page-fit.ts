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
import type { BoardInstance, Panel } from "@/lib/api";
import { isPanel, sizeKey } from "@/lib/board-dimensions";
import { isLedModel, resolveBoardModel } from "@/lib/device-preview";

/**
 * A display the app can size a page to: a FiestaPanel, or any other board
 * whose shape is a custom character grid (an output plugin's — an LED matrix).
 * The same geometry rule covers both: a page for it is a `panel` page of its
 * grid, and nothing on the page names the display.
 */
export interface PanelTarget {
  /** The panel's id for a FiestaPanel; the board's id for any other display. */
  id: string;
  name: string;
  /**
   * `panel` for a FiestaPanel (listed by `GET /panels`); `display` for any
   * other board with a custom grid (from `GET /settings/board`). Absent reads
   * as `panel`. Picks the size-picker value prefix (see {@link targetValue}).
   */
  kind?: "panel" | "display";
  /** The board pages for this target are shown on; null/absent when unknown. */
  boardId?: string | null;
  /** The board's device-model label (e.g. "Divoom Pixoo 64"); null when unknown. */
  modelLabel?: string | null;
  /** True when the board is drawn as an LED matrix. */
  led?: boolean;
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

/**
 * Every display a page can be sized to: the FiestaPanels first (as
 * {@link panelTargets} lists them), then every other board whose shape is a
 * custom character grid — a `panel` board with `grid_rows` × `grid_cols`,
 * which is how an output plugin's board (an LED matrix such as a Pixoo) is
 * stored. Driven only by board data: nothing here knows any particular
 * device. A panel's own virtual board is not listed a second time.
 */
export function displayTargets(
  panels: Panel[] | undefined,
  boards: readonly BoardInstance[] | undefined,
): PanelTarget[] {
  const boardOfPanel = new Map((panels ?? []).map((p) => [p.id, p.board_id]));
  const targets: PanelTarget[] = panelTargets(panels).map((t) => ({
    ...t,
    kind: "panel",
    boardId: boardOfPanel.get(t.id) ?? null,
  }));
  const panelBoards = new Set(boardOfPanel.values());
  for (const board of boards ?? []) {
    if (panelBoards.has(board.id) || !isPanel(board.device_type)) continue;
    const rows = board.grid_rows;
    const cols = board.grid_cols;
    if (typeof rows !== "number" || typeof cols !== "number" || rows <= 0 || cols <= 0) continue;
    const model = resolveBoardModel(board);
    targets.push({
      id: board.id,
      name: board.name,
      kind: "display",
      boardId: board.id,
      modelLabel: model?.label ?? null,
      led: isLedModel(model),
      deviceType: "panel",
      notesWide: 1,
      notesTall: 1,
      gridRows: rows,
      gridCols: cols,
      rows,
      cols,
    });
  }
  return targets;
}

/** The size picker's value for a target: `panel:<id>` or `display:<id>`. */
export function targetValue(target: PanelTarget): string {
  return `${target.kind ?? "panel"}:${target.id}`;
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
