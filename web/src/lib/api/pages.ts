// Pages domain: page CRUD, previews, sharing, staff picks, and the
// active-page setting.

import { fetchApi } from "./core";
import type { DeviceType, LineMetadata, PageType, RowConfig } from "./shared";

export interface PageDeleteResponse {
  /** The id of the page that was deleted. */
  id: string;
  message: string;
  default_page_created: boolean;
  /** Set (non-null) only when `default_page_created` is true. */
  new_page_id?: string | null;
  active_page_updated: boolean;
  /** Set (non-null) only when `active_page_updated` is true. */
  new_active_page_id?: string | null;
}

// Active page settings
export interface ActivePageResponse {
  page_id: string | null;
  // When page_id is a collection, the member page the collection is currently
  // rendering on the board (issue #1513). Equals page_id for plain pages.
  resolved_page_id?: string | null;
  // Seconds until that collection may switch pages, so the client can re-poll
  // on the collection's own cadence instead of a fixed timer. Null when the
  // active reference can't rotate (plain page, or a single-page collection).
  resolved_next_check_seconds?: number | null;
  board_id?: string | null;
}

export interface SetActivePageResponse {
  page_id: string | null;
  sent_to_board: boolean;
  paused: boolean;
  board_id: string | null;
  // Render/send failure reason when the page was persisted but never reached
  // the board (issue #1791). Null when the send succeeded or was skipped
  // benignly (paused board, UI-only output, unchanged content).
  error: string | null;
  // Page<->board size-compatibility warnings. Always present, empty when
  // there are none.
  warnings: string[];
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
  /** Set when this page is a plugin's demo page (singleton per plugin). */
  demo_plugin_id?: string | null;
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
  /** Set when this page is a plugin's demo page (singleton per plugin). */
  demo_plugin_id?: string | null;
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
  page: Page;
  /** Always present; empty unless the update changed the page's size. */
  incompatible_references: IncompatibleReference[];
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

/**
 * One entry of a batch preview. The batch endpoint tags both outcomes with
 * `available` (the single-page endpoint does not), which makes this a proper
 * discriminated union — without the `available: true` arm, narrowing a
 * successful entry was impossible.
 */
export type PagePreviewBatchEntry = (PagePreviewResponse & { available: true }) | { error: string; available: false };

export interface PagePreviewBatchResponse {
  previews: Record<string, PagePreviewBatchEntry>;
  total: number;
  successful: number;
}

export interface CurrentDisplayResponse {
  page_id: string;
  page_name: string;
  page_type: PageType;
  device_type: DeviceType;
  template: string[];
  line_metadata: LineMetadata[] | null;
}

export const pagesApi = {
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
  // Pages CRUD lives on /v1 (issue #1930). `/v1/pages*` delegates to the very
  // same handlers `/pages*` does — same models, same 404 wording — so this is
  // a path change with no response-shape change.
  getPages: () => fetchApi<PagesResponse>("/v1/pages"),
  getCurrentDisplay: () => fetchApi<CurrentDisplayResponse>("/pages/current-display"),
  getPage: (pageId: string) => fetchApi<Page>(`/v1/pages/${pageId}`),
  /** 201 with the created page itself — no envelope. */
  createPage: (page: PageCreate) =>
    fetchApi<Page>("/v1/pages", {
      method: "POST",
      body: JSON.stringify(page),
    }),
  updatePage: (pageId: string, page: PageUpdate) =>
    fetchApi<PageUpdateResponse>(`/v1/pages/${pageId}`, {
      method: "PUT",
      body: JSON.stringify(page),
    }),
  deletePage: (pageId: string) => fetchApi<PageDeleteResponse>(`/v1/pages/${pageId}`, { method: "DELETE" }),
  previewPage: (pageId: string) => fetchApi<PagePreviewResponse>(`/pages/${pageId}/preview`, { method: "POST" }),
  previewPagesBatch: (pageIds: string[]) =>
    fetchApi<PagePreviewBatchResponse>("/pages/preview/batch", {
      method: "POST",
      body: JSON.stringify({ page_ids: pageIds }),
    }),
  getPageShareString: (pageId: string) => fetchApi<{ share_string: string }>(`/pages/${pageId}/share`),
  /** 201 with the created page itself — no envelope, same as createPage. */
  importPage: (shareString: string) =>
    fetchApi<Page>("/pages/import", {
      method: "POST",
      body: JSON.stringify({ share_string: shareString }),
    }),
  getStaffPicks: () => fetchApi<StaffPick[]>("/staff-picks"),
  getStaffPickShareString: (pickId: string) => fetchApi<{ share_string: string }>(`/staff-picks/${pickId}/share`),
};
