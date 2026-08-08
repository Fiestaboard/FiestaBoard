/**
 * Plugin registry data for the docs-site plugin directory.
 * Re-exports plugin entries from the root plugin-registry.json and rendered
 * board previews from the root plugin-previews.json (the seed refreshed by
 * scripts/sync_plugin_previews.py — manifest teaser/previews win, seed
 * entries are the fallback).
 */
import previewsSeed from "../../plugin-previews.json";
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

/** One literal board, at one shape, from plugin-previews.json. */
export interface BoardPreviewEntry {
  /** Human tab label; when absent, derive one with `previewLabel()`. */
  label?: string;
  device_type?: "flagship" | "note" | "note_array";
  notes_wide?: number;
  notes_tall?: number;
  rows: string[];
}

export interface PluginPreviewEntry {
  /** One-line directory-card strip, at most 15 tiles. */
  teaser: string;
  /** Detail-page boards; the first entry is the hero. */
  previews: BoardPreviewEntry[];
}

export const pluginPreviews: Record<string, PluginPreviewEntry> = previewsSeed.plugins as Record<
  string,
  PluginPreviewEntry
>;

/** Tab label for a preview: its declared label, or one derived from the shape. */
export function previewLabel(preview: BoardPreviewEntry): string {
  if (preview.label) return preview.label;
  if (preview.device_type === "note_array") {
    return `Note Array ${preview.notes_wide ?? 1}×${preview.notes_tall ?? 1}`;
  }
  return preview.device_type === "note" ? "Note" : "Flagship";
}

/** The newline-joined message `StaticBoardDisplay` renders. */
export function previewMessage(preview: BoardPreviewEntry): string {
  return preview.rows.join("\n");
}

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

