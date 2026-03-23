/**
 * Plugin registry data for the docs-site plugin directory.
 * Re-exports plugin entries from the root plugin-registry.json.
 */
import registry from '../../plugin-registry.json';

export interface PluginEntry {
  id: string;
  name: string;
  description: string;
  repository: string;
  author: string;
  fiestaboard_version: string;
  icon: string;
  category: string;
}

export const plugins: PluginEntry[] = registry.plugins as PluginEntry[];

export const CATEGORY_LABELS: Record<string, string> = {
  art: 'Display Art',
  data: 'Data & Information',
  entertainment: 'Entertainment',
  home: 'Smart Home',
  transit: 'Transportation',
  utility: 'Utilities',
  weather: 'Weather & Environment',
};

export const CATEGORIES = Object.keys(CATEGORY_LABELS);

/**
 * Converts a plugin ID to its board display image path.
 * e.g. "air_fog" → "/img/air-fog-display.png"
 */
export function pluginImagePath(id: string): string {
  return `/img/${id.replace(/_/g, '-')}-display.png`;
}

/**
 * Converts a plugin ID to its board display image path for a specific board colour.
 * e.g. pluginBoardImagePath("air_fog", "dark") → "/img/black/air-fog-display.png"
 */
export function pluginBoardImagePath(id: string, colorMode: 'light' | 'dark'): string {
  const boardDir = colorMode === 'light' ? 'white' : 'black';
  return `/img/${boardDir}/${id.replace(/_/g, '-')}-display.png`;
}
