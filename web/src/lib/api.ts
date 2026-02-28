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

// Debug types
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
  dev_mode: boolean;
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
  dev_mode: boolean;
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

// Template types
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
  devices: DeviceType[]; // Computed from boards for backward compat
}

// Schedule types
export type DayPattern = "all" | "weekdays" | "weekends" | "custom";

export interface ScheduleEntry {
  id: string;
  board_id?: string; // Optional; "" or omitted = default board
  page_id: string;
  start_time: string; // HH:MM format
  end_time: string;   // HH:MM format
  day_pattern: DayPattern;
  custom_days?: string[]; // Only used when day_pattern is "custom"
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
  enabled?: boolean; // Defaults to true
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



// API client with typed methods
async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  // Queries (read-only)
  getStatus: () => fetchApi<StatusResponse>("/status"),
  getConfig: () => fetchApi<ConfigSummary>("/config"),

  // Mutations (actions)
  startService: () =>
    fetchApi<ActionResponse>("/start", { method: "POST" }),
  stopService: () =>
    fetchApi<ActionResponse>("/stop", { method: "POST" }),
  toggleDevMode: (devMode: boolean) =>
    fetchApi<ActionResponse>("/dev-mode", {
      method: "POST",
      body: JSON.stringify({ dev_mode: devMode }),
    }),

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

  // Pages endpoints
  getPages: () => fetchApi<PagesResponse>("/pages"),
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

  // Templates endpoints
  getTemplateVariables: () => fetchApi<TemplateVariables>("/templates/variables"),
  validateTemplate: (template: string | string[]) =>
    fetchApi<TemplateValidationResponse>("/templates/validate", {
      method: "POST",
      body: JSON.stringify({ template }),
    }),
  renderTemplate: (template: string | string[], lineMetadata?: LineMetadata[]) =>
    fetchApi<TemplateRenderResponse>("/templates/render", {
      method: "POST",
      body: JSON.stringify({ template, ...(lineMetadata && { line_metadata: lineMetadata }) }),
    }),
  renderTemplateLive: (template: string | string[], boardId?: string, lineMetadata?: LineMetadata[], signal?: AbortSignal) =>
    fetchApi<TemplateRenderLiveResponse>("/templates/render/live", {
      method: "POST",
      body: JSON.stringify({ template, ...(boardId && { board_id: boardId }), ...(lineMetadata && { line_metadata: lineMetadata }) }),
      signal,
    })
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

  // Polling settings
  getPollingSettings: () => fetchApi<PollingSettings>("/settings/polling"),
  updatePollingSettings: (interval_seconds: number) =>
    fetchApi<{ status: string; settings: PollingSettings; requires_restart: boolean }>("/settings/polling", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interval_seconds }),
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
  
  getAllPluginVariables: () =>
    fetchApi<AllPluginVariablesResponse>("/plugins/variables/all"),
  
  getPluginErrors: () =>
    fetchApi<PluginErrorsResponse>("/plugins/errors"),

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
};
