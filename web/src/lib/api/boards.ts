// Boards domain: board instances + settings, FiestaPanel, board
// connection config, and the setup wizard's board endpoints.

import { fetchApi } from "./core";
import type { GeneralConfig } from "./settings";
import type { Code62Glyph, DeviceType } from "./shared";

export interface BoardStatus {
  configured: boolean;
  paused: boolean;
  active_page_id: string | null;
  /**
   * Why this board has no client, when it has none (issue #1749). A board
   * skipped at startup because of a bad config is surfaced here; the rest of
   * the fleet keeps running.
   */
  error?: string | null;
}

export interface BoardCurrentMessageResponse {
  // characters/message are null for a secondary board that has no cached
  // content yet (board-state polling is primary-only; see issue #1247).
  characters: number[][] | null;
  message: string | null;
  rows: number;
  cols: number;
  expected_characters: number[][] | null;
  cached_at: string | null;
  api_mode: "local" | "cloud";
  board_id?: string | null;
}

// ---- FiestaPanel (mirrors src/panels/models.py) ----

export interface PanelAutoDim {
  enabled: boolean;
  start: string; // "HH:MM" 24h
  end: string;
}

export type PanelBackdrop = "wall" | "dark" | "none";

export interface Panel {
  id: string;
  /** Small sequential number behind the TV-typable /p/{n} viewer URL. */
  short_code: number;
  name: string;
  board_id: string;
  screen_diagonal_inches: number;
  /** Screen aspect ratio (width:height); 16:9 unless the owner said
   * otherwise. Optional for payloads cached before the field existed. */
  screen_aspect_w?: number;
  screen_aspect_h?: number;
  calibration_scale: number;
  /** Mechanical flip animation on the viewer; off = frames snap into place. */
  animations_enabled: boolean;
  /** Exactly one panel serves the reserved /p/display URL (HDMI kiosk). */
  is_display: boolean;
  backdrop: PanelBackdrop;
  auto_dim: PanelAutoDim;
  created_at: string;
  updated_at: string;
  // Attached by the API from the panel's virtual board (null/true when the
  // board was deleted out from under the panel). rows/cols are the board's
  // auto-fit grid, for display in the app.
  device_type?: DeviceType | null;
  board_missing?: boolean;
  rows?: number | null;
  cols?: number | null;
}

export interface PanelCreateRequest {
  name: string;
  screen_diagonal_inches: number;
  screen_aspect_w?: number;
  screen_aspect_h?: number;
}

export interface PanelUpdateRequest {
  name?: string;
  screen_diagonal_inches?: number;
  screen_aspect_w?: number;
  screen_aspect_h?: number;
  calibration_scale?: number;
  animations_enabled?: boolean;
  is_display?: boolean;
  backdrop?: PanelBackdrop;
  auto_dim?: PanelAutoDim;
}

/**
 * A schedule/active-page reference to a page that no longer fits the panel's
 * re-fit board (returned warn-only by PATCH /panels/{id} on a size change).
 */
export interface PanelIncompatibleReference {
  page_id: string;
  page_name: string;
  surface: "schedule" | "active_page";
  schedule_id: string | null;
}

/**
 * PATCH /panels/{id} — the updated panel, plus the warn-only references a
 * screen-size re-fit invalidated. `incompatible_references` is null when the
 * screen size did not change (it used to be an absent key).
 */
export interface PanelUpdateResult extends Panel {
  incompatible_references: PanelIncompatibleReference[] | null;
}

// Public viewer config served by GET /panel/{id} (no auth).
export interface PanelPublicConfig extends Panel {
  board_color: "black" | "white" | null;
  code62_glyph: "degree" | "heart" | null;
}

/** FiestaPi HDMI kiosk state (Settings → FiestaPanel; pi profile only). */
export interface HdmiKioskStatus {
  supported: boolean;
  status: "unsupported" | "unknown" | "in_progress" | "enabled" | "disabled" | "failed";
  // Always present; null when the platform cannot report one (no sidecar,
  // not a FiestaPi), so "off" and "unknown" stay distinguishable.
  enabled: boolean | null;
  action?: string;
  error?: string;
}

// Public frame served by GET /panel/{id}/frame (no auth).
export interface PanelFrame {
  characters: number[][] | null;
  message: string | null;
  rows: number;
  cols: number;
  updated_at: string | null;
}

// Configuration types
export interface BoardConfig {
  api_mode: "local" | "cloud";
  local_api_key: string;
  cloud_key: string;
  /** Note-array cloud token. Masked as "***" on read, like the other two. */
  note_array_token: string;
  host: string;
  transition_strategy: string | null;
  transition_interval_ms: number | null;
  transition_step_size: number | null;
}

// Backward compatibility alias
export type FiestaboardConfig = BoardConfig;

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
  /**
   * Which glyph this board's character-code-62 flap physically carries
   * (issue #1657). Flagship only — Note hardware has only ever had the heart.
   * Optional because boards saved before the setting existed have no value;
   * absent means "degree", the glyph every Flagship had before Vestaboard
   * swapped it, so an existing install renders exactly as it did.
   *
   * Display-only: both glyphs are code 62 on the wire.
   */
  code62_glyph?: Code62Glyph;
  enabled: boolean;
  // Per-board pause flag (issue #970). When true FiestaBoard does not
  // push anything to this board from any code path until it is resumed.
  paused?: boolean;
  /** Per-board schedule mode (issue #1242). Emitted on every GET /settings/board. */
  schedule_enabled?: boolean;
  api_mode: "local" | "cloud" | "virtual";
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

/**
 * `GET | PATCH /v1/boards/{board}` — mirrors `BoardDetail` in src/v1/models.py.
 *
 * A deliberate projection of a board plus what it is doing right now. It is
 * NOT a replacement for `BoardInstance` (`GET /settings/board`): v1 drops the
 * connection credentials, per-tile wiring, board colour and code-62 glyph on
 * purpose, so anything configuring a board still reads the settings shape.
 */
export interface BoardDetail {
  id: string;
  name: string;
  device_type: DeviceType;
  rows: number;
  cols: number;
  is_primary: boolean;
  paused: boolean;
  schedule_enabled: boolean;
  characters: number[][] | null;
  text: string | null;
  read_at: string | null;
  active_page_id: string | null;
  scheduled_page_id: string | null;
  resolved_page_id: string | null;
  source: "manual" | "schedule" | "none";
  default_page_id: string | null;
  override_expires_at: string | null;
}

/**
 * The `{board}` path segment of a v1 board route.
 *
 * v1 accepts the literal `primary` in place of an id, which is how an
 * id-less internal call ("no board_id" = the default board) is expressed:
 * `SettingsService.get_primary_board_id()` is the same resolution both sides
 * use. Non-empty string only — these wrappers get handed to TanStack Query
 * and event handlers as bare references (issue #1244).
 */
export function boardPathSegment(boardId?: string | null): string {
  return typeof boardId === "string" && boardId ? encodeURIComponent(boardId) : "primary";
}

export interface BoardSettings {
  board_type: "black" | "white" | null;
  boards: BoardInstance[];
  devices: DeviceType[]; // Computed from boards for backward compat
}

/**
 * Response from POST /settings/board/{id}/detect-size. Mirrors the Python
 * `classify_dimensions()` return shape. The note-grid fields are always
 * present and null for a flagship or a single Note. `matched_preset` is a
 * human-readable preset LABEL (not an id) or null — do not key UI off it;
 * match presets by (notes_wide, notes_tall) instead.
 */
export interface DetectBoardSizeResponse {
  device_type: DeviceType;
  rows: number;
  cols: number;
  notes_wide: number | null;
  notes_tall: number | null;
  matched_preset: string | null;
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
  board_id: string;
  results: { row: number; col: number; success: boolean }[];
}

export interface FullConfig {
  board: BoardConfig;
  general: GeneralConfig;
  plugins: Record<string, Record<string, unknown>>;
  /**
   * On-disk schema version of `config.json`. Bookkeeping for the ordered
   * migration runner in `config_manager.py`; `/config/full` echoes the raw
   * config, so it surfaces here. The UI never reads or writes it.
   */
  schema_version?: number;
  /**
   * Pre-migration key still present in `config.json` on older installs;
   * `/config/full` echoes the raw config, so it can surface here.
   * `ConfigManager.get_board()` falls back to it (see config_manager.py).
   * This redeclared `board` — shadowing the required field above rather than
   * describing the legacy one.
   */
  board_legacy?: BoardConfig;
}

export interface ConfigValidationResponse {
  valid: boolean;
  is_first_run: boolean;
  errors: string[];
  missing_fields: string[];
}

export const boardsApi = {
  // Non-empty string only — see the getActivePage note (issue #1244).
  getBoardCurrentMessage: (boardId?: string) =>
    fetchApi<BoardCurrentMessageResponse>(
      typeof boardId === "string" && boardId
        ? `/board/current-message?board_id=${encodeURIComponent(boardId)}`
        : "/board/current-message",
    ),
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
  // Board settings
  getBoardSettings: () => fetchApi<BoardSettings>("/settings/board"),
  updateBoardSettings: (updates: {
    board_type?: "black" | "white" | null;
    devices?: DeviceType[];
    boards?: BoardInstance[];
  }) =>
    fetchApi<BoardSettings>("/settings/board", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    }),
  addBoard: (board: Partial<BoardInstance> & { device_type: DeviceType }) =>
    fetchApi<BoardSettings>("/settings/board/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(board),
    }),
  removeBoard: (boardId: string) =>
    fetchApi<BoardSettings>(`/settings/board/${boardId}`, {
      method: "DELETE",
    }),
  // Pausing moved to `PATCH /v1/boards/{board}` (issue #1930), which calls the
  // same `SettingsService.set_paused`. The response is the v1 BoardDetail
  // rather than `{ board_id, paused, board_settings }` — no caller read those
  // fields; the one consumer invalidates its queries instead.
  setBoardPaused: (boardId: string, paused: boolean) =>
    fetchApi<BoardDetail>(`/v1/boards/${boardPathSegment(boardId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paused }),
    }),
  // ---- FiestaPanel ----
  listPanels: () => fetchApi<{ panels: Panel[]; total: number }>("/panels"),
  // 201 with the bare panel (Phase 2 slice 8; was 200 + { status, panel }).
  createPanel: (data: PanelCreateRequest) =>
    fetchApi<Panel>("/panels", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  // The bare panel, plus incompatible_references — always present, null unless
  // a screen-size change re-fit the board's grid.
  updatePanel: (panelId: string, data: PanelUpdateRequest) =>
    fetchApi<PanelUpdateResult>(`/panels/${encodeURIComponent(panelId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  deletePanel: (panelId: string) =>
    fetchApi<{ id: string }>(`/panels/${encodeURIComponent(panelId)}`, {
      method: "DELETE",
    }),
  getHdmiKiosk: () => fetchApi<HdmiKioskStatus>("/settings/hdmi-kiosk"),
  setHdmiKiosk: (enabled: boolean) =>
    fetchApi<{ status: string; action: string | null }>("/settings/hdmi-kiosk", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }),
  // Public viewer endpoints — reachable with no session (TV browsers).
  getPanel: (panelId: string) => fetchApi<PanelPublicConfig>(`/panel/${encodeURIComponent(panelId)}`),
  getPanelFrame: (panelId: string) => fetchApi<PanelFrame>(`/panel/${encodeURIComponent(panelId)}/frame`),
  detectBoardSize: (boardId: string) =>
    fetchApi<DetectBoardSizeResponse>(`/settings/board/${boardId}/detect-size`, {
      method: "POST",
    }),
  identifyBoardTile: (boardId: string, request: BoardIdentifyRequest) =>
    fetchApi<BoardIdentifyResponse>(`/settings/board/${boardId}/identify`, {
      method: "POST",
      body: JSON.stringify(request),
    }),
};
