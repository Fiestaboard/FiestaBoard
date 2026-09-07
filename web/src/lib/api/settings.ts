// Settings domain: general/polling/display/location/beta/plugin
// settings, transition strategy settings, and the all-settings
// aggregate.

import type { BoardSettings } from "./boards";
import { fetchApi } from "./core";
import type { SilenceScheduleSettings } from "./schedules";
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

export interface BetaSettings {
  https_enabled: boolean;
  transition_plugins_enabled: boolean;
}

export interface PluginSettings {
  auto_update: boolean;
}

export interface PluginSettingsResponse {
  settings: PluginSettings;
}

export interface PluginSettingsUpdateResponse {
  status: string;
  settings: PluginSettings;
}

export interface BetaHttpsStatus {
  cert_present: boolean;
  cert_path: string;
  key_path: string;
  updater_available: boolean;
}

export interface BetaSettingsResponse {
  settings: BetaSettings;
  https: BetaHttpsStatus;
}

export interface BetaSettingsUpdateResponse {
  status: string;
  settings: BetaSettings;
  https: BetaHttpsStatus;
  restart_required: boolean;
  cert_error?: string;
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
  transitions: TransitionSettings;
  output: OutputSettings;
  board: BoardSettings;
  mqtt: MqttSettings;
  display: DisplaySettings;
  location: LocationSettings;
  beta: BetaSettings;
  plugins: PluginSettings;
  status: {
    running: boolean;
  };
}

export const settingsApi = {
  // Settings endpoints
  getTransitionSettings: () => fetchApi<TransitionSettings>("/settings/transitions"),
  updateTransitionSettings: (settings: Partial<TransitionSettings>) =>
    fetchApi<{ status: string; settings: TransitionSettings }>("/settings/transitions", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
  getOutputSettings: () => fetchApi<OutputSettings>("/settings/output"),
  updateOutputSettings: (target: "ui" | "board" | "both") =>
    fetchApi<{ status: string; settings: { target: string } }>("/settings/output", {
      method: "PUT",
      body: JSON.stringify({ target }),
    }),
  // General configuration
  getGeneralConfig: () => fetchApi<GeneralConfig>("/config/general"),
  updateGeneralConfig: (config: Partial<GeneralConfig>) =>
    fetchApi<{ status: string; general: GeneralConfig }>("/config/general", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }),
  // Polling settings
  getPollingSettings: () => fetchApi<PollingSettings>("/settings/polling"),
  updatePollingSettings: (updates: Partial<PollingSettings>) =>
    fetchApi<{ status: string; settings: PollingSettings; requires_restart: boolean }>("/settings/polling", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    }),
  getAllSettings: () => fetchApi<AllSettingsResponse>("/settings/all"),
  // Display settings
  getDisplaySettings: () => fetchApi<DisplaySettings>("/settings/display"),
  updateDisplaySettings: (settings: Partial<DisplaySettings>) =>
    fetchApi<{ status: string; settings: DisplaySettings }>("/settings/display", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }),

  // Location settings (for sunrise/sunset schedules)
  getLocationSettings: () => fetchApi<LocationSettings>("/settings/location"),
  updateLocationSettings: (settings: Partial<LocationSettings>) =>
    fetchApi<{ status: string; settings: LocationSettings }>("/settings/location", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }),
  getSunTimes: (date?: string) =>
    fetchApi<SunTimesResponse>(`/settings/location/sun-times${date ? `?date=${date}` : ""}`),
  getSunTimesWeek: (weekStart: string) =>
    fetchApi<SunTimesWeekResponse>(`/settings/location/sun-times-week?week_start=${weekStart}`),

  // Beta features (HTTPS, transition plugins, etc.)
  getBetaSettings: () => fetchApi<BetaSettingsResponse>("/settings/beta"),
  updateBetaSettings: (updates: Partial<BetaSettings>) =>
    fetchApi<BetaSettingsUpdateResponse>("/settings/beta", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    }),
  getPluginSettings: () => fetchApi<PluginSettingsResponse>("/settings/plugins"),
  updatePluginSettings: (updates: Partial<PluginSettings>) =>
    fetchApi<PluginSettingsUpdateResponse>("/settings/plugins", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    }),
};
