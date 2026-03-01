/**
 * API client for FiestaBoard service.
 * Uses configurable baseUrl instead of hardcoded path (for web vs mobile/remote).
 */
import type {
  ActionResponse,
  ActivePageResponse,
  ActiveScheduleResponse,
  AllPluginVariablesResponse,
  AllSettingsResponse,
  BayWheelsStation,
  BoardConfig,
  BoardInstance,
  BoardScanResponse,
  BoardSettings,
  BoardTestRequest,
  BoardTestResponse,
  ConfigSummary,
  ConfigValidationResponse,
  DebugCacheStatus,
  DebugSystemInfo,
  DebugTestResponse,
  DefaultPageResponse,
  DeviceType,
  DisplayRawBatchResponse,
  DisplayRawResponse,
  DisplayResponse,
  DisplaysResponse,
  EnableLocalApiRequest,
  EnableLocalApiResponse,
  FullConfig,
  GeneralConfig,
  HomeAssistantEntitiesResponse,
  LineMetadata,
  MuniStop,
  Page,
  PageCreate,
  PageDeleteResponse,
  PagePreviewBatchResponse,
  PagePreviewResponse,
  PageSendResponse,
  PageUpdate,
  PagesResponse,
  PluginConfigUpdateResponse,
  PluginDataResponse,
  PluginDetailResponse,
  PluginEnableResponse,
  PluginErrorsResponse,
  PluginManifest,
  PluginVariablesResponse,
  PluginsListResponse,
  PollingSettings,
  QueueTimesPark,
  QueueTimesRide,
  ScheduleCreate,
  ScheduleEnabledResponse,
  ScheduleEntry,
  SchedulesResponse,
  ScheduleUpdate,
  ScheduleValidationResult,
  SetActivePageResponse,
  SilenceStatus,
  StockSymbol,
  StockSymbolValidation,
  StatusResponse,
  TemplateRenderLiveResponse,
  TemplateRenderResponse,
  TemplateValidationResponse,
  TemplateVariables,
  TransitionSettings,
  OutputSettings,
  UpdateCheckResponse,
  VersionResponse,
  WelcomeMessageResponse,
} from "./api-types";

export async function fetchApi<T>(
  baseUrl: string,
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${baseUrl}${path}`, {
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

export function createApiClient(baseUrl: string) {
  return {
    // Queries (read-only)
    getStatus: () => fetchApi<StatusResponse>(baseUrl, "/status"),
    getConfig: () => fetchApi<ConfigSummary>(baseUrl, "/config"),

    // Mutations (actions)
    startService: () =>
      fetchApi<ActionResponse>(baseUrl, "/start", { method: "POST" }),
    stopService: () =>
      fetchApi<ActionResponse>(baseUrl, "/stop", { method: "POST" }),
    toggleDevMode: (devMode: boolean) =>
      fetchApi<ActionResponse>(baseUrl, "/dev-mode", {
        method: "POST",
        body: JSON.stringify({ dev_mode: devMode }),
      }),

    // Display endpoints
    getDisplays: () => fetchApi<DisplaysResponse>(baseUrl, "/displays"),
    getDisplay: (type: string) =>
      fetchApi<DisplayResponse>(baseUrl, `/displays/${type}`),
    getDisplayRaw: (type: string) =>
      fetchApi<DisplayRawResponse>(baseUrl, `/displays/${type}/raw`),
    getDisplaysRawBatch: (displayTypes: string[], enabledOnly?: boolean) =>
      fetchApi<DisplayRawBatchResponse>(baseUrl, "/displays/raw/batch", {
        method: "POST",
        body: JSON.stringify({
          display_types: displayTypes,
          enabled_only: enabledOnly ?? true,
        }),
      }),
    sendDisplay: (type: string, target?: "ui" | "board" | "both") => {
      const params = target ? `?target=${target}` : "";
      return fetchApi<ActionResponse>(
        baseUrl,
        `/displays/${type}/send${params}`,
        { method: "POST" }
      );
    },

    // Settings endpoints
    getTransitionSettings: () =>
      fetchApi<TransitionSettings>(baseUrl, "/settings/transitions"),
    updateTransitionSettings: (settings: Partial<TransitionSettings>) =>
      fetchApi<{ status: string; settings: TransitionSettings }>(
        baseUrl,
        "/settings/transitions",
        {
          method: "PUT",
          body: JSON.stringify(settings),
        }
      ),
    getOutputSettings: () =>
      fetchApi<OutputSettings>(baseUrl, "/settings/output"),
    updateOutputSettings: (target: "ui" | "board" | "both") =>
      fetchApi<{ status: string; settings: { target: string } }>(
        baseUrl,
        "/settings/output",
        {
          method: "PUT",
          body: JSON.stringify({ target }),
        }
      ),

    // Active page settings
    getActivePage: () =>
      fetchApi<ActivePageResponse>(baseUrl, "/settings/active-page"),
    setActivePage: (pageId: string | null) =>
      fetchApi<SetActivePageResponse>(baseUrl, "/settings/active-page", {
        method: "PUT",
        body: JSON.stringify({ page_id: pageId }),
      }),

    // Pages endpoints
    getPages: () => fetchApi<PagesResponse>(baseUrl, "/pages"),
    getPage: (pageId: string) => fetchApi<Page>(baseUrl, `/pages/${pageId}`),
    createPage: (page: PageCreate) =>
      fetchApi<{ status: string; page: Page }>(baseUrl, "/pages", {
        method: "POST",
        body: JSON.stringify(page),
      }),
    updatePage: (pageId: string, page: PageUpdate) =>
      fetchApi<{ status: string; page: Page }>(baseUrl, `/pages/${pageId}`, {
        method: "PUT",
        body: JSON.stringify(page),
      }),
    deletePage: (pageId: string) =>
      fetchApi<PageDeleteResponse>(baseUrl, `/pages/${pageId}`, {
        method: "DELETE",
      }),
    previewPage: (pageId: string) =>
      fetchApi<PagePreviewResponse>(baseUrl, `/pages/${pageId}/preview`, {
        method: "POST",
      }),
    previewPagesBatch: (pageIds: string[]) =>
      fetchApi<PagePreviewBatchResponse>(baseUrl, "/pages/preview/batch", {
        method: "POST",
        body: JSON.stringify({ page_ids: pageIds }),
      }),
    sendPage: (pageId: string, target?: "ui" | "board" | "both") => {
      const params = target ? `?target=${target}` : "";
      return fetchApi<PageSendResponse>(
        baseUrl,
        `/pages/${pageId}/send${params}`,
        { method: "POST" }
      );
    },

    // Templates endpoints
    getTemplateVariables: () =>
      fetchApi<TemplateVariables>(baseUrl, "/templates/variables"),
    validateTemplate: (template: string | string[]) =>
      fetchApi<TemplateValidationResponse>(baseUrl, "/templates/validate", {
        method: "POST",
        body: JSON.stringify({ template }),
      }),
    renderTemplate: (
      template: string | string[],
      lineMetadata?: LineMetadata[]
    ) =>
      fetchApi<TemplateRenderResponse>(baseUrl, "/templates/render", {
        method: "POST",
        body: JSON.stringify({
          template,
          ...(lineMetadata && { line_metadata: lineMetadata }),
        }),
      }),
    renderTemplateLive: (
      template: string | string[],
      boardId?: string,
      lineMetadata?: LineMetadata[],
      signal?: AbortSignal
    ) =>
      fetchApi<TemplateRenderLiveResponse>(baseUrl, "/templates/render/live", {
        method: "POST",
        body: JSON.stringify({
          template,
          ...(boardId && { board_id: boardId }),
          ...(lineMetadata && { line_metadata: lineMetadata }),
        }),
        signal,
      }),
    forceRefresh: () =>
      fetchApi<{ status: string; message: string }>(baseUrl, "/force-refresh", {
        method: "POST",
      }),

    // Schedule endpoints (optional boardId for per-board schedules)
    getSchedules: (boardId?: string) =>
      fetchApi<SchedulesResponse>(
        baseUrl,
        boardId ? `/schedules?board_id=${encodeURIComponent(boardId)}` : "/schedules"
      ),
    createSchedule: (data: ScheduleCreate) =>
      fetchApi<ScheduleEntry>(baseUrl, "/schedules", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    getSchedule: (scheduleId: string) =>
      fetchApi<ScheduleEntry>(baseUrl, `/schedules/${scheduleId}`),
    updateSchedule: (scheduleId: string, data: ScheduleUpdate) =>
      fetchApi<ScheduleEntry>(baseUrl, `/schedules/${scheduleId}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
    deleteSchedule: (scheduleId: string) =>
      fetchApi<{ status: string; message: string }>(
        baseUrl,
        `/schedules/${scheduleId}`,
        { method: "DELETE" }
      ),
    getActiveSchedule: (boardId?: string) =>
      fetchApi<ActiveScheduleResponse>(
        baseUrl,
        boardId
          ? `/schedules/active/page?board_id=${encodeURIComponent(boardId)}`
          : "/schedules/active/page"
      ),
    validateSchedules: (boardId?: string) =>
      fetchApi<ScheduleValidationResult>(baseUrl, "/schedules/validate", {
        method: "POST",
        body: JSON.stringify(boardId != null ? { board_id: boardId } : {}),
      }),
    getDefaultPage: (boardId?: string) =>
      fetchApi<DefaultPageResponse>(
        baseUrl,
        boardId
          ? `/schedules/default-page?board_id=${encodeURIComponent(boardId)}`
          : "/schedules/default-page"
      ),
    setDefaultPage: (pageId: string | null, boardId?: string) =>
      fetchApi<{ status: string; default_page_id: string | null }>(
        baseUrl,
        "/schedules/default-page",
        {
          method: "PUT",
          body: JSON.stringify({
            page_id: pageId,
            ...(boardId != null && { board_id: boardId }),
          }),
        }
      ),
    getScheduleEnabled: (boardId?: string) =>
      fetchApi<ScheduleEnabledResponse>(
        baseUrl,
        boardId
          ? `/schedules/enabled?board_id=${encodeURIComponent(boardId)}`
          : "/schedules/enabled"
      ),
    setScheduleEnabled: (enabled: boolean, boardId?: string) =>
      fetchApi<{ status: string; enabled: boolean; message: string }>(
        baseUrl,
        "/schedules/enabled",
        {
          method: "PUT",
          body: JSON.stringify({
            enabled,
            ...(boardId != null && { board_id: boardId }),
          }),
        }
      ),

    // Configuration endpoints
    getFullConfig: () => fetchApi<FullConfig>(baseUrl, "/config/full"),
    getBoardConfig: () =>
      fetchApi<{ config: BoardConfig; api_modes: string[] }>(
        baseUrl,
        "/config/board"
      ),
    updateBoardConfig: (config: Partial<BoardConfig>) =>
      fetchApi<{ status: string; config: BoardConfig }>(
        baseUrl,
        "/config/board",
        {
          method: "PUT",
          body: JSON.stringify(config),
        }
      ),
    getFiestaboardConfig: () =>
      fetchApi<{ config: BoardConfig; api_modes: string[] }>(
        baseUrl,
        "/config/board"
      ),
    updateFiestaboardConfig: (config: Partial<BoardConfig>) =>
      fetchApi<{ status: string; config: BoardConfig }>(
        baseUrl,
        "/config/board",
        {
          method: "PUT",
          body: JSON.stringify(config),
        }
      ),
    validateConfig: () =>
      fetchApi<ConfigValidationResponse>(baseUrl, "/config/validate"),

    // Bay Wheels station search endpoints
    listBayWheelsStations: () =>
      fetchApi<{ stations: BayWheelsStation[]; total: number }>(
        baseUrl,
        "/baywheels/stations"
      ),
    findNearbyBayWheelsStations: (
      lat: number,
      lng: number,
      radius?: number,
      limit?: number
    ) => {
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
      }>(baseUrl, `/baywheels/stations/nearby?${params}`);
    },
    searchBayWheelsStationsByAddress: (
      address: string,
      radius?: number,
      limit?: number
    ) => {
      const params = new URLSearchParams({
        address,
        ...(radius !== undefined && { radius: radius.toString() }),
        ...(limit !== undefined && { limit: limit.toString() }),
      });
      return fetchApi<{
        stations: BayWheelsStation[];
        count: number;
        search_address: string;
        geocoded_location: {
          lat: number;
          lng: number;
          display_name: string;
        };
        radius_km: number;
      }>(baseUrl, `/baywheels/stations/search?${params}`);
    },

    // MUNI stop search endpoints
    listMuniStops: () =>
      fetchApi<{ stops: MuniStop[]; total: number }>(baseUrl, "/muni/stops"),
    findNearbyMuniStops: (
      lat: number,
      lng: number,
      radius?: number,
      limit?: number
    ) => {
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
      }>(baseUrl, `/muni/stops/nearby?${params}`);
    },
    searchMuniStopsByAddress: (
      address: string,
      radius?: number,
      limit?: number
    ) => {
      const params = new URLSearchParams({
        address,
        ...(radius !== undefined && { radius: radius.toString() }),
        ...(limit !== undefined && { limit: limit.toString() }),
      });
      return fetchApi<{
        stops: MuniStop[];
        count: number;
        search_address: string;
        geocoded_location: {
          lat: number;
          lng: number;
          display_name: string;
        };
        radius_km: number;
      }>(baseUrl, `/muni/stops/search?${params}`);
    },

    // Traffic route endpoints
    geocodeAddress: (address: string) =>
      fetchApi<{ lat: number; lng: number; formatted_address: string }>(
        baseUrl,
        "/traffic/routes/geocode",
        {
          method: "POST",
          body: JSON.stringify({ address }),
        }
      ),
    validateTrafficRoute: (
      origin: string,
      destination: string,
      destination_name: string,
      travel_mode: string = "DRIVE"
    ) =>
      fetchApi<{
        valid: boolean;
        distance_km?: number;
        static_duration_minutes?: number;
        error?: string;
      }>(baseUrl, "/traffic/routes/validate", {
        method: "POST",
        body: JSON.stringify({
          origin,
          destination,
          destination_name,
          travel_mode,
        }),
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
      }>(baseUrl, `/stocks/search?${params}`);
    },
    validateStockSymbol: (symbol: string) =>
      fetchApi<StockSymbolValidation>(baseUrl, "/stocks/validate", {
        method: "POST",
        body: JSON.stringify({ symbol }),
      }),

    // General configuration
    getGeneralConfig: () =>
      fetchApi<GeneralConfig>(baseUrl, "/config/general"),
    updateGeneralConfig: (config: Partial<GeneralConfig>) =>
      fetchApi<{ status: string; general: GeneralConfig }>(
        baseUrl,
        "/config/general",
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(config),
        }
      ),

    // Silence mode status
    getSilenceStatus: () =>
      fetchApi<SilenceStatus>(baseUrl, "/silence-status"),

    // Polling settings
    getPollingSettings: () =>
      fetchApi<PollingSettings>(baseUrl, "/settings/polling"),
    updatePollingSettings: (interval_seconds: number) =>
      fetchApi<{
        status: string;
        settings: PollingSettings;
        requires_restart: boolean;
      }>(baseUrl, "/settings/polling", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ interval_seconds }),
      }),

    // Board settings
    getBoardSettings: () =>
      fetchApi<BoardSettings>(baseUrl, "/settings/board"),
    updateBoardSettings: (
      updates: {
        board_type?: "black" | "white" | null;
        devices?: DeviceType[];
        boards?: BoardInstance[];
      }
    ) =>
      fetchApi<{ status: string; settings: BoardSettings }>(
        baseUrl,
        "/settings/board",
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(updates),
        }
      ),
    addBoard: (board: Partial<BoardInstance> & { device_type: DeviceType }) =>
      fetchApi<{ status: string; settings: BoardSettings }>(
        baseUrl,
        "/settings/board/add",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(board),
        }
      ),
    removeBoard: (boardId: string) =>
      fetchApi<{ status: string; settings: BoardSettings }>(
        baseUrl,
        `/settings/board/${boardId}`,
        { method: "DELETE" }
      ),
    getAllSettings: () =>
      fetchApi<AllSettingsResponse>(baseUrl, "/settings/all"),

    // Home Assistant endpoints
    getHomeAssistantEntities: () =>
      fetchApi<HomeAssistantEntitiesResponse>(
        baseUrl,
        "/home-assistant/entities"
      ),

    // Queue-Times (Disney parks) picker
    getQueueTimesParks: () =>
      fetchApi<QueueTimesPark[]>(baseUrl, "/queue-times/parks"),
    getQueueTimesRides: (parkId: number) =>
      fetchApi<QueueTimesRide[]>(
        baseUrl,
        `/queue-times/parks/${parkId}/rides`
      ),

    // Version endpoint
    getVersion: () => fetchApi<VersionResponse>(baseUrl, "/version"),

    // System management endpoints
    checkForUpdate: () =>
      fetchApi<UpdateCheckResponse>(baseUrl, "/system/update-check"),

    // Plugin system endpoints
    listPlugins: () => fetchApi<PluginsListResponse>(baseUrl, "/plugins"),
    getPlugin: (pluginId: string) =>
      fetchApi<PluginDetailResponse>(baseUrl, `/plugins/${pluginId}`),
    getPluginManifest: (pluginId: string) =>
      fetchApi<PluginManifest>(baseUrl, `/plugins/${pluginId}/manifest`),
    updatePluginConfig: (
      pluginId: string,
      config: Record<string, unknown>
    ) =>
      fetchApi<PluginConfigUpdateResponse>(
        baseUrl,
        `/plugins/${pluginId}/config`,
        {
          method: "PUT",
          body: JSON.stringify({ config }),
        }
      ),
    enablePlugin: (pluginId: string) =>
      fetchApi<PluginEnableResponse>(baseUrl, `/plugins/${pluginId}/enable`, {
        method: "POST",
      }),
    disablePlugin: (pluginId: string) =>
      fetchApi<PluginEnableResponse>(baseUrl, `/plugins/${pluginId}/disable`, {
        method: "POST",
      }),
    getPluginData: (pluginId: string) =>
      fetchApi<PluginDataResponse>(baseUrl, `/plugins/${pluginId}/data`),
    getPluginVariables: (pluginId: string) =>
      fetchApi<PluginVariablesResponse>(
        baseUrl,
        `/plugins/${pluginId}/variables`
      ),
    getAllPluginVariables: () =>
      fetchApi<AllPluginVariablesResponse>(baseUrl, "/plugins/variables/all"),
    getPluginErrors: () =>
      fetchApi<PluginErrorsResponse>(baseUrl, "/plugins/errors"),

    // Setup wizard endpoints
    validateSetup: () =>
      fetchApi<ConfigValidationResponse>(baseUrl, "/config/validate"),
    testBoardConnection: (request: BoardTestRequest) =>
      fetchApi<BoardTestResponse>(baseUrl, "/config/board/test", {
        method: "POST",
        body: JSON.stringify(request),
      }),
    sendWelcomeMessage: () =>
      fetchApi<WelcomeMessageResponse>(baseUrl, "/send-welcome-message", {
        method: "POST",
      }),
    enableLocalApi: (request: EnableLocalApiRequest) =>
      fetchApi<EnableLocalApiResponse>(
        baseUrl,
        "/config/board/enable-local-api",
        {
          method: "POST",
          body: JSON.stringify(request),
        }
      ),
    scanForBoards: (timeout?: number) =>
      fetchApi<BoardScanResponse>(baseUrl, "/config/board/scan", {
        method: "POST",
        body: JSON.stringify({ timeout: timeout ?? 4.0 }),
      }),

    // Debug endpoints
    blankBoard: () =>
      fetchApi<ActionResponse>(baseUrl, "/debug/blank", { method: "POST" }),
    fillBoard: (characterCode: number) =>
      fetchApi<ActionResponse>(baseUrl, "/debug/fill", {
        method: "POST",
        body: JSON.stringify({ character_code: characterCode }),
      }),
    showDebugInfo: () =>
      fetchApi<ActionResponse>(baseUrl, "/debug/info", { method: "POST" }),
    testDebugConnection: () =>
      fetchApi<DebugTestResponse>(baseUrl, "/debug/test-connection", {
        method: "POST",
      }),
    clearBoardCache: () =>
      fetchApi<ActionResponse>(baseUrl, "/debug/clear-cache", {
        method: "POST",
      }),
    getBoardCacheStatus: () =>
      fetchApi<DebugCacheStatus>(baseUrl, "/debug/cache-status"),
    getDebugSystemInfo: () =>
      fetchApi<DebugSystemInfo>(baseUrl, "/debug/system-info"),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
