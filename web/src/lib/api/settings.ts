// Settings domain: general/polling/display/location/beta/plugin
// settings, transition strategy settings, and the all-settings
// aggregate.

import type { BoardSettings } from "./boards";
import { fetchApi } from "./core";
import type { ScheduleBehaviorSettings, SilenceScheduleSettings } from "./schedules";
import type { MqttSettings } from "./system";

// Settings types
export interface TransitionSettings {
  strategy: string | null;
  step_interval_ms: number | null;
  step_size: number | null;
  available_strategies?: string[];
}

export interface OutputSettings {
  target: "ui" | "board" | "both";
  effective_target: string;
  available_targets: string[];
}

export interface GeneralConfig {
  timezone: string; // IANA timezone (e.g., "America/Los_Angeles")
  refresh_interval_seconds: number;
  output_target: "ui" | "board" | "both";
  instance_name?: string;
  time_format?: "12h" | "24h";
  date_format?: "MM/DD/YYYY" | "DD/MM/YYYY" | "YYYY-MM-DD";
  welcome_message?: string;
}

export interface PollingSettings {
  interval_seconds: number;
  board_read_interval_local: number;
  board_read_interval_cloud: number;
}

export type BoardAnimationsMode = "on" | "desktop" | "off";
export type SiteAnimationsMode = "on" | "off";

export interface DisplaySettings {
  reduce_motion: boolean;
  board_animations: BoardAnimationsMode;
  site_animations: SiteAnimationsMode;
  /** Milliseconds per split-flap character step for the ON-SCREEN board
   *  preview only — unrelated to `TransitionSettings.step_interval_ms`, which
   *  paces the physical Vestaboard over the Local API. Normally one of the
   *  `FLAP_SPEED_PRESETS` names from `@fiestaboard/ui` (`"hardware"` |
   *  `"quick"` | `"standard"` | `"relaxed"`); a raw millisecond count is
   *  accepted as an escape hatch and clamped to [8, 2000]. */
  board_flap_speed: string | number;
}

/**
 * `GET`/`PUT /settings/plugins`. `transition_plugins_enabled` was a
 * `/settings/beta` flag until settings v6.
 */
export interface PluginSettings {
  auto_update: boolean;
  /** Transition plugins (deprecated, beta) may be chosen as a display's or a page's transition. */
  transition_plugins_enabled: boolean;
  /**
   * @deprecated Always true, and ignored on a write: display plugins need no
   * opt-in since settings v7. Removed in v11.
   */
  output_plugins_enabled?: boolean;
}

export interface LocationSettings {
  latitude: number | null;
  longitude: number | null;
}

export interface SunTimesResponse {
  sunrise: string | null;
  sunset: string | null;
  location_configured: boolean;
}

export interface SunTimesWeekResponse {
  location_configured: boolean;
  dates: Record<string, { sunrise: string; sunset: string }>;
}

export interface AllSettingsResponse {
  general: GeneralConfig;
  silence_schedule: SilenceScheduleSettings;
  polling: PollingSettings;
  /** The FIRST display's transition. Deprecated (removed in v11): each display owns its own. */
  transitions: TransitionSettings;
  output: OutputSettings;
  board: BoardSettings;
  mqtt: MqttSettings;
  display: DisplaySettings;
  location: LocationSettings;
  plugins: PluginSettings;
  schedule: ScheduleBehaviorSettings;
  status: {
    running: boolean;
  };
}

/**
 * Mirrors `SettingsRestoreNotice` in src/settings/service.py: set when this
 * build booted by restoring its own pre-upgrade settings snapshot over a
 * settings.json a newer version wrote (a rollback).
 */
export interface SettingsRestoreNotice {
  aside_path: string;
  aside_file: string;
  found_version: number;
  restored_version: number;
  restored_at: string;
}

/** `GET`/`DELETE /settings/restore-notice`. */
export interface SettingsRestoreNoticeResponse {
  notice: SettingsRestoreNotice | null;
}

export const settingsApi = {
  // Downgrade bridge notice
  getSettingsRestoreNotice: () => fetchApi<SettingsRestoreNoticeResponse>("/settings/restore-notice"),
  dismissSettingsRestoreNotice: () =>
    fetchApi<SettingsRestoreNoticeResponse>("/settings/restore-notice", { method: "DELETE" }),
  // Settings endpoints. A display's transition is saved with its board
  // (`PUT /settings/board`); `/settings/transitions` is a deprecated alias
  // for the first display's, kept for other clients until v11.
  getOutputSettings: () => fetchApi<OutputSettings>("/settings/output"),
  updateOutputSettings: (target: "ui" | "board" | "both") =>
    fetchApi<{ target: string }>("/settings/output", {
      method: "PUT",
      body: JSON.stringify({ target }),
    }),
  // General configuration
  getGeneralConfig: () => fetchApi<GeneralConfig>("/config/general"),
  // Answers with the saved config, not a `{status, general}` envelope
  // (Phase 2 config slice). Neither call site reads the body — both
  // invalidate the all-settings query — so the change is type-only here.
  updateGeneralConfig: (config: Partial<GeneralConfig>) =>
    fetchApi<GeneralConfig>("/config/general", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }),
  // Polling settings
  getPollingSettings: () => fetchApi<PollingSettings>("/settings/polling"),
  updatePollingSettings: (updates: Partial<PollingSettings>) =>
    fetchApi<PollingSettings & { requires_restart: boolean }>("/settings/polling", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    }),
  getAllSettings: () => fetchApi<AllSettingsResponse>("/settings/all"),
  // Display settings
  getDisplaySettings: () => fetchApi<DisplaySettings>("/settings/display"),
  updateDisplaySettings: (settings: Partial<DisplaySettings>) =>
    fetchApi<DisplaySettings>("/settings/display", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }),

  // Location settings (for sunrise/sunset schedules)
  getLocationSettings: () => fetchApi<LocationSettings>("/settings/location"),
  updateLocationSettings: (settings: Partial<LocationSettings>) =>
    fetchApi<LocationSettings>("/settings/location", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }),
  getSunTimes: (date?: string) =>
    fetchApi<SunTimesResponse>(`/settings/location/sun-times${date ? `?date=${date}` : ""}`),
  getSunTimesWeek: (weekStart: string) =>
    fetchApi<SunTimesWeekResponse>(`/settings/location/sun-times-week?week_start=${weekStart}`),

  // Plugin settings: auto-update and the transition / output plugin flags
  getPluginSettings: () => fetchApi<PluginSettings>("/settings/plugins"),
  updatePluginSettings: (updates: Partial<PluginSettings>) =>
    fetchApi<PluginSettings>("/settings/plugins", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    }),
};
