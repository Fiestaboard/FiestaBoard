// API client for FiestaBoard service
// All API calls go through nginx at /api/* (same origin, unified container).
const API_BASE = "/api";

// Types for API responses
export interface StatusResponse {
  running: boolean;
  initialized: boolean;
  config_summary: ConfigSummary;
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

export interface PreviewResponse {
  message: string;
  lines: string[];
  display_type: string;
  line_count: number;
  preview: boolean;
}

export interface BoardCurrentMessageResponse {
  characters: number[][];
  message: string;
  rows: number;
  cols: number;
  expected_characters: number[][] | null;
  cached_at: string | null;
  api_mode: "local" | "cloud";
}

export interface ActionResponse {
  status: string;
  message: string;
  debug_info?: string;
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

export interface PageDeleteResponse {
  status: string;
  message: string;
  default_page_created: boolean;
  new_page_id?: string;
  active_page_updated: boolean;
  new_active_page_id?: string;
}

// Display types
export interface DisplayInfo {
  type: string;
  available: boolean;
  description: string;
}

export interface DisplaysResponse {
  displays: DisplayInfo[];
  total: number;
  available_count: number;
}

export interface DisplayResponse {
  display_type: string;
  message: string;
  lines: string[];
  line_count: number;
  available: boolean;
}

export interface DisplayRawResponse {
  display_type: string;
  data: Record<string, unknown>;
  available: boolean;
  error: string | null;
}

export interface DisplayRawBatchResponse {
  displays: Record<string, {
    data: Record<string, unknown>;
    available: boolean;
    error: string | null;
  }>;
  total: number;
  successful: number;
}

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

// Active page settings
export interface ActivePageResponse {
  page_id: string | null;
}

export interface SetActivePageResponse {
  status: string;
  page_id: string | null;
  sent_to_board: boolean;
}

// Page types
export type PageType = "single" | "composite" | "template";

// Device types
export type DeviceType = "flagship" | "note";

export interface RowConfig {
  source: string;
  row_index: number;
  target_row: number;
}

export type LineAlignment = "left" | "center" | "right";

export interface LineMetadata {
  alignment: LineAlignment;
  wrap: boolean;
}

export interface Page {
  id: string;
  name: string;
  type: PageType;
  device_type: DeviceType;
  display_type?: string;
  rows?: RowConfig[];
  template?: string[];
  line_metadata?: LineMetadata[];
  duration_seconds: number;
  // Transition settings (per-page override)
  transition_strategy?: string | null;
  transition_interval_ms?: number | null;
  transition_step_size?: number | null;
  created_at: string;
  updated_at?: string;
}

export interface PageCreate {
  name: string;
  type: PageType;
  device_type?: DeviceType;
  display_type?: string;
  rows?: RowConfig[];
  template?: string[];
  line_metadata?: LineMetadata[];
  duration_seconds?: number;
  // Transition settings (per-page override)
  transition_strategy?: string | null;
  transition_interval_ms?: number | null;
  transition_step_size?: number | null;
}

export interface PageUpdate {
  name?: string;
  display_type?: string;
  rows?: RowConfig[];
  template?: string[];
  line_metadata?: LineMetadata[];
  duration_seconds?: number;
  // Transition settings (per-page override)
  transition_strategy?: string | null;
  transition_interval_ms?: number | null;
  transition_step_size?: number | null;
}

export interface PagesResponse {
  pages: Page[];
  total: number;
}

export interface StaffPickPlugin {
  id: string;
  name: string;
}

export interface StaffPick {
  id: string;
  name: string;
  description: string;
  device_type: DeviceType;
  tags: string[];
  image: string | null;
  required_plugins: StaffPickPlugin[];
}

export interface PagePreviewResponse {
  page_id: string;
  message: string;
  lines: string[];
  display_type: string;
  raw: Record<string, unknown>;
}

export interface PagePreviewBatchResponse {
  previews: Record<string, PagePreviewResponse | { error: string; available: false }>;
  total: number;
  successful: number;
}

export interface PageSendResponse {
  status: string;
  page_id: string;
  message: string;
  sent_to_board: boolean;
  target: string;
}

export interface CurrentDisplayResponse {
  page_id: string;
  page_name: string;
  page_type: PageType;
  device_type: DeviceType;
  template: string[];
  line_metadata: LineMetadata[] | null;
}

// Template types
export interface FormattingVariable {
  syntax: string;
  description: string;
}

export interface VariableMetadataEntry {
  description?: string;
  type?: "string" | "number" | "boolean";
  max_length?: number;
  group?: string;
  preview?: string;
  example?: string;
}

export interface VariableGroup {
  label: string;
}

export interface TemplateVariables {
  variables: Record<string, string[]>;
  max_lengths: Record<string, number>;
  variable_metadata?: Record<string, Record<string, VariableMetadataEntry>>;
  variable_groups?: Record<string, Record<string, VariableGroup>>;
  colors: Record<string, number>;
  symbols: string[];
  filters: string[];
  formatting: Record<string, FormattingVariable>;
  syntax_examples: Record<string, string>;
}

export interface HomeAssistantEntity {
  entity_id: string;
  state: string;
  attributes: Record<string, any>;
  friendly_name: string;
}

export interface HomeAssistantEntitiesResponse {
  entities: HomeAssistantEntity[];
}

export interface QueueTimesPark {
  id: number;
  name: string;
  country?: string;
  timezone?: string;
}

export interface QueueTimesRide {
  id: number;
  name: string;
}

export interface FunctionSignatureEntry {
  category: string;
  signature: string;
  summary: string;
}

export interface FormulaFunctionsResponse {
  functions: Record<string, FunctionSignatureEntry>;
}

export interface TemplateValidationResponse {
  valid: boolean;
  errors: Array<{
    line: number;
    column: number;
    message: string;
  }>;
}

export interface TemplateRenderResponse {
  rendered: string;
  lines: string[];
  line_count: number;
}

export interface TemplateRenderLiveResponse {
  rendered: string;
  lines: string[];
  line_count: number;
  sent_to_board: boolean;
  board_id: string | null;
}

// Configuration types
export interface BoardConfig {
  api_mode: "local" | "cloud";
  local_api_key: string;
  cloud_key: string;
  host: string;
  transition_strategy: string | null;
  transition_interval_ms: number | null;
  transition_step_size: number | null;
}

// Backward compatibility alias
export type FiestaboardConfig = BoardConfig;

// Utility types for API helper endpoints (station finder, stop finder, etc.)
export interface MuniStop {
    stop_code: string;
    stop_id: string;
    name: string;
    lat: number | null;
    lon: number | null;
    distance_km?: number;
    routes?: string[];
}

export interface BayWheelsStation {
    station_id: string;
    name: string;
    lat?: number;
    lon?: number;
    address?: string;
    capacity?: number;
    distance_km?: number;
    num_bikes_available?: number;
    electric_bikes?: number;
    classic_bikes?: number;
    num_docks_available?: number;
    is_renting?: boolean;
}

export interface TrafficRoute {
    origin: string;
    destination: string;
    destination_name: string;
}

export interface StockSymbol {
  symbol: string;
  name: string;
}

export interface StockSymbolValidation {
  valid: boolean;
  symbol: string;
  name?: string;
  error?: string;
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

export interface SilenceStatus {
  enabled: boolean;
  active: boolean;
  start_time_utc: string;
  end_time_utc: string;
  current_time_utc: string;
  next_change_utc: string;
  mode?: string;
  indicator_text?: string;
  indicator_position?: string;
}

export interface PollingSettings {
  interval_seconds: number;
  board_read_interval_local: number;
  board_read_interval_cloud: number;
}

export interface BoardInstance {
  id: string;
  name: string;
  device_type: DeviceType;
  board_color: "black" | "white";
  enabled: boolean;
  api_mode: "local" | "cloud";
  host: string;
  local_api_key: string;
  cloud_key: string;
}

export interface BoardSettings {
  board_type: "black" | "white" | null;
  boards: BoardInstance[];
  devices: DeviceType[]; // Computed from boards for backward compat
}

// Schedule types
export type DayPattern = "all" | "weekdays" | "weekends" | "custom";
export type TimeType = "fixed" | "sunrise" | "sunset";

export interface ScheduleEntry {
  id: string;
  board_id?: string; // Optional; "" or omitted = default board
  page_id: string;
  start_time: string; // HH:MM format
  end_time?: string | null;  // HH:MM format or null (open-ended)
  day_pattern: DayPattern;
  custom_days?: string[]; // Only used when day_pattern is "custom"
  enabled: boolean;
  // Sun schedule fields
  start_type?: TimeType; // "fixed" | "sunrise" | "sunset" (default: "fixed")
  start_sun_offset?: number; // minutes (positive=after, negative=before)
  end_type?: TimeType;
  end_sun_offset?: number;
  // Resolved sun times (computed by server for today)
  resolved_start_time?: string; // HH:MM - actual start time for today
  resolved_end_time?: string | null; // HH:MM - actual end time for today
  created_at: string;
  updated_at?: string;
}

export interface ScheduleCreate {
  board_id?: string;
  page_id: string;
  start_time: string;
  end_time?: string | null; // null for open-ended schedule
  day_pattern: DayPattern;
  custom_days?: string[];
  enabled?: boolean; // Defaults to true
  start_type?: TimeType;
  start_sun_offset?: number;
  end_type?: TimeType;
  end_sun_offset?: number;
}

export interface ScheduleUpdate {
  board_id?: string;
  page_id?: string;
  start_time?: string;
  end_time?: string | null; // null to clear end_time
  day_pattern?: DayPattern;
  custom_days?: string[];
  enabled?: boolean;
  start_type?: TimeType;
  start_sun_offset?: number;
  end_type?: TimeType;
  end_sun_offset?: number;
}

export interface SchedulesResponse {
  schedules: ScheduleEntry[];
  total: number;
  default_page_id: string | null;
  enabled: boolean;
}

export interface Overlap {
  schedule1_id: string;
  schedule2_id: string;
  conflict_description: string;
}

export interface Gap {
  start_time: string;
  end_time: string;
  days: string[];
}

export interface ScheduleValidationResult {
  valid: boolean;
  overlaps: Overlap[];
  gaps: Gap[];
}

export interface TemporaryOverrideStatus {
  active: boolean;
  page_id: string | null;
  expires_at: string | null;
  remaining_seconds: number | null;
  revert_mode: "schedule" | "blank" | "page" | null;
  revert_page_id: string | null;
}

export interface SetTemporaryOverrideRequest {
  page_id: string;
  duration_minutes: number;
  revert_mode: "schedule";
}

export interface ActiveScheduleResponse {
  page_id: string | null;
  source: "schedule" | "manual" | "none";
  schedule_enabled: boolean;
  current_time?: string;
  current_day?: string;
  default_page_id?: string | null;
  temporary_override?: TemporaryOverrideStatus;
}

export interface ScheduleEnabledResponse {
  enabled: boolean;
}

export interface DefaultPageResponse {
  default_page_id: string | null;
}

// Carousel types
export const CAROUSEL_ID_PREFIX = "carousel:";

export function isCarouselId(id: string | null | undefined): boolean {
  return !!id && id.startsWith(CAROUSEL_ID_PREFIX);
}

export interface Carousel {
  id: string;
  name: string;
  page_ids: string[];
  interval_seconds: number;
  created_at: string;
  updated_at?: string;
}

export interface CarouselCreate {
  name: string;
  page_ids: string[];
  interval_seconds?: number;
}

export interface CarouselUpdate {
  name?: string;
  page_ids?: string[];
  interval_seconds?: number;
}

export interface CarouselsResponse {
  carousels: Carousel[];
  total: number;
}

export interface DisplaySettings {
  reduce_motion: boolean;
}

export interface BetaSettings {
  https_enabled: boolean;
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
  silence_schedule: Record<string, unknown>;
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

export interface MqttSettings {
  enabled: boolean;
  broker_host: string;
  broker_port: number;
  username: string;
  password: string;
  external_url: string;
}

export type AIProviderProtocol = "openai" | "anthropic";

export interface AIProvider {
  id: string;
  name: string;
  protocol?: AIProviderProtocol;
  base_url: string;
  api_key: string;
  models: string[];
  default_model?: string;
  headers?: Record<string, string>;
}

export interface AISettings {
  enabled: boolean;
  providers: AIProvider[];
  default_provider_id: string | null;
}

export interface AITestResult {
  ok: boolean;
  message: string;
  model_used: string | null;
}

export interface AIPageWarning {
  message: string;
}

export interface AIGenerateResult {
  page: {
    name: string;
    type: "template";
    device_type: DeviceType;
    template: string[];
    line_metadata: LineMetadata[];
    duration_seconds: number;
  };
  model_used: string;
  provider_id: string;
  warnings: string[];
  usage: {
    prompt_tokens: number | null;
    completion_tokens: number | null;
    total_tokens: number | null;
  };
}

export interface FullConfig {
  board: BoardConfig;
  general: GeneralConfig;
  plugins: Record<string, Record<string, unknown>>;
  // Backward compatibility alias (in case API returns old key)
  board?: BoardConfig;
}

export interface ConfigValidationResponse {
  valid: boolean;
  is_first_run: boolean;
  errors: string[];
  missing_fields: string[];
}

// Setup wizard types
export interface BoardTestRequest {
  api_mode: "local" | "cloud";
  local_api_key?: string;
  cloud_key?: string;
  host?: string;
}

export interface BoardTestResponse {
  success: boolean;
  message: string;
  error?: string;
  api_mode?: string;
  troubleshooting?: string[];
}

export interface WelcomeMessageResponse {
  status: string;
  message: string;
  skipped?: boolean;
  silence_mode?: boolean;
}

export interface EnableLocalApiRequest {
  host: string;
  enablement_token: string;
}

export interface EnableLocalApiResponse {
  success: boolean;
  api_key?: string;
  message: string;
  error?: string;
}

export interface DiscoveredBoard {
  ip: string;
  port: number;
  hostname: string;
  source: "mdns" | "port_scan";
}

export interface BoardScanResponse {
  boards: DiscoveredBoard[];
}

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
    arrays?: Record<string, {
      label_field: string;
      item_fields: string[];
      sub_arrays?: Record<string, {
        key_type?: "index" | "dynamic";
        key_field?: string;
        label_field?: string;
        item_fields: string[];
      }>;
    }>;
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

export interface VersionResponse {
  package_version: string;
  build_version: string;
  is_dev: boolean;
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
  profile: "docker" | "pi";
  sidecar_url: string;
  last_check: string | null;
  last_update: string | null;
}

export type AutoUpdateInterval = "daily" | "weekly" | "monthly" | "manual";

export const AUTO_UPDATE_INTERVALS: AutoUpdateInterval[] = [
  "daily",
  "weekly",
  "monthly",
  "manual",
];

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



// API client with typed methods
const DEFAULT_TIMEOUT_MS = 30000;

/**
 * On 401 (not authenticated) or 409 setup-required responses, send the
 * user to /login. The login page handles both cases: an unsigned-in
 * user sees the sign-in form; a fresh install with no admin yet sees
 * the first-run picker / setup form.
 *
 * Runs in the browser only and never on the login page itself (to avoid
 * a redirect loop while signing in). The current URL is preserved in the
 * `redirect` query param so we can bounce back after a successful login.
 *
 * Returns true if a redirect was initiated.
 */
function redirectToLoginIfNeeded(res: globalThis.Response): boolean {
  if (typeof window === "undefined") return false;
  if (window.location.pathname.startsWith("/login")) return false;
  if (res.status === 401 || res.status === 409) {
    // For 409 only redirect when the body actually says setup_required —
    // other 409s (e.g. "already set up") should bubble up as errors.
    if (res.status === 409) {
      const ct = res.headers.get("content-type") ?? "";
      if (!ct.includes("application/json")) return false;
      // Peek at the body without consuming it for the caller.
      const cloned = res.clone();
      cloned.json().then((body) => {
        if (body?.setup_required) {
          const target = encodeURIComponent(
            window.location.pathname + window.location.search,
          );
          window.location.assign(`/login?redirect=${target}`);
        }
      }).catch(() => {
        // Not JSON or malformed — leave the caller to surface the error.
      });
      return false;
    }
    const target = encodeURIComponent(
      window.location.pathname + window.location.search,
    );
    window.location.assign(`/login?redirect=${target}`);
    return true;
  }
  return false;
}

async function fetchApi<T>(path: string, options?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options ?? {};
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  const signal = fetchOptions.signal
    ? AbortSignal.any([fetchOptions.signal, timeoutSignal])
    : timeoutSignal;

  let res: globalThis.Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...fetchOptions,
      signal,
      // Send the session cookie on every API call so auth-protected
      // endpoints work when FIESTABOARD_AUTH_ENABLED is on. Same-origin
      // requests already include cookies by default, but be explicit so
      // future cross-origin deployments behave the same way.
      credentials: fetchOptions.credentials ?? "include",
      headers: {
        "Content-Type": "application/json",
        ...fetchOptions.headers,
      },
    });
  } catch (err) {
    throw err;
  }
  if (!res.ok) {
    redirectToLoginIfNeeded(res);
    let detail = `API error: ${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) {
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // ignore JSON parse errors; use status text fallback
    }
    throw new Error(detail);
  }
  return res.json();
}

/**
 * Shape of /auth/status. Exported so other UI surfaces (login page,
 * profile page) can share the type instead of redeclaring it.
 */
export type AuthStatusResponse = {
  enabled: boolean;
  setup_required: boolean;
  authenticated: boolean;
  username: string | null;
  mode: "enabled" | "disabled" | "undecided";
  first_run: boolean;
};

export const api = {
  // Queries (read-only)
  getStatus: () => fetchApi<StatusResponse>("/status"),
  getConfig: () => fetchApi<ConfigSummary>("/config"),
  getBoardCurrentMessage: () => fetchApi<BoardCurrentMessageResponse>("/board/current-message"),

  // Mutations (actions)
  startService: () =>
    fetchApi<ActionResponse>("/start", { method: "POST" }),
  stopService: () =>
    fetchApi<ActionResponse>("/stop", { method: "POST" }),
  // Display endpoints
  getDisplays: () => fetchApi<DisplaysResponse>("/displays"),
  getDisplay: (type: string) => fetchApi<DisplayResponse>(`/displays/${type}`),
  getDisplayRaw: (type: string) => fetchApi<DisplayRawResponse>(`/displays/${type}/raw`),
  getDisplaysRawBatch: (displayTypes: string[], enabledOnly?: boolean) =>
    fetchApi<DisplayRawBatchResponse>("/displays/raw/batch", {
      method: "POST",
      body: JSON.stringify({
        display_types: displayTypes,
        enabled_only: enabledOnly ?? true
      }),
    }),
  sendDisplay: (type: string, target?: "ui" | "board" | "both") => {
    const params = target ? `?target=${target}` : "";
    return fetchApi<ActionResponse>(`/displays/${type}/send${params}`, { method: "POST" });
  },

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

  // Active page settings
  getActivePage: () => fetchApi<ActivePageResponse>("/settings/active-page"),
  setActivePage: (pageId: string | null) =>
    fetchApi<SetActivePageResponse>("/settings/active-page", {
      method: "PUT",
      body: JSON.stringify({ page_id: pageId }),
    }),

  // Temporary override endpoints
  getTemporaryOverride: () =>
    fetchApi<TemporaryOverrideStatus>("/settings/temporary-override"),
  setTemporaryOverride: (request: SetTemporaryOverrideRequest) =>
    fetchApi<TemporaryOverrideStatus>("/settings/temporary-override", {
      method: "POST",
      body: JSON.stringify(request),
    }),
  clearTemporaryOverride: () =>
    fetchApi<{ status: string; revert_mode: string | null }>("/settings/temporary-override", {
      method: "DELETE",
    }),

  // Pages endpoints
  getPages: () => fetchApi<PagesResponse>("/pages"),
  getCurrentDisplay: () => fetchApi<CurrentDisplayResponse>("/pages/current-display"),
  getPage: (pageId: string) => fetchApi<Page>(`/pages/${pageId}`),
  createPage: (page: PageCreate) =>
    fetchApi<{ status: string; page: Page }>("/pages", {
      method: "POST",
      body: JSON.stringify(page),
    }),
  updatePage: (pageId: string, page: PageUpdate) =>
    fetchApi<{ status: string; page: Page }>(`/pages/${pageId}`, {
      method: "PUT",
      body: JSON.stringify(page),
    }),
  deletePage: (pageId: string) =>
    fetchApi<PageDeleteResponse>(`/pages/${pageId}`, { method: "DELETE" }),
  previewPage: (pageId: string) =>
    fetchApi<PagePreviewResponse>(`/pages/${pageId}/preview`, { method: "POST" }),
  previewPagesBatch: (pageIds: string[]) =>
    fetchApi<PagePreviewBatchResponse>("/pages/preview/batch", {
      method: "POST",
      body: JSON.stringify({ page_ids: pageIds }),
    }),
  sendPage: (pageId: string, target?: "ui" | "board" | "both") => {
    const params = target ? `?target=${target}` : "";
    return fetchApi<PageSendResponse>(`/pages/${pageId}/send${params}`, { method: "POST" });
  },
  getPageShareString: (pageId: string) =>
    fetchApi<{ share_string: string }>(`/pages/${pageId}/share`),
  importPage: (shareString: string) =>
    fetchApi<{ status: string; page: Page }>("/pages/import", {
      method: "POST",
      body: JSON.stringify({ share_string: shareString }),
    }),
  getStaffPicks: () => fetchApi<StaffPick[]>("/staff-picks"),
  getStaffPickShareString: (pickId: string) =>
    fetchApi<{ share_string: string }>(`/staff-picks/${pickId}/share`),

  // Templates endpoints
  getTemplateVariables: () => fetchApi<TemplateVariables>("/templates/variables"),
  getFormulaFunctions: () => fetchApi<FormulaFunctionsResponse>("/templates/formula-functions"),
  validateTemplate: (template: string | string[]) =>
    fetchApi<TemplateValidationResponse>("/templates/validate", {
      method: "POST",
      body: JSON.stringify({ template }),
    }),
  renderTemplate: (template: string | string[], lineMetadata?: LineMetadata[], deviceType?: string) =>
    fetchApi<TemplateRenderResponse>("/templates/render", {
      method: "POST",
      body: JSON.stringify({ template, ...(lineMetadata && { line_metadata: lineMetadata }), ...(deviceType && { device_type: deviceType }) }),
    }),
  renderTemplateLive: (template: string | string[], boardId?: string, lineMetadata?: LineMetadata[], deviceType?: string, signal?: AbortSignal) =>
    fetchApi<TemplateRenderLiveResponse>("/templates/render/live", {
      method: "POST",
      body: JSON.stringify({ template, ...(boardId && { board_id: boardId }), ...(lineMetadata && { line_metadata: lineMetadata }), ...(deviceType && { device_type: deviceType }) }),
      signal,
    }),
  forceRefresh: () =>
    fetchApi<{ status: string; message: string }>("/force-refresh", {
      method: "POST",
    }),

  // Schedule endpoints (optional boardId for per-board schedules)
  getSchedules: (boardId?: string) =>
    fetchApi<SchedulesResponse>(
      boardId ? `/schedules?board_id=${encodeURIComponent(boardId)}` : "/schedules"
    ),

  createSchedule: (data: ScheduleCreate) =>
    fetchApi<ScheduleEntry>("/schedules", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getSchedule: (scheduleId: string) =>
    fetchApi<ScheduleEntry>(`/schedules/${scheduleId}`),

  updateSchedule: (scheduleId: string, data: ScheduleUpdate) =>
    fetchApi<ScheduleEntry>(`/schedules/${scheduleId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteSchedule: (scheduleId: string) =>
    fetchApi<{ status: string; message: string }>(`/schedules/${scheduleId}`, {
      method: "DELETE",
    }),

  getActiveSchedule: (boardId?: string) =>
    fetchApi<ActiveScheduleResponse>(
      boardId ? `/schedules/active/page?board_id=${encodeURIComponent(boardId)}` : "/schedules/active/page"
    ),

  validateSchedules: (boardId?: string) =>
    fetchApi<ScheduleValidationResult>("/schedules/validate", {
      method: "POST",
      body: JSON.stringify(boardId != null ? { board_id: boardId } : {}),
    }),

  getDefaultPage: (boardId?: string) =>
    fetchApi<DefaultPageResponse>(
      boardId ? `/schedules/default-page?board_id=${encodeURIComponent(boardId)}` : "/schedules/default-page"
    ),

  setDefaultPage: (pageId: string | null, boardId?: string) =>
    fetchApi<{ status: string; default_page_id: string | null }>(
      "/schedules/default-page",
      {
        method: "PUT",
        body: JSON.stringify({ page_id: pageId, ...(boardId != null && { board_id: boardId }) }),
      }
    ),

  getScheduleEnabled: (boardId?: string) =>
    fetchApi<ScheduleEnabledResponse>(
      boardId ? `/schedules/enabled?board_id=${encodeURIComponent(boardId)}` : "/schedules/enabled"
    ),

  setScheduleEnabled: (enabled: boolean, boardId?: string) =>
    fetchApi<{ status: string; enabled: boolean; message: string }>(
      "/schedules/enabled",
      {
        method: "PUT",
        body: JSON.stringify({ enabled, ...(boardId != null && { board_id: boardId }) }),
      }
    ),

  // Carousel endpoints
  getCarousels: () =>
    fetchApi<CarouselsResponse>("/carousels"),

  createCarousel: (data: CarouselCreate) =>
    fetchApi<{ status: string; carousel: Carousel }>("/carousels", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getCarousel: (carouselId: string) =>
    fetchApi<Carousel>(`/carousels/${carouselId}`),

  updateCarousel: (carouselId: string, data: CarouselUpdate) =>
    fetchApi<{ status: string; carousel: Carousel }>(`/carousels/${carouselId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteCarousel: (carouselId: string) =>
    fetchApi<{ status: string; message: string }>(`/carousels/${carouselId}`, {
      method: "DELETE",
    }),

  // Configuration endpoints
  getFullConfig: () => fetchApi<FullConfig>("/config/full"),
  getBoardConfig: () =>
    fetchApi<{ config: BoardConfig; api_modes: string[] }>("/config/board"),
  updateBoardConfig: (config: Partial<BoardConfig>) =>
    fetchApi<{ status: string; config: BoardConfig }>("/config/board", {
      method: "PUT",
      body: JSON.stringify(config),
    }),
  // Backward compatibility aliases
  getFiestaboardConfig: () =>
    fetchApi<{ config: BoardConfig; api_modes: string[] }>("/config/board"),
  updateFiestaboardConfig: (config: Partial<BoardConfig>) =>
    fetchApi<{ status: string; config: BoardConfig }>("/config/board", {
      method: "PUT",
      body: JSON.stringify(config),
    }),
  validateConfig: () => fetchApi<ConfigValidationResponse>("/config/validate"),

  // Bay Wheels station search endpoints
  listBayWheelsStations: () =>
    fetchApi<{ stations: BayWheelsStation[]; total: number }>("/baywheels/stations"),
  findNearbyBayWheelsStations: (lat: number, lng: number, radius?: number, limit?: number) => {
    const params = new URLSearchParams({
      lat: lat.toString(),
      lng: lng.toString(),
      ...(radius !== undefined && { radius: radius.toString() }),
      ...(limit !== undefined && { limit: limit.toString() }),
    });
    return fetchApi<{
      stations: BayWheelsStation[];
      count: number;
      search_location: { lat: number; lng: number };
      radius_km: number;
    }>(`/baywheels/stations/nearby?${params}`);
  },
  searchBayWheelsStationsByAddress: (address: string, radius?: number, limit?: number) => {
    const params = new URLSearchParams({
      address,
      ...(radius !== undefined && { radius: radius.toString() }),
      ...(limit !== undefined && { limit: limit.toString() }),
    });
    return fetchApi<{
      stations: BayWheelsStation[];
      count: number;
      search_address: string;
      geocoded_location: { lat: number; lng: number; display_name: string };
      radius_km: number;
    }>(`/baywheels/stations/search?${params}`);
  },

  // MUNI stop search endpoints
  listMuniStops: () =>
    fetchApi<{ stops: MuniStop[]; total: number }>("/muni/stops"),
  findNearbyMuniStops: (lat: number, lng: number, radius?: number, limit?: number) => {
    const params = new URLSearchParams({
      lat: lat.toString(),
      lng: lng.toString(),
      ...(radius !== undefined && { radius: radius.toString() }),
      ...(limit !== undefined && { limit: limit.toString() }),
    });
    return fetchApi<{
      stops: MuniStop[];
      count: number;
      search_location: { lat: number; lng: number };
      radius_km: number;
    }>(`/muni/stops/nearby?${params}`);
  },
  searchMuniStopsByAddress: (address: string, radius?: number, limit?: number) => {
    const params = new URLSearchParams({
      address,
      ...(radius !== undefined && { radius: radius.toString() }),
      ...(limit !== undefined && { limit: limit.toString() }),
    });
    return fetchApi<{
      stops: MuniStop[];
      count: number;
      search_address: string;
      geocoded_location: { lat: number; lng: number; display_name: string };
      radius_km: number;
    }>(`/muni/stops/search?${params}`);
  },

  // Traffic route endpoints
  geocodeAddress: (address: string) =>
    fetchApi<{ lat: number; lng: number; formatted_address: string }>("/traffic/routes/geocode", {
      method: "POST",
      body: JSON.stringify({ address }),
    }),
  validateTrafficRoute: (origin: string, destination: string, destination_name: string, travel_mode: string = "DRIVE") =>
    fetchApi<{
      valid: boolean;
      distance_km?: number;
      static_duration_minutes?: number;
      error?: string;
    }>("/traffic/routes/validate", {
      method: "POST",
      body: JSON.stringify({ origin, destination, destination_name, travel_mode }),
    }),
  
  // Stocks endpoints
  searchStockSymbols: (query: string, limit?: number) => {
    const params = new URLSearchParams({
      query,
      ...(limit !== undefined && { limit: limit.toString() }),
    });
    return fetchApi<{
      symbols: StockSymbol[];
      count: number;
      query: string;
    }>(`/stocks/search?${params}`);
  },
  validateStockSymbol: (symbol: string) =>
    fetchApi<StockSymbolValidation>("/stocks/validate", {
      method: "POST",
      body: JSON.stringify({ symbol }),
    }),
  
  // General configuration
  getGeneralConfig: () => fetchApi<GeneralConfig>("/config/general"),
  updateGeneralConfig: (config: Partial<GeneralConfig>) =>
    fetchApi<{ status: string; general: GeneralConfig }>("/config/general", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    }),
  
  // Silence mode status
  getSilenceStatus: () => fetchApi<SilenceStatus>("/silence-status"),

  // Silence schedule (system feature, not a plugin)
  updateSilenceSchedule: (data: {
    enabled: boolean;
    start_time: string;
    end_time: string;
    mode?: "indicator" | "freeze" | "page";
    page_id?: string | null;
    indicator_text?: string | null;
    indicator_position?: string | null;
  }) =>
    fetchApi<{ status: string; config: Record<string, unknown> }>("/settings/silence-schedule", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  // Polling settings
  getPollingSettings: () => fetchApi<PollingSettings>("/settings/polling"),
  updatePollingSettings: (updates: Partial<PollingSettings>) =>
    fetchApi<{ status: string; settings: PollingSettings; requires_restart: boolean }>("/settings/polling", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    }),

  // Board settings
  getBoardSettings: () => fetchApi<BoardSettings>("/settings/board"),
  updateBoardSettings: (updates: { board_type?: "black" | "white" | null; devices?: DeviceType[]; boards?: BoardInstance[] }) =>
    fetchApi<{ status: string; settings: BoardSettings }>("/settings/board", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    }),
  addBoard: (board: Partial<BoardInstance> & { device_type: DeviceType }) =>
    fetchApi<{ status: string; settings: BoardSettings }>("/settings/board/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(board),
    }),
  removeBoard: (boardId: string) =>
    fetchApi<{ status: string; settings: BoardSettings }>(`/settings/board/${boardId}`, {
      method: "DELETE",
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

  // Beta features (HTTPS, etc.)
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

  // Home Assistant endpoints
  getHomeAssistantEntities: () =>
    fetchApi<HomeAssistantEntitiesResponse>("/home-assistant/entities"),

  // Queue-Times (Disney parks) picker
  getQueueTimesParks: () =>
    fetchApi<QueueTimesPark[]>("/queue-times/parks"),
  getQueueTimesRides: (parkId: number) =>
    fetchApi<QueueTimesRide[]>(`/queue-times/parks/${parkId}/rides`),

  // Version endpoint
  getVersion: () =>
    fetchApi<VersionResponse>("/version"),

  // System management endpoints
  checkForUpdate: () =>
    fetchApi<UpdateCheckResponse>("/system/update-check"),

  // Self-update sidecar endpoints (5.0+)
  getUpdateStatus: () =>
    fetchApi<UpdateStatusResponse>("/system/update/status"),

  applyUpdate: () =>
    fetchApi<UpdateApplyResponse>("/system/update", { method: "POST" }),

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

  restartSystem: () =>
    fetchApi<SystemActionResponse>("/system/restart", { method: "POST" }),

  shutdownSystem: () =>
    fetchApi<SystemActionResponse>("/system/shutdown", { method: "POST" }),

  // Plugin system endpoints
  listPlugins: () =>
    fetchApi<PluginsListResponse>("/plugins"),
  
  getPlugin: (pluginId: string) =>
    fetchApi<PluginDetailResponse>(`/plugins/${pluginId}`),
  
  getPluginManifest: (pluginId: string) =>
    fetchApi<PluginManifest>(`/plugins/${pluginId}/manifest`),
  
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
  
  getPluginData: (pluginId: string) =>
    fetchApi<PluginDataResponse>(`/plugins/${pluginId}/data`),
  
  getPluginVariables: (pluginId: string) =>
    fetchApi<PluginVariablesResponse>(`/plugins/${pluginId}/variables`),

  getPluginDemoPage: (pluginId: string) =>
    fetchApi<PluginDemoPageResponse>(`/plugins/${pluginId}/demo-page`),

  createPluginDemoPage: (pluginId: string) =>
    fetchApi<PluginDemoPageCreateResponse>(`/plugins/${pluginId}/demo-page`, {
      method: "POST",
    }),

  getAllPluginVariables: () =>
    fetchApi<AllPluginVariablesResponse>("/plugins/variables/all"),
  
  getPluginErrors: () =>
    fetchApi<PluginErrorsResponse>("/plugins/errors"),

  // Plugin instance endpoints
  listPluginInstances: (pluginId: string) =>
    fetchApi<PluginInstancesResponse>(`/plugins/${pluginId}/instances`),

  createPluginInstance: (pluginId: string, label: string) =>
    fetchApi<PluginInstanceCreateResponse>(`/plugins/${pluginId}/instances`, {
      method: "POST",
      body: JSON.stringify({ label }),
    }),

  deletePluginInstance: (pluginId: string, instanceLabel: string) =>
    fetchApi<PluginInstanceDeleteResponse>(`/plugins/${pluginId}/instances/${instanceLabel}`, {
      method: "DELETE",
    }),

  // Plugin registry endpoints
  listRegistryPlugins: () =>
    fetchApi<RegistryListResponse>("/plugins/registry"),

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

  getPluginUpdates: () =>
    fetchApi<PluginUpdatesResponse>("/plugins/updates"),

  triggerPluginUpdateCheck: () =>
    fetchApi<PluginUpdateCheckResponse>("/plugins/updates/check", {
      method: "POST",
      timeoutMs: 120000,
    }),

  applyAllPluginUpdates: () =>
    fetchApi<PluginApplyUpdatesResponse>("/plugins/updates/apply", {
      method: "POST",
    }),

  // Generic Data helper
  genericDataTestFetch: (request: {
    url: string;
    format?: string;
    method?: string;
    headers?: { name: string; value: string }[];
    body?: string;
  }) =>
    fetchApi<{ ok: boolean; data: unknown }>("/generic-data/test-fetch", {
      method: "POST",
      body: JSON.stringify(request),
    }),

  // Setup wizard endpoints
  validateSetup: () => fetchApi<ConfigValidationResponse>("/config/validate"),
  
  testBoardConnection: (request: BoardTestRequest) =>
    fetchApi<BoardTestResponse>("/config/board/test", {
      method: "POST",
      body: JSON.stringify(request),
    }),
  
  sendWelcomeMessage: () =>
    fetchApi<WelcomeMessageResponse>("/send-welcome-message", {
      method: "POST",
    }),
  
  enableLocalApi: (request: EnableLocalApiRequest) =>
    fetchApi<EnableLocalApiResponse>("/config/board/enable-local-api", {
      method: "POST",
      body: JSON.stringify(request),
    }),

  scanForBoards: (timeout?: number) =>
    fetchApi<BoardScanResponse>("/config/board/scan", {
      method: "POST",
      body: JSON.stringify({ timeout: timeout ?? 4.0 }),
    }),

  // Debug endpoints
  blankBoard: () => 
    fetchApi<ActionResponse>("/debug/blank", { method: "POST" }),
  
  fillBoard: (characterCode: number) =>
    fetchApi<ActionResponse>("/debug/fill", {
      method: "POST",
      body: JSON.stringify({ character_code: characterCode }),
    }),
  
  showDebugInfo: () =>
    fetchApi<ActionResponse>("/debug/info", { method: "POST" }),
  
  testDebugConnection: () =>
    fetchApi<DebugTestResponse>("/debug/test-connection", { method: "POST" }),
  
  clearBoardCache: () =>
    fetchApi<ActionResponse>("/debug/clear-cache", { method: "POST" }),
  
  getBoardCacheStatus: () =>
    fetchApi<DebugCacheStatus>("/debug/cache-status"),
  
  getDebugSystemInfo: () =>
    fetchApi<DebugSystemInfo>("/debug/system-info"),

  getNetworkDiagnostics: () =>
    fetchApi<NetworkDiagnosticsResponse>("/debug/network-diagnostics"),

  getMqttSettings: () => fetchApi<MqttSettings>("/settings/mqtt"),

  updateMqttSettings: (updates: Partial<MqttSettings>) =>
    fetchApi<MqttSettings>("/settings/mqtt", {
      method: "PUT",
      body: JSON.stringify(updates),
    }),

  getMqttStatus: () =>
    fetchApi<{ enabled: boolean; connected: boolean; running: boolean }>("/mqtt/status"),

  // Backup & Restore — return URL/raw content directly so the browser can
  // trigger a file download or upload arbitrary JSON.
  exportBackupUrl: () => `${API_BASE}/backup/export`,

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

  // AI page-generation ("Gen AI" button) settings + endpoints. BYO-LLM:
  // users supply their own OpenAI-compatible endpoint and key. The API
  // key is masked on read; sending "***" preserves the stored value.
  getAiSettings: () => fetchApi<AISettings>("/settings/ai"),

  updateAiSettings: (updates: Partial<AISettings>) =>
    fetchApi<AISettings>("/settings/ai", {
      method: "PUT",
      body: JSON.stringify(updates),
    }),

  testAiProvider: (params: {
    provider_id?: string;
    model?: string;
    provider?: AIProvider;
  }) =>
    fetchApi<AITestResult>("/settings/ai/test", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  generateAiPage: async (params: {
    prompt: string;
    device_type: DeviceType;
    provider_id?: string;
    model?: string;
    current_page?: unknown;
  }): Promise<AIGenerateResult> => {
    // Bespoke fetch so we can surface the FastAPI `detail` message
    // (the LLM's own error text) directly to the user.
    const res = await fetch(`${API_BASE}/pages/ai/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
      // Generous timeout — LLM calls can take 30s+.
      signal: AbortSignal.timeout(120000),
    });
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const body = (await res.json()) as { detail?: string };
        if (body && typeof body.detail === "string") detail = body.detail;
      } catch {
        // Ignore JSON parse errors; fall back to status text.
      }
      throw new Error(detail);
    }
    return (await res.json()) as AIGenerateResult;
  },

  // --- Auth -----------------------------------------------------------
  // The login/setup forms talk to /api/auth/* directly (see
  // web/src/app/login/page.tsx) because they need access to the response
  // `detail` field. The helpers below are for the rest of the UI — e.g.
  // a "Sign out" button in the profile menu.

  getAuthStatus: () => fetchApi<AuthStatusResponse>("/auth/status"),

  logout: () =>
    fetchApi<{ status: string }>("/auth/logout", { method: "POST" }),

  /**
   * Change the signed-in user's password. Uses a bespoke fetch (rather than
   * fetchApi) so the caller can surface FastAPI's ``detail`` body — e.g.
   * "Current password is incorrect".
   */
  changePassword: async (currentPassword: string, newPassword: string) => {
    const res = await fetch("/api/auth/change-password", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });
    if (!res.ok) {
      let detail: string | undefined;
      try {
        const data = await res.json();
        if (data && typeof data.detail === "string") {
          detail = data.detail;
        }
      } catch {
        /* no JSON body */
      }
      throw new Error(detail || `Password change failed (${res.status})`);
    }
    return (await res.json()) as { status: string; username: string };
  },

  /** Rename the signed-in user. Same bespoke-fetch reasoning as changePassword. */
  changeUsername: async (currentPassword: string, newUsername: string) => {
    const res = await fetch("/api/auth/change-username", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        current_password: currentPassword,
        new_username: newUsername,
      }),
    });
    if (!res.ok) {
      let detail: string | undefined;
      try {
        const data = await res.json();
        if (data && typeof data.detail === "string") {
          detail = data.detail;
        }
      } catch {
        /* no JSON body */
      }
      throw new Error(detail || `Username change failed (${res.status})`);
    }
    return (await res.json()) as { status: string; username: string };
  },

  /**
   * Turn off auth enforcement and delete the admin user. Gated by the
   * current password server-side so a stolen cookie alone can't open
   * the install up. After this returns the install is wide open —
   * the caller should redirect somewhere sensible (e.g. the home
   * page) since /login no longer applies.
   */
  disableAuth: async (currentPassword: string) => {
    const res = await fetch("/api/auth/disable", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: currentPassword }),
    });
    if (!res.ok) {
      let detail: string | undefined;
      try {
        const data = await res.json();
        if (data && typeof data.detail === "string") {
          detail = data.detail;
        }
      } catch {
        /* no JSON body */
      }
      throw new Error(detail || `Disable auth failed (${res.status})`);
    }
    return (await res.json()) as { status: string };
  },
};
