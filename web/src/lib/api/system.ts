// System domain: service status/start/stop, version + self-update,
// debug tools, MQTT, backup/restore, and FiestaPi WiFi.

import { apiUrl } from "../base-path";
import type { BoardStatus } from "./boards";
import { fetchApi } from "./core";

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

// Debug types. Bare bodies with no `{ status: "success" }` envelope since the
// Phase 2 debug slice; failures arrive as real status codes and `fetchApi`
// throws them (a paused board is 409, a throttled write 429, an unreachable
// board 503).
export interface DebugActionResponse {
  message: string;
}

export interface DebugInfoResponse {
  message: string;
  debug_info: string;
}

export interface DebugTestResponse {
  message: string;
  /** Always true on the 200 path — an unreachable board is a 503. */
  connected: boolean;
  latency_ms: number;
}

/**
 * One probe in a diagnostics run. Every field is always present: probes report
 * different subsets (DNS has hostname/ip, the port check host/port, the HTTP
 * checks url/status_code) and the API now sends an explicit null for the ones
 * a given probe does not produce, rather than omitting the key.
 */
export interface DiagnosticStepResult {
  ok: boolean;
  hostname: string | null;
  ip: string | null;
  url: string | null;
  host: string | null;
  port: number | null;
  status_code: number | null;
  latency_ms: number | null;
  error: string | null;
}

export interface VestaboardDiagnostics {
  ok: boolean;
  mode: "local" | "cloud" | null;
  steps: Record<string, DiagnosticStepResult>;
  error: string | null;
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

/** `GET /debug/network-diagnostics` returns the verdict itself. */
export type NetworkDiagnosticsResponse = NetworkDiagnosticsResult;

/** The board client's content-dedupe cache, as every client reports it. */
export interface CacheStatus {
  has_cached_text: boolean;
  has_cached_characters: boolean;
  skip_unchanged_enabled: boolean;
  cached_text_preview: string | null;
}

export interface DebugSystemInfo {
  board_ip: string;
  server_ip: string;
  uptime_seconds: number | null;
  uptime_formatted: string;
  connection_mode: string;
  version: string;
  timestamp: string;
  cache_status: CacheStatus | null;
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

/**
 * `POST /start` and `POST /stop` (Phase 2 Task 8 conventions pass).
 *
 * Replaces the `{ status: "already_running" | "started" | "not_running" |
 * "stopped" }` envelope: `running` is the state the caller asked about, and
 * `changed` says whether this request is what put it there.
 */
export interface ServiceStateResponse {
  running: boolean;
  changed: boolean;
  message: string;
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
  // `GET /v1/status` is `GET /status`'s own handler behind a new path.
  getStatus: () => fetchApi<StatusResponse>("/v1/status"),
  getConfig: () => fetchApi<ConfigSummary>("/config"),
  // Mutations (actions)
  startService: () => fetchApi<ServiceStateResponse>("/start", { method: "POST" }),
  stopService: () => fetchApi<ServiceStateResponse>("/stop", { method: "POST" }),
  forceRefresh: () =>
    fetchApi<{ message: string; sent: boolean }>("/force-refresh", {
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
  blankBoard: () => fetchApi<DebugActionResponse>("/debug/blank", { method: "POST" }),

  fillBoard: (characterCode: number) =>
    fetchApi<DebugActionResponse>("/debug/fill", {
      method: "POST",
      body: JSON.stringify({ character_code: characterCode }),
    }),

  showDebugInfo: () => fetchApi<DebugInfoResponse>("/debug/info", { method: "POST" }),

  testDebugConnection: () => fetchApi<DebugTestResponse>("/debug/test-connection", { method: "POST" }),

  clearBoardCache: () => fetchApi<DebugActionResponse>("/debug/clear-cache", { method: "POST" }),

  getBoardCacheStatus: () => fetchApi<CacheStatus>("/debug/cache-status"),

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
      restored_files: string[];
      skipped_files: string[];
      pre_restore_backup_suffix: string;
      pre_restore_backup_files: string[];
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
    fetchApi<{ name: string }>(`/network/wifi/saved/${encodeURIComponent(conName)}`, { method: "DELETE" }),
};
