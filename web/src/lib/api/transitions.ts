// Transition plugins domain (beta): frame-by-frame board animation
// plugins under /transitions/*. Distinct from the global transition
// strategy settings in ./settings.ts.

import { fetchApi } from "./core";
import type { DeviceType } from "./shared";

// Transition plugins (beta): frame-by-frame board animation plugins.
// Endpoints 404 until beta.transition_plugins_enabled is on.
export interface TransitionPluginEntry {
  id: string;
  name: string;
  description: string;
  icon: string;
  version: string;
  author: string;
  settings_schema: Record<string, unknown>;
  transition_settings: {
    interruptible: boolean;
    min_interval_ms: number;
    max_frames: number;
    max_runtime_seconds: number;
  };
  config: Record<string, unknown>;
  strategy: string;
}

export interface TransitionPluginsResponse {
  plugins: TransitionPluginEntry[];
}

export interface TransitionPreviewFrame {
  grid: number[][];
  delay_ms: number;
}

export interface TransitionPreviewResponse {
  plugin_id: string;
  device_type: DeviceType;
  frames: TransitionPreviewFrame[];
  frame_count: number;
  total_delay_ms: number;
  capped: boolean;
  from_grid: number[][];
  to_grid: number[][];
}

export interface TransitionPreviewRequest {
  plugin_id: string;
  to_text: string;
  from_text?: string;
  device_type?: DeviceType;
  notes_wide?: number;
  notes_tall?: number;
  config?: Record<string, unknown>;
}

export interface TransitionTestLiveRequest {
  plugin_id: string;
  to_page_id: string;
  from_page_id?: string;
  config?: Record<string, unknown>;
  board_id?: string;
}

export interface TransitionTestLiveResponse {
  status: string;
  sent: boolean;
  plugin_id: string;
  from_page_id: string | null;
  to_page_id: string;
  board_id: string | null;
}

export interface TransitionRestoreRequest {
  board_id?: string;
}

export interface TransitionRestoreResponse {
  status: string;
  page_id: string;
  sent: boolean;
  board_id: string | null;
}

export const transitionsApi = {
  // Transition plugins (beta): frame-by-frame animation plugins. Distinct
  // from the global transition strategy settings — these live under
  // /transitions/* and 404 while the beta flag is off.
  listTransitionPlugins: () => fetchApi<TransitionPluginsResponse>("/transitions/plugins"),
  previewTransition: (request: TransitionPreviewRequest) =>
    fetchApi<TransitionPreviewResponse>("/transitions/preview", {
      method: "POST",
      body: JSON.stringify(request),
    }),
  testTransitionLive: (request: TransitionTestLiveRequest) =>
    fetchApi<TransitionTestLiveResponse>("/transitions/test-live", {
      method: "POST",
      body: JSON.stringify(request),
    }),
  restoreTransitionTest: (request: TransitionRestoreRequest = {}) =>
    fetchApi<TransitionRestoreResponse>("/transitions/restore", {
      method: "POST",
      body: JSON.stringify(request),
    }),
};
