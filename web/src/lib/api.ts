// API client for FiestaBoard service
// All API calls go through nginx at /api/* (same origin, unified container).
// URLs are built via apiUrl() so they pick up the runtime base path when
// the app is served from a subpath (HA Ingress) — see lib/base-path.ts.
import { apiUrl, appUrl, stripBasePath } from "./base-path";

// Types for API responses
export interface StatusResponse {
  running: boolean;
  initialized: boolean;
  config_summary: ConfigSummary;
  /** Per-board status keyed by board id (issue #1244). */
  boards?: Record<string, BoardStatus>;
}

export interface BoardStatus {
  configured: boolean;
  paused: boolean;
  active_page_id: string | null;
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
  displays: Record<
    string,
    {
      data: Record<string, unknown>;
      available: boolean;
      error: string | null;
    }
  >;
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
  board_id?: string | null;
}

export interface SetActivePageResponse {
  status: string;
  page_id: string | null;
  sent_to_board: boolean;
  board_id?: string | null;
}

// Page types
export type PageType = "single" | "composite" | "template";

// Device types
export type DeviceType = "flagship" | "note" | "note_array";

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
  /** Number of Notes wide (note_array device_type only). */
  notes_wide?: number;
  /** Number of Notes tall (note_array device_type only). */
  notes_tall?: number;
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
  /** Number of Notes wide (note_array device_type only). */
  notes_wide?: number;
  /** Number of Notes tall (note_array device_type only). */
  notes_tall?: number;
}

export interface PageUpdate {
  name?: string;
  /** Device/size retarget (issue #1250) — converting geometries is lossy. */
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
  /** Number of Notes wide (note_array device_type only). */
  notes_wide?: number;
  /** Number of Notes tall (note_array device_type only). */
  notes_tall?: number;
}

export interface PagesResponse {
  pages: Page[];
  total: number;
}

/**
 * A schedule/active-page reference left pointing at a board the page no
 * longer fits after a device/size retarget (issue #1250). Warn-only — the
 * backend never mutates or removes these.
 */
export interface IncompatibleReference {
  board_id: string;
  board_name: string;
  surface: "schedule" | "active_page";
  schedule_id?: string | null;
}

export interface PageUpdateResponse {
  status: string;
  page: Page;
  /** Present iff the update changed the page's size (may be empty). */
  incompatible_references?: IncompatibleReference[];
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
  board_id?: string | null;
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
  attributes: Record<string, unknown>;
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
  seconds_until_next_change?: number | null;
  mode?: string;
  page_id?: string | null;
  indicator_text?: string;
  indicator_position?: string;
}

export interface PollingSettings {
  interval_seconds: number;
  board_read_interval_local: number;
  board_read_interval_cloud: number;
}

/**
 * One physical Note tile of a local-mode note array. Addresses the board's
 * slot at (row, col) — 0-indexed note coordinates — via its own Local API
 * endpoint. `local_api_key` is masked as "***" on read; sending "***" back
 * preserves the stored key for the tile at the same (row, col).
 */
export interface NoteArrayTile {
  row: number;
  col: number;
  host: string;
  /** Local API port (default 7000). */
  port?: number;
  local_api_key: string;
  enabled?: boolean;
}

export interface BoardInstance {
  id: string;
  name: string;
  device_type: DeviceType;
  board_color: "black" | "white";
  enabled: boolean;
  // Per-board pause flag (issue #970). When true FiestaBoard does not
  // push anything to this board from any code path until it is resumed.
  paused?: boolean;
  /** Per-board schedule mode (issue #1242). Emitted on every GET /settings/board. */
  schedule_enabled?: boolean;
  api_mode: "local" | "cloud";
  host: string;
  /** Local API port (default 7000). */
  port?: number;
  local_api_key: string;
  cloud_key: string;
  /** X-Vestaboard-Token for a Note array (note_array only). Masked as "***" on read. */
  note_array_token?: string;
  /** Number of Notes arranged horizontally (note_array only; default 1). */
  notes_wide?: number;
  /** Number of Notes arranged vertically (note_array only; default 1). */
  notes_tall?: number;
  /**
   * Local array mode (note_array + api_mode "local"): per-tile Local API
   * endpoints. Out-of-range tiles are preserved server-side across W×H
   * resizes; filter by the current dimensions when rendering.
   */
  tiles?: NoteArrayTile[];
}

export interface BoardSettings {
  board_type: "black" | "white" | null;
  boards: BoardInstance[];
  devices: DeviceType[]; // Computed from boards for backward compat
}

/**
 * Response from POST /settings/board/{id}/detect-size. Mirrors the Python
 * `classify_dimensions()` return shape. For flagship/note only `device_type`,
 * `rows`, `cols` are present; for note arrays the note-grid fields are filled.
 * `matched_preset` is a human-readable preset LABEL (not an id) or null — do
 * not key UI off it; match presets by (notes_wide, notes_tall) instead.
 */
export interface DetectBoardSizeResponse {
  device_type: DeviceType;
  rows: number;
  cols: number;
  notes_wide?: number;
  notes_tall?: number;
  matched_preset?: string | null;
}

/**
 * Request for POST /settings/board/{id}/identify — flashes slot positions
 * onto local note-array tiles (monitor-arrangement style). `target: "tile"`
 * needs row/col; the optional host/port/local_api_key override identifies a
 * board whose tile has not been saved yet (row/col name the slot being
 * assigned).
 */
export interface BoardIdentifyRequest {
  target: "tile" | "all";
  row?: number;
  col?: number;
  host?: string;
  port?: number;
  local_api_key?: string;
}

export interface BoardIdentifyResponse {
  status: string;
  board_id: string;
  results: { row: number; col: number; success: boolean }[];
}

// Schedule types
export type DayPattern = "all" | "weekdays" | "weekends" | "custom";
export type TimeType = "fixed" | "sunrise" | "sunset";
export type RecurrenceType = "weekly" | "annual_date" | "one_off_date";

export interface ScheduleEntry {
  id: string;
  board_id?: string; // Optional; "" or omitted = default board
  page_id: string;
  start_time: string; // HH:MM format
  end_time?: string | null; // HH:MM format or null (open-ended)
  day_pattern: DayPattern;
  custom_days?: string[]; // Only used when day_pattern is "custom"
  enabled: boolean;
  // Recurrence: "weekly" (day-of-week, default) | "annual_date" (MM-DD, repeats yearly)
  // | "one_off_date" (YYYY-MM-DD). Date-specific recurrences override weekly.
  recurrence_type?: RecurrenceType;
  annual_date?: string | null; // "MM-DD"
  annual_end_date?: string | null; // "MM-DD" (optional, for multi-day windows)
  one_off_date?: string | null; // "YYYY-MM-DD"
  one_off_end_date?: string | null; // "YYYY-MM-DD" (optional)
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
  day_pattern?: DayPattern; // defaults to "all" server-side
  custom_days?: string[];
  enabled?: boolean; // Defaults to true
  recurrence_type?: RecurrenceType;
  annual_date?: string | null;
  annual_end_date?: string | null;
  one_off_date?: string | null;
  one_off_end_date?: string | null;
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
  recurrence_type?: RecurrenceType;
  annual_date?: string | null;
  annual_end_date?: string | null;
  one_off_date?: string | null;
  one_off_end_date?: string | null;
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

// Collection types
export const COLLECTION_ID_PREFIX = "collection:";

export function isCollectionId(id: string | null | undefined): boolean {
  return !!id && id.startsWith(COLLECTION_ID_PREFIX);
}

export type CollectionSelectionMode = "time" | "variable" | "random";

export interface TimeModeConfig {
  interval_seconds: number;
}

export interface VariableRule {
  expression: string;
  page_id: string;
}

export interface VariableModeConfig {
  rules: VariableRule[];
  default_page_id: string;
  poll_seconds: number;
}

export interface RandomModeConfig {
  interval_seconds: number;
}

export interface Collection {
  id: string;
  name: string;
  page_ids: string[];
  selection_mode: CollectionSelectionMode;
  time: TimeModeConfig;
  variable: VariableModeConfig | null;
  random: RandomModeConfig | null;
  created_at: string;
  updated_at?: string;
}

export interface CollectionCreate {
  name: string;
  page_ids: string[];
  selection_mode?: CollectionSelectionMode;
  time?: TimeModeConfig;
  variable?: VariableModeConfig | null;
  random?: RandomModeConfig | null;
}

export interface CollectionUpdate {
  name?: string;
  page_ids?: string[];
  selection_mode?: CollectionSelectionMode;
  time?: TimeModeConfig;
  variable?: VariableModeConfig | null;
  random?: RandomModeConfig | null;
}

export interface CollectionsResponse {
  collections: Collection[];
  total: number;
}

export type BoardAnimationsMode = "on" | "desktop" | "off";
export type SiteAnimationsMode = "on" | "off";

export interface DisplaySettings {
  reduce_motion: boolean;
  board_animations: BoardAnimationsMode;
  site_animations: SiteAnimationsMode;
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

export type SilenceMode = "indicator" | "freeze" | "page";

export interface SilenceScheduleConfig {
  enabled: boolean;
  start_time: string;
  end_time: string;
  mode: SilenceMode;
  page_id: string | null;
  indicator_text: string | null;
  indicator_position: string | null;
}

export interface SilenceScheduleSettings {
  config?: Partial<SilenceScheduleConfig>;
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
  /** Local API port (default 7000). Local-array tiles can sit on other ports. */
  port?: number;
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
  profile: "docker" | "pi";
  sidecar_url: string;
  last_check: string | null;
  last_update: string | null;
}

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
  // Compare app-relative routes: under HA Ingress the raw pathname is
  // "<prefix>/login", which a bare "/login" check would miss and loop.
  if (stripBasePath(window.location.pathname).startsWith("/login")) return false;
  if (res.status === 401 || res.status === 409) {
    // For 409 only redirect when the body actually says setup_required —
    // other 409s (e.g. "already set up") should bubble up as errors.
    if (res.status === 409) {
      const ct = res.headers.get("content-type") ?? "";
      if (!ct.includes("application/json")) return false;
      // Peek at the body without consuming it for the caller.
      const cloned = res.clone();
      cloned
        .json()
        .then((body) => {
          if (body?.setup_required) {
            window.location.assign(appUrl(`/login?redirect=${loginRedirectTarget()}`));
          }
        })
        .catch(() => {
          // Not JSON or malformed — leave the caller to surface the error.
        });
      return false;
    }
    window.location.assign(appUrl(`/login?redirect=${loginRedirectTarget()}`));
    return true;
  }
  return false;
}

/**
 * App-relative route to bounce back to after login. Kept prefix-free:
 * the login page navigates with the basename-aware router, which
 * re-applies the ingress prefix on its own.
 */
function loginRedirectTarget(): string {
  return encodeURIComponent(stripBasePath(window.location.pathname) + window.location.search);
}

async function fetchApi<T>(path: string, options?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, ...fetchOptions } = options ?? {};
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  const signal = fetchOptions.signal ? AbortSignal.any([fetchOptions.signal, timeoutSignal]) : timeoutSignal;

  let res: globalThis.Response;
  try {
    res = await fetch(apiUrl(path), {
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

/**
 * Status of the pre-shared bearer token used by external MCP clients.
 * ``source: "env"`` means ``FIESTABOARD_MCP_TOKEN`` is pinned by ops and
 * the UI must hide rotate/clear actions; ``"stored"`` means it's
 * UI-managed; ``"none"`` means no token is configured (cookie auth only).
 */
export type McpTokenStatus = {
  configured: boolean;
  source: "env" | "stored" | "none";
};

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

export const api = {
  // Queries (read-only)
  getStatus: () => fetchApi<StatusResponse>("/status"),
  getConfig: () => fetchApi<ConfigSummary>("/config"),
  getBoardCurrentMessage: () => fetchApi<BoardCurrentMessageResponse>("/board/current-message"),

  // Mutations (actions)
  startService: () => fetchApi<ActionResponse>("/start", { method: "POST" }),
  stopService: () => fetchApi<ActionResponse>("/stop", { method: "POST" }),
  // Display endpoints
  getDisplays: () => fetchApi<DisplaysResponse>("/displays"),
  getDisplay: (type: string) => fetchApi<DisplayResponse>(`/displays/${type}`),
  getDisplayRaw: (type: string) => fetchApi<DisplayRawResponse>(`/displays/${type}/raw`),
  getDisplaysRawBatch: (displayTypes: string[], enabledOnly?: boolean) =>
    fetchApi<DisplayRawBatchResponse>("/displays/raw/batch", {
      method: "POST",
      body: JSON.stringify({
        display_types: displayTypes,
        enabled_only: enabledOnly ?? true,
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

  // Active page settings (optional boardId targets a specific board).
  // boardId is only honored when it's a non-empty string: these wrappers may
  // be handed to TanStack Query or event handlers as bare references, which
  // would otherwise pass a context/event object as boardId (issue #1244).
  getActivePage: (boardId?: string) =>
    fetchApi<ActivePageResponse>(
      typeof boardId === "string" && boardId
        ? `/settings/active-page?board_id=${encodeURIComponent(boardId)}`
        : "/settings/active-page",
    ),
  setActivePage: (pageId: string | null, boardId?: string) =>
    fetchApi<SetActivePageResponse>("/settings/active-page", {
      method: "PUT",
      body: JSON.stringify({
        page_id: pageId,
        ...(typeof boardId === "string" && boardId && { board_id: boardId }),
      }),
    }),

  // Temporary override endpoints
  getTemporaryOverride: () => fetchApi<TemporaryOverrideStatus>("/settings/temporary-override"),
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
    fetchApi<PageUpdateResponse>(`/pages/${pageId}`, {
      method: "PUT",
      body: JSON.stringify(page),
    }),
  deletePage: (pageId: string) => fetchApi<PageDeleteResponse>(`/pages/${pageId}`, { method: "DELETE" }),
  previewPage: (pageId: string) => fetchApi<PagePreviewResponse>(`/pages/${pageId}/preview`, { method: "POST" }),
  previewPagesBatch: (pageIds: string[]) =>
    fetchApi<PagePreviewBatchResponse>("/pages/preview/batch", {
      method: "POST",
      body: JSON.stringify({ page_ids: pageIds }),
    }),
  sendPage: (pageId: string, target?: "ui" | "board" | "both", boardId?: string) => {
    const query = new URLSearchParams();
    if (target) query.set("target", target);
    // Non-empty string only — see the getActivePage note (issue #1244).
    if (typeof boardId === "string" && boardId) query.set("board_id", boardId);
    const qs = query.toString();
    return fetchApi<PageSendResponse>(`/pages/${pageId}/send${qs ? `?${qs}` : ""}`, { method: "POST" });
  },
  getPageShareString: (pageId: string) => fetchApi<{ share_string: string }>(`/pages/${pageId}/share`),
  importPage: (shareString: string) =>
    fetchApi<{ status: string; page: Page }>("/pages/import", {
      method: "POST",
      body: JSON.stringify({ share_string: shareString }),
    }),
  getStaffPicks: () => fetchApi<StaffPick[]>("/staff-picks"),
  getStaffPickShareString: (pickId: string) => fetchApi<{ share_string: string }>(`/staff-picks/${pickId}/share`),

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
      body: JSON.stringify({
        template,
        ...(lineMetadata && { line_metadata: lineMetadata }),
        ...(deviceType && { device_type: deviceType }),
      }),
    }),
  renderTemplateLive: (
    template: string | string[],
    boardId?: string,
    lineMetadata?: LineMetadata[],
    deviceType?: string,
    signal?: AbortSignal,
  ) =>
    fetchApi<TemplateRenderLiveResponse>("/templates/render/live", {
      method: "POST",
      body: JSON.stringify({
        template,
        ...(boardId && { board_id: boardId }),
        ...(lineMetadata && { line_metadata: lineMetadata }),
        ...(deviceType && { device_type: deviceType }),
      }),
      signal,
    }),
  forceRefresh: () =>
    fetchApi<{ status: string; message: string }>("/force-refresh", {
      method: "POST",
    }),

  // Schedule endpoints (optional boardId for per-board schedules)
  getSchedules: (boardId?: string) =>
    fetchApi<SchedulesResponse>(boardId ? `/schedules?board_id=${encodeURIComponent(boardId)}` : "/schedules"),

  createSchedule: (data: ScheduleCreate) =>
    fetchApi<ScheduleEntry>("/schedules", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getSchedule: (scheduleId: string) => fetchApi<ScheduleEntry>(`/schedules/${scheduleId}`),

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
      boardId ? `/schedules/active/page?board_id=${encodeURIComponent(boardId)}` : "/schedules/active/page",
    ),

  validateSchedules: (boardId?: string) =>
    fetchApi<ScheduleValidationResult>("/schedules/validate", {
      method: "POST",
      body: JSON.stringify(boardId != null ? { board_id: boardId } : {}),
    }),

  getDefaultPage: (boardId?: string) =>
    fetchApi<DefaultPageResponse>(
      boardId ? `/schedules/default-page?board_id=${encodeURIComponent(boardId)}` : "/schedules/default-page",
    ),

  setDefaultPage: (pageId: string | null, boardId?: string) =>
    fetchApi<{ status: string; default_page_id: string | null }>("/schedules/default-page", {
      method: "PUT",
      body: JSON.stringify({ page_id: pageId, ...(boardId != null && { board_id: boardId }) }),
    }),

  getScheduleEnabled: (boardId?: string) =>
    fetchApi<ScheduleEnabledResponse>(
      boardId ? `/schedules/enabled?board_id=${encodeURIComponent(boardId)}` : "/schedules/enabled",
    ),

  setScheduleEnabled: (enabled: boolean, boardId?: string) =>
    fetchApi<{ status: string; enabled: boolean; message: string }>("/schedules/enabled", {
      method: "PUT",
      body: JSON.stringify({ enabled, ...(boardId != null && { board_id: boardId }) }),
    }),

  // Collection endpoints
  getCollections: () => fetchApi<CollectionsResponse>("/collections"),

  createCollection: (data: CollectionCreate) =>
    fetchApi<{ status: string; collection: Collection }>("/collections", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getCollection: (collectionId: string) => fetchApi<Collection>(`/collections/${collectionId}`),

  updateCollection: (collectionId: string, data: CollectionUpdate) =>
    fetchApi<{ status: string; collection: Collection }>(`/collections/${collectionId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteCollection: (collectionId: string) =>
    fetchApi<{ status: string; message: string }>(`/collections/${collectionId}`, {
      method: "DELETE",
    }),

  // Configuration endpoints
  getFullConfig: () => fetchApi<FullConfig>("/config/full"),
  getBoardConfig: () => fetchApi<{ config: BoardConfig; api_modes: string[] }>("/config/board"),
  updateBoardConfig: (config: Partial<BoardConfig>) =>
    fetchApi<{ status: string; config: BoardConfig }>("/config/board", {
      method: "PUT",
      body: JSON.stringify(config),
    }),
  // Backward compatibility aliases
  getFiestaboardConfig: () => fetchApi<{ config: BoardConfig; api_modes: string[] }>("/config/board"),
  updateFiestaboardConfig: (config: Partial<BoardConfig>) =>
    fetchApi<{ status: string; config: BoardConfig }>("/config/board", {
      method: "PUT",
      body: JSON.stringify(config),
    }),
  validateConfig: () => fetchApi<ConfigValidationResponse>("/config/validate"),

  // Bay Wheels station search endpoints
  listBayWheelsStations: () => fetchApi<{ stations: BayWheelsStation[]; total: number }>("/baywheels/stations"),
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
  listMuniStops: () => fetchApi<{ stops: MuniStop[]; total: number }>("/muni/stops"),
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
  validateTrafficRoute: (
    origin: string,
    destination: string,
    destination_name: string,
    travel_mode: string = "DRIVE",
  ) =>
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
  updateBoardSettings: (updates: {
    board_type?: "black" | "white" | null;
    devices?: DeviceType[];
    boards?: BoardInstance[];
  }) =>
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
  setBoardPaused: (boardId: string, paused: boolean) =>
    fetchApi<{ status: string; board_id: string; paused: boolean; settings: BoardSettings }>(
      `/settings/board/${boardId}/pause`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paused }),
      },
    ),
  detectBoardSize: (boardId: string) =>
    fetchApi<DetectBoardSizeResponse>(`/settings/board/${boardId}/detect-size`, {
      method: "POST",
    }),
  identifyBoardTile: (boardId: string, request: BoardIdentifyRequest) =>
    fetchApi<BoardIdentifyResponse>(`/settings/board/${boardId}/identify`, {
      method: "POST",
      body: JSON.stringify(request),
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
  getHomeAssistantEntities: () => fetchApi<HomeAssistantEntitiesResponse>("/home-assistant/entities"),

  // Queue-Times (Disney parks) picker
  getQueueTimesParks: () => fetchApi<QueueTimesPark[]>("/queue-times/parks"),
  getQueueTimesRides: (parkId: number) => fetchApi<QueueTimesRide[]>(`/queue-times/parks/${parkId}/rides`),

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

  // AI page-generation ("Gen AI" button) settings + endpoints. BYO-LLM:
  // users supply their own OpenAI-compatible endpoint and key. The API
  // key is masked on read; sending "***" preserves the stored value.
  getAiSettings: () => fetchApi<AISettings>("/settings/ai"),

  updateAiSettings: (updates: Partial<AISettings>) =>
    fetchApi<AISettings>("/settings/ai", {
      method: "PUT",
      body: JSON.stringify(updates),
    }),

  testAiProvider: (params: { provider_id?: string; model?: string; provider?: AIProvider }) =>
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
    const res = await fetch(apiUrl("/pages/ai/generate"), {
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
  // web/app/routes/login.tsx) because they need access to the response
  // `detail` field. The helpers below are for the rest of the UI — e.g.
  // a "Sign out" button in the profile menu.

  getAuthStatus: () => fetchApi<AuthStatusResponse>("/auth/status"),

  logout: () => fetchApi<{ status: string }>("/auth/logout", { method: "POST" }),

  /**
   * Change the signed-in user's password. Uses a bespoke fetch (rather than
   * fetchApi) so the caller can surface FastAPI's ``detail`` body — e.g.
   * "Current password is incorrect".
   */
  changePassword: async (currentPassword: string, newPassword: string) => {
    const res = await fetch(apiUrl("/auth/change-password"), {
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
    const res = await fetch(apiUrl("/auth/change-username"), {
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
   * Record the first-run / "should we lock this down" preference.
   * The backend refuses (409) when an admin user already exists or
   * when FIESTABOARD_AUTH_ENABLED pins the mode. Used by the first-
   * run picker on /login and by the "Turn on login" card in the
   * Account tab after a user has previously disabled auth.
   */
  setAuthPreference: async (enabled: boolean) => {
    const res = await fetch(apiUrl("/auth/preference"), {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
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
      throw new Error(detail || `Setting preference failed (${res.status})`);
    }
    return (await res.json()) as { status: string };
  },

  /**
   * Turn off auth enforcement and delete the admin user. Gated by the
   * current password server-side so a stolen cookie alone can't open
   * the install up. After this returns the install is wide open —
   * the caller should redirect somewhere sensible (e.g. the home
   * page) since /login no longer applies.
   */
  disableAuth: async (currentPassword: string) => {
    const res = await fetch(apiUrl("/auth/disable"), {
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

  // ── MCP bearer token (admin only) ───────────────────────────────────────
  // Lets external MCP clients (Claude Desktop, Claude Code) connect by
  // pasting a one-time-shown token into their connector config instead
  // of editing FIESTABOARD_MCP_TOKEN in .env. See src/auth/routes.py.

  getMcpTokenStatus: () => fetchApi<McpTokenStatus>("/auth/mcp-token"),

  /**
   * Generate a fresh token, persist it server-side, and return the
   * plaintext value ONCE. The caller is responsible for showing it to
   * the user immediately — it can't be read back after this response.
   */
  rotateMcpToken: () => fetchApi<{ token: string }>("/auth/mcp-token", { method: "POST" }),

  clearMcpToken: () => fetchApi<{ status: string }>("/auth/mcp-token", { method: "DELETE" }),

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
