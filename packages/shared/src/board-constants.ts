/**
 * Board hardware constants shared between web and mobile.
 */

// Re-use the DeviceType from api-types
import type { DeviceType } from './api-types';
export type { DeviceType } from './api-types';

export interface DeviceDimensions {
  rows: number;
  cols: number;
}

// Board dimensions per device type
export const DEVICE_DIMENSIONS: Record<DeviceType, DeviceDimensions> = {
  flagship: { rows: 6, cols: 22 },
  note: { rows: 3, cols: 15 },
};

// Default board dimensions (flagship)
export const BOARD_WIDTH = 22;
export const BOARD_LINES = 6;

// Board color codes (hardware character codes 63-70)
export const BOARD_COLOR_CODES = {
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

export type BoardColorCodeName = keyof typeof BOARD_COLOR_CODES;

// All displayable board characters indexed by character code (0-71)
export const BOARD_CHARS = [
  ' ',  // 0  - Blank
  'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M',
  'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z',
  '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
  '!', '@', '#', '$', '(', ')', ' ', '-', ' ', '+', '&', '=', ';', ':',
  ' ', "'", '"', '%', ',', '.', ' ', ' ', '/', '?', ' ', '°',
  '63', '64', '65', '66', '67', '68', '69', '70', '71',
];

// Color tile character codes
export const COLOR_TILE_CODES = new Set(['63', '64', '65', '66', '67', '68', '69', '70', '71']);

// Special variable names used in templates
export const FILL_SPACE_VAR = "fill_space";
export const FILL_SPACE_REPEAT_VAR = "fill_space_repeat";
