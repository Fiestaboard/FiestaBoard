"use client";

/**
 * The install's plugin settings (`GET`/`PUT /settings/plugins`): auto-update
 * and the two plugin flags, transition plugins and output plugins, which
 * were `/settings/beta` until settings v6. One query, shared by every
 * control that reads or writes them (the Integrations toolbar, a display's
 * transition, the page editor, the setup wizard).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type PluginSettings } from "@/lib/api";

export const PLUGIN_SETTINGS_QUERY_KEY = ["settings", "plugins"] as const;

export function usePluginSettings() {
  return useQuery({ queryKey: PLUGIN_SETTINGS_QUERY_KEY, queryFn: () => api.getPluginSettings() });
}

/** Save some plugin settings; the shared query is refreshed on success. */
export function useUpdatePluginSettings(options: { onSuccess?: () => void; onError?: (err: Error) => void } = {}) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (updates: Partial<PluginSettings>) => api.updatePluginSettings(updates),
    onSuccess: (saved) => {
      queryClient.setQueryData(PLUGIN_SETTINGS_QUERY_KEY, saved);
      queryClient.invalidateQueries({ queryKey: PLUGIN_SETTINGS_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: ["all-settings"] });
      options.onSuccess?.();
    },
    onError: (err: Error) => options.onError?.(err),
  });
}
