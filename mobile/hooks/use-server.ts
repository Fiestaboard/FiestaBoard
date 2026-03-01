import { useState, useEffect, useCallback } from 'react';
import { getServerUrl, setServerUrl as storeServerUrl, clearServerUrl } from '../lib/storage';
import { getApi, clearApiCache } from '../lib/api';
import type { ApiClient } from '@fiestaboard/shared';

interface ServerState {
  /** The stored server URL, or null if not configured */
  serverUrl: string | null;
  /** Whether we're loading the stored URL */
  loading: boolean;
  /** Whether the server is reachable */
  connected: boolean;
  /** The API client (null if no server configured) */
  api: ApiClient | null;
  /** Set a new server URL */
  setServer: (url: string) => Promise<void>;
  /** Clear the stored server URL */
  disconnect: () => Promise<void>;
  /** Test the connection to a URL */
  testConnection: (url: string) => Promise<boolean>;
}

export function useServer(): ServerState {
  const [serverUrl, setServerUrlState] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);

  // Load stored server URL on mount
  useEffect(() => {
    (async () => {
      const url = await getServerUrl();
      setServerUrlState(url);
      setLoading(false);

      if (url) {
        // Test connection in background
        try {
          const api = getApi(url);
          await api.getStatus();
          setConnected(true);
        } catch {
          setConnected(false);
        }
      }
    })();
  }, []);

  const setServer = useCallback(async (url: string) => {
    const normalized = url.replace(/\/+$/, '');
    await storeServerUrl(normalized);
    clearApiCache();
    setServerUrlState(normalized);
    setConnected(true);
  }, []);

  const disconnect = useCallback(async () => {
    await clearServerUrl();
    clearApiCache();
    setServerUrlState(null);
    setConnected(false);
  }, []);

  const testConnection = useCallback(async (url: string): Promise<boolean> => {
    try {
      const api = getApi(url);
      await api.getStatus();
      return true;
    } catch {
      return false;
    }
  }, []);

  const api = serverUrl ? getApi(serverUrl) : null;

  return {
    serverUrl,
    loading,
    connected,
    api,
    setServer,
    disconnect,
    testConnection,
  };
}
