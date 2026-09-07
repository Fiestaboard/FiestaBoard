// Plugins domain: installed plugin listing/config/enablement,
// options catalogs, data/variables/errors, instances, demo pages.

import { fetchApi } from "./core";
import type { Page } from "./pages";
import type { VariableGroup, VariableMetadataEntry } from "./templates";

// Logs types
// Plugin system types
export interface PluginInfo {
  id: string;
  name: string;
  version: string;
  description: string;
  author: string;
  enabled: boolean;
  configured: boolean;
  icon: string;
  category: string;
  /**
   * `"transition"` plugins supply a board-transition animation instead of
   * template data. They have no polling loop, so the registry runs any
   * installed one regardless of `enabled` — the UI must not offer a toggle
   * for them. Absent on responses that predate the field; treat as `"data"`.
   */
  plugin_type?: "data" | "transition";
  fiestaboard_version?: string;
  config: Record<string, unknown>;
  source?: { source_type: "builtin" | "registry" | "external" | "git"; repository_url?: string; local_path?: string };
  update_available?: boolean;
  instance_label?: string | null;
  base_plugin_id?: string;
  settings_schema?: Record<string, unknown>;
}

export interface PluginsListResponse {
  plugins: PluginInfo[];
  plugin_system_enabled: boolean;
  total: number;
  enabled_count: number;
  message?: string;
}

/**
 * One selectable choice returned by a plugin's `get_options()`.
 * Mirrors `src/plugins/base.py::Option`. `value` is a JSON scalar and is what
 * gets persisted into the plugin's config verbatim.
 */
export interface PluginOption {
  value: string | number | boolean;
  label: string;
  description?: string | null;
  group?: string | null;
  preview?: string | null;
  disabled?: boolean;
  meta?: Record<string, unknown> | null;
}

/** Body of `POST /plugins/{plugin_id}/options/{options_id}`. */
export interface PluginOptionsRequest {
  /** Values of the fields this one `depends_on`, so the plugin can scope the catalog. */
  parent?: Record<string, unknown>;
  /** Free-text the user typed, for server-side search. */
  query?: string;
  limit?: number;
  cursor?: string | null;
}

/** Response of `POST /plugins/{plugin_id}/options/{options_id}`. */
export interface PluginOptionsResponse {
  plugin_id: string;
  options_id: string;
  options: PluginOption[];
  has_more: boolean;
  cursor: string | null;
  total: number | null;
  /**
   * Human-readable reason the list is empty or partial (the plugin raised
   * `OptionsUnavailable`). Not an incident — the UI shows it as a hint.
   */
  error: string | null;
  cached: boolean;
  stale: boolean;
  cache_seconds: number;
}

export interface PluginManifest {
  id: string;
  name: string;
  version: string;
  description: string;
  author: string;
  icon?: string;
  category?: string;
  repository?: string;
  documentation?: string;
  settings_schema: Record<string, unknown>;
  variables: {
    auto_discover?: boolean;
    groups?: Record<string, VariableGroup>;
    simple?: string[] | Record<string, VariableMetadataEntry>;
    arrays?: Record<
      string,
      {
        label_field: string;
        item_fields: string[];
        sub_arrays?: Record<
          string,
          {
            key_type?: "index" | "dynamic";
            key_field?: string;
            label_field?: string;
            item_fields: string[];
          }
        >;
      }
    >;
    nested?: Record<string, unknown>;
    dynamic?: boolean;
  };
  max_lengths: Record<string, number>;
  variable_metadata?: Record<string, VariableMetadataEntry>;
  variable_groups?: Record<string, VariableGroup>;
  color_rules_schema?: Record<string, unknown>;
  env_vars?: Array<{
    name: string;
    required: boolean;
    description: string;
  }>;
}

export interface PluginDetailResponse {
  id: string;
  name: string;
  version: string;
  description: string;
  author: string;
  icon: string;
  category: string;
  enabled: boolean;
  config: Record<string, unknown>;
  settings_schema: Record<string, unknown>;
  variables: Record<string, unknown>;
  max_lengths: Record<string, number>;
  env_vars: Array<{
    name: string;
    required: boolean;
    description: string;
  }>;
  documentation: string;
  has_demo: boolean;
  demo_page_id: string | null;
  instance_label?: string | null;
  base_plugin_id?: string;
  instances?: PluginInstanceInfo[];
}

export interface PluginInstanceInfo {
  label: string;
  key: string;
  enabled: boolean;
  has_config: boolean;
}

export interface PluginInstancesResponse {
  plugin_id: string;
  instances: PluginInstanceInfo[];
  total: number;
}

export interface PluginInstanceCreateResponse {
  status: string;
  plugin_id: string;
  instance_label: string;
  instance_key: string;
  message: string;
}

export interface PluginInstanceDeleteResponse {
  status: string;
  plugin_id: string;
  instance_label: string;
  instance_key: string;
  message: string;
}

export interface PluginDemoPageResponse {
  exists: boolean;
  page_id: string | null;
  has_demo_template: boolean;
}

export interface PluginDemoPageCreateResponse {
  status: "created" | "recreated";
  page: Page;
}

export interface PluginConfigUpdateResponse {
  status: string;
  plugin_id: string;
  config: Record<string, unknown>;
}

export interface PluginEnableResponse {
  status: string;
  plugin_id: string;
  enabled: boolean;
}

export interface PluginDataResponse {
  plugin_id: string;
  available: boolean;
  data: Record<string, unknown>;
  formatted?: string;
  error?: string;
}

export interface PluginVariablesResponse {
  plugin_id: string;
  variables: Record<string, unknown>;
  max_lengths: Record<string, number>;
  color_rules_schema: Record<string, unknown>;
}

export interface AllPluginVariablesResponse {
  variables: Record<string, string[]>;
  max_lengths: Record<string, number>;
  plugin_system_enabled: boolean;
}

export interface PluginErrorsResponse {
  errors: Record<string, string[]>;
  plugin_system_enabled: boolean;
}

export const pluginsApi = {
  // Plugin system endpoints
  listPlugins: () => fetchApi<PluginsListResponse>("/plugins"),

  getPlugin: (pluginId: string) => fetchApi<PluginDetailResponse>(`/plugins/${pluginId}`),

  getPluginManifest: (pluginId: string) => fetchApi<PluginManifest>(`/plugins/${pluginId}/manifest`),

  updatePluginConfig: (pluginId: string, config: Record<string, unknown>) =>
    fetchApi<PluginConfigUpdateResponse>(`/plugins/${pluginId}/config`, {
      method: "PUT",
      body: JSON.stringify({ config }),
    }),

  enablePlugin: (pluginId: string) =>
    fetchApi<PluginEnableResponse>(`/plugins/${pluginId}/enable`, {
      method: "POST",
    }),

  disablePlugin: (pluginId: string) =>
    fetchApi<PluginEnableResponse>(`/plugins/${pluginId}/disable`, {
      method: "POST",
    }),

  /**
   * Browse a plugin's upstream catalog for one `remote-options` field. Runs on
   * a throwaway plugin instance server-side, so it is safe to call while the
   * settings dialog is open on an unconfigured plugin.
   */
  getPluginOptions: (pluginId: string, optionsId: string, request: PluginOptionsRequest = {}) =>
    fetchApi<PluginOptionsResponse>(`/plugins/${pluginId}/options/${optionsId}`, {
      method: "POST",
      body: JSON.stringify(request),
    }),

  getPluginData: (pluginId: string) => fetchApi<PluginDataResponse>(`/plugins/${pluginId}/data`),

  getPluginVariables: (pluginId: string) => fetchApi<PluginVariablesResponse>(`/plugins/${pluginId}/variables`),

  getPluginDemoPage: (pluginId: string) => fetchApi<PluginDemoPageResponse>(`/plugins/${pluginId}/demo-page`),

  createPluginDemoPage: (pluginId: string) =>
    fetchApi<PluginDemoPageCreateResponse>(`/plugins/${pluginId}/demo-page`, {
      method: "POST",
    }),

  getAllPluginVariables: () => fetchApi<AllPluginVariablesResponse>("/plugins/variables/all"),

  getPluginErrors: () => fetchApi<PluginErrorsResponse>("/plugins/errors"),

  // Plugin instance endpoints
  listPluginInstances: (pluginId: string) => fetchApi<PluginInstancesResponse>(`/plugins/${pluginId}/instances`),

  createPluginInstance: (pluginId: string, label: string) =>
    fetchApi<PluginInstanceCreateResponse>(`/plugins/${pluginId}/instances`, {
      method: "POST",
      body: JSON.stringify({ label }),
    }),

  deletePluginInstance: (pluginId: string, instanceLabel: string) =>
    fetchApi<PluginInstanceDeleteResponse>(`/plugins/${pluginId}/instances/${instanceLabel}`, {
      method: "DELETE",
    }),
};
