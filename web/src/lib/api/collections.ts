// Collections domain: rotating groups of pages and their selection
// modes.

import { fetchApi } from "./core";

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
  revision?: string;
  edit_protocol?: "collection-revision-v1";
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
  expected_revision?: string;
  name?: string;
  page_ids?: string[];
  selection_mode?: CollectionSelectionMode;
  time?: TimeModeConfig;
  variable?: VariableModeConfig | null;
  random?: RandomModeConfig | null;
}

/** Read-only evaluation of a saved Collection using the hub's cached values. */
export interface CollectionEvaluation {
  collection_id: string;
  selection_mode: CollectionSelectionMode;
  at: string;
  page_id: string | null;
  rules: Array<{
    index: number;
    expression: string;
    page_id: string;
    value: string;
    error: string | null;
    message: string | null;
    matched: boolean;
  }> | null;
  matched_rule: number | null;
  /** The dry run's merged windows from `at` on (each `{from, until, page_id}`). */
  timeline?: { from: string; until: string; page_id: string | null }[];
}

// No hub protocol advertises an editable no-repeat flag. Random selection
// always uses shuffle bags (src/collections/models.py); never send a fake flag.
export const collectionCapabilities = { editableNoRepeat: false } as const;

export interface CollectionsResponse {
  collections: Collection[];
  total: number;
}

/** Body of `DELETE /collections/{id}` — the id of the collection that was removed. */
export interface CollectionDeleteResponse {
  id: string;
}

/** H8: read-only evaluation; no collection cursor is advanced or stored. */
export interface CollectionDryRunRequest {
  at?: string;
  data?: "live" | "cached";
  values?: Record<string, unknown>;
  missing?: string[];
  window_seconds?: number;
  step_seconds?: number;
}
export interface CollectionDryRunResponse {
  collection_id: string;
  selection_mode: string;
  at: string;
  page_id: string | null;
  rules:
    | {
        index: number;
        expression: string;
        page_id: string;
        value: string;
        error: string | null;
        message: string | null;
        matched: boolean;
      }[]
    | null;
  matched_rule: number | null;
  timeline: { from: string; until: string; page_id: string | null }[];
  truncated: boolean;
  truncated_reason?: "segments" | "budget" | null;
  shown_on: string[];
  sources: Record<string, unknown>;
}

// Create / update / delete return bare bodies, not `{status, collection}`
// envelopes — see docs/internal/reference/API_CONVENTIONS.md. Create answers
// 201; `fetchApi` already treats any 2xx as success.
//
// All of these are on /v1 (issue #1930): `/v1/collections*` delegates to the
// same handlers `/collections*` does, so the models and status codes are
// identical and only the path moved.
export const collectionsApi = {
  dryRunCollection: (collectionId: string, request: CollectionDryRunRequest) =>
    fetchApi<CollectionDryRunResponse>(`/collections/${encodeURIComponent(collectionId)}/dry-run`, {
      method: "POST",
      body: JSON.stringify({ data: "cached", ...request }),
    }),

  /** `windowSeconds` adds the timeline after `at` (what shows until when, and what's next). */
  evaluateCollection: (collectionId: string, at?: string, windowSeconds?: number) =>
    fetchApi<CollectionEvaluation>(`/collections/${encodeURIComponent(collectionId)}/dry-run`, {
      method: "POST",
      body: JSON.stringify({ ...(at && { at }), ...(windowSeconds && { window_seconds: windowSeconds }) }),
    }),

  // Collection endpoints
  getCollections: () => fetchApi<CollectionsResponse>("/v1/collections"),

  createCollection: (data: CollectionCreate) =>
    fetchApi<Collection>("/v1/collections", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateCollection: (collectionId: string, data: CollectionUpdate) =>
    fetchApi<Collection>(`/v1/collections/${collectionId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteCollection: (collectionId: string, expectedRevision?: string) =>
    fetchApi<CollectionDeleteResponse>(
      `/v1/collections/${collectionId}${expectedRevision ? `?expected_revision=${encodeURIComponent(expectedRevision)}` : ""}`,
      {
        method: "DELETE",
      },
    ),
};
