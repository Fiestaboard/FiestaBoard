// API client for FiestaBoard service.
// All API calls go through nginx at /api/* (same origin, unified container).
// URLs are built via apiUrl() so they pick up the runtime base path when
// the app is served from a subpath (HA Ingress) — see lib/base-path.ts.
//
// This file is a barrel over the per-domain modules in ./api/ (issue #1763):
// every interface/type and the `api` object keep the import path they had
// when this was one ~2,800-line file — `import { api, type Page } from
// "@/lib/api"` works unchanged. Shared fetch/auth plumbing (fetchApi,
// ApiError, the 401/409 login redirect) lives in ./api/core.ts; new
// endpoints go in the matching domain module, or a new one composed here.

import { aiApi } from "./api/ai";
import { authApi } from "./api/auth";
import { boardsApi } from "./api/boards";
import { collectionsApi } from "./api/collections";
import { miscApi } from "./api/misc";
import { pagesApi } from "./api/pages";
import { pluginRegistryApi } from "./api/plugin-registry";
import { pluginsApi } from "./api/plugins";
import { schedulesApi } from "./api/schedules";
import { settingsApi } from "./api/settings";
import { setupApi } from "./api/setup";
import { systemApi } from "./api/system";
import { templatesApi } from "./api/templates";
import { transitionsApi } from "./api/transitions";

export * from "./api/ai";
export * from "./api/auth";
export * from "./api/boards";
export * from "./api/collections";
export * from "./api/core";
export * from "./api/misc";
export * from "./api/pages";
export * from "./api/plugin-registry";
export * from "./api/plugins";
export * from "./api/schedules";
export * from "./api/settings";
export * from "./api/setup";
export * from "./api/shared";
export * from "./api/system";
export * from "./api/templates";
export * from "./api/transitions";

// The single typed `api` object, composed from the domain modules. Domains
// never overlap keys, so spread order carries no meaning.
export const api = {
  ...systemApi,
  ...boardsApi,
  ...setupApi,
  ...pagesApi,
  ...templatesApi,
  ...schedulesApi,
  ...collectionsApi,
  ...settingsApi,
  ...transitionsApi,
  ...pluginsApi,
  ...pluginRegistryApi,
  ...aiApi,
  ...authApi,
  ...miscApi,
};
