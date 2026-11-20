// Creator IDE hub routes (web slice 2.11): H9a drafts, saved versions and
// restore, H9b per-page send history, H9c duplicate to another display's
// size, and the H4 board-width validate the Problems console reads.
//
// Kept in its own module (not spread into the `api` barrel) so only the
// lazily loaded IDE chunk pulls it in.

import { fetchApi } from "./core";
import type { Page, PageUpdate, PageUpdateResponse } from "./pages";
import type { DeviceType, LineMetadata } from "./shared";
import type { TemplateRenderResponse } from "./templates";

/** A page's content without its identity (hub `PageContent`). */
export interface PageContent {
  name: string;
  type: string;
  device_type: DeviceType;
  template?: string[] | null;
  line_metadata?: LineMetadata[] | null;
  duration_seconds?: number;
  transition_strategy?: string | null;
  notes_wide?: number;
  notes_tall?: number;
  grid_rows?: number | null;
  grid_cols?: number | null;
  canvases?: Page["canvases"];
  [extension: string]: unknown;
}

export type SaveVia = "web" | "phone" | "api" | "mcp" | "hub";

export interface PageDraft {
  page_id: string;
  revision: string;
  saved_at: string;
  based_on?: string | null;
  stale: boolean;
  restored_from?: string | null;
  via?: SaveVia | null;
  content: PageContent;
}

export type RevisionOrigin =
  "created" | "edited" | "published" | "restored" | "resized" | "assistant" | "duplicated" | "imported" | "baseline";

export interface PageRevisionSummary {
  id: string;
  saved_at: string;
  origin: RevisionOrigin;
  via?: SaveVia | null;
  restored_from?: string | null;
  name: string;
  rows: number;
  cols: number;
  /** This version is what the published page holds now. */
  current: boolean;
}

export interface PageRevisionDetail extends PageRevisionSummary {
  content: PageContent;
}

export interface PageRevisionListResponse {
  page_id: string;
  revisions: PageRevisionSummary[];
  total: number;
}

export type PageSendOutcome = "sent" | "failed" | "paused" | "silenced" | "held";

export interface PageSendEntry {
  at: string;
  outcome: PageSendOutcome;
  via: "auto" | "show_now";
  board_id?: string | null;
  board_name?: string | null;
  error?: string | null;
  count?: number;
  last_at?: string | null;
}

export interface PageSendHistoryResponse {
  page_id: string;
  sends: PageSendEntry[];
  total: number;
}

export interface PageDuplicateRequest {
  board_id?: string;
  name?: string;
}

export interface PageDuplicateReport {
  rows: number;
  cols: number;
  from_rows: number;
  from_cols: number;
  lines_too_long: { line: number; max_length: number }[];
  rows_dropped: number[];
  composite_rows_dropped: number[];
  canvases_scaled: number;
  drawing?: { source?: string } | null;
}

export interface PageDuplicateResponse {
  page: Page;
  report: PageDuplicateReport;
}

export type BoardValidationCode =
  | "mismatched_braces"
  | "line_too_long"
  | "unknown_filter"
  | "unknown_source"
  | "unknown_field"
  | "formula"
  | "beyond_board";

export interface BoardValidationError {
  /** 1-based. */
  line: number;
  column: number;
  message: string;
  code: BoardValidationCode;
  max_length?: number | null;
}

export interface BoardValidationResponse {
  valid: boolean;
  errors: BoardValidationError[];
  rows: number;
  cols: number;
}

/** The template and geometry an IDE check runs against. */
export interface IdeTemplateTarget {
  template: string[];
  line_metadata?: LineMetadata[] | null;
  device_type?: DeviceType;
  notes_wide?: number;
  notes_tall?: number;
  grid_rows?: number | null;
  grid_cols?: number | null;
  board_id?: string;
}

const pagePath = (pageId: string) => `/pages/${encodeURIComponent(pageId)}`;

export const pageHistoryApi = {
  getDraft: (pageId: string) => fetchApi<PageDraft>(`${pagePath(pageId)}/draft`),
  /** Every page that has a draft (`GET /pages/drafts`), so a page without one is never asked for it. */
  listDrafts: () => fetchApi<{ drafts: { page_id: string; saved_at: string; stale: boolean }[] }>("/pages/drafts"),
  saveDraft: (pageId: string, body: PageUpdate) =>
    fetchApi<PageDraft>(`${pagePath(pageId)}/draft`, { method: "PUT", body: JSON.stringify(body) }),
  discardDraft: (pageId: string, expectedRevision?: string) =>
    fetchApi<{ page_id: string; discarded: true }>(
      `${pagePath(pageId)}/draft${expectedRevision ? `?expected_revision=${encodeURIComponent(expectedRevision)}` : ""}`,
      { method: "DELETE" },
    ),
  publishDraft: (pageId: string, body: { expected_revision?: string; expected_draft_revision?: string } = {}) =>
    fetchApi<PageUpdateResponse>(`${pagePath(pageId)}/draft/publish`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listRevisions: (pageId: string) => fetchApi<PageRevisionListResponse>(`${pagePath(pageId)}/revisions`),
  getRevision: (pageId: string, revisionId: string) =>
    fetchApi<PageRevisionDetail>(`${pagePath(pageId)}/revisions/${encodeURIComponent(revisionId)}`),
  /** Restores into the draft, never the live page. A 409 means a draft exists: ask before `replaceDraft`. */
  restoreRevision: (pageId: string, revisionId: string, replaceDraft = false) =>
    fetchApi<PageDraft>(`${pagePath(pageId)}/revisions/${encodeURIComponent(revisionId)}/restore`, {
      method: "POST",
      body: JSON.stringify({ replace_draft: replaceDraft }),
    }),
  listSends: (pageId: string) => fetchApi<PageSendHistoryResponse>(`${pagePath(pageId)}/sends`),
  duplicatePage: (pageId: string, body: PageDuplicateRequest) =>
    fetchApi<PageDuplicateResponse>(`${pagePath(pageId)}/duplicate`, { method: "POST", body: JSON.stringify(body) }),
  /** H4: validate at the width the board renders (its grid and charset when `board_id` is set). */
  validateAtBoard: (target: IdeTemplateTarget) =>
    fetchApi<BoardValidationResponse>("/templates/validate", { method: "POST", body: JSON.stringify(target) }),
  /** Render cached data for a thumbnail or the Warnings tab (charset substitutions at the board). */
  renderAtBoard: (target: IdeTemplateTarget & { canvases?: Page["canvases"] }) =>
    fetchApi<TemplateRenderResponse>("/templates/render", {
      method: "POST",
      body: JSON.stringify({ ...target, preview: { data: "cached" } }),
    }),
};
