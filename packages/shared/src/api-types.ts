/** Shared API types for FiestaBoard - used by web and mobile */

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
  dev_mode: boolean;
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

export interface ActionResponse {
  status: string;
  message: string;
  dev_mode?: boolean;
  debug_info?: string;
}

export interface DebugTestResponse {
  status: string;
  message: string;
  connected: boolean;
  latency_ms: number | null;
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
  dev_mode: boolean;
}

export interface PageDeleteResponse {
  status: string;
  message: string;
  default_page_created: boolean;
  new_page_id?: string;
  active_page_updated: boolean;
  new_active_page_id?: string;
}

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

export interface TransitionSettings {
  strategy: string | null;
  step_interval_ms: number | null;
  step_size: number | null;
  available_strategies?: string[];
}

export interface OutputSettings {
  target: "ui" | "board" | "both";
  dev_mode: boolean;
  effective_target: string;
  available_targets: string[];
}

export interface ActivePageResponse {
  page_id: string | null;
}

export interface SetActivePageResponse {
  status: string;
  page_id: string | null;
  sent_to_board: boolean;
  dev_mode: boolean;
}

export type PageType = "single" | "composite" | "template";

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
  transition_strategy?: string | null;
  transition_interval_ms?: number | null;
  transition_step_size?: number | null;
}

export interface PagesResponse {
  pages: Page[];
  total: number;
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
  dev_mode: boolean;
}

export interface FormattingVariable {
  syntax: string;
  description: string;
}

export interface TemplateVariables {
  variables: Record<string, string[]>;
  max_lengths: Record<string, number>;
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

export interface BoardConfig {
  api_mode: "local" | "cloud";
  local_api_key: string;
  cloud_key: string;
  host: string;
  transition_strategy: string | null;
  transition_interval_ms: number | null;
  transition_step_size: number | null;
}

export type FiestaboardConfig = BoardConfig;

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
  timezone: string;
  refresh_interval_seconds: number;
  output_target: "ui" | "board" | "both";
}

export interface SilenceStatus {
  enabled: boolean;
  active: boolean;
  start_time_utc: string;
  end_time_utc: string;
  current_time_utc: string;
  next_change_utc: string;
}

export interface PollingSettings {
  interval_seconds: number;
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
  devices: DeviceType[];
}

export type DayPattern = "all" | "weekdays" | "weekends" | "custom";

export interface ScheduleEntry {
  id: string;
  board_id?: string;
  page_id: string;
  start_time: string;
  end_time: string;
  day_pattern: DayPattern;
  custom_days?: string[];
  enabled: boolean;
  created_at: string;
  updated_at?: string;
}

export interface ScheduleCreate {
  board_id?: string;
  page_id: string;
  start_time: string;
  end_time: string;
  day_pattern: DayPattern;
  custom_days?: string[];
  enabled?: boolean;
}

export interface ScheduleUpdate {
  board_id?: string;
  page_id?: string;
  start_time?: string;
  end_time?: string;
  day_pattern?: DayPattern;
  custom_days?: string[];
  enabled?: boolean;
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

export interface ActiveScheduleResponse {
  page_id: string | null;
  source: "schedule" | "manual" | "none";
  schedule_enabled: boolean;
  current_time?: string;
  current_day?: string;
  default_page_id?: string | null;
}

export interface ScheduleEnabledResponse {
  enabled: boolean;
}

export interface DefaultPageResponse {
  default_page_id: string | null;
}

export interface AllSettingsResponse {
  general: GeneralConfig;
  silence_schedule: Record<string, unknown>;
  polling: PollingSettings;
  transitions: TransitionSettings;
  output: OutputSettings;
  board: BoardSettings;
  status: {
    running: boolean;
    dev_mode: boolean;
  };
}

export interface FullConfig {
  board: BoardConfig;
  general: GeneralConfig;
  plugins: Record<string, Record<string, unknown>>;
}

export interface ConfigValidationResponse {
  valid: boolean;
  is_first_run: boolean;
  errors: string[];
  missing_fields: string[];
}

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
}

export interface WelcomeMessageResponse {
  status: string;
  message: string;
  dev_mode?: boolean;
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
  config: Record<string, unknown>;
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
    simple?: string[];
    arrays?: Record<string, {
      label_field: string;
      item_fields: string[];
      sub_arrays?: Record<string, {
        key_type?: "index" | "dynamic";
        key_field?: string;
        item_fields: string[];
      }>;
    }>;
    nested?: Record<string, unknown>;
    dynamic?: boolean;
  };
  max_lengths: Record<string, number>;
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
