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

export const collectionsApi = {
  // Collection endpoints
  getCollections: () => fetchApi<CollectionsResponse>("/collections"),

  createCollection: (data: CollectionCreate) =>
    fetchApi<{ status: string; collection: Collection }>("/collections", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getCollection: (collectionId: string) => fetchApi<Collection>(`/collections/${collectionId}`),

  updateCollection: (collectionId: string, data: CollectionUpdate) =>
    fetchApi<{ status: string; collection: Collection }>(`/collections/${collectionId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  deleteCollection: (collectionId: string) =>
    fetchApi<{ status: string; message: string }>(`/collections/${collectionId}`, {
      method: "DELETE",
    }),
};
