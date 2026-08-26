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

export interface PanelBoardScaleOptions {
  screenWidthPx: number;
  screenHeightPx: number;
  diagonalInches: number;
  deviceType: "flagship" | "note";
  /** Measured unscaled width of the rendered board (bezel included). */
  boardNaturalWidthPx: number;
  /** User fine-tune for TVs that misreport resolution or overscan. */
  calibration: number;
}

/** CSS transform scale that puts the rendered board at physical size. */
export function panelBoardScale(opts: PanelBoardScaleOptions): number {
  const { screenWidthPx, screenHeightPx, diagonalInches, deviceType, boardNaturalWidthPx, calibration } = opts;
  if (boardNaturalWidthPx <= 0) {
    throw new Error(`panelBoardScale requires a positive measured board width (got ${boardNaturalWidthPx})`);
  }
  const ppi = screenPpi(screenWidthPx, screenHeightPx, diagonalInches);
  const targetWidthPx = PANEL_PHYSICAL_WIDTH_IN[deviceType] * ppi;
  return (targetWidthPx / boardNaturalWidthPx) * calibration;
}
