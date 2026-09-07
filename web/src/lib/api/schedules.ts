// Schedules domain: schedule CRUD/validation, default page,
// temporary overrides, and the silence (quiet hours) feature.

import { fetchApi } from "./core";
import type { LineMetadata } from "./shared";

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
  /** Echo of the requested board (issue #1788); null when unscoped. */
  board_id?: string | null;
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

/** Mirrors `TemporaryOverride` in src/settings/service.py. */
export interface TemporaryOverrideStatus {
  active: boolean;
  page_id: string | null;
  // Null when the override is indefinite — it runs until it is cancelled
  // (issue #1787), which is what a manual-mode one-off message needs.
  expires_at: string | null;
  remaining_seconds: number | null;
  revert_mode: "schedule" | "blank" | "page" | null;
  revert_page_id: string | null;
  // Inline one-off content, set instead of page_id
  template?: string[] | null;
  line_metadata?: LineMetadata[] | null;
  device_type?: string | null;
  notes_wide?: number | null;
  notes_tall?: number | null;
}

/**
 * An override carries exactly one of `page_id` or `template`; the server
 * rejects both-or-neither with a 422. `duration_minutes` is optional —
 * omitting it makes the override indefinite.
 */
export type SetTemporaryOverrideRequest = {
  duration_minutes?: number;
  revert_mode?: "schedule" | "blank" | "page";
  revert_page_id?: string;
} & (
  | { page_id: string; template?: never }
  | {
      page_id?: never;
      template: string[];
      line_metadata?: LineMetadata[];
      device_type?: string;
      notes_wide?: number;
      notes_tall?: number;
    }
);

export interface ActiveScheduleResponse {
  page_id: string | null;
  // When page_id is a collection, the member page the collection is currently
  // rendering on the board (issue #1513). Equals page_id for plain pages.
  resolved_page_id?: string | null;
  // Seconds until that collection may switch pages, so the client can re-poll
  // on the collection's own cadence instead of a fixed timer. Null when the
  // active reference can't rotate (plain page, or a single-page collection).
  resolved_next_check_seconds?: number | null;
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

export type SilenceMode = "indicator" | "freeze" | "page";

export interface SilenceScheduleConfig {
  enabled: boolean;
  start_time: string;
  end_time: string;
  mode: SilenceMode;
  page_id: string | null;
  indicator_text: string | null;
  indicator_position: string | null;
  /**
   * Per-board overrides (issue #1788): board_id -> partial override. The keys
   * above are the install-wide default every board without an entry resolves
   * to. Read it through `resolveSilenceConfig` rather than indexing directly.
   */
  by_board?: Record<string, Partial<Omit<SilenceScheduleConfig, "by_board">>>;
}

export interface SilenceScheduleSettings {
  config?: Partial<SilenceScheduleConfig>;
}

export const schedulesApi = {
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
  // Silence mode status (optional boardId reads that board's window).
  // boardId is only honored when it's a non-empty string: this wrapper is
  // handed to TanStack Query as a bare reference, which would otherwise pass
  // the query context as boardId (issue #1244).
  getSilenceStatus: (boardId?: string) =>
    fetchApi<SilenceStatus>(
      typeof boardId === "string" && boardId
        ? `/silence-status?board_id=${encodeURIComponent(boardId)}`
        : "/silence-status",
    ),

  // Silence schedule (system feature, not a plugin).
  // board_id targets one board (issue #1788); omitted writes the install-wide
  // layer. It goes in the BODY, mirroring PUT /settings/active-page.
  updateSilenceSchedule: (data: {
    enabled: boolean;
    start_time: string;
    end_time: string;
    mode?: "indicator" | "freeze" | "page";
    page_id?: string | null;
    indicator_text?: string | null;
    indicator_position?: string | null;
    board_id?: string;
  }) =>
    fetchApi<{ status: string; config: Record<string, unknown> }>("/settings/silence-schedule", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
};
