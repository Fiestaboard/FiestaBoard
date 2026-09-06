// System domain: service status/start/stop, version + self-update,
// debug tools, MQTT, backup/restore, and FiestaPi WiFi.

import { apiUrl } from "../base-path";
import type { BoardStatus } from "./boards";
import { fetchApi } from "./core";
import type { ActionResponse } from "./shared";

// Types for API responses
export interface StatusResponse {
  running: boolean;
  initialized: boolean;
  config_summary: ConfigSummary;
  /** Per-board status keyed by board id (issue #1244). */
  boards?: Record<string, BoardStatus>;
}

export interface ConfigSummary {
  weather_enabled: boolean;
  home_assistant_enabled: boolean;
  guest_wifi_enabled: boolean;
  star_trek_quotes_enabled: boolean;
  transition_strategy?: string | null;
  transition_interval_ms?: number | null;
  transition_step_size?: number | null;
  [key: string]: boolean | string | number | null | undefined;
}

// Debug types
export interface DebugTestResponse {
  status: string;
  message: string;
  connected: boolean;
  latency_ms: number | null;
}

export interface DiagnosticStepResult {
  ok: boolean;
  hostname?: string;
  ip?: string | null;
  url?: string;
  host?: string;
  port?: number;
  status_code?: number | null;
  latency_ms?: number;
  error?: string;
}

export interface VestaboardDiagnostics {
  ok: boolean;
  mode: "local" | "cloud" | null;
  steps: Record<string, DiagnosticStepResult>;
  error?: string;
}

export interface DiagnosticRecommendation {
  summary: string;
  steps: string[];
}

export interface NetworkDiagnosticsResult {
  dns: DiagnosticStepResult;
  internet: DiagnosticStepResult;
  vestaboard: VestaboardDiagnostics;
  overall_ok: boolean;
  recommendations: DiagnosticRecommendation[];
}

export interface NetworkDiagnosticsResponse {
  status: string;
  diagnostics: NetworkDiagnosticsResult;
}

export interface DebugCacheStatus {
  status: string;
  cache: {
    has_cached_text: boolean;
    has_cached_characters: boolean;
    skip_unchanged_enabled: boolean;
    cached_text_preview: string | null;
  };
}

export interface DebugSystemInfo {
  board_ip: string;
  server_ip: string;
  uptime_seconds: number | null;
  uptime_formatted: string;
  connection_mode: string;
  version: string;
  timestamp: string;
  cache_status: {
    has_cached_text: boolean;
    has_cached_characters: boolean;
    skip_unchanged_enabled: boolean;
    cached_text_preview: string | null;
  } | null;
  board_configured: boolean;
  service_running: boolean;
}

export interface MqttSettings {
  enabled: boolean;
  broker_host: string;
  broker_port: number;
  username: string;
  password: string;
  external_url: string;
}

export interface VersionResponse {
  package_version: string;
  build_version: string;
  is_dev: boolean;
  hardware_model: string | null;
}

export interface UpdateCheckResponse {
  current_version: string;
  latest_version: string | null;
  update_available: boolean;
  package_url: string;
  error: string | null;
  is_production: boolean;
}

export interface UpdateStatusResponse {
  updater_available: boolean;
  auto_update_enabled: boolean;
  auto_update_interval: AutoUpdateInterval;
  /**
   * True when an external supervisor (the Home Assistant add-on) owns
   * updates. FiestaBoard cannot update itself in that case, so all
   * update-available notifications are hidden. Sourced from the server's
   * `_managed_externally()` check.
   */
  managed_externally: boolean;
  profile: "docker" | "pi";
  sidecar_url: string;
  last_check: string | null;
  last_update: string | null;
  /**
   * Outcome of the most recent /update or /rollback attempt, as recorded by
   * the fiestaupdater sidecar. The sidecar owns this state, so it survives
   * the FiestaBoard container being torn down and recreated — which makes it
   * the only trustworthy "did the update actually finish?" signal available
   * to the UI. `null` when the sidecar is unreachable.
   */
  last_update_status: UpdateAttemptStatus | null;
  last_update_action: "update" | "rollback" | null;
  /** Sidecar error code, e.g. "pull_failed" | "recreate_failed" | "retag_failed". */
  last_update_error: string | null;
  last_update_previous_digest: string | null;
  last_update_completed_at: string | null;
}

/**
 * Sidecar-reported lifecycle of an update/rollback attempt.
 * `none` means no attempt has ever been recorded.
 */
export type UpdateAttemptStatus = "in_progress" | "success" | "rolled_back" | "rollback_failed" | "failed" | "none";

export type AutoUpdateInterval = "daily" | "weekly" | "monthly" | "manual";

export const AUTO_UPDATE_INTERVALS: AutoUpdateInterval[] = ["daily", "weekly", "monthly", "manual"];

export interface UpdateApplyResponse {
  status: "queued" | "manual";
  mode: "sidecar" | "manual";
  previous_digest: string | null;
  hint?: string | null;
}

export interface SystemActionResponse {
  status: "queued";
  action: "restart" | "shutdown";
}

// ── WiFi (FiestaPi only) ──────────────────────────────────────────────────
export interface WifiCapability {
  available: boolean;
  reason: string | null;
}

export interface WifiNetwork {
  ssid: string;
  signal: number;
  security: string;
  in_use: boolean;
}

export interface SavedWifiNetwork {
  name: string;
  autoconnect: boolean;
}

export interface WifiStatus {
  connected: boolean;
  ssid: string | null;
  ip_address: string | null;
  gateway: string | null;
  signal: number | null;
  internet_reachable: boolean;
}

export interface WifiConnectPayload {
  ssid: string;
  password?: string;
  hidden?: boolean;
}

export interface WifiConnectResponse {
  status: WifiStatus;
  connectivity_confirmed: boolean;
  message: string;
}

export const systemApi = {
  // Queries (read-only)
  getStatus: () => fetchApi<StatusResponse>("/status"),
  getConfig: () => fetchApi<ConfigSummary>("/config"),
  // Mutations (actions)
  startService: () => fetchApi<ActionResponse>("/start", { method: "POST" }),
  stopService: () => fetchApi<ActionResponse>("/stop", { method: "POST" }),
  forceRefresh: () =>
    fetchApi<{ status: string; message: string }>("/force-refresh", {
      method: "POST",
    }),
  // Version endpoint
  getVersion: () => fetchApi<VersionResponse>("/version"),

  // System management endpoints
  checkForUpdate: () => fetchApi<UpdateCheckResponse>("/system/update-check"),

  // Self-update sidecar endpoints (5.0+)
  getUpdateStatus: () => fetchApi<UpdateStatusResponse>("/system/update/status"),

  applyUpdate: () => fetchApi<UpdateApplyResponse>("/system/update", { method: "POST" }),

  setAutoUpdate: (enabled: boolean) =>
    fetchApi<{ enabled: boolean; interval: AutoUpdateInterval }>("/system/update/auto", {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),

  setAutoUpdateInterval: (interval: AutoUpdateInterval) =>
    fetchApi<{ enabled: boolean; interval: AutoUpdateInterval }>("/system/update/auto", {
      method: "POST",
      body: JSON.stringify({ interval }),
    }),

  restartSystem: () => fetchApi<SystemActionResponse>("/system/restart", { method: "POST" }),

  shutdownSystem: () => fetchApi<SystemActionResponse>("/system/shutdown", { method: "POST" }),
  // Debug endpoints
  blankBoard: () => fetchApi<ActionResponse>("/debug/blank", { method: "POST" }),

  fillBoard: (characterCode: number) =>
    fetchApi<ActionResponse>("/debug/fill", {
      method: "POST",
      body: JSON.stringify({ character_code: characterCode }),
    }),

  showDebugInfo: () => fetchApi<ActionResponse>("/debug/info", { method: "POST" }),

  testDebugConnection: () => fetchApi<DebugTestResponse>("/debug/test-connection", { method: "POST" }),

  clearBoardCache: () => fetchApi<ActionResponse>("/debug/clear-cache", { method: "POST" }),

  getBoardCacheStatus: () => fetchApi<DebugCacheStatus>("/debug/cache-status"),

  getDebugSystemInfo: () => fetchApi<DebugSystemInfo>("/debug/system-info"),

  getNetworkDiagnostics: () => fetchApi<NetworkDiagnosticsResponse>("/debug/network-diagnostics"),

  getMqttSettings: () => fetchApi<MqttSettings>("/settings/mqtt"),

  updateMqttSettings: (updates: Partial<MqttSettings>) =>
    fetchApi<MqttSettings>("/settings/mqtt", {
      method: "PUT",
      body: JSON.stringify(updates),
    }),

  getMqttStatus: () => fetchApi<{ enabled: boolean; connected: boolean; running: boolean }>("/mqtt/status"),
  // Backup & Restore — return URL/raw content directly so the browser can
  // trigger a file download or upload arbitrary JSON.
  exportBackupUrl: () => apiUrl("/backup/export"),

  importBackup: (payload: unknown, reinstallPlugins: boolean = true) =>
    fetchApi<{
      status: string;
      restored_files: string[];
      skipped_files: string[];
      pre_restore_backup_suffix: string;
      plugins: {
        attempted: string[];
        installed: string[];
        already_present: string[];
        failed: { plugin_id: string; error: string }[];
        manual_reinstall_required: {
          plugin_id: string;
          reason: string;
          repository_url: string;
        }[];
      };
      reload_errors: string[];
    }>(`/backup/import?reinstall_plugins=${reinstallPlugins ? "true" : "false"}`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  // ── WiFi (FiestaPi only) ────────────────────────────────────────────────
  getWifiCapability: () => fetchApi<WifiCapability>("/network/wifi/capability"),
  getWifiStatus: () => fetchApi<WifiStatus>("/network/wifi/status"),
  scanWifi: () =>
    fetchApi<WifiNetwork[]>("/network/wifi/scan", {
      method: "POST",
      // Scans take several seconds with --rescan auto on cold cache.
      timeoutMs: 45_000,
    }),
  getSavedWifi: () => fetchApi<SavedWifiNetwork[]>("/network/wifi/saved"),
  connectWifi: (payload: WifiConnectPayload) =>
    fetchApi<WifiConnectResponse>("/network/wifi/connect", {
      method: "POST",
      body: JSON.stringify(payload),
      // connect = nmcli add + up + nm-online (up to ~30s wait).
      timeoutMs: 90_000,
    }),
  disconnectWifi: () => fetchApi<WifiStatus>("/network/wifi/disconnect", { method: "POST" }),
  forgetWifi: (conName: string) =>
    fetchApi<{ status: string }>(`/network/wifi/saved/${encodeURIComponent(conName)}`, { method: "DELETE" }),
};
