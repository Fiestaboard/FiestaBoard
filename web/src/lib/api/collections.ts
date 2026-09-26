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

/** Body of `DELETE /collections/{id}` — the id of the collection that was removed. */
export interface CollectionDeleteResponse {
  id: string;
}

// Create / update / delete return bare bodies, not `{status, collection}`
// envelopes — see docs/internal/reference/API_CONVENTIONS.md. Create answers
// 201; `fetchApi` already treats any 2xx as success.
//
// All of these are on /v1 (issue #1930): `/v1/collections*` delegates to the
// same handlers `/collections*` does, so the models and status codes are
// identical and only the path moved.
export const collectionsApi = {
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

  deleteCollection: (collectionId: string) =>
    fetchApi<CollectionDeleteResponse>(`/v1/collections/${collectionId}`, {
      method: "DELETE",
    }),
};
