import { BOARD_COLORS } from '@fiestaboard/shared';

/**
 * App theme colors for FiestaBoard mobile.
 * Uses the board's official colors plus iOS system-style tokens.
 */
export const colors = {
  // Board colors (shared with web)
  board: BOARD_COLORS,

  // App colors
  primary: '#f5a623', // FiestaBoard orange
  primaryLight: '#ffd080',

  // Semantic colors (adapt to light/dark via useColorScheme)
  light: {
    background: '#f2f2f7',
    surface: '#ffffff',
    surfaceSecondary: '#f2f2f7',
    text: '#000000',
    textSecondary: '#8e8e93',
    separator: '#c6c6c8',
    destructive: '#ff3b30',
    success: '#34c759',
    warning: '#ff9500',
    info: '#007aff',
  },
  dark: {
    background: '#000000',
    surface: '#1c1c1e',
    surfaceSecondary: '#2c2c2e',
    text: '#ffffff',
    textSecondary: '#8e8e93',
    separator: '#38383a',
    destructive: '#ff453a',
    success: '#30d158',
    warning: '#ff9f0a',
    info: '#0a84ff',
  },
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
} as const;

export const fontSize = {
  caption: 12,
  body: 17,
  headline: 20,
  title: 28,
  largeTitle: 34,
} as const;
