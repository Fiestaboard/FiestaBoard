/**
 * Plugin registry data for the docs-site plugin directory.
 * Re-exports plugin entries from the root plugin-registry.json.
 */
import registry from "../../plugin-registry.json";

export interface PluginEntry {
  id: string;
  name: string;
  description: string;
  repository: string;
  /** When set, README is fetched from this branch only (matches plugin-registry.json). */
  branch?: string;
  author: string;
  fiestaboard_version: string;
  icon: string;
  category: string;
}

export const plugins: PluginEntry[] = registry.plugins as PluginEntry[];

export const CATEGORY_LABELS: Record<string, string> = {
  art: "Display Art",
  data: "Data & Information",
  entertainment: "Entertainment",
  home: "Smart Home",
  transit: "Transportation",
  utility: "Utilities",
  weather: "Weather & Environment",
};

export const CATEGORIES = Object.keys(CATEGORY_LABELS);

/**
 * Converts a plugin ID to its board display image path.
 * e.g. "air_fog" → "/img/air-fog-display.png"
 */
export function pluginImagePath(id: string): string {
  return `/img/${id.replace(/_/g, "-")}-display.png`;
}

/**
 * Derives the raw GitHub content URL for a plugin's board-display screenshot.
 * e.g. pluginBoardImagePath(plugin, "dark")
 *   → "https://raw.githubusercontent.com/Fiestaboard/fiestaboard-plugin--air-fog/main/docs/black/board-display.png"
 *
 * Falls back to the legacy local static path if no repository is available.
 */
export function pluginBoardImagePath(plugin: PluginEntry, colorMode: "light" | "dark"): string {
  const boardDir = colorMode === "light" ? "white" : "black";

  if (plugin.repository) {
    const cleaned = plugin.repository.replace(/\.git$/, "").replace(/\/$/, "");
    const match = cleaned.match(/github\.com\/(.+)/);
    if (match) {
      const branch = plugin.branch?.trim() || "main";
      return `https://raw.githubusercontent.com/${match[1]}/${branch}/docs/${boardDir}/board-display.png`;
    }
  }

  // Fallback for plugins without an external repository
  return `/img/${boardDir}/${plugin.id.replace(/_/g, "-")}-display.png`;
}
