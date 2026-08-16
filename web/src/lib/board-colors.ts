/**
 * FiestaBoard Official Color Palette — re-exported from the design system.
 *
 * The palette itself lives in `@fiestaboard/ui` (`src/lib/board-colors.ts`),
 * where the hex values are kept in lockstep with the `--color-board-*` tokens
 * in theme.css. This module exists only so app code can keep importing from
 * `@/lib/board-colors`, and to carry the pre-3.0 alias names that the design
 * system does not export.
 *
 * Do not redefine any colour here — a drifted copy silently disagrees with the
 * board hardware. Add new colours upstream in FiestaUI.
 *
 * Reference: https://fiestaboard.app/docs/reference/color-guide
 */

import {
  ALL_COLOR_CODES,
  AVAILABLE_COLORS,
  BOARD_COLORS,
  type BoardColorName,
  COLOR_CODE_MAP,
  COLOR_DISPLAY,
  getBoardColor,
  isValidBoardColor,
  resolveColorCode,
} from "@fiestaboard/ui";

export {
  ALL_COLOR_CODES,
  AVAILABLE_COLORS,
  BOARD_COLORS,
  COLOR_CODE_MAP,
  COLOR_DISPLAY,
  getBoardColor,
  isValidBoardColor,
  resolveColorCode,
};
export type { BoardColorName };

// Backward compatibility aliases (pre-3.0 names, not exported by @fiestaboard/ui).
export const FIESTABOARD_COLORS = BOARD_COLORS;
export const getFiestaboardColor = getBoardColor;
export const isValidFiestaboardColor = isValidBoardColor;
export type FiestaboardColorName = BoardColorName;
