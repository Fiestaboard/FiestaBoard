/**
 * Constants for TipTap Template Editor
 * Maps template syntax to FiestaBoard hardware constraints
 */

// Device types
export type DeviceType = "flagship" | "note";

export interface DeviceDimensions {
  rows: number;
  cols: number;
}

// Board dimensions per device type
export const DEVICE_DIMENSIONS: Record<DeviceType, DeviceDimensions> = {
  flagship: { rows: 6, cols: 22 },
  note: { rows: 3, cols: 15 },
};

// FiestaBoard color codes (63-70)
export const BOARD_COLORS = {
  red: 63,
  orange: 64,
  yellow: 65,
  green: 66,
  blue: 67,
  violet: 68,
  purple: 68, // alias
  white: 69,
  black: 70,
} as const;

export type BoardColorName = keyof typeof BOARD_COLORS;

// Board dimensions (default flagship)
export const BOARD_WIDTH = 22; // characters per line
export const BOARD_LINES = 6; // total lines

// Special variable names
export const FILL_SPACE_VAR = "fill_space";
export const FILL_SPACE_REPEAT_VAR = "fill_space_repeat";
