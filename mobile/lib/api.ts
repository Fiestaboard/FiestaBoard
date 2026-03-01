import { createApiClient, type ApiClient } from '@fiestaboard/shared';

let cachedApi: ApiClient | null = null;
let cachedUrl: string | null = null;

/**
 * Get or create an API client for the given server URL.
 * Caches the client so repeated calls with the same URL reuse it.
 */
export function getApi(serverUrl: string): ApiClient {
  if (serverUrl !== cachedUrl || !cachedApi) {
    const base = serverUrl.replace(/\/+$/, '');
    cachedApi = createApiClient(`${base}/api`);
    cachedUrl = serverUrl;
  }
  return cachedApi;
}

/**
 * Clear the cached API client (e.g. when server URL changes).
 */
export function clearApiCache(): void {
  cachedApi = null;
  cachedUrl = null;
}
