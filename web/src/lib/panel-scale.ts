/**
 * Physical-scale math for FiestaPanel: render the board at real-world size
 * on a screen whose diagonal the user has told us.
 *
 * All lengths are CSS pixels. `window.screen.width/height` report CSS px
 * for the full screen, so devicePixelRatio cancels out of the ppi math.
 */

/**
 * Real Vestaboard unit widths in inches (bezel included), from the
 * published spec sheets: Flagship 41.2″ × 22″; Note 24.5″ × 8.6″ without
 * its decorative frame. Width is the scale anchor — the rendered bezel is
 * slimmer than the real one, so matching width keeps the flaps life-size.
 */
export const PANEL_PHYSICAL_WIDTH_IN: Record<"flagship" | "note", number> = {
  flagship: 41.2,
  note: 24.5,
};

/** CSS pixels per physical inch for a screen of the given diagonal. */
export function screenPpi(screenWidthPx: number, screenHeightPx: number, diagonalInches: number): number {
  if (screenWidthPx <= 0 || screenHeightPx <= 0 || diagonalInches <= 0) {
    throw new Error(
      `screenPpi requires positive dimensions (got ${screenWidthPx}×${screenHeightPx} @ ${diagonalInches}")`,
    );
  }
  return Math.hypot(screenWidthPx, screenHeightPx) / diagonalInches;
}

/**
 * Auto-fit flap pitch, anchored to the real Vestaboard Note: 24.5″ of
 * frameless unit for 15 columns. Row pitch follows the renderer's invariant
 * tile geometry (FiestaUI board-metrics.ts: tile width = 0.70·h, gutter =
 * 0.145·h in both axes → col pitch 0.845·h, row pitch 1.145·h), so one
 * uniform scale keeps both axes true. Mirrors src/panels/autofit.py.
 */
export const NOTE_COL_PITCH_IN = 24.5 / 15;
export const NOTE_ROW_PITCH_IN = NOTE_COL_PITCH_IN * (1.145 / 0.845);

/** One auto-fit building block: a 15×3 Note at physical pitch. */
export const BLOCK_WIDTH_IN = 15 * NOTE_COL_PITCH_IN;
export const BLOCK_HEIGHT_IN = 3 * NOTE_ROW_PITCH_IN;

/** Grid axes never exceed this many Note blocks (mirrors src/devices.py). */
const MAX_NOTES_PER_AXIS = 8;

/**
 * (width, height) in inches of an aspectW:aspectH screen with the given
 * diagonal. Mirrors src/panels/autofit.py screen_dimensions_in().
 */
export function screenDimensionsIn(diagonalInches: number, aspectW = 16, aspectH = 9): [number, number] {
  if (diagonalInches <= 0 || aspectW <= 0 || aspectH <= 0) {
    throw new Error(`screenDimensionsIn requires positive inputs (got ${diagonalInches}" @ ${aspectW}:${aspectH})`);
  }
  const hyp = Math.hypot(aspectW, aspectH);
  return [(diagonalInches * aspectW) / hyp, (diagonalInches * aspectH) / hyp];
}

/**
 * (notesWide, notesTall) of the largest true-scale grid that fits the
 * screen. Mirrors src/panels/autofit.py compute_autofit_grid() — the panel
 * editor previews the grid live with this, and the backend computes the
 * board it actually creates with the Python twin; their tests share the
 * same example cases so drift fails loudly.
 */
export function computeAutofitGrid(
  diagonalInches: number,
  aspectW = 16,
  aspectH = 9,
): { notesWide: number; notesTall: number } {
  const [widthIn, heightIn] = screenDimensionsIn(diagonalInches, aspectW, aspectH);
  const clamp = (blocks: number) => Math.max(1, Math.min(MAX_NOTES_PER_AXIS, blocks));
  return {
    notesWide: clamp(Math.floor(widthIn / BLOCK_WIDTH_IN)),
    notesTall: clamp(Math.floor(heightIn / BLOCK_HEIGHT_IN)),
  };
}

/** Max stretch beyond true flap size allowed to close the gap to the screen edge. */
export const MAX_FILL_STRETCH = 1.1;

export interface PanelAutofitScaleOptions {
  screenWidthPx: number;
  screenHeightPx: number;
  diagonalInches: number;
  /** Grid columns (drives the physical width anchor). */
  cols: number;
  /** Measured unscaled grid size (tiles only, no bezel). */
  gridWidthPx: number;
  gridHeightPx: number;
  /** User fine-tune for TVs that misreport resolution or overscan. */
  calibration: number;
  /** Physical column pitch in inches; defaults to the Note pitch. */
  colPitchIn?: number;
}

/**
 * Scale for a borderless auto-fit grid: flaps at true physical size, then
 * gently stretched (≤ MAX_FILL_STRETCH) toward the nearest screen edge.
 *
 * Never shrinks below true size to fill — EXCEPT when the grid overflows
 * the screen at true size. Auto-fit always picks a grid that fits, so that
 * only happens on a screen smaller than one Note block (the 3" pocket
 * displays panels support): there the whole block shrinks to fit instead
 * of showing a life-size crop of its top-left corner.
 */
export function panelAutofitScale(opts: PanelAutofitScaleOptions): number {
  const {
    screenWidthPx,
    screenHeightPx,
    diagonalInches,
    cols,
    gridWidthPx,
    gridHeightPx,
    calibration,
    colPitchIn = NOTE_COL_PITCH_IN,
  } = opts;
  if (gridWidthPx <= 0 || gridHeightPx <= 0 || cols <= 0) {
    throw new Error(
      `panelAutofitScale requires positive grid measurements (got ${gridWidthPx}×${gridHeightPx}, ${cols} cols)`,
    );
  }
  const ppi = screenPpi(screenWidthPx, screenHeightPx, diagonalInches);
  const trueScale = (cols * colPitchIn * ppi) / gridWidthPx;
  const fill = Math.min(screenWidthPx / (gridWidthPx * trueScale), screenHeightPx / (gridHeightPx * trueScale));
  const stretch = fill < 1 ? fill : Math.min(MAX_FILL_STRETCH, fill);
  return trueScale * stretch * calibration;
}
