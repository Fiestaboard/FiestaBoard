// Plugin registry domain: the marketplace catalog, git installs,
// uninstall, and plugin update checks.

import type { BoardPreviewEntry } from "@fiestaboard/ui";

import { fetchApi } from "./core";

export interface RegistryEntry {
  id: string;
  name: string;
  description: string;
  repository: string;
  branch: string;
  author: string;
  fiestaboard_version: string;
  icon: string;
  category: string;
  installed: boolean;
  /**
   * "data" (a plugin that publishes template variables) or "transition" (a
   * frame-by-frame board animation). Absent on registry payloads that predate
   * the field — treat missing as "data".
   */
  plugin_type?: "data" | "transition";
  /**
   * One-line board strip for the marketplace card, at most 15 tiles. Empty for
   * plugins that predate the previews contract.
   */
  teaser: string;
  /** Literal boards for the detail-page hero, one per declared shape. */
  previews: BoardPreviewEntry[];
}

export interface RegistryListResponse {
  entries: RegistryEntry[];
}

export interface PluginInstallResponse {
  status: string;
  plugin_id: string;
  message: string;
}

export interface PluginUninstallResponse {
  status: string;
  plugin_id: string;
  message: string;
}

export interface PluginUpdatesResponse {
  updates: Record<string, boolean>;
}

export interface PluginUpdateCheckResponse {
  checked: number;
  updates_available: string[];
}

export interface PluginApplyUpdatesResponse {
  updated: string[];
  failed: Record<string, string>;
  message: string;
}

export const pluginRegistryApi = {
  // Plugin registry endpoints
  listRegistryPlugins: () => fetchApi<RegistryListResponse>("/plugins/registry"),

  installRegistryPlugin: (pluginId: string) =>
    fetchApi<PluginInstallResponse>(`/plugins/registry/${pluginId}/install`, {
      method: "POST",
    }),

  installGitPlugin: (repoUrl: string, pluginId?: string, branch?: string) =>
    fetchApi<PluginInstallResponse>("/plugins/install", {
      method: "POST",
      body: JSON.stringify({ repository: repoUrl, plugin_id: pluginId, branch: branch ?? "" }),
    }),

  uninstallPlugin: (pluginId: string) =>
    fetchApi<PluginUninstallResponse>(`/plugins/${pluginId}/uninstall`, {
      method: "DELETE",
    }),

  updatePlugin: (pluginId: string) =>
    fetchApi<PluginInstallResponse>(`/plugins/${pluginId}/update`, {
      method: "POST",
    }),

  getPluginUpdates: () => fetchApi<PluginUpdatesResponse>("/plugins/updates"),

  triggerPluginUpdateCheck: () =>
    fetchApi<PluginUpdateCheckResponse>("/plugins/updates/check", {
      method: "POST",
      timeoutMs: 120000,
    }),

  applyAllPluginUpdates: () =>
    fetchApi<PluginApplyUpdatesResponse>("/plugins/updates/apply", {
      method: "POST",
    }),
};
