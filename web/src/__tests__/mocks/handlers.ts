import { http, HttpResponse } from "msw";
import type {
  StatusResponse,
  PreviewResponse,
  ConfigSummary,
  DisplaysResponse,
  DisplayResponse,
  DisplayRawResponse,
  DisplayRawBatchResponse,
  TransitionSettings,
  OutputSettings,
  PagesResponse,
  Page,
  PageCreate,
  TemplateVariables,
  TemplateRenderResponse,
  RotationsResponse,
  Rotation,
  RotationCreate,
  RotationStateResponse,
  LogsResponse,
  LogEntry,
  GeneralConfig,
  SilenceStatus,
  PluginDetailsResponse,
} from "@/lib/api";

const API_BASE = "/api";

// Type-safe mock data
export const mockStatus: StatusResponse = {
  running: true,
  initialized: true,
  config_summary: {
    weather_enabled: true,
    home_assistant_enabled: false,
    guest_wifi_enabled: false,
    star_trek_quotes_enabled: true,
    rotation_enabled: true,
    dev_mode: true,
  },
};

export const mockPreview: PreviewResponse = {
  message: "START WHERE YOU ARE\nUSE WHAT YOU HAVE\nDO WHAT YOU CAN\n-ARTHUR ASHE",
  lines: [
    "START WHERE YOU ARE",
    "USE WHAT YOU HAVE",
    "DO WHAT YOU CAN",
    "-ARTHUR ASHE",
  ],
  display_type: "star_trek",
  line_count: 4,
  preview: true,
};

export const mockConfig: ConfigSummary = {
  weather_enabled: true,
  home_assistant_enabled: false,
  guest_wifi_enabled: false,
  star_trek_quotes_enabled: true,
  rotation_enabled: true,
  dev_mode: false,
};

export const mockDisplays: DisplaysResponse = {
  displays: [
    { type: "weather", available: true, description: "Current weather conditions" },
    { type: "datetime", available: true, description: "Current date and time" },
    { type: "weather_datetime", available: true, description: "Combined weather and datetime" },
    { type: "home_assistant", available: false, description: "Home Assistant status" },
    { type: "star_trek", available: true, description: "Star Trek quotes" },
    { type: "guest_wifi", available: false, description: "Guest WiFi credentials" },
  ],
  total: 7,
  available_count: 5,
};

export const mockWeatherDisplay: DisplayResponse = {
  display_type: "weather",
  message: "San Francisco: * Sunny\nTemp: 72°F",
  lines: ["San Francisco: * Sunny", "Temp: 72°F"],
  line_count: 2,
  available: true,
};

export const mockWeatherRaw: DisplayRawResponse = {
  display_type: "weather",
  data: {
    temperature: 72,
    condition: "Sunny",
    location: "San Francisco",
    humidity: 45,
  },
  available: true,
  error: null,
};

export const mockTransitionSettings: TransitionSettings = {
  strategy: "column",
  step_interval_ms: 500,
  step_size: 2,
  available_strategies: [
    "column",
    "reverse-column",
    "edges-to-center",
    "row",
    "diagonal",
    "random",
  ],
};

export const mockOutputSettings: OutputSettings = {
  target: "board",
  dev_mode: true,
  effective_target: "ui",
  available_targets: ["ui", "board", "both"],
};

export const mockPage: Page = {
  id: "page-1",
  name: "Weather Page",
  type: "single",
  device_type: "flagship",
  display_type: "weather",
  duration_seconds: 300,
  created_at: "2024-01-01T00:00:00Z",
};

export const mockCompositePage: Page = {
  id: "page-2",
  name: "Composite Page",
  type: "composite",
  device_type: "flagship",
  rows: [
    { source: "weather", row_index: 0, target_row: 0 },
    { source: "datetime", row_index: 1, target_row: 1 },
  ],
  duration_seconds: 300,
  created_at: "2024-01-01T00:00:00Z",
};

export const mockPages: PagesResponse = {
  pages: [mockPage, { ...mockCompositePage, id: "page-2", name: "Custom Template", type: "template" }],
  total: 2,
};

export const mockTemplateVariables: TemplateVariables = {
  variables: {
    weather: ["temperature", "condition", "location", "humidity", "wind_speed", "feels_like", "uv_index", "pressure", "visibility", "dew_point", "cloud_cover"],
    datetime: ["time", "date", "day"],
  },
  max_lengths: {
    "weather.temperature": 3,
    "weather.condition": 12,
    "weather.location": 15,
    "datetime.time": 5,
    "datetime.date": 10,
    "datetime.day": 2,
  },
  colors: { red: 63, orange: 64, yellow: 65, green: 66, blue: 67, violet: 68, white: 69, black: 70 },
  symbols: ["sun", "cloud", "rain", "star", "heart"],
  filters: ["pad:N", "truncate:N", "wrap"],
  formatting: {
    fill_space: {
      syntax: "{{fill_space}}",
      description: "Expands to fill remaining space on the line. Use multiple for multi-column layouts.",
    },
  },
  syntax_examples: {
    variable: "{{weather.temperature}}",
    variable_with_filter: "{{weather.temperature|pad:3}}",
    color_inline: "{{red}}Warning{{/}}",
    color_code: "{{63}}",
    symbol: "{sun}",
    fill_space: "Left{{fill_space}}Right",
  },
};

export const mockRotation: Rotation = {
  id: "rot-1",
  name: "Main Rotation",
  pages: [{ page_id: "page-1" }, { page_id: "page-2", duration_override: 120 }],
  default_duration: 300,
  enabled: true,
  created_at: "2024-01-01T00:00:00Z",
};

export const mockRotations: RotationsResponse = {
  rotations: [mockRotation],
  total: 1,
  active_rotation_id: "rot-1",
};

export const mockRotationState: RotationStateResponse = {
  active: true,
  rotation_id: "rot-1",
  rotation_name: "Main Rotation",
  current_page_index: 0,
  current_page_id: "page-1",
  time_on_page: 45,
  page_duration: 300,
  total_pages: 2,
};

export const mockCacheStatus = {
  cached: true,
  last_message_hash: "abc123",
  last_sent_at: "2024-01-01T12:00:00Z",
  cache_hits: 5,
  total_sends: 10,
};

// Mock log entries
export const mockLogEntries: LogEntry[] = [
  {
    timestamp: "2025-12-25T10:00:00",
    level: "INFO",
    logger: "src.api_server",
    message: "API server starting up...",
  },
  {
    timestamp: "2025-12-25T10:00:01",
    level: "INFO",
    logger: "src.main",
    message: "Initializing FiestaBoard Display Service...",
  },
  {
    timestamp: "2025-12-25T10:00:02",
    level: "DEBUG",
    logger: "src.board_client",
    message: "Connecting to board at 192.168.1.100",
  },
  {
    timestamp: "2025-12-25T10:00:03",
    level: "WARNING",
    logger: "src.data_sources.weather",
    message: "Weather API rate limit approaching",
  },
  {
    timestamp: "2025-12-25T10:00:04",
    level: "ERROR",
    logger: "src.displays.service",
    message: "Failed to render display: timeout",
  },
  {
    timestamp: "2025-12-25T10:00:05",
    level: "INFO",
    logger: "src.api_server",
    message: "Background service auto-started",
  },
];

export const mockLogsResponse: LogsResponse = {
  logs: mockLogEntries,
  total: mockLogEntries.length,
  limit: 50,
  offset: 0,
  has_more: false,
  filters: {
    level: null,
    search: null,
  },
};

// General config mock
export const mockGeneralConfig: GeneralConfig = {
  timezone: "America/Los_Angeles",
  refresh_interval_seconds: 300,
  output_target: "board",
};

// Silence status mock
export const mockSilenceStatus: SilenceStatus = {
  enabled: false,
  active: false,
  start_time_utc: "04:00+00:00", // 8PM PST
  end_time_utc: "15:00+00:00", // 7AM PST
  current_time_utc: "2025-12-26T18:30:00+00:00",
  next_change_utc: "2025-12-27T04:00:00+00:00",
};

// Plugin config mock for silence_schedule
export const mockSilenceSchedulePlugin: PluginDetailsResponse = {
  id: "silence_schedule",
  name: "Silence Schedule",
  version: "1.0.0",
  description: "Configure quiet hours when the board won't update",
  author: "FiestaBoard",
  icon: "moon",
  category: "utility",
  enabled: true,
  config: {
    enabled: false,
    start_time: "04:00+00:00",
    end_time: "15:00+00:00",
  },
  settings_schema: {
    type: "object",
    properties: {
      enabled: { type: "boolean" },
      start_time: { type: "string" },
      end_time: { type: "string" },
    },
  },
  variables: {},
  max_lengths: {},
  env_vars: [],
  documentation: "",
};

// Store for tracking request bodies in tests
export const requestStore: {
  lastRotationCreate?: RotationCreate;
  lastPageCreate?: PageCreate;
  lastTransitionUpdate?: Partial<TransitionSettings>;
  lastOutputUpdate?: { target: string };
  lastLiveRender?: { template: string | string[]; board_id?: string };
  liveRenderCallCount: number;
} = {
  liveRenderCallCount: 0,
};

// Handlers with request validation
export const handlers = [
  // Core status endpoints
  http.get(`${API_BASE}/status`, () => {
    return HttpResponse.json(mockStatus);
  }),

  http.get(`${API_BASE}/preview`, () => {
    return HttpResponse.json(mockPreview);
  }),

  http.get(`${API_BASE}/config`, () => {
    return HttpResponse.json(mockConfig);
  }),

  http.post(`${API_BASE}/start`, () => {
    return HttpResponse.json({ status: "started", message: "Service started successfully" });
  }),

  http.post(`${API_BASE}/stop`, () => {
    return HttpResponse.json({ status: "stopped", message: "Service stopped successfully" });
  }),

  http.post(`${API_BASE}/dev-mode`, async ({ request }) => {
    const body = await request.json() as { dev_mode: boolean };
    return HttpResponse.json({
      status: "success",
      dev_mode: body.dev_mode,
      message: `Dev mode ${body.dev_mode ? "enabled" : "disabled"}`,
    });
  }),

  http.post(`${API_BASE}/publish-preview`, () => {
    return HttpResponse.json({
      status: "success",
      message: "Preview published to board successfully",
    });
  }),

  // Display endpoints
  http.get(`${API_BASE}/displays`, () => {
    return HttpResponse.json(mockDisplays);
  }),

  http.get(`${API_BASE}/displays/:type`, ({ params }) => {
    const { type } = params;
    if (type === "weather") {
      return HttpResponse.json(mockWeatherDisplay);
    }
    const response: DisplayResponse = {
      display_type: String(type),
      message: `${type} display`,
      lines: [`${type} display`],
      line_count: 1,
      available: true,
    };
    return HttpResponse.json(response);
  }),

  http.post(`${API_BASE}/displays/raw/batch`, async ({ request }) => {
    const body = await request.json() as { display_types?: string[] };
    const displayTypes = body.display_types || [];
    const displays: Record<string, DisplayRawResponse> = {};
    
    displayTypes.forEach((type: string) => {
      displays[type] = {
        display_type: type,
        data: {},
        available: true,
        error: null,
      };
    });
    
    return HttpResponse.json({ displays });
  }),

  http.get(`${API_BASE}/displays/:type/raw`, ({ params }) => {
    const { type } = params;
    if (type === "weather") {
      return HttpResponse.json(mockWeatherRaw);
    }
    const response: DisplayRawResponse = {
      display_type: String(type),
      data: {},
      available: true,
      error: null,
    };
    return HttpResponse.json(response);
  }),

  http.post(`${API_BASE}/displays/:type/send`, ({ params }) => {
    const { type } = params;
    return HttpResponse.json({
      status: "success",
      display_type: type,
      message: `${type} sent`,
      sent_to_board: true,
      target: "board",
      dev_mode: false,
    });
  }),

  // Settings endpoints
  http.get(`${API_BASE}/settings/transitions`, () => {
    return HttpResponse.json(mockTransitionSettings);
  }),

  http.put(`${API_BASE}/settings/transitions`, async ({ request }) => {
    const body = await request.json() as Partial<TransitionSettings>;
    requestStore.lastTransitionUpdate = body;
    const response: TransitionSettings = {
      strategy: body.strategy ?? mockTransitionSettings.strategy,
      step_interval_ms: body.step_interval_ms ?? mockTransitionSettings.step_interval_ms,
      step_size: body.step_size ?? mockTransitionSettings.step_size,
      available_strategies: mockTransitionSettings.available_strategies,
    };
    return HttpResponse.json({
      status: "success",
      settings: response,
    });
  }),

  http.get(`${API_BASE}/settings/output`, () => {
    return HttpResponse.json(mockOutputSettings);
  }),

  http.put(`${API_BASE}/settings/output`, async ({ request }) => {
    const body = await request.json() as { target: string };
    requestStore.lastOutputUpdate = body;
    return HttpResponse.json({
      status: "success",
      settings: { target: body.target },
    });
  }),

  // Active page settings
  http.get(`${API_BASE}/settings/active-page`, () => {
    return HttpResponse.json({
      page_id: "page-1",
    });
  }),

  http.put(`${API_BASE}/settings/active-page`, async ({ request }) => {
    const body = await request.json() as { page_id: string | null };
    return HttpResponse.json({
      status: "success",
      page_id: body.page_id,
      sent_to_board: true,
      dev_mode: false,
    });
  }),

  // Pages endpoints
  http.get(`${API_BASE}/pages`, () => {
    return HttpResponse.json(mockPages);
  }),

  http.get(`${API_BASE}/pages/:id`, ({ params }) => {
    const { id } = params;
    if (id === "page-1") {
      return HttpResponse.json(mockPage);
    }
    if (id === "page-2") {
      return HttpResponse.json(mockCompositePage);
    }
    return HttpResponse.json(mockPage);
  }),

  http.post(`${API_BASE}/pages`, async ({ request }) => {
    const body = await request.json() as PageCreate;
    requestStore.lastPageCreate = body;
    
    const newPage: Page = {
      id: "new-page-" + Date.now(),
      name: body.name,
      type: body.type,
      device_type: body.device_type || "flagship",
      display_type: body.display_type,
      rows: body.rows,
      template: body.template,
      duration_seconds: body.duration_seconds ?? 300,
      created_at: new Date().toISOString(),
    };
    return HttpResponse.json({
      status: "success",
      page: newPage,
    });
  }),

  http.put(`${API_BASE}/pages/:id`, async ({ request, params }) => {
    const body = await request.json() as Partial<Page>;
    const { id } = params;
    const updatedPage: Page = {
      ...mockPage,
      id: String(id),
      ...body,
      updated_at: new Date().toISOString(),
    };
    return HttpResponse.json({
      status: "success",
      page: updatedPage,
    });
  }),

  http.delete(`${API_BASE}/pages/:id`, () => {
    return HttpResponse.json({ status: "success", message: "Page deleted" });
  }),

  http.post(`${API_BASE}/pages/:id/preview`, ({ params }) => {
    const { id } = params;
    return HttpResponse.json({
      page_id: id,
      message: "Preview content",
      lines: ["Preview content"],
      display_type: "single",
      raw: {},
    });
  }),

  http.post(`${API_BASE}/pages/:id/send`, ({ params }) => {
    const { id } = params;
    return HttpResponse.json({
      status: "success",
      page_id: id,
      message: "Page sent",
      sent_to_board: true,
      target: "board",
      dev_mode: false,
    });
  }),

  // Template endpoints
  http.get(`${API_BASE}/templates/variables`, () => {
    return HttpResponse.json(mockTemplateVariables);
  }),

  http.post(`${API_BASE}/templates/validate`, async () => {
    return HttpResponse.json({
      valid: true,
      errors: [],
    });
  }),

  http.post(`${API_BASE}/templates/render`, async ({ request }) => {
    const body = await request.json() as { template: string | string[] };
    const template = Array.isArray(body.template) ? body.template.join("\n") : body.template;
    const response: TemplateRenderResponse = {
      rendered: template || "Rendered template",
      lines: template ? template.split("\n") : ["Rendered template"],
      line_count: template ? template.split("\n").length : 1,
    };
    return HttpResponse.json(response);
  }),

  http.post(`${API_BASE}/templates/render/live`, async ({ request }) => {
    const body = await request.json() as { template: string | string[]; board_id?: string };
    requestStore.lastLiveRender = body;
    requestStore.liveRenderCallCount++;
    const template = Array.isArray(body.template) ? body.template.join("\n") : body.template;
    return HttpResponse.json({
      rendered: template || "",
      lines: template ? template.split("\n") : [""],
      line_count: template ? template.split("\n").length : 1,
      sent_to_board: true,
      board_id: body.board_id || "default",
    });
  }),

  // Rotation endpoints
  http.get(`${API_BASE}/rotations`, () => {
    return HttpResponse.json(mockRotations);
  }),

  http.get(`${API_BASE}/rotations/active`, () => {
    return HttpResponse.json(mockRotationState);
  }),

  http.get(`${API_BASE}/rotations/:id`, ({ params }) => {
    const { id } = params;
    return HttpResponse.json({
      ...mockRotation,
      id: String(id),
      missing_pages: [],
    });
  }),

  http.post(`${API_BASE}/rotations`, async ({ request }) => {
    const body = await request.json() as RotationCreate;
    requestStore.lastRotationCreate = body;
    
    const newRotation: Rotation = {
      id: "new-rot-" + Date.now(),
      name: body.name,
      pages: body.pages,
      default_duration: body.default_duration ?? 300,
      enabled: body.enabled ?? true,
      created_at: new Date().toISOString(),
    };
    return HttpResponse.json({
      status: "success",
      rotation: newRotation,
    });
  }),

  http.put(`${API_BASE}/rotations/:id`, async ({ request, params }) => {
    const body = await request.json() as Partial<Rotation>;
    const { id } = params;
    const updatedRotation: Rotation = {
      ...mockRotation,
      id: String(id),
      ...body,
      updated_at: new Date().toISOString(),
    };
    return HttpResponse.json({
      status: "success",
      rotation: updatedRotation,
    });
  }),

  http.delete(`${API_BASE}/rotations/:id`, () => {
    return HttpResponse.json({ status: "success", message: "Rotation deleted" });
  }),

  http.post(`${API_BASE}/rotations/:id/activate`, ({ params }) => {
    const { id } = params;
    return HttpResponse.json({
      status: "success",
      message: "Rotation activated",
      state: { ...mockRotationState, rotation_id: String(id) },
    });
  }),

  http.post(`${API_BASE}/rotations/deactivate`, () => {
    return HttpResponse.json({
      status: "success",
      message: "Rotation deactivated",
    });
  }),

  // Cache endpoints
  http.get(`${API_BASE}/cache-status`, () => {
    return HttpResponse.json(mockCacheStatus);
  }),

  http.post(`${API_BASE}/clear-cache`, () => {
    return HttpResponse.json({
      status: "success",
      message: "Cache cleared",
    });
  }),

  http.post(`${API_BASE}/force-refresh`, () => {
    return HttpResponse.json({
      status: "success",
      message: "Display force-refreshed",
    });
  }),

  // Logs endpoint
  http.get(`${API_BASE}/logs`, ({ request }) => {
    const url = new URL(request.url);
    const limit = parseInt(url.searchParams.get("limit") || "50");
    const offset = parseInt(url.searchParams.get("offset") || "0");
    const level = url.searchParams.get("level")?.toUpperCase();
    const search = url.searchParams.get("search")?.toLowerCase();

    let filteredLogs = [...mockLogEntries];

    // Filter by level
    if (level) {
      filteredLogs = filteredLogs.filter((log) => log.level === level);
    }

    // Filter by search
    if (search) {
      filteredLogs = filteredLogs.filter(
        (log) =>
          log.message.toLowerCase().includes(search) ||
          log.logger.toLowerCase().includes(search)
      );
    }

    const total = filteredLogs.length;
    const paginatedLogs = filteredLogs.slice(offset, offset + limit);
    const hasMore = offset + limit < total;

    const response: LogsResponse = {
      logs: paginatedLogs,
      total,
      limit,
      offset,
      has_more: hasMore,
      filters: {
        level: level as LogsResponse["filters"]["level"],
        search: search || null,
      },
    };

    return HttpResponse.json(response);
  }),

  // General config endpoints
  http.get(`${API_BASE}/config/general`, () => {
    return HttpResponse.json(mockGeneralConfig);
  }),

  http.put(`${API_BASE}/config/general`, async ({ request }) => {
    const body = await request.json() as Partial<GeneralConfig>;
    const updatedConfig = {
      ...mockGeneralConfig,
      ...body,
    };
    return HttpResponse.json({
      status: "success",
      general: updatedConfig,
    });
  }),

  // Plugin config endpoints
  http.get(`${API_BASE}/plugins/:pluginId`, ({ params }) => {
    const { pluginId } = params;
    if (pluginId === "silence_schedule") {
      return HttpResponse.json(mockSilenceSchedulePlugin);
    }
    // Return generic plugin response for other plugins
    return HttpResponse.json({
      id: pluginId,
      name: String(pluginId),
      version: "1.0.0",
      description: "",
      author: "Unknown",
      icon: "puzzle",
      category: "utility",
      enabled: false,
      config: {},
      settings_schema: {},
      variables: {},
      max_lengths: {},
      env_vars: [],
      documentation: "",
    });
  }),

  http.get(`${API_BASE}/plugins/:pluginId/manifest`, ({ params }) => {
    const { pluginId } = params;
    // Return mock manifest for weather plugin
    if (pluginId === "weather") {
      return HttpResponse.json({
        id: "weather",
        name: "Weather",
        version: "1.0.0",
        variables: {
          simple: ["temperature", "condition", "location", "humidity", "wind_speed", "feels_like", "uv_index", "pressure", "visibility", "dew_point", "cloud_cover"],
        },
      });
    }
    // Return generic manifest for other plugins
    return HttpResponse.json({
      id: String(pluginId),
      name: String(pluginId),
      version: "1.0.0",
      variables: {
        simple: [],
      },
    });
  }),

  http.post(`${API_BASE}/plugins/:pluginId/config`, async ({ request, params }) => {
    const { pluginId } = params;
    const body = await request.json() as { config: Record<string, unknown> };
    return HttpResponse.json({
      status: "success",
      plugin_id: pluginId,
      config: body.config,
    });
  }),

  http.put(`${API_BASE}/plugins/:pluginId/config`, async ({ request, params }) => {
    const { pluginId } = params;
    const body = await request.json() as { config: Record<string, unknown> };
    return HttpResponse.json({
      status: "success",
      plugin_id: pluginId,
      config: body.config,
    });
  }),

  // Silence status endpoint
  http.get(`${API_BASE}/silence-status`, () => {
    return HttpResponse.json(mockSilenceStatus);
  }),

  // Schedule endpoints (for active-page-display)
  http.get(`${API_BASE}/schedules`, ({ request }) => {
    const url = new URL(request.url);
    const boardId = url.searchParams.get("board_id");
    return HttpResponse.json({
      schedules: [],
      total: 0,
      default_page_id: null,
      enabled: false,
      ...(boardId && { board_id: boardId }),
    });
  }),

  http.get(`${API_BASE}/schedules/active/page`, ({ request }) => {
    const url = new URL(request.url);
    return HttpResponse.json({
      page_id: "page-1",
      source: "schedule",
      schedule_enabled: true,
      ...(url.searchParams.get("board_id") && { board_id: url.searchParams.get("board_id") }),
    });
  }),

  // All settings endpoint (for general-settings)
  http.get(`${API_BASE}/settings/all`, () => {
    return HttpResponse.json({
      general: {
        timezone: "America/Los_Angeles",
        refresh_interval_seconds: 300,
        output_target: "board",
      },
      silence_schedule: {
        config: {
          enabled: false,
          start_time: "04:00+00:00",
          end_time: "15:00+00:00",
        },
      },
      polling: { interval_seconds: 300 },
      transitions: mockTransitionSettings,
      output: mockOutputSettings,
      board: {
        board_type: "black",
        boards: [{ id: "default", name: "Flagship", device_type: "flagship", board_color: "black" }],
        devices: ["flagship"],
      },
      status: {
        running: true,
        config_summary: { dev_mode: false },
      },
    });
  }),

  // Config validation endpoint
  http.get(`${API_BASE}/config/validate`, () => {
    return HttpResponse.json({
      valid: true,
      is_first_run: false,
      errors: [],
      missing_fields: [],
    });
  }),

  // Version endpoint
  http.get(`${API_BASE}/version`, () => {
    return HttpResponse.json({
      package_version: "2.0.1",
      build_version: "dev",
      is_dev: true,
    });
  }),

  // System management endpoints
  http.get(`${API_BASE}/system/update-check`, () => {
    return HttpResponse.json({
      current_version: "2.0.1",
      latest_version: "2.0.1",
      update_available: false,
      package_url: "https://github.com/Fiestaboard/FiestaBoard/pkgs/container/fiestaboard",
      error: null,
      is_production: false,
    });
  }),

  // Polling settings endpoints
  http.get(`${API_BASE}/settings/polling`, () => {
    return HttpResponse.json({
      interval_seconds: 300
    });
  }),

  http.put(`${API_BASE}/settings/polling`, async ({ request }) => {
    const body = await request.json() as { interval_seconds: number };
    return HttpResponse.json({
      status: "success",
      settings: { interval_seconds: body.interval_seconds },
      requires_restart: false
    });
  }),

  // Board settings endpoints
  http.get(`${API_BASE}/settings/board`, () => {
    return HttpResponse.json({
      board_type: "black",
      boards: [{ id: "default", name: "Flagship", device_type: "flagship", board_color: "black" }],
      devices: ["flagship"]
    });
  }),

  http.put(`${API_BASE}/settings/board`, async ({ request }) => {
    const body = await request.json() as { board_type?: "black" | "white" | null; devices?: string[]; boards?: object[] };
    return HttpResponse.json({
      status: "success",
      settings: {
        board_type: body.board_type ?? "black",
        boards: body.boards ?? [{ id: "default", name: "Flagship", device_type: "flagship", board_color: "black" }],
        devices: body.devices ?? ["flagship"]
      }
    });
  }),

  http.post(`${API_BASE}/settings/board/add`, async ({ request }) => {
    const body = await request.json() as { device_type: string; name?: string; board_color?: string };
    return HttpResponse.json({
      status: "success",
      settings: {
        board_type: "black",
        boards: [
          { id: "default", name: "Flagship", device_type: "flagship", board_color: "black" },
          { id: "new", name: body.name || (body.device_type === "note" ? "Note" : "Flagship"), device_type: body.device_type, board_color: body.board_color || "black" }
        ],
        devices: ["flagship", body.device_type]
      }
    });
  }),

  http.delete(`${API_BASE}/settings/board/:boardId`, () => {
    return HttpResponse.json({
      status: "success",
      settings: {
        board_type: "black",
        boards: [{ id: "default", name: "Flagship", device_type: "flagship", board_color: "black" }],
        devices: ["flagship"]
      }
    });
  }),
];

