/**
 * FiestaBoard Official Color Palette
 *
 * These are the 8 official colors supported by the board hardware.
 * All UI components should use these colors for consistency between
 * the preview display and status indicators.
 *
 * Reference: https://fiestaboard.app/docs/reference/color-guide
 *
 * Color Codes:
 * - 63: Red    - Alerts, hot temperatures, errors
 * - 64: Orange - Warm temperatures, warnings
 * - 65: Yellow - Comfortable temperatures, cautions
 * - 66: Green  - Good status, success, cool temperatures
 * - 67: Blue   - Information, cold temperatures
 * - 68: Violet - Very cold, secondary info
 * - 69: White  - Reserved
 * - 70: Black  - Reserved (same as tile background)
 */

// Board's official color hex values
export const BOARD_COLORS = {
  red: "#eb4034",
  orange: "#f5a623",
  yellow: "#f8e71c",
  green: "#7ed321",
  blue: "#4a90d9",
  violet: "#9b59b6",
  white: "#ffffff",
  black: "#1a1a1a",
} as const;

// Backward compatibility alias
export const FIESTABOARD_COLORS = BOARD_COLORS;

// Type for board color names
export type BoardColorName = keyof typeof BOARD_COLORS;
export type FiestaboardColorName = BoardColorName;

// Numeric code to color mapping (for board API)
export const COLOR_CODE_MAP: Record<string, string> = {
  "63": BOARD_COLORS.red,
  "64": BOARD_COLORS.orange,
  "65": BOARD_COLORS.yellow,
  "66": BOARD_COLORS.green,
  "67": BOARD_COLORS.blue,
  "68": BOARD_COLORS.violet,
  "69": BOARD_COLORS.white,
  "70": BOARD_COLORS.black,
  "71": BOARD_COLORS.black, // Filled tile
};

// Combined mapping for both numeric codes and named colors
export const ALL_COLOR_CODES: Record<string, string> = {
  // Numeric codes
  ...COLOR_CODE_MAP,
  // Named aliases
  red: BOARD_COLORS.red,
  orange: BOARD_COLORS.orange,
  yellow: BOARD_COLORS.yellow,
  green: BOARD_COLORS.green,
  blue: BOARD_COLORS.blue,
  violet: BOARD_COLORS.violet,
  purple: BOARD_COLORS.violet, // alias
  white: BOARD_COLORS.white,
  black: BOARD_COLORS.black,
};

// List of available color names for pickers/selectors
export const AVAILABLE_COLORS: BoardColorName[] = [
  "red",
  "orange",
  "yellow",
  "green",
  "blue",
  "violet",
  "white",
  "black",
];

// Color display configuration for UI elements (backgrounds, text colors)
export const COLOR_DISPLAY: Record<BoardColorName, { bg: string; text: string }> = {
  red: { bg: "bg-board-red", text: "text-board-black" },
  orange: { bg: "bg-board-orange", text: "text-board-black" },
  yellow: { bg: "bg-board-yellow", text: "text-board-black" },
  green: { bg: "bg-board-green", text: "text-board-black" },
  blue: { bg: "bg-board-blue", text: "text-board-black" },
  violet: { bg: "bg-board-violet", text: "text-board-white" },
  white: { bg: "bg-board-white border", text: "text-board-black" },
  black: { bg: "bg-board-black", text: "text-board-white" },
};

// Helper function to get color by name or code
export function getBoardColor(nameOrCode: string): string {
  const lowerKey = nameOrCode.toLowerCase();
  return ALL_COLOR_CODES[nameOrCode] || ALL_COLOR_CODES[lowerKey] || BOARD_COLORS.black;
}

// Backward compatibility alias
export const getFiestaboardColor = getBoardColor;

// Helper function to check if a string is a valid color
export function isValidBoardColor(value: string): boolean {
  const lowerKey = value.toLowerCase();
  return value in ALL_COLOR_CODES || lowerKey in ALL_COLOR_CODES;
}

// Backward compatibility alias
export const isValidFiestaboardColor = isValidBoardColor;
